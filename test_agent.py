#!/usr/bin/env python3
"""
Test Agent v2.0 - 测试Agent
核心改进:
  1. 等待后端 API spec 就绪后才生成测试
  2. 测试内容精确匹配后端 API 端点
  3. 不再猜测端点，直接使用 APISpecStore 中的数据
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


def create_tests_with_llm(task_description: str, api_spec: dict) -> str:
    """使用 LLM 生成测试代码，基于真实 API spec"""
    if client is None:
        return create_default_tests(api_spec)

    api_info = json.dumps(api_spec, indent=2, ensure_ascii=False)
    base_url = api_spec.get("base_url", "http://localhost:5000")

    prompt = f"""
你是一个QA测试工程师。根据以下API规范生成Python测试代码：

测试需求: {task_description}

**后端 API 规范（必须严格基于此编写测试）:**
{api_info}

请生成 test_api.py（包含在```python```代码块中）：
- 使用 pytest 或 unittest 框架
- API 基础URL为: {base_url}
- 测试每一个 API 端点（根据上述规范）
- 包含正常情况和边界情况
- 测试错误处理（404, 参数校验失败等）
- 每个测试函数有清晰的 docstring

**重要**: 所有测试用例的端点路径和方法必须与上述 API 规范完全一致！
"""

    try:
        response = client.messages.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=3000
        )
        result_text = extract_text_from_response(response)
        test_code = extract_code_block(result_text, "python")
        if not test_code:
            test_code = create_default_test_code(api_spec)
        save_test(test_code)
        return "测试用例已生成（已对齐后端API）"
    except Exception as e:
        print(f"❌ LLM生成失败: {e}")
        return create_default_tests(api_spec)


def extract_code_block(text: str, lang: str) -> str:
    pattern = rf'```{lang}\n(.*?)\n```'
    match = re.search(pattern, text, re.DOTALL)
    return match.group(1) if match else None


def save_test(test_code: str):
    tests_dir = PROJECT_DIR / "tests"
    tests_dir.mkdir(exist_ok=True)
    (tests_dir / "test_api.py").write_text(test_code, encoding='utf-8')


def create_default_test_code(api_spec: dict) -> str:
    """根据 API spec 动态生成默认测试代码"""
    base_url = api_spec.get("base_url", "http://localhost:5000")
    endpoints = api_spec.get("endpoints", [])

    # 生成测试端点列表
    test_methods = []
    for ep in endpoints:
        method = ep.get("method", "GET")
        path = ep.get("path", "/")
        desc = ep.get("description", f"{method} {path}")
        safe_name = re.sub(r'[^a-zA-Z0-9]', '_', f"{method}_{path}".replace('/', '_'))

        if method == "GET":
            test_methods.append(f'''
    def test_{safe_name.lower()}(self):
        """{desc}"""
        response = requests.get(f"{{BASE_URL}}{path}")
        self.assertIn(response.status_code, [200, 201])''')
        elif method == "POST":
            test_methods.append(f'''
    def test_{safe_name.lower()}(self):
        """{desc}"""
        response = requests.post(f"{{BASE_URL}}{path}", json={{"test": "data"}})
        self.assertIn(response.status_code, [200, 201, 400])''')

    tests_body = "\n".join(test_methods) if test_methods else '''
    def test_health(self):
        """测试健康检查"""
        response = requests.get(f"{BASE_URL}/api/health")
        self.assertEqual(response.status_code, 200)'''

    return f'''import unittest
import requests
import time

BASE_URL = "{base_url}"

class TestAPI(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls):
        """等待服务启动"""
        time.sleep(2)
{tests_body}

if __name__ == "__main__":
    unittest.main()
'''


def create_default_tests(api_spec: dict) -> str:
    test_code = create_default_test_code(api_spec)
    save_test(test_code)
    return "默认测试已创建"


def main():
    print("=" * 70)
    print("🧪 Test Agent v2.0 - 等待 API spec 后生成测试")
    print("=" * 70)
    print("\n等待 Lead Agent 分配任务（后端 API 就绪后才会收到）...\n")

    wait_time = 0
    max_wait = 600

    while wait_time < max_wait:
        messages = BUS.read_inbox("test")

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

                # 从共享存储获取 API spec
                print("🔍 正在获取后端 API 规范...")
                api_spec = API_SPEC.wait_for_spec(timeout=60)

                if api_spec:
                    print(f"✓ API 规范已获取: {len(api_spec.get('endpoints', []))} 个端点")
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

                print("🤖 Test Agent 使用 LLM 生成测试代码（匹配后端 API）...")
                result = create_tests_with_llm(task_content, api_spec)
                print(f"✓ {result}\n")

                BUS.send(
                    sender="test",
                    to="lead",
                    content=f"测试完成: {result}",
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
        print("\n\n👋 Test Agent 停止")
        sys.exit(0)
