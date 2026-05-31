#!/usr/bin/env python3
"""
Lead Agent v4.0 — 主控 Agent，ReAct 循环 + 管理类 Tools
核心改进：
  1. 移除 analyze_requirement（内嵌 LLM 调用），任务分析由 ReAct 中的 LLM 直接完成
  2. 保留 create_and_link_tasks / dispatch_ready_tasks / mark_task_done / check_all_tasks（操作型工具）
  3. 监控阶段继续使用 run() 中的事件循环（读收件箱 → 标记完成 → 分派下一批）
"""

import sys
import time
import json
from agent_base import BaseAgent, LLM_AVAILABLE
from shared_context import TASK_MGR, BUS


class LeadAgent(BaseAgent):
    """主控 Agent —— 需求分析 + 任务编排 + 进度监控"""

    def __init__(self):
        super().__init__(name="lead", role="lead", max_rounds=6)
        self._role_to_id: dict = {}      # role → task_id
        self._dispatched: set = set()    # 已分发的 task_id
        self._all_done_reported = False

    def _setup_tools(self):
        """注册 Lead 专属管理 tools（均为操作型，不调内层 LLM）"""
        self.register_tool(
            name="create_and_link_tasks",
            description="根据任务计划 JSON 批量创建任务并设置依赖关系。JSON 格式：{\"project_name\":\"...\",\"tasks\":[{\"role\":\"backend\",\"subject\":\"...\",\"description\":\"...\",\"depends_on\":[]},...]}",
            input_schema={
                "type": "object",
                "properties": {
                    "analysis_json": {"type": "string", "description": "任务计划 JSON 字符串"},
                },
                "required": ["analysis_json"],
            },
            handler=self._handle_create_and_link_tasks,
        )

        self.register_tool(
            name="dispatch_ready_tasks",
            description="扫描所有就绪（无阻塞）的 pending 任务，分发消息给对应的 Worker Agent。",
            input_schema={"type": "object", "properties": {}},
            handler=self._handle_dispatch_ready_tasks,
        )

        self.register_tool(
            name="check_all_tasks",
            description="查看所有任务的状态。",
            input_schema={"type": "object", "properties": {}},
            handler=self._handle_check_all_tasks,
        )

        self.register_tool(
            name="mark_task_done",
            description="标记一个 Worker 完成的任务。Agent 将自动解锁依赖该任务的其他任务。",
            input_schema={
                "type": "object",
                "properties": {
                    "worker_name": {"type": "string", "description": "完成任务的 Worker 名称 (backend/frontend/test/devops)"},
                    "output": {"type": "string", "description": "Worker 汇报的输出内容"},
                },
                "required": ["worker_name"],
            },
            handler=self._handle_mark_task_done,
        )

    def get_system_prompt(self) -> str:
        return f"""你是 Lead Agent，项目主管。负责分析需求、编排任务、监控进度。

## 可用的团队成员（role）
- backend：Python Flask 后端开发，产出 api_spec.json + app.py
- frontend：HTML/CSS/JS 前端开发，产出 index.html
- test：Python unittest 测试，产出 tests/test_api.py
- devops：文档工程师，产出 README.md

## 团队协作的依赖规则
- backend 设计 API 契约，其他成员需要先拿到 API 规范才能工作
- 因此 frontend 和 test 必须依赖 backend
- devops 需要看到完整的项目产物，所以依赖 frontend + test 都完成

## create_and_link_tasks 的 JSON 格式示例（必须严格按此结构填写 depends_on）
```json
{
  "project_name": "用户管理系统",
  "tasks": [
    {"role": "backend",  "subject": "设计 REST API 并实现后端", "description": "...(详细描述API端点)...", "depends_on": []},
    {"role": "frontend", "subject": "实现管理页面前端",         "description": "...(详细描述页面功能)...", "depends_on": ["backend"]},
    {"role": "test",     "subject": "编写 API 测试用例",        "description": "...(详细描述测试场景)...", "depends_on": ["backend"]},
    {"role": "devops",   "subject": "编写项目 README 文档",     "description": "...(详细描述文档要求)...", "depends_on": ["frontend", "test"]}
  ]
}
```
⚠️ depends_on 必须包含依赖的 role 名称（如 "backend"），第一个任务通常填 []，不要全部填空数组！

## 你的工作方式
1. 认真阅读需求，判断这是一个什么类型的项目，需要哪些角色参与
2. 根据需求的具体内容，为每个需要的角色撰写详细的任务 description（包含具体的 API 端点、字段要求等）
3. 调用 create_and_link_tasks 创建任务图（只调一次）
4. 调用 dispatch_ready_tasks 分发就绪任务（只调一次）
5. 调用 finish_task 结束（Worker 完成后会由后台事件循环自动处理）

## 任务 description 撰写要求
- backend 的描述必须列出具体 API 端点：path、HTTP method、request/response 字段
- frontend 的描述必须说明：API_BASE 用 'http://localhost:5000/api'（绝对地址）、需读 api_spec.json 了解接口
- test 的描述必须说明：需读 api_spec.json、覆盖正常+边界场景

## 约束
- create_and_link_tasks 只能调用一次
- dispatch_ready_tasks 只能调用一次
- 调用 dispatch_ready_tasks 后立即 finish_task，不要轮询等待
- 描述要具体，不要写"实现所有 API"这种空泛内容"""

    # ── Tool Handlers（纯操作型，不调 LLM）──

    def _handle_create_and_link_tasks(self, analysis_json: str) -> str:
        """根据分析结果批量创建任务并设置依赖"""
        try:
            analysis = json.loads(analysis_json)
        except json.JSONDecodeError as e:
            return f"❌ JSON 解析失败: {e}"

        project_name = analysis.get("project_name", "Untitled")
        TASK_MGR.set_project(project_name, "")

        self._role_to_id = {}
        lines = [f"📁 项目: {project_name}", ""]

        for t in analysis["tasks"]:
            task = TASK_MGR.create(
                subject=t["subject"],
                description=t["description"],
                role=t["role"],
                blocked_by=[],
            )
            self._role_to_id[t["role"]] = task["id"]
            lines.append(f"  📋 Task #{task['id']}: [{t['role']}] {t['subject']}")

        for t in analysis["tasks"]:
            tid = self._role_to_id[t["role"]]
            blocked_ids = [self._role_to_id[d] for d in t["depends_on"] if d in self._role_to_id]
            if blocked_ids:
                TASK_MGR.update(tid, add_blocked_by=blocked_ids)
                deps = ", ".join(f"#{bid}" for bid in blocked_ids)
                lines.append(f"    ↳ Task #{tid} 依赖: {deps}")

        self._dispatched.clear()
        self._all_done_reported = False
        lines.append(f"\n✓ 共创建 {len(analysis['tasks'])} 个任务")
        return "\n".join(lines)

    def _handle_dispatch_ready_tasks(self) -> str:
        """扫描就绪任务并分派给对应 Worker"""
        dispatched = []
        for role, tid in self._role_to_id.items():
            if tid in self._dispatched:
                continue
            if TASK_MGR.is_ready(tid):
                task = TASK_MGR.get(tid)
                BUS.send(
                    sender="lead", to=role, content=task["description"],
                    msg_type="task",
                    extra={"task_id": tid, "subject": task["subject"]},
                )
                TASK_MGR.claim(tid, role)
                self._dispatched.add(tid)
                dispatched.append(f"  🚀 Task #{tid} → {role}: {task['subject']}")

        if not dispatched:
            if TASK_MGR.all_completed() and not self._all_done_reported:
                self._all_done_reported = True
                return "🎉 所有任务已完成！\n" + TASK_MGR.list_all()
            return "当前没有新的就绪任务可分配（等待依赖解锁）。\n" + TASK_MGR.list_all()

        return "\n".join(dispatched) + "\n\n" + TASK_MGR.list_all()

    def _handle_check_all_tasks(self) -> str:
        return TASK_MGR.list_all()

    def _handle_mark_task_done(self, worker_name: str, output: str = "") -> str:
        """标记 Worker 完成的任务"""
        for tid in self._dispatched:
            task = TASK_MGR.get(tid)
            if task.get("owner") == worker_name and task.get("status") == "in_progress":
                TASK_MGR.update(tid, status="completed", output=output)
                print(f"  ✅ Task #{tid} ({worker_name}) 完成!")
                return f"✓ Task #{tid} ({worker_name}) 已标记完成。现在可以调用 dispatch_ready_tasks 检查是否有新任务解锁。"

        return f"⚠️ 未找到 {worker_name} 的 in_progress 任务"

    # ── 主循环（分析阶段用 ReAct，监控阶段用事件循环）──

    def run(self, poll_forever: bool = True):
        """Lead 专属主循环：交互式输入 → ReAct 分析分发 → 事件循环监控"""
        print("=" * 70)
        print("👔 Lead Agent v4.0 — 纯 ReAct + 操作型工具")
        print("=" * 70)
        print("\n💡 提示: 可直接输入需求，或等待外部消息\n")

        try:
            user_input = input("📝 请输入项目需求（直接回车则等待外部消息）: ").strip()
        except (EOFError, KeyboardInterrupt):
            user_input = ""

        if user_input:
            self._process_new_requirement(user_input)
            print("\n⏳ 等待 Agent 完成工作...\n")
        else:
            print("\n⏳ 等待外部需求输入...\n")

        # ── 事件循环：监控 Worker 汇报 ──
        while True:
            time.sleep(2)
            inbox = BUS.read_inbox("lead")
            for msg in inbox:
                sender = msg.get("from", "unknown")
                msg_type = msg.get("type", "")
                content = msg.get("content", "")

                print(f"\n📬 来自 {sender} [{msg_type}]: {content[:120]}")

                if msg_type == "requirement" or (sender == "system" and "requirement:" in content.lower()):
                    req = content.replace("requirement:", "").strip()
                    self._process_new_requirement(req)

                elif sender in ("backend", "frontend", "test", "devops"):
                    did = self._handle_mark_task_done(sender, content)
                    print(did)
                    disp = self._handle_dispatch_ready_tasks()
                    print(disp)
                    if "所有任务已完成" in disp:
                        print("\n" + "=" * 70)
                        print("🎉 全部完成！输出在 .project/ 目录")
                        print("=" * 70)
                        if not poll_forever:
                            return

    def _process_new_requirement(self, requirement: str):
        """处理新需求：ReAct 分析 → 创建任务 → 分发（LLM 直接在 ReAct 中产出任务 JSON）"""
        prompt = f"""收到新需求，请分析并编排任务：

<requirement>
{requirement}
</requirement>

请执行以下步骤：
1. 先分析这个需求需要哪些角色参与、需要哪些 API 端点、任务的依赖关系应该怎么安排
2. 调用 create_and_link_tasks 创建任务图（给每个任务写详细描述，不要空泛）
3. 调用 dispatch_ready_tasks 分发就绪任务
4. 调用 finish_task 结束"""

        result = self.react_loop(prompt)
        print(f"\n[Lead] 需求分析完成: {result[:200]}")


def main():
    agent = LeadAgent()
    try:
        agent.run()
    except KeyboardInterrupt:
        print("\n\n👋 Lead Agent 停止")
        sys.exit(0)


if __name__ == "__main__":
    main()