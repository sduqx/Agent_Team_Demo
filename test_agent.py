#!/usr/bin/env python3
"""
Test Agent - 测试Agent
"""

import sys
import time
from pathlib import Path
from shared_context import SharedContext, send_message, read_messages

context = SharedContext()
PROJECT_DIR = Path.cwd() / ".project"
PROJECT_DIR.mkdir(exist_ok=True)


def create_tests():
    """创建测试文件"""
    
    test_code = '''import unittest
import sys
from pathlib import Path

class TestProject(unittest.TestCase):
    
    def test_project_backend_exists(self):
        """测试后端文件存在"""
        project_dir = Path(__file__).parent.parent / ".project"
        self.assertTrue((project_dir / "app.py").exists(), "app.py 应该存在")
    
    def test_project_frontend_exists(self):
        """测试前端文件存在"""
        project_dir = Path(__file__).parent.parent / ".project"
        self.assertTrue((project_dir / "index.html").exists(), "index.html 应该存在")
    
    def test_basic_math(self):
        """基础数学测试"""
        self.assertEqual(1 + 1, 2)
        self.assertTrue(2 > 1)

if __name__ == '__main__':
    unittest.main(verbosity=2)
'''
    
    tests_dir = PROJECT_DIR / "tests"
    tests_dir.mkdir(exist_ok=True)
    (tests_dir / "test_basic.py").write_text(test_code, encoding='utf-8')
    
    return "测试文件已创建 (tests/test_basic.py)"


def main():
    print("=" * 70)
    print("🧪 Test Agent 已启动")
    print("=" * 70)
    print("\n等待任务分配...\n")
    
    wait_time = 0
    max_wait = 120
    
    while wait_time < max_wait:
        messages = read_messages("test")
        
        if messages:
            for msg in messages:
                print(f"\n📋 收到任务来自 {msg['from']}:")
                print(f"   {msg['content']}\n")
                
                print("🧪 正在创建测试文件...")
                result = create_tests()
                print(f"✓ {result}\n")
                
                context.update_task("test", "completed", result)
                send_message("test", "lead", f"测试完成: {result}")
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
        print("\n\n👋 Test Agent 停止")
        sys.exit(0)
