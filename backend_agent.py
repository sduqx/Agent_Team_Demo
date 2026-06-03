#!/usr/bin/env python3
"""
Backend Agent v4.0 — 纯 ReAct + 基础工具，无内嵌 LLM 调用
所有代码生成由 ReAct 循环中的 LLM 直接完成，不再通过包装工具调内层 LLM。
"""

import sys
from agent_base import BaseAgent, LLM_AVAILABLE
from shared_context import BUS


class BackendAgent(BaseAgent):
    """后端开发 Agent —— 在 ReAct 循环中直接设计 API + 生成代码 + 发布契约"""

    def __init__(self):
        super().__init__(name="backend", role="backend", max_rounds=15)

    def _setup_tools(self):
        """只使用 BaseAgent 提供的 6 个基础工具，不注册任何自定义工具"""
        pass

    def get_system_prompt(self) -> str:
        return f"""你是 Backend Agent，Python 后端开发工程师。
工作目录: {self.project_dir}

你需要按以下步骤完成任务（全部使用基础工具）：

1. 先用 read_inbox 确认任务内容
2. 设计 REST API 规范（JSON 格式，包含端点 path、method、request_body schema、response schema），用 write_file 保存到 api_spec.json
3. 根据规范生成完整 Flask 代码，用 write_file 保存到 app.py
4. 用 write_file 保存 requirements.txt（Flask==2.3.3 + Flask-CORS==4.0.0）
5. 用 send_message 通知 frontend 和 test："API 规范已写入 api_spec.json，请 read_file 读取"
6. 调用 finish_task 提交总结

关键规则：
- 代码必须包含 CORS 支持和错误处理
- POST/PUT 端点的 request_body 必须标明必填字段
- 每个端点的 response 必须包含完整 properties
- 直接行动，不要空谈。需要生成代码时直接 write_file，不要在对话中输出完整代码"""


def main():
    if not LLM_AVAILABLE:
        print("[FAIL] LLM 不可用，请检查 .env 配置")
        sys.exit(1)
    agent = BackendAgent()
    try:
        agent.run()
    except KeyboardInterrupt:
        print("\n\n[BYE] Backend Agent 停止")
        sys.exit(0)


if __name__ == "__main__":
    main()