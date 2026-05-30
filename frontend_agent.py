#!/usr/bin/env python3
"""
Frontend Agent - 前端开发Agent，使用LLM生成UI代码
权限: 可以读写项目文件、创建HTML/CSS/JS
"""

import sys
import time
import json
from pathlib import Path
from shared_context import SharedContext, send_message, read_messages

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


def create_frontend_with_llm(task_description: str) -> str:
    """使用LLM生成前端代码"""
    
    if client is None:
        return create_default_frontend()
    
    # 获取后端规范
    backend_spec = context.project_data.get("backend_spec", {})
    backend_info = f"\n后端信息: {json.dumps(backend_spec, ensure_ascii=False)}"
    
    prompt = f"""
你是一个前端开发工程师。根据以下需求生成完整的HTML前端应用：

需求: {task_description}
{backend_info}

请生成一个单页面HTML应用（包含在```html```代码块中），包括：
1. 美观的UI设计
2. 与后端API的集成（使用Fetch API）
3. 错误处理和加载状态
4. 响应式设计
5. 所有CSS和JavaScript都内嵌在HTML中

代码应该是可以直接在浏览器中打开运行的。
"""
    
    try:
        response = client.messages.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4000
        )
        
        result_text = response.content[0].text
        return parse_and_save_html(result_text)
    except Exception as e:
        print(f"❌ LLM生成失败: {e}")
        return create_default_frontend()


def parse_and_save_html(response_text: str) -> str:
    """从LLM响应中提取HTML并保存"""
    import re
    
    html_match = re.search(r'```html\n(.*?)\n```', response_text, re.DOTALL)
    if html_match:
        html_code = html_match.group(1)
    else:
        html_code = create_default_html_code()
    
    (PROJECT_DIR / "index.html").write_text(html_code, encoding='utf-8')
    return "HTML前端已生成"


def create_default_html_code() -> str:
    """默认HTML前端代码"""
    return '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>应用</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: Arial; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; display: flex; justify-content: center; align-items: center; padding: 20px; }
        .container { max-width: 800px; width: 100%; background: white; padding: 30px; border-radius: 12px; box-shadow: 0 10px 40px rgba(0,0,0,0.2); }
        h1 { color: #333; margin-bottom: 30px; text-align: center; }
        .input-group { display: flex; gap: 10px; margin-bottom: 30px; }
        input { flex: 1; padding: 12px; border: 2px solid #ddd; border-radius: 8px; }
        button { padding: 12px 30px; background: #667eea; color: white; border: none; border-radius: 8px; cursor: pointer; }
        button:hover { background: #764ba2; }
        .item { padding: 15px; border: 1px solid #eee; margin-bottom: 10px; border-radius: 8px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>应用</h1>
        <div class="input-group">
            <input type="text" id="input" placeholder="输入内容...">
            <button onclick="submit()">提交</button>
        </div>
        <div id="list"></div>
    </div>
    <script>
        const API_URL = 'http://localhost:5000/api/data';
        
        async function loadData() {
            try {
                const response = await fetch(API_URL);
                const data = await response.json();
                document.getElementById('list').innerHTML = Object.values(data).map(item => 
                    `<div class="item">${JSON.stringify(item)}</div>`
                ).join('');
            } catch(e) {
                console.error('Error:', e);
            }
        }
        
        async function submit() {
            const input = document.getElementById('input');
            try {
                await fetch(API_URL, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ content: input.value })
                });
                input.value = '';
                loadData();
            } catch(e) {
                console.error('Error:', e);
            }
        }
        
        loadData();
    </script>
</body>
</html>'''


def create_default_frontend() -> str:
    """创建默认前端"""
    (PROJECT_DIR / "index.html").write_text(create_default_html_code(), encoding='utf-8')
    return "默认HTML前端已创建"


def main():
    print("="*70)
    print("🎨 Frontend Agent 已启动 (LLM驱动)")
    print("="*70)
    print("\n等待任务分配...\n")
    
    wait_time = 0
    max_wait = 120
    
    while wait_time < max_wait:
        messages = read_messages("frontend")
        
        if messages:
            for msg in messages:
                print(f"\n📋 收到任务来自 {msg['from']}:")
                print(f"   {msg['content'][:100]}...\n")
                
                print("🤖 Frontend Agent 使用LLM生成代码...")
                result = create_frontend_with_llm(msg['content'])
                print(f"✓ {result}\n")
                
                context.update_task("frontend", "completed", result)
                send_message("frontend", "lead", f"前端完成: {result}")
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
        print("\n\n👋 Frontend Agent 停止")
        sys.exit(0)
