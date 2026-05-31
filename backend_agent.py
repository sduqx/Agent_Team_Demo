#!/usr/bin/env python3
"""
Backend Agent v2.0 - 后端开发Agent
核心改进:
  1. 从 MessageBus 接任务，完成后发布 API spec 给前端/测试
  2. 提取并结构化 API 端点和数据格式
  3. 前端和测试 Agent 可以直接读取 API spec 来保证一致性
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


def generate_api_spec_from_code(app_code: str) -> dict:
    """
    从生成的 Flask 代码中提取 API 规范。
    使用正则提取路由定义和请求/响应格式。
    """
    endpoints = []

    # 提取所有 @app.route 装饰器
    route_pattern = re.findall(
        r"@app\.route\(['\"](.*?)['\"],?\s*methods=\[(.*?)\]\)",
        app_code
    )
    for path, methods in route_pattern:
        method_list = [m.strip().strip("'\"") for m in methods.split(",")]
        for method in method_list:
            if method in ("GET", "POST", "PUT", "DELETE", "PATCH"):
                endpoints.append({
                    "method": method,
                    "path": path,
                    "description": f"{method} {path}"
                })

    # 如果正则提取失败，给一个基本的 spec
    if not endpoints:
        # 尝试更宽松的匹配
        simple_routes = re.findall(
            r"@app\.route\(['\"](.*?)['\"]",
            app_code
        )
        for path in simple_routes:
            endpoints.append({"method": "GET", "path": path, "description": f"GET {path}"})

    return {
        "api_type": "Flask REST API",
        "base_url": "http://localhost:5000",
        "endpoints": endpoints,
        "cors_enabled": "CORS" in app_code,
        "data_format": "JSON",
    }


def create_backend_with_llm(task_description: str) -> tuple:
    """使用 LLM 生成 Flask 后端代码，返回 (结果描述, API spec)"""
    if client is None:
        print("⚠️ LLM 不可用，使用默认代码")
        app_code = create_default_app_code()
        save_code(app_code)
        spec = generate_api_spec_from_code(app_code)
        return "默认Flask应用已创建", spec

    prompt = f"""
你是一个Python后端开发工程师。根据以下需求生成完整的Flask REST API应用：

需求: {task_description}

请生成以下Python代码（包含在```python```代码块中）：
1. app.py - 完整的Flask应用，包含：
   - 所有必需的API端点
   - 错误处理
   - 数据验证
   - CORS支持
   - 每个端点的注释说明其功能和请求/响应格式

代码应该是可以直接运行的、生产就绪的。
"""

    try:
        response = client.messages.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4000
        )
        result_text = extract_text_from_response(response)
        app_code = extract_code_block(result_text, "python")
        if not app_code:
            app_code = create_default_app_code()

        save_code(app_code)
        spec = generate_api_spec_from_code(app_code)
        return "Flask REST API 已生成", spec

    except Exception as e:
        print(f"❌ LLM生成失败: {e}")
        app_code = create_default_app_code()
        save_code(app_code)
        spec = generate_api_spec_from_code(app_code)
        return f"使用默认代码（LLM失败: {e}）", spec


def extract_code_block(text: str, lang: str) -> str:
    """从 LLM 响应中提取代码块"""
    pattern = rf'```{lang}\n(.*?)\n```'
    match = re.search(pattern, text, re.DOTALL)
    return match.group(1) if match else None


def save_code(app_code: str):
    """保存生成的代码"""
    (PROJECT_DIR / "app.py").write_text(app_code, encoding='utf-8')
    (PROJECT_DIR / "requirements.txt").write_text(
        "Flask==2.3.3\nFlask-CORS==4.0.0\n", encoding='utf-8'
    )


def create_default_app_code() -> str:
    """默认Flask应用代码"""
    return '''#!/usr/bin/env python3
from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

data = {}

@app.route('/api/health', methods=['GET'])
def health():
    """健康检查 - GET /api/health → {"status": "healthy"}"""
    return jsonify({"status": "healthy"})

@app.route('/api/data', methods=['GET'])
def get_data():
    """获取所有数据 - GET /api/data → {id: item, ...}"""
    return jsonify(data)

@app.route('/api/data', methods=['POST'])
def create_data():
    """创建数据 - POST /api/data  Body: JSON → 201 Created"""
    item = request.json
    data[len(data)] = item
    return jsonify(item), 201

if __name__ == '__main__':
    print("🚀 Flask服务启动在 http://localhost:5000")
    app.run(debug=True, port=5000, use_reloader=False)
'''


def format_api_spec_message(spec: dict) -> str:
    """将 API spec 格式化为人类可读消息"""
    lines = ["📡 后端 API 规范已发布:", f"   基础URL: {spec.get('base_url', 'N/A')}"]
    for ep in spec.get("endpoints", []):
        lines.append(f"   {ep.get('method', '?'):6s} {ep.get('path', '?')}")
    return "\n".join(lines)


def main():
    print("=" * 70)
    print("🔧 Backend Agent v2.0 - 等待任务 (API规范发布) ")
    print("=" * 70)
    print("\n等待 Lead Agent 分配任务...\n")

    wait_time = 0
    max_wait = 600  # 10分钟超时

    while wait_time < max_wait:
        # 从增强 MessageBus 读取消息
        messages = BUS.read_inbox("backend")

        for msg in messages:
            msg_type = msg.get("type", "")
            sender = msg.get("from", "")

            if msg_type == "task" and sender == "lead":
                task_id = msg.get("extra", {}).get("task_id", "?")
                task_content = msg.get("content", "")

                print(f"\n📋 收到任务 #{task_id} 来自 Lead:")
                print(f"   {task_content[:100]}...\n")
                print("🤖 Backend Agent 使用 LLM 生成代码...")

                result, api_spec = create_backend_with_llm(task_content)
                print(f"✓ {result}\n")

                # ===== 关键改进: 发布 API spec 给前端和测试 =====
                API_SPEC.publish(api_spec)
                print("📡 API 规范已发布到共享存储\n")

                # 显示提取到的端点
                print(format_api_spec_message(api_spec))
                print()

                # 通知前端 Agent —— API 已就绪
                BUS.send(
                    sender="backend",
                    to="frontend",
                    content=format_api_spec_message(api_spec),
                    msg_type="api_spec",
                    extra={"api_spec": api_spec}
                )
                print("✓ 已通知 Frontend Agent: API 规范已就绪\n")

                # 通知测试 Agent —— API 已就绪
                BUS.send(
                    sender="backend",
                    to="test",
                    content=format_api_spec_message(api_spec),
                    msg_type="api_spec",
                    extra={"api_spec": api_spec}
                )
                print("✓ 已通知 Test Agent: API 规范已就绪\n")

                # 汇报给 Lead
                endpoints_str = ", ".join(
                    f"{ep['method']} {ep['path']}"
                    for ep in api_spec.get("endpoints", [])
                )
                BUS.send(
                    sender="backend",
                    to="lead",
                    content=f"后端完成。API端点: {endpoints_str}",
                    msg_type="status",
                    extra={"task_id": task_id, "api_spec": api_spec}
                )
                print("✓ 已通知 Lead Agent: 后端任务完成\n")

                # 完成，退出循环
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
        print("\n\n👋 Backend Agent 停止")
        sys.exit(0)
