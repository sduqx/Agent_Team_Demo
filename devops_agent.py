#!/usr/bin/env python3
"""
DevOps Agent v2.0 - 部署和文档Agent
核心改进:
  1. 等待所有其他 Agent 完成后才执行
  2. 汇总前后端、测试产出物生成完整部署配置
  3. 包含服务端口、运行方式等实际信息
"""

import sys
import time
import json
import re
from pathlib import Path
from shared_context import (
    TASK_MGR, BUS, API_SPEC,
    send_message, read_messages, extract_text_from_response
)

try:
    from anthropic import Anthropic
    from dotenv import load_dotenv
    import os

    load_dotenv(override=True)
    client = Anthropic(base_url=os.getenv("ANTHROPIC_BASE_URL"))
    MODEL = os.environ["MODEL_ID"]
except:
    client = None
    MODEL = None

PROJECT_DIR = Path.cwd() / ".project"
PROJECT_DIR.mkdir(exist_ok=True)


def create_deployment_with_llm(task_description: str, api_spec: dict) -> str:
    """使用 LLM 生成部署配置，包含项目实际信息"""
    if client is None:
        return create_default_deployment()

    api_info = json.dumps(api_spec, indent=2, ensure_ascii=False)

    # 收集已生成的文件列表
    generated_files = []
    for f in sorted(PROJECT_DIR.rglob("*")):
        if f.is_file() and not f.name.startswith("."):
            generated_files.append(f"  - {f.relative_to(PROJECT_DIR)}")
    files_list = "\n".join(generated_files) if generated_files else "  (暂无)"

    prompt = f"""
你是一个DevOps工程师。根据以下信息生成完整的部署配置和文档：

项目需求: {task_description}

**后端 API 规范:**
{api_info}

**已生成的项目文件:**
{files_list}

请生成以下内容，每个文件用对应的markdown代码块包裹：

1. README.md（```markdown```代码块）：
   - 项目概述
   - 技术栈说明
   - 快速开始指南（安装、启动后端、打开前端）
   - API文档（基于上面的API规范）
   - 运行测试的说明
   - Docker部署说明

2. Dockerfile（```dockerfile```代码块）：
   - 基于python:3.10-slim
   - 安装依赖、复制代码
   - 暴露5000端口
   - 启动Flask应用

3. docker-compose.yml（```yaml```代码块）：
   - 包含web服务配置
   - 端口映射 5000:5000

4. .dockerignore（```text```代码块）：
   - 忽略不必要的文件

注意: 文档中描述的API端点必须与提供的API规范完全一致！
"""

    try:
        response = client.messages.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4000
        )
        result_text = extract_text_from_response(response)
        return parse_and_save_deployment(result_text)
    except Exception as e:
        print(f"❌ LLM生成失败: {e}")
        return create_default_deployment()


def parse_and_save_deployment(response_text: str) -> str:
    """从 LLM 响应中提取并保存部署配置"""
    saved = []

    # README
    readme = extract_code_block(response_text, "markdown")
    if readme:
        (PROJECT_DIR / "README.md").write_text(readme, encoding='utf-8')
        saved.append("README.md")

    # Dockerfile
    dockerfile = extract_code_block(response_text, "dockerfile")
    if dockerfile:
        (PROJECT_DIR / "Dockerfile").write_text(dockerfile, encoding='utf-8')
        saved.append("Dockerfile")

    # docker-compose
    compose = extract_code_block(response_text, "yaml")
    if compose and ("services" in compose or "version" in compose):
        (PROJECT_DIR / "docker-compose.yml").write_text(compose, encoding='utf-8')
        saved.append("docker-compose.yml")

    # .dockerignore
    ignore = extract_code_block(response_text, "text") or extract_code_block(response_text, "")
    if ignore and any(x in ignore for x in [".git", "node_", ".env"]):
        (PROJECT_DIR / ".dockerignore").write_text(ignore, encoding='utf-8')
        saved.append(".dockerignore")

    if not saved:
        return create_default_deployment()

    return f"部署配置已生成: {', '.join(saved)}"


def extract_code_block(text: str, lang: str) -> str:
    if lang:
        pattern = rf'```{lang}\n(.*?)\n```'
    else:
        pattern = r'```\n(.*?)\n```'
    match = re.search(pattern, text, re.DOTALL)
    return match.group(1) if match else None


def create_default_readme() -> str:
    return '''# 项目应用

使用 Flask + HTML 构建的完整 Web 应用，由 AI Agent 团队协作生成。

## 技术栈

- **后端**: Python Flask + Flask-CORS
- **前端**: 原生 HTML/CSS/JS (单页面应用)
- **测试**: unittest / pytest

## 快速开始

### 1. 安装依赖
```bash
pip install -r requirements.txt
```

### 2. 启动后端
```bash
python app.py
```
服务将在 http://localhost:5000 启动

### 3. 打开前端
在浏览器中打开 `index.html` 文件即可使用应用。

### 4. 运行测试
```bash
cd tests
python test_api.py
```

## API 文档

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/health | 健康检查 |
| GET | /api/data | 获取所有数据 |
| POST | /api/data | 创建新数据项 |

## Docker 部署

```bash
docker-compose up
```

服务将在 http://localhost:5000 可用。
'''


def create_default_dockerfile() -> str:
    return '''FROM python:3.10-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 5000
CMD ["python", "app.py"]
'''


def create_default_docker_compose() -> str:
    return '''version: '3.8'
services:
  web:
    build: .
    ports:
      - "5000:5000"
    environment:
      - FLASK_ENV=production
    volumes:
      - .:/app
'''


def create_default_deployment() -> str:
    (PROJECT_DIR / "README.md").write_text(create_default_readme(), encoding='utf-8')
    (PROJECT_DIR / "Dockerfile").write_text(create_default_dockerfile(), encoding='utf-8')
    (PROJECT_DIR / "docker-compose.yml").write_text(create_default_docker_compose(), encoding='utf-8')
    return "默认部署配置已创建"


def main():
    print("=" * 70)
    print("📦 DevOps Agent v2.0 - 等待所有 Agent 完成后执行")
    print("=" * 70)
    print("\n等待 Lead Agent 分配任务...\n")

    wait_time = 0
    max_wait = 600

    while wait_time < max_wait:
        messages = BUS.read_inbox("devops")

        for msg in messages:
            msg_type = msg.get("type", "")
            sender = msg.get("from", "")

            if msg_type == "task" and sender == "lead":
                task_id = msg.get("extra", {}).get("task_id", "?")
                task_content = msg.get("content", "")

                print(f"\n📋 收到任务 #{task_id} 来自 Lead:")
                print(f"   {task_content[:100]}...\n")

                # 获取 API spec 用于文档
                print("🔍 获取项目信息...")
                api_spec = API_SPEC.get_spec()
                if api_spec:
                    print(f"✓ API 规范已获取: {len(api_spec.get('endpoints', []))} 个端点")
                else:
                    print("⚠️ 无 API spec，使用默认信息")
                    api_spec = {"base_url": "http://localhost:5000", "endpoints": []}

                print("\n🤖 DevOps Agent 使用 LLM 生成部署配置...")
                result = create_deployment_with_llm(task_content, api_spec)
                print(f"✓ {result}\n")

                BUS.send(
                    sender="devops",
                    to="lead",
                    content=f"DevOps完成: {result}",
                    msg_type="status",
                    extra={"task_id": task_id}
                )
                print("✓ 已通知 Lead Agent\n")

                wait_time = max_wait
                break

        wait_time += 1
        time.sleep(1)

    if wait_time >= max_wait:
        print(f"⚠️ 等待超时({max_wait}秒)，未收到任务")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 DevOps Agent 停止")
        sys.exit(0)
