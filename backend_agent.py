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
    从生成的 Flask 代码中提取 API 规范（含请求/响应 schema）。
    增强版：不仅提取路由，还从 docstring 和 request.json 中提取字段信息。
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
            if method not in ("GET", "POST", "PUT", "DELETE", "PATCH"):
                continue

            ep = {
                "method": method,
                "path": path,
                "description": f"{method} {path}",
            }

            # 尝试从函数注释/docstring 中提取 schema 信息
            # 查找该路由对应的函数
            func_match = re.search(
                rf"@app\.route\(['\"]{re.escape(path)}['\"].*?\)\s*\ndef\s+(\w+)\(\):.*?\"\"\"(.*?)\"\"\"",
                app_code, re.DOTALL
            )
            if func_match:
                func_name, docstring = func_match.groups()
                ep["description"] = docstring.strip().split("\n")[0] if docstring.strip() else ep["description"]

                # 从 docstring 中提取请求/响应格式信息
                # 格式: "→ {status: 200, body: {key: type, ...}}" 或 "Body: JSON → 201"
                body_match = re.search(r'Body:\s*(\{.*?\})', docstring)
                resp_match = re.search(r'→\s*(\{.*?\})', docstring)

                if method in ("POST", "PUT", "PATCH"):
                    request_body = {"type": "object", "properties": {}}
                    if body_match:
                        try:
                            body_schema = json.loads(body_match.group(1))
                            request_body["properties"] = body_schema
                            # 推断必填字段
                            request_body["required"] = list(body_schema.keys())
                        except json.JSONDecodeError:
                            pass

                    # 也尝试从函数体 request.json 中提取
                    req_json_pattern = re.findall(
                        r"request\.json(?:\.get)?\(?['\"](\w+)['\"]",
                        app_code
                    )
                    if req_json_pattern and not request_body["properties"]:
                        for key in req_json_pattern:
                            request_body["properties"][key] = {"type": "string"}

                    ep["request_body"] = request_body

                if resp_match:
                    try:
                        ep["response"] = json.loads(resp_match.group(1))
                    except json.JSONDecodeError:
                        ep["response"] = {"status": 200}
                else:
                    ep["response"] = {"status": 200 if method == "GET" else 201}

            # 如果没匹配到函数，给默认 schema
            if method in ("POST", "PUT", "PATCH") and "request_body" not in ep:
                ep["request_body"] = {
                    "type": "object",
                    "properties": {"content": {"type": "string", "description": "请求内容"}},
                    "required": ["content"]
                }
            if "response" not in ep:
                ep["response"] = {"status": 200 if method == "GET" else 201,
                                  "body": {"type": "object"}}

            endpoints.append(ep)

    # 如果正则提取失败，返回默认 spec
    if not endpoints:
        return _default_api_spec()

    return {
        "api_type": "Flask REST API",
        "base_url": "http://localhost:5000",
        "endpoints": endpoints,
        "cors_enabled": "CORS" in app_code,
        "data_format": "JSON",
    }


def create_backend_with_llm(task_description: str) -> tuple:
    """使用 LLM 生成 Flask 后端代码 + 完整 API 契约，返回 (结果描述, API spec)"""
    if client is None:
        print("⚠️ LLM 客户端不可用（检查 .env 中的 ANTHROPIC_BASE_URL 和 MODEL_ID）")
        print("   将使用默认代码 + 默认 API 规范\n")
        app_code = create_default_app_code()
        save_code(app_code)
        spec = _default_api_spec()
        return "默认Flask应用已创建", spec

    prompt = f"""
你是一个Python后端开发工程师。根据以下需求，请严格按两步走完成任务：

需求: {task_description}

============================================================
第一步：API 规范设计（```json 代码块）
============================================================
设计完整的 REST API 规范，JSON 格式如下：
{{
  "api_type": "Flask REST API",
  "base_url": "http://localhost:5000",
  "endpoints": [
    {{
      "method": "GET",
      "path": "/api/xxx",
      "description": "端点功能描述",
      "request_query": {{"properties": {{"page": {{"type": "integer", "required": false}}}}}},  // 仅GET需要
      "response": {{
        "status": 200,
        "body": {{
          "type": "object",
          "properties": {{
            "data": {{"type": "array", "items": {{"type": "object"}}}},
            "total": {{"type": "integer"}}
          }}
        }}
      }}
    }},
    {{
      "method": "POST",
      "path": "/api/xxx",
      "description": "创建资源",
      "request_body": {{
        "required": ["title"],
        "properties": {{
          "title": {{"type": "string", "description": "标题"}},
          "content": {{"type": "string", "description": "内容"}}
        }}
      }},
      "response": {{
        "status": 201,
        "body": {{
          "type": "object",
          "properties": {{
            "id": {{"type": "string"}},
            "title": {{"type": "string"}},
            "content": {{"type": "string"}}
          }}
        }}
      }}
    }}
  ]
}}

**关键要求**：
- 每个端点的 request_body.properties 和 response.body.properties 必须包含完整的字段名、类型
- POST/PUT/PATCH 必须有 request_body.required 标明必填字段
- GET 响应如果是嵌套结构（如 {{"data": [...], "total": N}}），必须完整描述

============================================================
第二步：Flask 代码实现（```python 代码块）
============================================================
根据第一步的 API 规范，生成完整的 Flask 应用代码：
- 所有 API 端点
- 错误处理和数据验证
- CORS 支持
- 每个函数有 docstring 说明请求/响应格式
- 代码可直接运行
"""

    try:
        response = client.messages.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=6000
        )
        result_text = extract_text_from_response(response)

        # 1. 先尝试提取 LLM 输出的 API 规范 JSON
        spec_json = extract_code_block(result_text, "json")
        spec = None
        if spec_json:
            try:
                spec = json.loads(spec_json)
                if "endpoints" not in spec:
                    spec = None
            except json.JSONDecodeError:
                print("⚠️ API 规范 JSON 解析失败，将从代码中提取")

        # 2. 提取 Python 代码
        app_code = extract_code_block(result_text, "python")
        if not app_code:
            app_code = create_default_app_code()

        # 3. 如果 LLM 没输出规范 JSON，从代码中提取作为后备
        if spec is None:
            spec = generate_api_spec_from_code(app_code)

        save_code(app_code)
        return "Flask REST API 已生成（含完整契约）", spec

    except Exception as e:
        print(f"❌ LLM生成失败: {e}")
        app_code = create_default_app_code()
        save_code(app_code)
        spec = _default_api_spec()
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


def _default_api_spec() -> dict:
    """默认 API 规范（含完整 schema），与 create_default_app_code 对应"""
    return {
        "api_type": "Flask REST API",
        "base_url": "http://localhost:5000",
        "data_format": "JSON",
        "cors_enabled": True,
        "endpoints": [
            {
                "method": "GET",
                "path": "/api/health",
                "description": "健康检查",
                "response": {
                    "status": 200,
                    "body": {
                        "type": "object",
                        "properties": {
                            "status": {"type": "string", "description": "服务状态"}
                        }
                    }
                }
            },
            {
                "method": "GET",
                "path": "/api/data",
                "description": "获取所有数据",
                "response": {
                    "status": 200,
                    "body": {
                        "type": "object",
                        "description": "键值对，key 为数字 ID，value 为数据对象"
                    }
                }
            },
            {
                "method": "POST",
                "path": "/api/data",
                "description": "创建数据",
                "request_body": {
                    "type": "object",
                    "description": "任意 JSON 对象",
                    "properties": {
                        "content": {"type": "string", "description": "数据内容"}
                    }
                },
                "response": {
                    "status": 201,
                    "body": {
                        "type": "object",
                        "description": "创建的数据对象"
                    }
                }
            }
        ]
    }


def create_default_app_code() -> str:
    """默认Flask应用代码（docstring 含 format 信息供正则提取）"""
    return '''#!/usr/bin/env python3
from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

data = {}

@app.route('/api/health', methods=['GET'])
def health():
    """健康检查 → {"status": 200, "body": {"status": "string"}}"""
    return jsonify({"status": "healthy"})

@app.route('/api/data', methods=['GET'])
def get_data():
    """获取所有数据 → {"status": 200, "body": {"type": "object", "description": "键值对"}}"""
    return jsonify(data)

@app.route('/api/data', methods=['POST'])
def create_data():
    """创建数据 Body: {"content": "string"} → {"status": 201, "body": {"type": "object"}}"""
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
        method = ep.get('method', '?')
        path = ep.get('path', '?')
        # 检查是否有 schema
        has_req = "request_body" in ep
        has_resp = "response" in ep
        schema_info = ""
        if has_req:
            props = ep["request_body"].get("properties", {})
            if props:
                schema_info = f"  [fields: {', '.join(props.keys())}]"
        elif has_resp:
            body = ep.get("response", {}).get("body", {})
            props = body.get("properties", {})
            if props:
                schema_info = f"  [resp-fields: {', '.join(props.keys())}]"
        lines.append(f"   {method:6s} {path}{schema_info}")
    return "\n".join(lines)


def main():
    print("=" * 70)
    print("🔧 Backend Agent v2.1 - 等待任务 (API规范发布)")
    print("=" * 70)

    # 检查 LLM 状态
    if client is None:
        print("⚠️ LLM 客户端不可用，将使用默认代码 + 默认 API 规范")
        print("   如需使用 LLM，请检查 .env 中的 ANTHROPIC_BASE_URL 和 MODEL_ID\n")
    else:
        print(f"✓ LLM 客户端已就绪 (model: {MODEL})\n")

    print("等待 Lead Agent 分配任务...\n")

    wait_time = 0
    max_wait = 600  # 10分钟超时

    while wait_time < max_wait:
        # 从增强 MessageBus 读取消息
        messages = BUS.read_inbox("backend")

        for msg in messages:
            try:
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

                    # ===== 发布 API spec 给前端和测试 =====
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
            except Exception as e:
                print(f"❌ 处理消息时出错: {e}")
                import traceback
                traceback.print_exc()

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
