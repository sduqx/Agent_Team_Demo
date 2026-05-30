#!/usr/bin/env python3
"""
DevOps Agent - 部署和文档Agent，使用LLM生成配置
权限: 可以读写项目文件、创建部署配置
"""

import sys
import time
from pathlib import Path
from shared_context import SharedContext, send_message, read_messages, extract_text_from_response

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

context = SharedContext()
PROJECT_DIR = Path.cwd() / ".project"
PROJECT_DIR.mkdir(exist_ok=True)


def create_deployment_with_llm(task_description: str) -> str:
    """使用LLM生成部署配置"""
    
    if client is None:
        return create_default_deployment()
    
    prompt = f"""
你是一个DevOps工程师。根据以下需求生成完整的部署配置和文档：

需求: {task_description}

请生成：
1. README.md - 完整的项目文档（markdown格式）
   - 项目描述
   - 快速开始指南
   - API文档
   - 部署说明

2. Dockerfile - Docker容器配置

3. docker-compose.yml - Docker Compose配置

4. .dockerignore - Docker忽略文件

返回格式: 在```markdown```、```dockerfile```等代码块中分别返回各个文件内容
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
    """从LLM响应中提取并保存部署配置"""
    import re
    
    # 提取README
    readme_match = re.search(r'```markdown\n(.*?)\n```', response_text, re.DOTALL)
    if readme_match:
        readme = readme_match.group(1)
    else:
        readme = create_default_readme()
    (PROJECT_DIR / "README.md").write_text(readme, encoding='utf-8')
    
    # 提取Dockerfile
    docker_match = re.search(r'```dockerfile\n(.*?)\n```', response_text, re.DOTALL)
    if docker_match:
        dockerfile = docker_match.group(1)
    else:
        dockerfile = create_default_dockerfile()
    (PROJECT_DIR / "Dockerfile").write_text(dockerfile, encoding='utf-8')
    
    # 提取docker-compose
    compose_match = re.search(r'```yaml\n(.*?)\n```', response_text, re.DOTALL)
    if compose_match:
        compose = compose_match.group(1)
    else:
        compose = create_default_docker_compose()
    (PROJECT_DIR / "docker-compose.yml").write_text(compose, encoding='utf-8')
    
    return "部署配置已生成"


def create_default_readme() -> str:
    """默认README"""
    return '''# 项目应用

一个使用Flask + HTML的完整应用。

## 快速开始

### 1. 安装依赖
```bash
pip install -r requirements.txt
```

### 2. 启动后端
```bash
python app.py
```

### 3. 打开前端
在浏览器中打开 `index.html` 即可使用应用。

## API 文档

### GET /api/health
检查服务健康状态

### GET /api/data
获取所有数据

### POST /api/data
创建新数据项

## Docker部署

```bash
docker-compose up
```
'''


def create_default_dockerfile() -> str:
    """默认Dockerfile"""
    return '''FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000

CMD ["python", "app.py"]
'''


def create_default_docker_compose() -> str:
    """默认docker-compose.yml"""
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
    """创建默认部署配置"""
    (PROJECT_DIR / "README.md").write_text(create_default_readme(), encoding='utf-8')
    (PROJECT_DIR / "Dockerfile").write_text(create_default_dockerfile(), encoding='utf-8')
    (PROJECT_DIR / "docker-compose.yml").write_text(create_default_docker_compose(), encoding='utf-8')
    return "默认部署配置已创建"


def main():
    print("="*70)
    print("📦 DevOps Agent 已启动 (LLM驱动)")
    print("="*70)
    print("\n等待任务分配...\n")
    
    wait_time = 0
    max_wait = 300
    
    while wait_time < max_wait:
        messages = read_messages("devops")
        
        if messages:
            for msg in messages:
                print(f"\n📋 收到任务来自 {msg['from']}:")
                print(f"   {msg['content'][:100]}...\n")
                
                print("🤖 DevOps Agent 使用LLM生成配置...")
                result = create_deployment_with_llm(msg['content'])
                print(f"✓ {result}\n")
                
                context.update_task("devops", "completed", result)
                send_message("devops", "lead", f"DevOps完成: {result}")
                print("✓ 已通知Lead Agent\n")
            
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
