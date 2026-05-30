#!/usr/bin/env python3
"""
Test Agent - 测试Agent，使用LLM生成测试代码
权限: 可以读写项目文件、执行测试
"""

import sys
import time
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


def create_tests_with_llm(task_description: str) -> str:
    """使用LLM生成测试代码"""
    
    if client is None:
        return create_default_tests()
    
    prompt = f"""
你是一个QA测试工程师。根据以下需求生成完整的Python测试代码：

需求: {task_description}

请生成：
1. test_api.py - 使用pytest或unittest的API测试（包含在```python```代码块中）
   - 测试所有主要API端点
   - 包含正常情况和边界情况
   - 测试错误处理

代码应该能够直接运行，并测试http://localhost:5000上的API。
"""
    
    try:
        response = client.messages.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=3000
        )
        
        result_text = response.content[0].text
        return parse_and_save_tests(result_text)
    except Exception as e:
        print(f"❌ LLM生成失败: {e}")
        return create_default_tests()


def parse_and_save_tests(response_text: str) -> str:
    """从LLM响应中提取测试代码并保存"""
    import re
    
    test_match = re.search(r'```python\n(.*?)\n```', response_text, re.DOTALL)
    if test_match:
        test_code = test_match.group(1)
    else:
        test_code = create_default_test_code()
    
    tests_dir = PROJECT_DIR / "tests"
    tests_dir.mkdir(exist_ok=True)
    (tests_dir / "test_api.py").write_text(test_code, encoding='utf-8')
    
    return "测试用例已生成"


def create_default_test_code() -> str:
    """默认测试代码"""
    return '''import unittest
import requests
import time

BASE_URL = "http://localhost:5000/api"

class TestAPI(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls):
        time.sleep(2)  # 等待服务启动
    
    def test_health(self):
        """测试健康检查端点"""
        response = requests.get(f"{BASE_URL}/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "healthy")
    
    def test_get_data(self):
        """测试获取数据"""
        response = requests.get(f"{BASE_URL}/data")
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.json(), dict)
    
    def test_create_data(self):
        """测试创建数据"""
        data = {"name": "test", "value": 123}
        response = requests.post(f"{BASE_URL}/data", json=data)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["name"], "test")

if __name__ == "__main__":
    unittest.main()
'''


def create_default_tests() -> str:
    """创建默认测试"""
    tests_dir = PROJECT_DIR / "tests"
    tests_dir.mkdir(exist_ok=True)
    (tests_dir / "test_api.py").write_text(create_default_test_code(), encoding='utf-8')
    return "默认测试已创建"


def main():
    print("="*70)
    print("🧪 Test Agent 已启动 (LLM驱动)")
    print("="*70)
    print("\n等待任务分配...\n")
    
    wait_time = 0
    max_wait = 120
    
    while wait_time < max_wait:
        messages = read_messages("test")
        
        if messages:
            for msg in messages:
                print(f"\n📋 收到任务来自 {msg['from']}:")
                print(f"   {msg['content'][:100]}...\n")
                
                print("🤖 Test Agent 使用LLM生成测试代码...")
                result = create_tests_with_llm(msg['content'])
                print(f"✓ {result}\n")
                
                context.update_task("test", "completed", result)
                send_message("test", "lead", f"测试完成: {result}")
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
        print("\n\n👋 Test Agent 停止")
        sys.exit(0)
