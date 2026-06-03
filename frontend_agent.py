#!/usr/bin/env python3
"""
Frontend Agent v4.0 — 纯 ReAct + 基础工具，无内嵌 LLM 调用
通过 read_file 读取 api_spec.json，ReAct 中直接生成 HTML 并用 write_file 保存。
"""

import sys
from agent_base import BaseAgent, LLM_AVAILABLE
from shared_context import BUS


class FrontendAgent(BaseAgent):
    """前端开发 Agent —— 在 ReAct 循环中直接读取 API 契约并生成前端代码"""

    def __init__(self):
        super().__init__(name="frontend", role="frontend", max_rounds=10)

    def _setup_tools(self):
        """只使用 BaseAgent 提供的 6 个基础工具"""
        pass

    def get_system_prompt(self) -> str:
        return f"""你是 Frontend Agent，前端开发工程师。
工作目录: {self.project_dir}

你需要按以下步骤完成任务（全部使用基础工具）：

1. 用 read_inbox 确认任务内容
2. 用 read_file 读取 api_spec.json 了解后端 API 端点、HTTP 方法、请求/响应字段
3. 根据 API 契约生成完整 HTML 单页面应用（内嵌 CSS + JS），用 write_file 保存到 index.html
4. 调用 finish_task 提交总结

关键规则（必须严格遵守）：
- API_BASE 必须使用绝对地址 'http://localhost:5000/api'（后端在 localhost:5000，前端直接双击打开，跨域访问）
- 所有 fetch 请求路径必须与 api_spec.json 的端点完全一致（method、path、request/response 字段名）
- POST/PUT 请求必须设置 Content-Type: application/json
- 美观现代的 UI（渐变、阴影、圆角），响应式设计（移动端适配）
- 必须包含：搜索/过滤框 + 新建按钮（工具栏区）+ 卡片列表 + 空状态提示
- 空状态必须包含醒目的创建按钮，不能只显示"暂无数据"文本
- 所有交互（增删改查）必须有 loading 状态和错误提示（toast 组件）
- 直接行动，不要空谈。需要生成代码时直接 write_file，不要在对话中输出完整代码"""


def main():
    if not LLM_AVAILABLE:
        print("[FAIL] LLM 不可用，请检查 .env 配置")
        sys.exit(1)
    agent = FrontendAgent()
    try:
        agent.run()
    except KeyboardInterrupt:
        print("\n\n[BYE] Frontend Agent 停止")
        sys.exit(0)


if __name__ == "__main__":
    main()