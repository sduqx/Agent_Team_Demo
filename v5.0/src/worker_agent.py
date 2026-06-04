#!/usr/bin/env python3
"""
Worker Agent v2.0 — 通用工作者，动态角色 + 动态技术栈
══════════════════════════════════════════════════════════
v2.0 核心改进（相比 v1.0 的 backend/frontend/test/devops）：
  1. 不再绑定特定语言或框架：System Prompt 根据启动参数动态生成
  2. 通过 --name 和 --tech 参数注入角色和技术栈描述
  3. 从 Lead Agent 接收任务后，利用 LLM 的通用能力处理任意技术栈的代码生成
  4. Worker 不知道自己叫"Backend Agent"还是"Mobile Agent"，只知道自己是什么角色

启动方式（由 Lead Agent 自动孵化）：
  python worker_agent.py --name backend --tech "Node.js Express + PostgreSQL 后端开发"
  python worker_agent.py --name mobile --tech "Flutter 跨平台移动端开发"
  python worker_agent.py --name frontend --tech "React + TypeScript 前端开发"
  python worker_agent.py --name test --tech "测试工程师，编写自动化测试"
"""

import sys
import argparse
from pathlib import Path
from .agent_base import BaseAgent, LLM_AVAILABLE


class WorkerAgent(BaseAgent):
    """
    通用 Worker Agent v2.0。
    不再写死技术栈，而是通过启动参数接收角色描述和技术栈信息，
    由 LLM 自行发挥生成任何技术栈的代码。
    """

    def __init__(self, name: str, tech_description: str = "",
                 project_dir: Path = None, max_rounds: int = 50):
        self.tech_description = tech_description
        super().__init__(
            name=name,
            role=name,
            max_rounds=max_rounds,
            project_dir=project_dir,
        )

    def _setup_tools(self):
        """Worker 只使用 BaseAgent 提供的通用工具，不注册额外工具。"""
        pass

    def get_system_prompt(self) -> str:
        """动态生成 System Prompt，根据角色和技术栈描述自适应。"""
        return f"""你是 '{self.name}' Agent，{self.tech_description}。
工作目录: {self.project_dir}

## 你的工作方式
你是一个全栈开发专家。虽然你的角色是 {self.name}，但你拥有通用编程知识。
你需要根据收到的任务描述，用合适的语言、框架和工具完成工作。

## 工作步骤
1. 用 read_inbox 确认收到的任务内容（Lead 发送的 task 消息包含详细的需求描述）
2. 理解任务：需要产出什么文件？用什么语言/框架？有什么接口契约需要遵循？
3. 产出代码文件：使用 write_file 工具逐个创建所需文件
4. 如果需要读取其他 Agent 的产出（如 API 契约、数据模型），使用 read_file
5. 如果需要通知其他 Agent（如你完成了契约文档让别人开始），使用 send_message
6. ═══ 自验证 ═══ 在调用 finish_task 之前，务必执行以下验证：
   a. 用 list_directory 确认所有承诺的产出文件都存在且大小合理
   b. 如果是代码文件，用 run_command 执行编译/语法检查（如 python -m py_compile、node -c、go build 等）
   c. 如果是测试文件，用 run_command 运行测试确认通过
   d. 如果验证不通过，修复问题后重新验证，直到全部通过
7. 所有验证通过后，调用 finish_task 提交完成总结

## 关键规则
- **产出代码必须是完整可运行的**：包含所有 import、配置、依赖声明（如 package.json/requirements.txt/go.mod 等）
- **契约优先**：如果你产出了其他 Agent 依赖的接口定义（如 API 契约），要明确告知并在总结中说明
- **文件组织合理**：使用合适的目录结构，不要所有文件堆在根目录
- **代码规范**：注释清晰、错误处理完善、遵循对应语言的最佳实践
- **直接行动**：需要生成代码时直接 write_file，不要在对话中输出完整代码（对话中只做简要说明）
- **必须自验证**：产出代码后必须用 run_command 验证编译/运行，确认无误后再 finish_task

## 技术自由度
- 你精通多种编程语言和框架：Python、JavaScript/TypeScript、Go、Java、Rust、Dart 等
- 你熟悉各种前端框架：React、Vue、Angular、Svelte、Flutter 等
- 你熟悉各种后端框架：Flask、FastAPI、Express、Gin、Spring Boot 等
- 你可以处理数据库相关：SQL、NoSQL、ORM、迁移脚本等
- 你可以编写测试、文档、部署配置等各类文件

## 遇到不确定的情况
- 如果任务描述不清晰，优先根据上下文合理推断并继续
- 如果技术选型存在明显问题（如任务要求的技术与你擅长的方向不符），可以适当调整
- 只有在确实需要人类决策的关键问题上才使用 ask_user

记住：你是一位经验丰富的工程师，不是固定的代码模板。分析需求 → 设计方案 → 产出代码 → 自验证 → 提交完成。"""


def parse_args():
    parser = argparse.ArgumentParser(
        description="Worker Agent v2.0 — 通用工作者",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python worker_agent.py --name backend --tech "Node.js Express 后端开发"
  python worker_agent.py --name mobile --tech "Flutter 跨平台移动端开发"
  python worker_agent.py --name frontend --tech "React + TypeScript 前端开发"
        """
    )
    parser.add_argument("--name", type=str, required=True,
                        help="Agent 名称（也是角色名，如 backend/frontend/mobile/test/devops/design 等）")
    parser.add_argument("--tech", type=str, default="通用开发工程师",
                        help="角色描述和技术栈说明")
    parser.add_argument("--project-dir", type=str, default=None,
                        help="项目产物输出目录（默认 .project）")
    parser.add_argument("--max-rounds", type=int, default=50,
                        help="ReAct 循环最大轮数")
    return parser.parse_args()


def main():
    args = parse_args()

    print("=" * 70)
    print(f"[WORKER] Worker Agent v2.0 — 通用工作者")
    print(f"  名称: {args.name}")
    print(f"  技术栈: {args.tech}")
    print(f"  产物目录: {args.project_dir or '.project'}")
    print("=" * 70)

    if not LLM_AVAILABLE:
        print("[FAIL] LLM 不可用，请检查 .env 配置")
        sys.exit(1)

    project_dir = Path(args.project_dir) if args.project_dir else None

    agent = WorkerAgent(
        name=args.name,
        tech_description=args.tech,
        project_dir=project_dir,
        max_rounds=args.max_rounds,
    )

    try:
        agent.run()
    except KeyboardInterrupt:
        print(f"\n\n[BYE] Worker '{args.name}' 停止")
        sys.exit(0)


if __name__ == "__main__":
    main()
