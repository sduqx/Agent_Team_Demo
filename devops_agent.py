#!/usr/bin/env python3
"""
DevOps Agent - 部署和文档Agent
"""

import sys
import time
from pathlib import Path
from shared_context import SharedContext, send_message, read_messages

context = SharedContext()
PROJECT_DIR = Path.cwd() / ".project"
PROJECT_DIR.mkdir(exist_ok=True)


def create_deployment_files():
    """创建部署文件"""
    
    readme = '''# TODO 应用

一个简单的TODO管理应用，采用Flask后端 + HTML前端。

## 快速开始

### 1. 安装依赖
```bash
pip install -r requirements.txt
```

### 2. 启动后端
```bash
python app.py
```

后端将在 http://localhost:5000 运行

### 3. 打开前端
在浏览器中打开 `index.html` 即可使用应用

## 项目结构
```
.
├── app.py              # Flask后端应用
├── index.html          # 前端HTML界面
├── requirements.txt    # Python依赖
├── config.py          # 配置文件
├── README.md          # 本文件
├── Dockerfile         # Docker配置
├── docker-compose.yml # Docker Compose配置
└── tests/             # 测试目录
    └── test_basic.py  # 基础测试
```

## API 文档

### GET /api/todos
获取所有TODO项

**响应:**
```json
[
  {"id": 1, "title": "任务名称", "completed": false}
]
```

### POST /api/todos
创建新的TODO项

**请求体:**
```json
{"title": "新任务"}
```

### PUT /api/todos/<id>
更新TODO项

**请求体:**
```json
{"completed": true, "title": "更新的标题"}
```

### DELETE /api/todos/<id>
删除TODO项

## 运行测试
```bash
python -m pytest tests/ -v
# 或
python tests/test_basic.py
```

## Docker部署

### 构建镜像
```bash
docker build -t todo-app .
```

### 运行容器
```bash
docker run -p 5000:5000 todo-app
```

### 使用 Docker Compose
```bash
docker-compose up
```

## 技术栈

- **后端**: Flask (Python)
- **前端**: HTML5 + CSS3 + JavaScript
- **数据交互**: RESTful API + Fetch API
- **部署**: Docker
- **测试**: unittest

## 许可证

MIT License
'''
    
    dockerfile = '''FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000

CMD ["python", "app.py"]
'''
    
    docker_compose = '''version: '3.8'

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
    
    (PROJECT_DIR / "README.md").write_text(readme, encoding='utf-8')
    (PROJECT_DIR / "Dockerfile").write_text(dockerfile, encoding='utf-8')
    (PROJECT_DIR / "docker-compose.yml").write_text(docker_compose, encoding='utf-8')
    
    return "部署文件已创建 (README.md, Dockerfile, docker-compose.yml)"


def main():
    print("=" * 70)
    print("📦 DevOps Agent 已启动")
    print("=" * 70)
    print("\n等待任务分配...\n")
    
    wait_time = 0
    max_wait = 120
    
    while wait_time < max_wait:
        messages = read_messages("devops")
        
        if messages:
            for msg in messages:
                print(f"\n📋 收到任务来自 {msg['from']}:")
                print(f"   {msg['content']}\n")
                
                print("📦 正在创建部署配置...")
                result = create_deployment_files()
                print(f"✓ {result}\n")
                
                context.update_task("devops", "completed", result)
                send_message("devops", "lead", f"DevOps完成: {result}")
                print("✓ 已通知Lead Agent\n")
            
            break
        
        wait_time += 1
        time.sleep(1)
    
    if wait_time >= max_wait:
        print(f"⚠️  等待超时({max_wait}秒)，未收到任务")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 DevOps Agent 停止")
        sys.exit(0)
