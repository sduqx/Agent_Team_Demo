#!/usr/bin/env python3
"""
Frontend Agent - 前端开发Agent
"""

import sys
import time
from pathlib import Path
from shared_context import SharedContext, send_message, read_messages

context = SharedContext()
PROJECT_DIR = Path.cwd() / ".project"
PROJECT_DIR.mkdir(exist_ok=True)


def create_html_ui():
    """创建HTML界面"""
    
    html_code = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TODO 应用</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }
        .container { 
            max-width: 800px; 
            width: 100%;
            background: white; 
            padding: 30px; 
            border-radius: 12px; 
            box-shadow: 0 10px 40px rgba(0,0,0,0.2); 
        }
        h1 { 
            color: #333; 
            margin-bottom: 30px; 
            text-align: center;
            font-size: 2.5em;
        }
        .input-group { 
            display: flex; 
            gap: 10px; 
            margin-bottom: 30px; 
        }
        input { 
            flex: 1; 
            padding: 12px 15px; 
            border: 2px solid #ddd; 
            border-radius: 8px; 
            font-size: 1em;
            transition: border-color 0.3s;
        }
        input:focus { 
            outline: none; 
            border-color: #667eea;
        }
        button { 
            padding: 12px 30px; 
            background: #667eea; 
            color: white; 
            border: none; 
            border-radius: 8px; 
            cursor: pointer; 
            font-size: 1em;
            font-weight: bold;
            transition: background 0.3s;
        }
        button:hover { 
            background: #764ba2; 
        }
        .todo-list { 
            list-style: none; 
        }
        .todo-item { 
            display: flex; 
            align-items: center; 
            padding: 15px; 
            border: 1px solid #eee; 
            margin-bottom: 10px; 
            border-radius: 8px; 
            background: #f9f9f9;
            transition: all 0.3s;
        }
        .todo-item:hover { 
            background: #f0f0f0; 
        }
        .todo-item input[type="checkbox"] { 
            margin-right: 15px; 
            width: 20px;
            height: 20px;
            cursor: pointer;
        }
        .todo-item.completed { 
            opacity: 0.6; 
            text-decoration: line-through; 
        }
        .todo-text {
            flex: 1;
        }
        .delete-btn { 
            margin-left: 15px; 
            background: #dc3545; 
            padding: 8px 15px; 
            font-size: 0.9em;
        }
        .delete-btn:hover { 
            background: #c82333; 
        }
        .empty-state {
            text-align: center;
            color: #999;
            padding: 40px 20px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>📝 我的TODO清单</h1>
        <div class="input-group">
            <input type="text" id="todoInput" placeholder="输入新任务..." autocomplete="off">
            <button onclick="addTodo()">➕ 添加</button>
        </div>
        <ul class="todo-list" id="todoList"></ul>
        <div class="empty-state" id="emptyState">暂无任务，开始添加吧！</div>
    </div>
    
    <script>
        const API_URL = 'http://localhost:5000/api/todos';
        const todoInput = document.getElementById('todoInput');
        
        async function loadTodos() {
            try {
                const response = await fetch(API_URL);
                const todos = await response.json();
                renderTodos(todos);
            } catch(e) {
                console.log('❌ 后端未连接，使用离线模式');
                renderEmpty();
            }
        }
        
        function renderTodos(todos) {
            const list = document.getElementById('todoList');
            const empty = document.getElementById('emptyState');
            
            if (todos.length === 0) {
                list.innerHTML = '';
                empty.style.display = 'block';
                return;
            }
            
            empty.style.display = 'none';
            list.innerHTML = todos.map(todo => `
                <li class="todo-item ${todo.completed ? 'completed' : ''}">
                    <input type="checkbox" ${todo.completed ? 'checked' : ''} 
                           onchange="toggleTodo(${todo.id}, this.checked)">
                    <span class="todo-text">${escapeHtml(todo.title)}</span>
                    <button class="delete-btn" onclick="deleteTodo(${todo.id})">🗑️ 删除</button>
                </li>
            `).join('');
        }
        
        function renderEmpty() {
            document.getElementById('todoList').innerHTML = '';
            document.getElementById('emptyState').style.display = 'block';
        }
        
        async function addTodo() {
            const title = todoInput.value.trim();
            if (!title) return;
            
            try {
                await fetch(API_URL, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ title })
                });
            } catch(e) {
                console.log('离线模式');
            }
            
            todoInput.value = '';
            loadTodos();
        }
        
        async function toggleTodo(id, completed) {
            try {
                await fetch(API_URL + '/' + id, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ completed })
                });
            } catch(e) {}
            loadTodos();
        }
        
        async function deleteTodo(id) {
            try {
                await fetch(API_URL + '/' + id, { method: 'DELETE' });
            } catch(e) {}
            loadTodos();
        }
        
        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }
        
        todoInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') addTodo();
        });
        
        loadTodos();
        setInterval(loadTodos, 3000);
    </script>
</body>
</html>
'''
    
    (PROJECT_DIR / "index.html").write_text(html_code, encoding='utf-8')
    return "HTML UI已创建 (index.html)"


def main():
    print("=" * 70)
    print("🎨 Frontend Agent 已启动")
    print("=" * 70)
    print("\n等待任务分配...\n")
    
    wait_time = 0
    max_wait = 120
    
    while wait_time < max_wait:
        messages = read_messages("frontend")
        
        if messages:
            for msg in messages:
                print(f"\n📋 收到任务来自 {msg['from']}:")
                print(f"   {msg['content']}\n")
                
                print("🎨 正在创建前端界面...")
                result = create_html_ui()
                print(f"✓ {result}\n")
                
                context.update_task("frontend", "completed", result)
                send_message("frontend", "lead", f"前端完成: {result}")
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
        print("\n\n👋 Frontend Agent 停止")
        sys.exit(0)
