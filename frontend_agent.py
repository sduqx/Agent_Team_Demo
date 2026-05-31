#!/usr/bin/env python3
"""
Frontend Agent v2.1 - 前端开发Agent
核心改进:
  1. 等待后端 API spec 就绪后才开始工作
  2. 根据后端实际端点生成前端代码，确保 API 一致性
  3. 不再猜测 API 格式，直接使用 APISpecStore 中的数据
  4. 默认模板根据 API spec 的 request_body/response schema 动态生成
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
2. 与后端API的精确集成 —— 端点路径、方法、请求体字段名、响应数据结构必须与上述 API 规范完全一致
3. 使用 Fetch API 调用后端，API 基础URL为: {api_spec.get('base_url', 'http://localhost:5000')}
4. 错误处理和加载状态
5. 响应式设计
6. 所有CSS和JavaScript都内嵌在HTML中

**重要**: 前端中的所有 API 调用必须严格匹配上面给出的后端 API 规范中的端点和数据格式！
特别注意：POST 请求体的字段名必须与 API 规范的 request_body.properties 完全一致！
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


def _build_input_fields(api_spec: dict) -> tuple:
    """根据 API spec 生成输入框 HTML 和 POST body 构建代码。
    返回: (input_fields_html, post_body_code, clear_inputs_code)
    """
    endpoints = api_spec.get("endpoints", [])
    post_ep = next((ep for ep in endpoints if ep.get("method") == "POST"), {})

    req_body = post_ep.get("request_body", {})
    req_properties = req_body.get("properties", {})
    req_required = req_body.get("required", [])

    if not req_properties:
        # 兼容回退
        return (
            '            <input type="text" id="input" placeholder="输入内容..." onkeypress="if(event.key==\'Enter\')submit()">',
            'JSON.stringify({ content: value })',
            '            input.value = "";'
        )

    # 动态生成输入框
    parts = []
    field_names = list(req_properties.keys())
    for fname in field_names:
        finfo = req_properties[fname]
        ft = finfo.get("type", "text")
        desc = finfo.get("description", fname)
        req_mark = " *" if fname in req_required else ""
        html_input_type = "number" if ft in ("integer", "number") else "text"
        parts.append(
            f'            <input type="{html_input_type}" id="field_{fname}" '
            f'placeholder="{desc}{req_mark}" '
            f'onkeypress="if(event.key==\'Enter\')submit()">'
        )
    input_fields = "\n".join(parts)

    # POST body 构建
    field_assignments = ",\n".join(
        [f'                "{f}": document.getElementById("field_{f}").value' for f in field_names]
    )
    post_body = f"JSON.stringify({{\n{field_assignments}\n            }})"

    # 清空输入框
    clear_lines = "\n".join(
        [f'            document.getElementById("field_{f}").value = "";' for f in field_names]
    )

    return input_fields, post_body, clear_lines


def _build_display_logic(api_spec: dict) -> tuple:
    """根据 API spec 生成 GET 响应的显示逻辑。
    返回: (data_accessor_code, render_items_code)
    """
    endpoints = api_spec.get("endpoints", [])
    get_eps = [ep for ep in endpoints
               if ep.get("method") == "GET" and "/api/health" not in ep.get("path", "")]
    data_ep = get_eps[0] if get_eps else {}

    resp_body = data_ep.get("response", {}).get("body", {})
    resp_props = resp_body.get("properties", {})

    if "data" in resp_props and resp_props["data"].get("type") == "array":
        # 模式: {"data": [...], "total": N}
        data_accessor = "data.data || []"
        render_items = """            if(items.length === 0) {
                list.innerHTML = '<div class="empty">暂无数据，请添加</div>';
            } else {
                list.innerHTML = items.map((item, idx) => `
                    <div class="item">
                        <div class="item-id"># ${idx + 1}</div>
                        <div class="item-content">${JSON.stringify(item)}</div>
                    </div>
                `).join('');
            }"""
    else:
        # 默认模式: 扁平对象或数组
        data_accessor = "data"
        render_items = """            const entries = Array.isArray(data) ? data : Object.entries(data);
            if(entries.length === 0) {
                list.innerHTML = '<div class="empty">暂无数据，请添加</div>';
            } else {
                list.innerHTML = entries.map((item, idx) => {
                    const key = Array.isArray(item) ? item[0] : idx;
                    const val = Array.isArray(item) ? item[1] : item;
                    return `
                    <div class="item">
                        <div class="item-id"># ${typeof key === 'object' ? idx : key}</div>
                        <div class="item-content">${JSON.stringify(val)}</div>
                    </div>`;
                }).join('');
            }"""

    return data_accessor, render_items


def create_default_html_code(api_spec: dict) -> str:
    """根据 API spec 动态生成默认前端 —— 字段名、请求体、响应解析全部来自 API 契约"""
    try:
        return _create_default_html_code_impl(api_spec)
    except Exception as e:
        print(f"⚠️ 动态模板生成失败: {e}，使用最简回退模板")
        import traceback
        traceback.print_exc()
        return _create_fallback_html(api_spec)


def _create_fallback_html(api_spec: dict) -> str:
    """最简回退模板，绝对不出错"""
    base_url = api_spec.get("base_url", "http://localhost:5000")
    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>应用</title>
    <style>
        body {{ font-family: sans-serif; max-width: 600px; margin: 40px auto; padding: 20px; }}
        input, button {{ padding: 10px; margin: 5px; }}
    </style>
</head>
<body>
    <h1>📋 数据管理</h1>
    <p>API: {base_url}</p>
    <div id="status"></div>
    <input type="text" id="input" placeholder="输入内容...">
    <button onclick="submit()">提交</button>
    <div id="list"></div>
    <script>
        const BASE = '{base_url}';
        function status(m,t){{ var e=document.getElementById("status");e.textContent=m;e.style.color=t==="error"?"red":"green"; }}
        async function load(){{ try{{ var r=await fetch(BASE+"/api/data");var d=await r.json();var l=document.getElementById("list");l.innerHTML=JSON.stringify(d);status("OK","ok"); }}catch(e){{ status(e.message,"error"); }} }}
        async function submit(){{ var v=document.getElementById("input").value;if(!v)return; try{{ var r=await fetch(BASE+"/api/data",{{method:"POST",headers:{{"Content-Type":"application/json"}},body:JSON.stringify({{content:v}})}});status(r.ok?"OK":"HTTP "+r.status,r.ok?"ok":"error");load(); }}catch(e){{ status(e.message,"error"); }} }}
        load();
    </script>
</body>
</html>'''


def _create_default_html_code_impl(api_spec: dict) -> str:
    base_url = api_spec.get("base_url", "http://localhost:5000")
    endpoints = api_spec.get("endpoints", [])

    # ── 找到主数据端点 ──
    get_eps = [ep for ep in endpoints
               if ep.get("method") == "GET" and "/api/health" not in ep.get("path", "")]
    post_eps = [ep for ep in endpoints if ep.get("method") == "POST"]

    data_ep = get_eps[0] if get_eps else {"path": "/api/data"}
    post_ep = post_eps[0] if post_eps else {"path": "/api/data"}

    data_path = data_ep["path"]
    post_path = post_ep["path"]

    # ── 动态生成输入框和 POST body 代码 ──
    input_fields_html, post_body_code, clear_inputs = _build_input_fields(api_spec)

    # ── 动态生成 GET 响应显示逻辑 ──
    data_accessor, render_items = _build_display_logic(api_spec)

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
        .input-group {{ display: flex; gap: 10px; margin-bottom: 20px; flex-wrap: wrap; }}
        .input-group input {{ flex: 1; min-width: 120px; padding: 14px; border: 2px solid #e0e0e0; border-radius: 10px; font-size: 14px; transition: border-color 0.3s; }}
        .input-group input:focus {{ outline: none; border-color: #667eea; }}
        button {{ padding: 14px 28px; background: linear-gradient(135deg, #667eea, #764ba2); color: white; border: none; border-radius: 10px; cursor: pointer; font-size: 14px; font-weight: bold; transition: transform 0.2s, opacity 0.2s; white-space: nowrap; }}
        button:hover {{ transform: translateY(-1px); opacity: 0.9; }}
        button:disabled {{ opacity: 0.5; cursor: not-allowed; }}
        .status {{ padding: 8px 12px; border-radius: 6px; margin-bottom: 15px; font-size: 13px; display: none; }}
        .status.success {{ background: #d4edda; color: #155724; display: block; }}
        .status.error {{ background: #f8d7da; color: #721c24; display: block; }}
        .status.loading {{ background: #fff3cd; color: #856404; display: block; }}
        .item {{ padding: 16px; background: #f8f9fa; border-radius: 10px; margin-bottom: 10px; border-left: 4px solid #667eea; transition: transform 0.2s; }}
        .item:hover {{ transform: translateX(5px); }}
        .item-id {{ font-size: 12px; color: #999; margin-bottom: 5px; }}
        .item-content {{ color: #333; font-family: monospace; font-size: 13px; word-break: break-all; }}
        .empty {{ text-align: center; color: #bbb; padding: 40px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📋 数据管理</h1>
        <p class="subtitle">API: {base_url}</p>
        <div id="status" class="status"></div>
        <div class="input-group">
{input_fields_html}
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
                const items = {data_accessor};
{render_items}
                showStatus('✓ 数据加载成功', 'success');
            }} catch(e) {{
                document.getElementById('list').innerHTML = '<div class="empty">加载失败: ' + e.message + '</div>';
                showStatus('✗ 加载失败: ' + e.message, 'error');
            }}
        }}

        async function submit() {{
            showStatus('提交中...', 'loading');
            try {{
                const resp = await fetch(API_BASE + POST_URL, {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: {post_body_code}
                }});
                if(!resp.ok) throw new Error(`HTTP ${{resp.status}}`);
{clear_inputs}
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
    print("🎨 Frontend Agent v2.1 - 等待 API spec 后生成")
    print("=" * 70)

    # 检查 LLM 状态
    if client is None:
        print("⚠️ LLM 客户端不可用，将使用动态默认模板\n")
    else:
        print("✓ LLM 客户端已就绪\n")

    print("等待 Lead Agent 分配任务（后端 API 就绪后才会收到）...\n")

    wait_time = 0
    max_wait = 600

    while wait_time < max_wait:
        messages = BUS.read_inbox("frontend")

        for msg in messages:
            try:
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

                    # ===== 从共享存储读取 API spec =====
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
        print("\n\n👋 Frontend Agent 停止")
        sys.exit(0)
