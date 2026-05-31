#!/usr/bin/env python3
"""
Frontend Agent v2.0 - 前端开发Agent
核心改进:
  1. 等待后端 API spec 就绪后才开始工作
  2. 根据后端实际端点生成前端代码，确保 API 一致性
  3. 不再猜测 API 格式，直接使用 APISpecStore 中的数据
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


def create_frontend_with_llm(task_description: str, api_spec: dict) -> str:
    """使用 LLM 生成前端代码，基于真实 API spec"""
    if client is None:
        return create_default_frontend(api_spec)

    # 格式化 API 信息给 LLM
    api_info = json.dumps(api_spec, indent=2, ensure_ascii=False)

    prompt = f"""
你是一个前端开发工程师。根据以下需求生成完整的HTML前端应用：

需求: {task_description}

**后端 API 规范（必须严格遵循）:**
{api_info}

请生成一个单页面HTML应用（包含在```html```代码块中），需要：
1. 美观现代的UI设计（使用渐变、阴影、圆角等）
2. 与后端API的精确集成 —— 端点路径、方法、参数格式必须与上述 API 规范完全一致
3. 使用 Fetch API 调用后端，API 基础URL为: {api_spec.get('base_url', 'http://localhost:5000')}
4. 错误处理和加载状态
5. 响应式设计
6. 所有CSS和JavaScript都内嵌在HTML中

**重要**: 前端中的所有 API 调用必须严格匹配上面给出的后端 API 规范中的端点和数据格式！
"""

    try:
        response = client.messages.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4000
        )
        result_text = extract_text_from_response(response)
        html_code = extract_code_block(result_text, "html")
        if not html_code:
            html_code = create_default_html_code(api_spec)
        (PROJECT_DIR / "index.html").write_text(html_code, encoding='utf-8')
        return "HTML前端已生成（已对齐后端API规范）"
    except Exception as e:
        print(f"❌ LLM生成失败: {e}")
        return create_default_frontend(api_spec)


def extract_code_block(text: str, lang: str) -> str:
    pattern = rf'```{lang}\n(.*?)\n```'
    match = re.search(pattern, text, re.DOTALL)
    return match.group(1) if match else None


def create_default_html_code(api_spec: dict) -> str:
    """根据 API spec 动态生成默认前端"""
    base_url = api_spec.get("base_url", "http://localhost:5000")

    # 从 API spec 中智能提取端点
    endpoints = api_spec.get("endpoints", [])
    data_ep = next((ep for ep in endpoints if ep.get("method") == "GET"), None)
    post_ep = next((ep for ep in endpoints if ep.get("method") == "POST"), None)

    data_path = data_ep["path"] if data_ep else "/api/data"
    post_path = post_ep["path"] if post_ep else "/api/data"

    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>应用</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: 'Segoe UI', Arial, sans-serif; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; display: flex; justify-content: center; align-items: center; padding: 20px; }}
        .container {{ max-width: 800px; width: 100%; background: white; padding: 30px; border-radius: 16px; box-shadow: 0 20px 60px rgba(0,0,0,0.3); }}
        h1 {{ color: #333; margin-bottom: 10px; text-align: center; }}
        .subtitle {{ text-align: center; color: #888; margin-bottom: 30px; font-size: 14px; }}
        .input-group {{ display: flex; gap: 10px; margin-bottom: 20px; }}
        input {{ flex: 1; padding: 14px; border: 2px solid #e0e0e0; border-radius: 10px; font-size: 14px; transition: border-color 0.3s; }}
        input:focus {{ outline: none; border-color: #667eea; }}
        button {{ padding: 14px 28px; background: linear-gradient(135deg, #667eea, #764ba2); color: white; border: none; border-radius: 10px; cursor: pointer; font-size: 14px; font-weight: bold; transition: transform 0.2s, opacity 0.2s; }}
        button:hover {{ transform: translateY(-1px); opacity: 0.9; }}
        button:disabled {{ opacity: 0.5; cursor: not-allowed; }}
        .status {{ padding: 8px 12px; border-radius: 6px; margin-bottom: 15px; font-size: 13px; display: none; }}
        .status.success {{ background: #d4edda; color: #155724; display: block; }}
        .status.error {{ background: #f8d7da; color: #721c24; display: block; }}
        .status.loading {{ background: #fff3cd; color: #856404; display: block; }}
        .item {{ padding: 16px; background: #f8f9fa; border-radius: 10px; margin-bottom: 10px; border-left: 4px solid #667eea; transition: transform 0.2s; }}
        .item:hover {{ transform: translateX(5px); }}
        .item-id {{ font-size: 12px; color: #999; margin-bottom: 5px; }}
        .item-content {{ color: #333; font-family: monospace; font-size: 13px; }}
        .empty {{ text-align: center; color: #bbb; padding: 40px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📋 数据管理</h1>
        <p class="subtitle">API: {base_url}</p>
        <div id="status" class="status"></div>
        <div class="input-group">
            <input type="text" id="input" placeholder="输入内容..." onkeypress="if(event.key==='Enter')submit()">
            <button onclick="submit()">提交</button>
        </div>
        <div id="list"><div class="empty">加载中...</div></div>
    </div>
    <script>
        const API_BASE = '{base_url}';
        const DATA_URL = '{data_path}';
        const POST_URL = '{post_path}';

        function showStatus(msg, type) {{
            const el = document.getElementById('status');
            el.textContent = msg;
            el.className = 'status ' + type;
            if(type !== 'loading') setTimeout(() => el.className = 'status', 3000);
        }}

        async function loadData() {{
            showStatus('加载数据中...', 'loading');
            try {{
                const resp = await fetch(API_BASE + DATA_URL);
                if (!resp.ok) throw new Error(`HTTP ${{resp.status}}`);
                const data = await resp.json();
                const list = document.getElementById('list');
                const items = Object.entries(data);
                if(items.length === 0) {{
                    list.innerHTML = '<div class="empty">暂无数据，请添加</div>';
                }} else {{
                    list.innerHTML = items.map(([id, item]) => `
                        <div class="item">
                            <div class="item-id"># ${{id}}</div>
                            <div class="item-content">${{JSON.stringify(item)}}</div>
                        </div>
                    `).join('');
                }}
                showStatus('✓ 数据加载成功', 'success');
            }} catch(e) {{
                document.getElementById('list').innerHTML = '<div class="empty">加载失败: ' + e.message + '</div>';
                showStatus('✗ 加载失败: ' + e.message, 'error');
            }}
        }}

        async function submit() {{
            const input = document.getElementById('input');
            const value = input.value.trim();
            if(!value) return;
            showStatus('提交中...', 'loading');
            try {{
                const resp = await fetch(API_BASE + POST_URL, {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ content: value }})
                }});
                if(!resp.ok) throw new Error(`HTTP ${{resp.status}}`);
                input.value = '';
                showStatus('✓ 提交成功', 'success');
                loadData();
            }} catch(e) {{
                showStatus('✗ 提交失败: ' + e.message, 'error');
            }}
        }}

        loadData();
    </script>
</body>
</html>'''


def create_default_frontend(api_spec: dict) -> str:
    html_code = create_default_html_code(api_spec)
    (PROJECT_DIR / "index.html").write_text(html_code, encoding='utf-8')
    return "默认HTML前端已创建"


def main():
    print("=" * 70)
    print("🎨 Frontend Agent v2.0 - 等待 API spec 后生成")
    print("=" * 70)
    print("\n等待 Lead Agent 分配任务（后端 API 就绪后才会收到）...\n")

    wait_time = 0
    max_wait = 600

    while wait_time < max_wait:
        messages = BUS.read_inbox("frontend")

        for msg in messages:
            msg_type = msg.get("type", "")
            sender = msg.get("from", "")

            # 收到后端 API 规范
            if msg_type == "api_spec" and sender == "backend":
                print(f"\n📡 收到后端 API 规范:")
                print(f"   {msg['content']}\n")

            # 收到 Lead 分配的任务
            if msg_type == "task" and sender == "lead":
                task_id = msg.get("extra", {}).get("task_id", "?")
                task_content = msg.get("content", "")

                print(f"\n📋 收到任务 #{task_id} 来自 Lead:")
                print(f"   {task_content[:100]}...\n")

                # ===== 关键改进: 从共享存储读取 API spec =====
                print("🔍 正在获取后端 API 规范...")
                api_spec = API_SPEC.wait_for_spec(timeout=60)

                if api_spec:
                    print(f"✓ API 规范已获取: {len(api_spec.get('endpoints', []))} 个端点")
                    for ep in api_spec.get("endpoints", []):
                        print(f"   {ep.get('method', '?'):6s} {ep.get('path', '?')}")
                    print()
                else:
                    print("⚠️ 等待 API 规范超时，使用默认值\n")
                    api_spec = {
                        "base_url": "http://localhost:5000",
                        "endpoints": [
                            {"method": "GET", "path": "/api/health"},
                            {"method": "GET", "path": "/api/data"},
                            {"method": "POST", "path": "/api/data"},
                        ]
                    }

                print("🤖 Frontend Agent 使用 LLM 生成代码（匹配后端 API）...")
                result = create_frontend_with_llm(task_content, api_spec)
                print(f"✓ {result}\n")

                # 通知 Lead
                BUS.send(
                    sender="frontend",
                    to="lead",
                    content=f"前端完成: {result}",
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
        print("\n\n👋 Frontend Agent 停止")
        sys.exit(0)
