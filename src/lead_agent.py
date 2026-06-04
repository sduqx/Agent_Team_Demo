#!/usr/bin/env python3
"""
Lead Agent v4.0 — 三阶段流程 (规划 → 审查 → 执行)
核心改进：
  1. 规划阶段：LLM 分析需求 → submit_plan → 等待审查（不直接创建任务）
  2. 审查阶段：展示计划 → 人工批准/拒绝/修改 → 确保任务编排合理
  3. 执行阶段：程序化创建任务并分发（无 LLM 参与，避免误操作）
  4. 监控阶段：事件循环监听 Worker 汇报 → 自动标记完成 → 解锁下一批
"""

import sys
import time
import json
from .agent_base import BaseAgent, LLM_AVAILABLE
from .shared_context import TASK_MGR, BUS


class LeadAgent(BaseAgent):
    """主控 Agent —— 需求分析 + 任务编排 + 进度监控"""

    def __init__(self):
        super().__init__(name="lead", role="lead", max_rounds=6)
        self._role_to_id: dict = {}      # role → task_id
        self._dispatched: set = set()    # 已分发的 task_id
        self._all_done_reported = False
        self._submitted_plan: dict = None  # LLM 提交的待审查计划

    def _setup_tools(self):
        """注册 Lead 专属管理 tools。
        注意：create_and_link_tasks / dispatch_ready_tasks 不暴露给 LLM，
        它们在人工审查通过后由代码直接调用。"""

        # ── 规划阶段：LLM 可用 ──
        self.register_tool(
            name="submit_plan",
            description="将分析好的任务计划提交给用户审查。在完成需求分析、任务拆分和依赖规划后调用此工具。",
            input_schema={
                "type": "object",
                "properties": {
                    "plan_json": {"type": "string", "description": "任务计划 JSON 字符串。格式：{\"project_name\":\"...\",\"tasks\":[{\"role\":\"backend\",\"subject\":\"...\",\"description\":\"...\",\"depends_on\":[]},...]}"},
                },
                "required": ["plan_json"],
            },
            handler=self._handle_submit_plan,
        )

        # ── 监控阶段：事件循环使用的操作型工具（保留 handler，不依赖 LLM）──
        self._handlers["check_all_tasks"] = self._handle_check_all_tasks
        self._handlers["mark_task_done"] = self._handle_mark_task_done

        # 执行阶段程序化调用（不注册为 LLM 工具）
        self._handlers["create_and_link_tasks"] = self._handle_create_and_link_tasks
        self._handlers["dispatch_ready_tasks"] = self._handle_dispatch_ready_tasks

    def get_system_prompt(self) -> str:
        # 注意：这里不能用 f-string，因为下面 JSON 示例中的 { 会被误解析为表达式
        return """你是 Lead Agent，项目主管。负责分析需求、编排任务、监控进度。

## 可用的团队成员（role）
- backend：Python Flask 后端开发，产出 api_spec.json + app.py
- frontend：HTML/CSS/JS 前端开发，产出 index.html
- test：Python unittest 测试，产出 tests/test_api.py
- devops：文档工程师，产出 README.md

## 团队协作的依赖规则
- backend 设计 API 契约，其他成员需要先拿到 API 规范才能工作
- 因此 frontend 和 test 必须依赖 backend
- devops 需要看到完整的项目产物，所以依赖 frontend + test 都完成

## 你的自主决策权
你有权根据实际情况自主决定工作流程。当需求明确、技术方案无争议时，直接执行即可。
只有在以下情况才考虑使用 ask_user：
- 需求描述模糊、有歧义，你无法确定用户意图
- 技术选型存在多种合理方案，需要用户偏好来决定
- 任务拆分方案涉及关键取舍，你不确定用户的优先级
不要事无巨细都问，简单问题请自行判断。

## submit_plan 的 JSON 格式示例（你只需分析并提交计划，不要自己创建任务）
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
depends_on 包含依赖的 role 名称（如 "backend"），第一个任务通常填 []。

## 你的工作流程
1. 分析需求：判断项目类型、需要哪些角色、任务的依赖关系
2. 如有不确定的关键决策，使用 ask_user 工具向用户确认
3. 调用 submit_plan 提交任务计划 → 等待人工审查（审查通过后系统会自动创建任务并分发）
4. 调用 finish_task 结束本次分析

## 任务 description 撰写要求
- backend：列出具体 API 端点：path、HTTP method、request/response 字段
- frontend：API_BASE 用 'http://localhost:5000/api'（绝对地址）、需读 api_spec.json 了解接口
- test：需读 api_spec.json、覆盖正常+边界场景
- 描述要具体，不要写"实现所有 API"这种空泛内容

## 工具使用注意
- 你只能使用 ask_user、submit_plan、finish_task、read_inbox 这些工具
- 不要试图直接创建任务或分发任务——这些会在人工审查通过后由系统自动完成
- submit_plan 后应调用 finish_task，不要轮询等待"""

    # ── Tool Handlers（纯操作型，不调 LLM）──

    def _handle_create_and_link_tasks(self, analysis_json: str) -> str:
        """根据分析结果批量创建任务并设置依赖"""
        try:
            analysis = json.loads(analysis_json)
        except json.JSONDecodeError as e:
            return f"[FAIL] JSON 解析失败: {e}"

        project_name = analysis.get("project_name", "Untitled")
        TASK_MGR.set_project(project_name, "")

        self._role_to_id = {}
        lines = [f"[DIR] 项目: {project_name}", ""]

        for t in analysis["tasks"]:
            task = TASK_MGR.create(
                subject=t["subject"],
                description=t["description"],
                role=t["role"],
                blocked_by=[],
            )
            self._role_to_id[t["role"]] = task["id"]
            lines.append(f"  [TASK] Task #{task['id']}: [{t['role']}] {t['subject']}")

        for t in analysis["tasks"]:
            tid = self._role_to_id[t["role"]]
            blocked_ids = [self._role_to_id[d] for d in t["depends_on"] if d in self._role_to_id]
            if blocked_ids:
                TASK_MGR.update(tid, add_blocked_by=blocked_ids)
                deps = ", ".join(f"#{bid}" for bid in blocked_ids)
                lines.append(f"    ↳ Task #{tid} 依赖: {deps}")

        self._dispatched.clear()
        self._all_done_reported = False
        lines.append(f"\n[OK] 共创建 {len(analysis['tasks'])} 个任务")
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
                dispatched.append(f"  [SEND] Task #{tid} → {role}: {task['subject']}")

        if not dispatched:
            if TASK_MGR.all_completed() and not self._all_done_reported:
                self._all_done_reported = True
                return "[DONE] 所有任务已完成！\n" + TASK_MGR.list_all()
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
                print(f"  [OK] Task #{tid} ({worker_name}) 完成!")
                return f"[OK] Task #{tid} ({worker_name}) 已标记完成。现在可以调用 dispatch_ready_tasks 检查是否有新任务解锁。"

        return f"[WARN] 未找到 {worker_name} 的 in_progress 任务"

    def _handle_submit_plan(self, plan_json: str) -> str:
        """LLM 提交任务计划，存储等待人工审查"""
        try:
            plan = json.loads(plan_json)
        except json.JSONDecodeError as e:
            return f"[FAIL] 计划 JSON 解析失败: {e}。请修正格式后重试。"

        required = ["project_name", "tasks"]
        for k in required:
            if k not in plan:
                return f"[FAIL] 计划缺少必要字段: {k}。请补充后重试。"

        self._submitted_plan = plan
        tasks_count = len(plan["tasks"])
        roles = [t["role"] for t in plan["tasks"]]
        return (
            f"[OK] 计划已提交，共 {tasks_count} 个任务，涉及角色: {', '.join(roles)}。"
            f"请调用 finish_task 等待人工审查结果。"
        )

    # ── 主循环（分析阶段用 ReAct，监控阶段用事件循环）──

    def run(self, poll_forever: bool = True):
        """Lead 专属主循环：交互式输入 → ReAct 分析 → 人工审查 → 分发 → 事件循环监控 → 重新提示"""
        print("=" * 70)
        print("[LEAD] Lead Agent v5.0 — 三阶段流程 (规划 → 审查 → 执行)")
        print("=" * 70)

        while True:  # ← 外层：每个项目需求循环一次
            print("\n[TIP] 提示: 可直接输入需求，或等待外部消息")
            print("   (输入 'exit' 或 'quit' 退出)\n")

            try:
                user_input = input("[INPUT] 请输入项目需求（直接回车则等待外部消息）: ").strip()
            except (EOFError, KeyboardInterrupt):
                user_input = ""

            if user_input.lower() in ("exit", "quit"):
                print("\n[BYE] Lead Agent 停止\n")
                return

            if user_input:
                self._process_new_requirement(user_input)
            else:
                print("\n[WAIT] 等待外部需求输入...\n")

            # ── 内层事件循环：监控 Worker 汇报 ──
            project_done = False
            while not project_done:
                time.sleep(2)
                inbox = BUS.read_inbox("lead")
                for msg in inbox:
                    sender = msg.get("from", "unknown")
                    msg_type = msg.get("type", "")
                    content = msg.get("content", "")

                    print(f"\n[RECV] 来自 {sender} [{msg_type}]: {content[:120]}")

                    if msg_type == "requirement" or (sender == "system" and "requirement:" in content.lower()):
                        req = content.replace("requirement:", "").strip()
                        self._process_new_requirement(req)

                    elif sender in ("backend", "frontend", "test", "devops"):
                        did = self._handle_mark_task_done(sender, content)
                        print(did)
                        disp = self._handle_dispatch_ready_tasks()
                        print(disp)
                        if "所有任务已完成" in disp:
                            TASK_MGR.set_project_status("completed")
                            print("\n" + "=" * 70)
                            print("[DONE] 项目所有任务已完成！输出在 .project/ 目录")
                            print("[FILE] project.json 状态已更新为 'completed'")
                            print("=" * 70)
                            if not poll_forever:
                                return
                            project_done = True
                            break  # 跳出 for 循环，退出内层 while

    # ── 三阶段需求处理：规划 → 人工审查 → 执行 ──

    def _planning_phase(self, requirement: str) -> dict | None:
        """Phase 1: LLM 分析需求，输出任务计划（不创建任务）"""
        self._submitted_plan = None

        prompt = f"""收到新需求，请分析并提交任务计划：

<requirement>
{requirement}
</requirement>

请按推荐流程执行：
1. 分析需求：需要哪些角色、哪些 API 端点、任务的依赖关系
2. 如有不确定的关键决策，使用 ask_user 向用户确认
3. 调用 submit_plan 提交完整的任务计划
4. 调用 finish_task 结束"""

        try:
            self.react_loop(prompt)
        except Exception as e:
            print(f"\n[FAIL] [Lead] 需求分析失败: {e}")
            import traceback
            traceback.print_exc()
            return None

        if not self._submitted_plan:
            print("\n[WARN] [Lead] LLM 未提交计划（可能因无工具调用直接结束了）")
            return None

        return self._submitted_plan

    def _review_phase(self, plan: dict) -> bool:
        """Phase 2: 展示任务计划，等待人工审查"""
        project_name = plan.get("project_name", "未命名")
        tasks = plan.get("tasks", [])

        print()
        print("=" * 70)
        print(f"[TASK] 任务计划审查 — {project_name}")
        print("=" * 70)

        role_icons = {"backend": "[TOOL]", "frontend": "", "test": "", "devops": ""}

        for i, t in enumerate(tasks, 1):
            icon = role_icons.get(t["role"], "")
            deps = ", ".join(t.get("depends_on", [])) or "无"
            print(f"\n  {icon} 任务 {i}: [{t['role']}] {t['subject']}")
            print(f"      依赖: {deps}")
            desc = t.get("description", "")
            if desc:
                lines = desc.split("\n")[:4]
                for line in lines:
                    print(f"      {line[:100]}")

        print(f"\n{'─' * 70}")
        print(f"  共 {len(tasks)} 个任务，涉及角色: {', '.join(set(t['role'] for t in tasks))}")

        while True:
            print(f"\n{'─' * 70}")
            try:
                choice = input("[USER] 请审查计划 (y=批准执行 / n=拒绝 / m=修改需求描述后重试): ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                choice = "n"

            if choice == "y":
                print("\n[OK] 计划已批准，开始创建任务并分发...\n")
                return True
            elif choice == "n":
                print("\n[FAIL] 计划已拒绝\n")
                return False
            elif choice == "m":
                print()
                try:
                    feedback = input("[INPUT] 请输入修改意见或补充需求描述: ").strip()
                except (EOFError, KeyboardInterrupt):
                    feedback = ""
                if feedback:
                    plan["_feedback"] = feedback
                    print(f"\n[INPUT] 已记录反馈，将重新分析...\n")
                return False
            else:
                print("[WARN] 无效输入，请输入 y / n / m")

    def _execution_phase(self, plan: dict):
        """Phase 3: 程序化创建任务并分发（无 LLM 参与）"""
        project_name = plan.get("project_name", "Untitled")
        TASK_MGR.set_project(project_name, "")

        self._role_to_id = {}
        tasks = plan["tasks"]
        created = []

        # 先创建所有任务
        for t in tasks:
            task = TASK_MGR.create(
                subject=t["subject"],
                description=t.get("description", ""),
                role=t["role"],
                blocked_by=[],
            )
            self._role_to_id[t["role"]] = task["id"]
            created.append(task)
            print(f"  [TASK] Task #{task['id']}: [{t['role']}] {t['subject']}")

        # 再设置依赖关系
        for t in tasks:
            tid = self._role_to_id[t["role"]]
            blocked_ids = [
                self._role_to_id[d]
                for d in t.get("depends_on", [])
                if d in self._role_to_id
            ]
            if blocked_ids:
                TASK_MGR.update(tid, add_blocked_by=blocked_ids)
                deps = ", ".join(f"#{bid}" for bid in blocked_ids)
                print(f"    ↳ Task #{tid} 依赖: {deps}")

        self._dispatched.clear()
        self._all_done_reported = False

        print(f"\n[OK] 共创建 {len(tasks)} 个任务\n")

        # 分发就绪任务
        disp_result = self._handle_dispatch_ready_tasks()
        print(disp_result)

    def _process_new_requirement(self, requirement: str):
        """处理新需求：Phase1 LLM规划 → Phase2 人工审查 → Phase3 程序化执行"""

        # Phase 1: LLM 分析并提交计划
        plan = self._planning_phase(requirement)
        if plan is None:
            print("\n[WAIT] 计划生成失败，继续等待下一个需求...\n")
            return

        # Phase 2: 人工审查
        approved = self._review_phase(plan)
        if not approved:
            # 检查是否有修改反馈，有则带上反馈重新规划
            feedback = plan.get("_feedback", "")
            if feedback:
                new_req = f"原需求:\n{requirement}\n\n用户修改意见:\n{feedback}"
                print("[RETRY] 根据用户反馈重新规划...\n")
                self._process_new_requirement(new_req)
                return
            print("\n[WAIT] 计划被拒绝，继续等待下一个需求...\n")
            return

        # Phase 3: 程序化执行
        self._execution_phase(plan)
        print("\n[WAIT] 等待 Agent 完成工作...\n")


def main():
    agent = LeadAgent()
    try:
        agent.run()
    except KeyboardInterrupt:
        print("\n\n[BYE] Lead Agent 停止")
        sys.exit(0)


if __name__ == "__main__":
    main()