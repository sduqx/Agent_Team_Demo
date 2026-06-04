#!/usr/bin/env python3
"""
DevOps Agent v4.0 — 纯 ReAct + 基础工具，无内嵌 LLM 调用
职责：只负责编写项目 Markdown 文档（README.md 等），不做部署相关操作。
"""

import sys
from .agent_base import BaseAgent, LLM_AVAILABLE
from .shared_context import BUS


class DevOpsAgent(BaseAgent):
    """DevOps Agent —— 只负责编写 Markdown 文档"""

    def __init__(self):
        super().__init__(name="devops", role="devops", max_rounds=8)

    def _setup_tools(self):
        """只使用 BaseAgent 提供的 6 个基础工具"""
        pass

    def get_system_prompt(self) -> str:
        return f"""你是 DevOps Agent，文档工程师。
工作目录: {self.project_dir}

你的唯一职责是编写 Markdown 文档。不要生成 Dockerfile、docker-compose.yml 或其他部署文件。

任务步骤：
1. 用 read_inbox 确认任务内容
2. 用 list_directory 查看项目中的文件
3. 用 read_file 读取 api_spec.json 了解 API 端点
4. 用 read_file 读取 app.py 了解后端入口
5. 用 write_file 生成 README.md
6. 调用 finish_task 完成

README.md 应包含：
- 项目概述
- API 接口文档（基于 api_spec.json）
- 快速开始（如何运行项目）
- 项目结构说明

规则：只写 .md 文件，不生成其他类型的文件。直接行动，不要空谈。"""


def main():
    if not LLM_AVAILABLE:
        print("[FAIL] LLM 不可用，请检查 .env 配置")
        sys.exit(1)
    agent = DevOpsAgent()
    try:
        agent.run()
    except KeyboardInterrupt:
        print("\n\n[BYE] DevOps Agent 停止")
        sys.exit(0)


if __name__ == "__main__":
    main()
