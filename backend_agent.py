#!/usr/bin/env python3
"""
Backend Agent - 后端开发Agent
"""

import sys
import time
from pathlib import Path
from shared_context import SharedContext, send_message, read_messages

context = SharedContext()
PROJECT_DIR = Path.cwd() / ".project"
PROJECT_DIR.mkdir(exist_ok=True)


def create_flask_app():
    """创建Flask应用"""
    
    app_code = '''#!/usr/bin/env python3
from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

todos = []

@app.route('/api/todos', methods=['GET'])
def get_todos():
    return jsonify(todos)

@app.route('/api/todos', methods=['POST'])
def create_todo():
    data = request.json
    todo = {
        'id': len(todos) + 1,
        'title': data.get('title', ''),
        'completed': False
    }
    todos.append(todo)
    return jsonify(todo), 201

@app.route('/api/todos/<int:todo_id>', methods=['PUT'])
def update_todo(todo_id):
    data = request.json
    for todo in todos:
        if todo['id'] == todo_id:
            todo.update(data)
            return jsonify(todo)
    return {'error': 'Not found'}, 404

@app.route('/api/todos/<int:todo_id>', methods=['DELETE'])
def delete_todo(todo_id):
    global todos
    todos = [t for t in todos if t['id'] != todo_id]
    return '', 204

if __name__ == '__main__':
    print("🚀 Flask服务启动在 http://localhost:5000")
    app.run(debug=True, port=5000, use_reloader=False)
'''
    
    requirements = '''Flask==2.3.3
Flask-CORS==4.0.0
Werkzeug==2.3.7
'''
    
    config = '''DEBUG = True
HOST = '127.0.0.1'
PORT = 5000
'''
    
    (PROJECT_DIR / "app.py").write_text(app_code, encoding='utf-8')
    (PROJECT_DIR / "requirements.txt").write_text(requirements, encoding='utf-8')
    (PROJECT_DIR / "config.py").write_text(config, encoding='utf-8')
    
    return "Flask应用已创建 (app.py, requirements.txt)"


def main():
    print("=" * 70)
    print("🔧 Backend Agent 已启动")
    print("=" * 70)
    print("\n等待任务分配...\n")
    
    wait_time = 0
    max_wait = 120
    
    while wait_time < max_wait:
        messages = read_messages("backend")
        
        if messages:
            for msg in messages:
                print(f"\n📋 收到任务来自 {msg['from']}:")
                print(f"   {msg['content']}\n")
                
                print("⚙️  正在创建后端应用...")
                result = create_flask_app()
                print(f"✓ {result}\n")
                
                context.update_task("backend", "completed", result)
                send_message("backend", "lead", f"后端完成: {result}")
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
        print("\n\n👋 Backend Agent 停止")
        sys.exit(0)
