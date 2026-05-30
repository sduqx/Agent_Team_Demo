#!/usr/bin/env python3
"""
Backend Agent - 后端开发Agent，使用LLM生成代码
权限: 可以读写项目文件、创建API
"""

import sys
import time
import json
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


def create_backend_with_llm(task_description: str) -> str:
    """使用LLM生成Flask后端代码"""
    
    if client is None:
        print("⚠️ LLM不可用")
        return create_default_backend()
    
    prompt = f"""
你是一个Python后端开发工程师。根据以下需求生成完整的Flask REST API应用：

需求: {task_description}

请生成以下Python代码（包含在```python```代码块中）：
1. app.py - 完整的Flask应用，包含：
   - 所有必需的API端点
   - 错误处理
   - 数据验证
   - CORS支持
2. requirements.txt - 依赖列表

代码应该是可以直接运行的、生产就绪的。
"""
    
    try:
        response = client.messages.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4000
        )
        
        result_text = extract_text_from_response(response)
        return parse_and_save_code(result_text)
    except Exception as e:
        print(f"❌ LLM生成失败: {e}")
        return create_default_backend()


def parse_and_save_code(response_text: str) -> str:
    """从LLM响应中提取代码并保存"""
    import re
    
    # 提取app.py
    app_match = re.search(r'```python\n(.*?)\n```', response_text, re.DOTALL)
    if app_match:
        app_code = app_match.group(1)
        (PROJECT_DIR / "app.py").write_text(app_code, encoding='utf-8')
    else:
        app_code = create_default_app_code()
        (PROJECT_DIR / "app.py").write_text(app_code, encoding='utf-8')
    
    # 提取requirements.txt
    req_match = re.search(r'requirements\.txt[\s\S]*?```(.*?)```', response_text, re.DOTALL)
    if req_match:
        reqs = req_match.group(1).strip()
    else:
        reqs = "Flask==2.3.3\nFlask-CORS==4.0.0\n"
    (PROJECT_DIR / "requirements.txt").write_text(reqs, encoding='utf-8')
    
    return "Flask REST API已生成"


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
    return jsonify({"status": "healthy"})

@app.route('/api/data', methods=['GET'])
def get_data():
    return jsonify(data)

@app.route('/api/data', methods=['POST'])
def create_data():
    item = request.json
    data[len(data)] = item
    return jsonify(item), 201

if __name__ == '__main__':
    print("🚀 Flask服务启动在 http://localhost:5000")
    app.run(debug=True, port=5000, use_reloader=False)
'''


def create_default_backend() -> str:
    """创建默认后端"""
    (PROJECT_DIR / "app.py").write_text(create_default_app_code(), encoding='utf-8')
    (PROJECT_DIR / "requirements.txt").write_text("Flask==2.3.3\nFlask-CORS==4.0.0\n", encoding='utf-8')
    return "默认Flask应用已创建"


def main():
    print("="*70)
    print("🔧 Backend Agent 已启动 (LLM驱动)")
    print("="*70)
    print("\n等待任务分配...\n")
    
    wait_time = 0
    max_wait = 300
    
    while wait_time < max_wait:
        messages = read_messages("backend")
        
        if messages:
            for msg in messages:
                print(f"\n📋 收到任务来自 {msg['from']}:")
                print(f"   {msg['content'][:100]}...\n")
                
                print("🤖 Backend Agent 使用LLM生成代码...")
                result = create_backend_with_llm(msg['content'])
                print(f"✓ {result}\n")
                
                # 保存API规范供其他Agent参考
                backend_spec = {
                    "api_type": "Flask REST API",
                    "endpoints": ["/api/health", "/api/data"],
                    "base_url": "http://localhost:5000"
                }
                context.update_backend_spec(backend_spec)
                context.update_task("backend", "completed", result)
                
                send_message("backend", "lead", f"后端完成: {result}")
                send_message("backend", "frontend", f"后端API已准备好。基础URL: http://localhost:5000, 可用端点: /api/health, /api/data")
                print("✓ 已通知其他Agent\n")
            
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
