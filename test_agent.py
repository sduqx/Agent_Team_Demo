#!/usr/bin/env python3
"""
Test Agent v4.0 — 纯 ReAct + 基础工具，无内嵌 LLM 调用
通过 read_file 读取 api_spec.json，ReAct 中直接生成测试代码并用 write_file 保存。
"""

import sys
from agent_base import BaseAgent, LLM_AVAILABLE
from shared_context import BUS


class TestAgent(BaseAgent):
    """测试 Agent —— 在 ReAct 循环中直接基于 API 契约生成测试用例"""

    def __init__(self):
        super().__init__(name="test", role="test", max_rounds=10)

    def _setup_tools(self):
        """只使用 BaseAgent 提供的 6 个基础工具"""
        pass

    def get_system_prompt(self) -> str:
        return f"""你是 Test Agent，QA 测试工程师。
工作目录: {self.project_dir}

你需要按以下步骤完成任务（全部使用基础工具）：

1. 用 read_inbox 确认任务内容
2. 用 read_file 读取 api_spec.json 了解后端 API 端点、方法、请求/响应字段
3. 根据 API 契约生成 Python 测试代码（unittest 框架），用 write_file 保存到 tests/test_api.py
4. 调用 finish_task 提交总结

关键规则：
- 测试端点路径和方法必须与 api_spec.json 完全一致
- POST/PUT 测试数据的字段名和类型必须精确匹配 request_body.properties
- 覆盖正常场景 + 边界情况
- 包含 setUpClass 等待服务启动
- 直接行动，不要空谈。需要生成代码时直接 write_file，不要在对话中输出完整代码"""


def main():
    if not LLM_AVAILABLE:
        print("❌ LLM 不可用，请检查 .env 配置")
        sys.exit(1)
    agent = TestAgent()
    try:
        agent.run()
    except KeyboardInterrupt:
        print("\n\n👋 Test Agent 停止")
        sys.exit(0)


if __name__ == "__main__":
    main()