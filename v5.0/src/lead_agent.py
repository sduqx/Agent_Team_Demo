#!/usr/bin/env python3
"""
Lead Agent v2.0 — 动态技术栈 + 动态团队组建 + Worker 自动孵化
══════════════════════════════════════════════════════════════
核心改进（相比 v1.0）：
  1. 技术栈不固定：LLM 根据需求决定用 React/Vue/Node.js/Go/Java/... 任意技术
  2. 团队不固定：LLM 根据项目需要决定需要哪些角色（mobile/data/design/...）
  3. 自动孵化 Worker：计划批准后，自动为每个角色启动一个通用 Worker 进程
  4. 保持三阶段流程：规划 → 人工审查 → 执行

流程：
  用户输入 "做一个 Flutter 跨平台 App" 
  → Lead 分析：需要 flutter（移动端）、firebase（后端）、design（UI设计）
  → 用户批准
  → Lead 自动启动 3 个 Worker 进程（各自携带动态 System Prompt）
  → Worker 协作完成项目
"""

import sys
import time
import json
import re
import subprocess
from pathlib import Path
from .agent_base import BaseAgent, LLM_AVAILABLE
from .shared_context import TASK_MGR, BUS


class LeadAgent(BaseAgent):
    """Lead Agent v2.0 — 动态技术选型 + 动态团队组建 + Worker 孵化"""

    def __init__(self, project_dir: Path = None):
        super().__init__(name="lead", role="lead", max_rounds=50,
                         project_dir=project_dir)
        self._tid_to_role: dict[int, str] = {}      # task_id → role
        self._role_to_tids: dict[str, list[int]] = {} # role → [task_ids]
        self._dispatched: set = set()      # 已分发的 task_id
        self._all_done_reported = False
        self._submitted_plan: dict = None  # LLM 提交的待审查计划
        self._current_project_dir = project_dir or Path.cwd() / ".project"
        self._worker_processes: list = []  # 跟踪启动的 worker 子进程
        self._known_roles: set = set()     # 当前项目涉及的角色集合

    def _setup_tools(self):
        """注册 Lead 专属管理 tools。只暴露 submit_plan + ask_user + finish_task 给 LLM。"""

        self.register_tool(
            name="submit_plan",
            description="""将分析好的任务计划提交给用户审查。

在完成以下分析后调用此工具：
1. 分析用户需求，确定项目的技术栈（前后端框架、数据库、语言等）
2. 确定需要哪些开发角色来协作完成
3. 将项目拆分为任务，规划任务之间的依赖关系""",
            input_schema={
                "type": "object",
                "properties": {
                    "plan_json": {
                        "type": "string",
                        "description": (
                            "任务计划 JSON 字符串。格式：\n"
                            '{"project_name":"项目名称",'
                            '"tech_stack":{"frontend":"React + TypeScript","backend":"Node.js Express + PostgreSQL",'
                            '"reason":"选型理由..."},'
                            '"tasks":[{"role":"backend","subject":"...","description":"...(写明产出文件和功能)...","depends_on":[]},'
                            '{"role":"frontend","subject":"...","description":"...","depends_on":["backend"]}]}\n'
                            "depends_on 填写依赖的 role 名称列表。"
                            "tech_stack 写明你推荐的具体技术栈，reason 简短说明理由。"
                            "role 名称用英文，如 backend、frontend、mobile、test、data、devops、design、ai 等，"
                            "根据项目实际需要决定，不必全部使用。"
                        )
                    },
                },
                "required": ["plan_json"],
            },
            handler=self._handle_submit_plan,
        )

        # 监控阶段内部工具（不暴露给 LLM）
        self._handlers["check_all_tasks"] = self._handle_check_all_tasks
        self._handlers["mark_task_done"] = self._handle_mark_task_done
        self._handlers["create_and_link_tasks"] = self._handle_create_and_link_tasks
        self._handlers["dispatch_ready_tasks"] = self._handle_dispatch_ready_tasks

    # ── System Prompt：核心创新点 ──

    def get_system_prompt(self) -> str:
        return """你是 Lead Agent v2.0，项目主管。你的核心能力是：根据需求动态决定技术栈和团队构成。

## 你的自主决策权

### 1. 技术栈选择（完全自主）
你不需要遵循任何预设的技术栈。根据项目需求性质自主选择最合适的技术：

- **前端**：React、Vue、Angular、Svelte、Solid、原生 HTML/CSS/JS、Flutter（移动端）、React Native、微信小程序
- **后端**：Python（Flask/FastAPI/Django）、Node.js（Express/Koa/NestJS）、Go（Gin/Echo）、Java（Spring Boot）、Rust（Actix）
- **数据库**：SQLite、PostgreSQL、MySQL、MongoDB、Firebase、Supabase
- **其他**：Redis、RabbitMQ、Docker、K8s、Nginx 等

选择原则：小型项目用轻量方案，数据密集型用关系型DB，实时应用考虑 WebSocket，
移动端用跨平台框架。在 plan 的 tech_stack.reason 中简要说明选型理由。

### 2. 团队组建（按需决定）
根据项目复杂度决定需要哪些角色，而不是每次都全部派出。可选角色示例：

| 角色 | 适用场景 |
|------|----------|
| backend | 需要服务端 API |
| frontend | 需要 Web 前端界面 |
| mobile | 需要移动端 App |
| test | 需要自动化测试 |
| devops | 需要部署/文档/Docker |
| data | 需要数据建模/ETL |
| design | 需要 UI/UX 设计稿 |
| security | 需要安全审计 |
| ai | 需要 AI/ML 模块 |

简单的 CRUD 应用只需 backend + frontend（+ test）；
复杂的全栈项目可能需要 4-5 个角色；
纯后端 API 项目可能只需 backend + test + devops。

### 3. 任务拆分原则
- 每个角色至少一个任务，复杂角色可拆分多个
- 后端先产出接口契约（api_spec 或 proto 文件），前端/移动端/测试基于契约开发
- 文档/部署任务应排到最后
- depends_on 填写 role 名称字符串列表，无依赖填 []

## submit_plan JSON 示例

```json
{
  "project_name": "跨平台任务管理 App",
  "tech_stack": {
    "frontend": "Flutter + Dart",
    "backend": "Node.js Express + SQLite",
    "reason": "Flutter 一套代码覆盖 iOS/Android；Express 轻量快速适合任务管理类应用，SQLite 零配置适合原型"
  },
  "tasks": [
    {"role": "backend", "subject": "设计 REST API 并生成 Express 后端", "description": "产出文件: api_spec.json（API契约）+ server.js（Express入口）+ db.js（SQLite初始化）+ package.json。API包含：POST /api/tasks（创建任务，字段: title/description/status）、GET /api/tasks（列表查询，支持 ?status= 过滤）、PUT /api/tasks/:id（更新）、DELETE /api/tasks/:id（删除）。所有响应格式: {success: bool, data/error}。需包含 CORS。", "depends_on": []},
    {"role": "frontend", "subject": "实现 Flutter 任务管理界面", "description": "产出文件: lib/main.dart + lib/screens/home_page.dart + lib/models/task.dart + lib/services/api_service.dart + pubspec.yaml。基于 api_spec.json 实现完整 CRUD 界面，包括任务列表（支持状态过滤）、新建/编辑弹窗、删除确认。API_BASE 使用 http://localhost:3000/api。", "depends_on": ["backend"]},
    {"role": "test", "subject": "编写后端 API 自动化测试", "description": "产出文件: tests/test_api.py。用 Python unittest + requests 测试所有 CRUD 端点，覆盖正常场景和边界情况。需读取 api_spec.json 确保测试对齐契约。", "depends_on": ["backend"]},
    {"role": "devops", "subject": "输出项目文档和启动脚本", "description": "产出文件: README.md + run.sh + run.bat。README包含项目概述、技术栈说明、API文档（基于api_spec.json）、启动步骤。脚本一键安装依赖并启动所有服务。", "depends_on": ["frontend", "test"]}
  ]
}
```

## 你的工作流程
1. 分析需求：判断项目类型 → 选择技术栈 → 确定需要的角色 → 拆分任务和依赖
2. 遇到不确定的决策（如用户没指定平台、技术偏好不明确），使用 ask_user 向用户确认
3. 调用 submit_plan 提交完整的任务计划 → 等待审查
4. 审查通过后，调用 finish_task 结束分析（系统会自动创建任务、孵化 Worker、分发任务）

## 约束
- 你只能使用 ask_user、submit_plan、finish_task、read_inbox 这些工具
- 不需要直接创建任务或分发任务——审查通过后系统自动处理
- **Task description 必须用"产出文件: xxx.py, yyy.js"格式明确列出所有预期产出文件**，系统会自动验证这些文件是否被创建
- 写清楚 Worker 应该产出什么文件，前端/移动端要明确 API_BASE 地址
- 每个 task 的 description 越具体越好——它就是发给 Worker 的任务书"""

    # ── Tool Handlers（纯操作型，不调 LLM）──

    def _handle_submit_plan(self, plan_json: str) -> str:
        """LLM 提交任务计划，存储等待人工审查"""
        try:
            plan = json.loads(plan_json)
        except json.JSONDecodeError as e:
            return f"[FAIL] 计划 JSON 解析失败: {e}。请修正格式后重试。"

        # 验证必要字段
        if "project_name" not in plan:
            return "[FAIL] 计划缺少 project_name 字段"
        if "tasks" not in plan or not plan["tasks"]:
            return "[FAIL] 计划缺少 tasks 字段或任务列表为空"
        if "tech_stack" not in plan:
            return "[FAIL] v2.0 要求计划包含 tech_stack 字段，请指定推荐的技术栈"

        for i, t in enumerate(plan["tasks"]):
            for field in ["role", "subject", "description"]:
                if field not in t:
                    return f"[FAIL] 任务 #{i+1} 缺少 {field} 字段"

        self._submitted_plan = plan
        tasks_count = len(plan["tasks"])
        roles = list(set(t["role"] for t in plan["tasks"]))
        tech = plan.get("tech_stack", {})
        tech_desc = tech.get("reason", f"{tech.get('frontend','?')} + {tech.get('backend','?')}")

        return (
            f"[OK] 计划已提交！\n"
            f"  项目: {plan['project_name']}\n"
            f"  技术栈: {tech_desc}\n"
            f"  任务数: {tasks_count}\n"
            f"  团队角色: {', '.join(roles)}\n"
            f"请调用 finish_task，等待人工审查。"
        )

    def _handle_create_and_link_tasks(self, analysis_json: str) -> str:
        """根据分析结果批量创建任务并设置依赖（支持同一 role 多个任务）"""
        try:
            analysis = json.loads(analysis_json)
        except json.JSONDecodeError as e:
            return f"[FAIL] JSON 解析失败: {e}"

        project_name = analysis.get("project_name", "Untitled")
        TASK_MGR.set_project(project_name, "")

        self._tid_to_role = {}
        self._role_to_tids = {}
        lines = [f"[DIR] 项目: {project_name}", ""]

        # 先创建所有任务，记录 task_id → role 映射
        created = []  # [(task_id, original_task_dict), ...]
        for t in analysis["tasks"]:
            expected_files = self._parse_expected_files(t.get("description", ""))
            task = TASK_MGR.create(
                subject=t["subject"],
                description=t["description"],
                role=t["role"],
                blocked_by=[],
                expected_files=expected_files,
            )
            tid = task["id"]
            role = t["role"]
            self._tid_to_role[tid] = role
            self._role_to_tids.setdefault(role, []).append(tid)
            created.append((tid, t))
            lines.append(f"  [TASK] Task #{tid}: [{role}] {t['subject']}")
            if expected_files:
                lines.append(f"    ↳ 预期产出: {', '.join(expected_files)}")


        # 再设置依赖关系（depends_on 填 role 名，取该 role 的第一个 task）
        for tid, t in created:
            blocked_ids = []
            for dep_role in t.get("depends_on", []):
                if dep_role in self._role_to_tids and self._role_to_tids[dep_role]:
                    # 依赖该 role 的第一个任务（按创建顺序）
                    blocked_ids.append(self._role_to_tids[dep_role][0])
            if blocked_ids:
                TASK_MGR.update(tid, add_blocked_by=blocked_ids)
                deps = ", ".join(f"#{bid}" for bid in blocked_ids)
                lines.append(f"    ↳ Task #{tid} 依赖: {deps}")

        self._dispatched.clear()
        self._all_done_reported = False
        lines.append(f"\n[OK] 共创建 {len(analysis['tasks'])} 个任务")
        return "\n".join(lines)

    def _handle_dispatch_ready_tasks(self) -> str:
        """扫描就绪任务并分派给对应 Worker（支持同一 role 多个任务）"""
        dispatched = []
        for tid, role in self._tid_to_role.items():
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
            return "当前没有新的就绪任务可分配。\n" + TASK_MGR.list_all()

        return "\n".join(dispatched) + "\n\n" + TASK_MGR.list_all()

    def _handle_check_all_tasks(self) -> str:
        return TASK_MGR.list_all()

    def _handle_mark_task_done(self, worker_name: str, output: str = "") -> str:
        """标记 Worker 完成的任务（支持同一 role 多个任务），并自动验证产出。"""
        for tid in self._dispatched:
            task = TASK_MGR.get(tid)
            if self._tid_to_role.get(tid) == worker_name and task.get("status") == "in_progress":
                TASK_MGR.update(tid, status="completed", output=output)
                print(f"  [OK] Task #{tid} ({worker_name}) 完成!")

                # ═══ 自动验证产出文件 ═══
                verify_result = TASK_MGR.verify_task_output(tid, self._current_project_dir)
                if verify_result["detail"]:
                    print(f"  [VERIFY] Task #{tid} 产出验证:")
                    for line in verify_result["detail"].split("\n"):
                        print(f"    {line}")
                    if verify_result["pass"]:
                        print(f"  [VERIFY] 全部产出文件验证通过 ✅")
                    else:
                        print(f"  [WARN] 缺失 {len(verify_result['missing'])} 个产出文件 ⚠️")
                        # 不阻塞流程，但发出警告

                return f"[OK] Task #{tid} ({worker_name}) 已标记完成。"
        return f"[WARN] 未找到 {worker_name} 的 in_progress 任务"

    # ── Worker 孵化（v2.0 核心新功能）──

    def _spawn_workers(self, plan: dict):
        """
        根据计划孵化 Worker 进程。
        每个唯一的 role 启动一个 worker_agent.py 进程，传入角色和技术栈描述。
        """
        unique_roles = list(set(t["role"] for t in plan["tasks"]))
        tech_stack = plan.get("tech_stack", {})

        self._known_roles = set(unique_roles)
        self._worker_processes = []

        def _safe_arg(s: str) -> str:
            """给含有空格或特殊字符的参数加引号，避免 cmd 将其拆分为多个参数"""
            s = str(s)
            if any(c in s for c in (' ', '\t', '(', ')', '&', '^', '|', '<', '>', '~')):
                # Windows cmd 中需要双引号包裹含特殊字符的参数
                return f'"{s}"'
            return s

        for role in unique_roles:
            # 为该角色构建技术描述
            tech_desc = self._build_role_tech_desc(role, tech_stack)
            project_dir = str(self._current_project_dir.resolve())

            cmd_parts = [
                sys.executable,
                "-m", "src.worker_agent",
                "--name", role,
                "--tech", tech_desc,
                "--project-dir", project_dir,
            ]

            try:
                if sys.platform == "win32":
                    # Windows: 在新 cmd 窗口中启动，每个参数独立安全转义
                    cmd_str = " ".join(_safe_arg(a) for a in cmd_parts)
                    proc = subprocess.Popen(
                        f'start "Worker-{role}" cmd /k {cmd_str}',
                        shell=True
                    )
                else:
                    # Linux/macOS: 尝试在新终端中启动
                    proc = subprocess.Popen(
                        ["xterm", "-T", f"Worker-{role}", "-e"] + cmd_parts,
                    )
                self._worker_processes.append(proc)
                print(f"  [SPAWN] Worker '{role}' 已启动 → {project_dir}")
            except Exception as e:
                print(f"  [FAIL] 启动 Worker '{role}' 失败: {e}")
                print(f"  请手动运行: python -m src.worker_agent --name {role} --tech \"{tech_desc}\"")

        print(f"\n[OK] 共启动 {len(self._worker_processes)} 个 Worker 进程")
        # 等 Workers 就绪
        time.sleep(3)

    @staticmethod
    def _parse_expected_files(description: str) -> list:
        """从任务描述中提取预期产出文件名。
        支持格式: '产出文件: a.py + b.js + c/' 或 'path/to/file.ext'"""
        files = []
        # 模式1: "产出文件:" 后的文件列表
        m = re.search(r'产出文件[:：]\s*(.+?)(?:。|\n|$)', description)
        if m:
            raw = m.group(1)
            # 按 + / , 分隔
            parts = re.split(r'[+、，,]\s*', raw)
            for p in parts:
                p = p.strip().rstrip('。，,')
                if p and ('.' in p or '/' in p):  # 看起来像文件/目录路径
                    files.append(p)
        # 模式2: 描述中所有带扩展名的路径
        if not files:
            path_pattern = re.findall(r'[\w./-]+\.[a-zA-Z]{1,6}', description)
            for p in path_pattern:
                p = p.strip()
                if p not in files and not p.startswith('http'):
                    files.append(p)
        return files

    @staticmethod
    def _build_role_tech_desc(role: str, tech_stack: dict) -> str:
        """根据角色和技术栈构建 role description"""
        mapping = {
            "backend": f"后端开发工程师。技术栈: {tech_stack.get('backend', '自选语言和框架')}。"
                       f"产出服务器端代码、API 接口、数据库模型。优先输出 API 契约文档。",
            "frontend": f"前端开发工程师。技术栈: {tech_stack.get('frontend', '自选框架')}。"
                        f"产出 Web 前端界面代码，优先从 API 契约获取接口信息。",
            "mobile": f"移动端开发工程师。技术栈: {tech_stack.get('mobile', tech_stack.get('frontend', '自选跨平台框架'))}。"
                      f"产出移动端 App 代码，优先从 API 契约获取接口信息。",
            "test": "测试工程师。根据 API 契约编写自动化测试，覆盖正常和边界场景。确保测试可运行。",
            "devops": "DevOps/文档工程师。产出 README、启动脚本、部署配置。汇总项目产物。",
            "data": "数据工程师。产出数据模型设计、ETL 脚本、数据库 schema。",
            "design": "UI/UX 设计师。产出设计规范文档、样式指南、组件库说明。",
            "security": "安全工程师。产出安全审计报告、安全加固代码、认证授权模块。",
            "ai": "AI/ML 工程师。产出 ML 模型代码、推理服务、数据处理 pipeline。",
        }

        if role in mapping:
            return mapping[role]

        # 泛用描述
        frontend = tech_stack.get('frontend', '')
        backend = tech_stack.get('backend', '')
        reason = tech_stack.get('reason', '')
        return (f"角色: {role}。"
                f"{'前端: ' + frontend + '。' if frontend else ''}"
                f"{'后端: ' + backend + '。' if backend else ''}"
                f"{'说明: ' + reason if reason else ''}")

    # ── 三阶段需求处理 ──

    def _planning_phase(self, requirement: str) -> dict | None:
        """Phase 1: LLM 分析需求，输出任务计划"""
        self._submitted_plan = None

        prompt = f"""收到新需求，请分析并提交任务计划：

<requirement>
{requirement}
</requirement>

请按推荐流程：
1. 判断项目类型：Web应用？移动App？纯API？CLI工具？数据管道？
2. 选择合适的技术栈（前后端框架、数据库等），在 tech_stack 中说明
3. 确定需要哪些角色，拆分任务，设置依赖关系
4. 如有不确定的决策，使用 ask_user 向用户确认
5. 调用 submit_plan 提交计划
6. 调用 finish_task 结束"""

        try:
            self.react_loop(prompt)
        except Exception as e:
            print(f"\n[FAIL] [Lead] 需求分析失败: {e}")
            import traceback
            traceback.print_exc()
            return None

        if not self._submitted_plan:
            print("\n[WARN] [Lead] LLM 未提交计划")
            return None

        return self._submitted_plan

    def _review_phase(self, plan: dict) -> bool:
        """Phase 2: 展示计划，等待人工审查"""
        project_name = plan.get("project_name", "未命名")
        tasks = plan.get("tasks", [])
        tech_stack = plan.get("tech_stack", {})

        print()
        print("=" * 70)
        print(f"[PLAN] 项目计划审查 — {project_name}")
        print("=" * 70)

        # 显示技术栈
        print(f"\n  技术栈:")
        for k, v in tech_stack.items():
            if k != "reason":
                print(f"    {k}: {v}")
        if tech_stack.get("reason"):
            print(f"    选型理由: {tech_stack['reason']}")

        # 显示任务
        print(f"\n  任务编排（共 {len(tasks)} 个）:")
        role_icons = {"backend": "[SVR]", "frontend": "[WEB]", "mobile": "[APP]",
                       "test": "[TST]", "devops": "[OPS]", "data": "[DAT]",
                       "design": "[UI]", "security": "[SEC]", "ai": "[AI]"}

        for i, t in enumerate(tasks, 1):
            icon = role_icons.get(t["role"], "[...]")
            deps = ", ".join(t.get("depends_on", [])) or "无"
            print(f"\n  {icon} 任务 {i}: [{t['role']}] {t['subject']}")
            print(f"      依赖: {deps}")
            desc = t.get("description", "")
            if desc:
                for line in desc.split("\n")[:3]:
                    print(f"      {line[:100]}")

        print(f"\n{'─' * 70}")
        roles = list(set(t["role"] for t in tasks))
        print(f"  涉及角色: {', '.join(roles)}")

        while True:
            print(f"\n{'─' * 70}")
            try:
                choice = input("[USER] 请审查计划 (y=批准 / n=拒绝 / m=修改需求): ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                choice = "n"

            if choice == "y":
                print("\n[OK] 计划已批准，开始创建任务并孵化 Worker...\n")
                return True
            elif choice == "n":
                print("\n[FAIL] 计划已拒绝\n")
                return False
            elif choice == "m":
                try:
                    feedback = input("[INPUT] 请输入修改意见或补充需求: ").strip()
                except (EOFError, KeyboardInterrupt):
                    feedback = ""
                if feedback:
                    plan["_feedback"] = feedback
                    print(f"\n[INPUT] 已记录反馈，将重新分析...\n")
                return False
            else:
                print("[WARN] 无效输入，请输入 y / n / m")

    def _execution_phase(self, plan: dict):
        """Phase 3: 创建任务 + 孵化 Worker + 分发任务（支持同一 role 多个任务）"""
        project_name = plan.get("project_name", "Untitled")
        TASK_MGR.set_project(project_name, "")

        self._tid_to_role = {}
        self._role_to_tids = {}
        tasks = plan["tasks"]

        # 创建所有任务，记录 task_id → role 映射
        created = []  # [(task_id, original_task_dict), ...]
        for t in tasks:
            expected_files = self._parse_expected_files(t.get("description", ""))
            task = TASK_MGR.create(
                subject=t["subject"],
                description=t.get("description", ""),
                role=t["role"],
                blocked_by=[],
                expected_files=expected_files,
            )
            tid = task["id"]
            role = t["role"]
            self._tid_to_role[tid] = role
            self._role_to_tids.setdefault(role, []).append(tid)
            created.append((tid, t))
            print(f"  [TASK] Task #{tid}: [{role}] {t['subject']}")
            if expected_files:
                print(f"    ↳ 预期产出: {', '.join(expected_files)}")

        # 设置依赖关系（depends_on 填 role 名，取该 role 的第一个 task）
        for tid, t in created:
            blocked_ids = []
            for dep_role in t.get("depends_on", []):
                if dep_role in self._role_to_tids and self._role_to_tids[dep_role]:
                    blocked_ids.append(self._role_to_tids[dep_role][0])
            if blocked_ids:
                TASK_MGR.update(tid, add_blocked_by=blocked_ids)
                deps = ", ".join(f"#{bid}" for bid in blocked_ids)
                print(f"    ↳ Task #{tid} 依赖: {deps}")

        self._dispatched.clear()
        self._all_done_reported = False

        print(f"\n[OK] 共创建 {len(tasks)} 个任务\n")

        # ═══ v2.0 核心：自动孵化 Worker ═══
        self._spawn_workers(plan)

        # 分发就绪任务
        disp_result = self._handle_dispatch_ready_tasks()
        print(disp_result)

    def _process_new_requirement(self, requirement: str):
        """处理新需求：Planning → Review → Execution"""
        plan = self._planning_phase(requirement)
        if plan is None:
            print("\n[WAIT] 计划生成失败，等待下一个需求...\n")
            return

        approved = self._review_phase(plan)
        if not approved:
            feedback = plan.get("_feedback", "")
            if feedback:
                new_req = f"原需求:\n{requirement}\n\n用户修改意见:\n{feedback}"
                print("[RETRY] 根据用户反馈重新规划...\n")
                self._process_new_requirement(new_req)
                return
            print("\n[WAIT] 计划被拒绝，等待下一个需求...\n")
            return

        self._execution_phase(plan)
        print("\n[WAIT] Worker 正在工作中，监控任务进度...\n")

    # ── 主循环 ──

    def run(self, poll_forever: bool = True):
        """Lead 主循环：交互式输入 → 规划 → 审查 → 执行孵化 → 事件循环监控"""
        print("=" * 70)
        print("[LEAD] Lead Agent v2.0 — 动态技术栈 + 自动团队孵化")
        print("=" * 70)
        print("[INFO] 与 v1.0 的区别：")
        print("       1. 不再预设 Python+Flask 技术栈，由你输入需求后 LLM 自主决定")
        print("       2. 不再预设 4 个固定 Worker，LLM 按需组建团队")
        print("       3. 计划批准后自动孵化对应 Worker 进程")
        print("=" * 70)

        while True:
            print("\n[TIP] 输入项目需求，或输入 'exit' 退出")
            print("[TIP] 示例: '做一个 React + Go 的任务管理Web应用'")
            print("[TIP] 示例: '做一个 Flutter 跨平台日记App'")
            print("[TIP] 示例: '做一个纯后端的用户认证微服务'")
            print()

            try:
                user_input = input("[INPUT] 请输入项目需求: ").strip()
            except (EOFError, KeyboardInterrupt):
                user_input = ""

            if user_input.lower() in ("exit", "quit"):
                print("\n[BYE] Lead Agent 停止\n")
                return

            if user_input:
                self._process_new_requirement(user_input)

            # ── 事件循环：监控 Worker 汇报 ──
            project_done = False
            while not project_done:
                time.sleep(2)
                inbox = BUS.read_inbox("lead")
                for msg in inbox:
                    sender = msg.get("from", "unknown")
                    msg_type = msg.get("type", "")
                    content = msg.get("content", "")

                    print(f"\n[RECV] 来自 {sender} [{msg_type}]: {content[:120]}")

                    if msg_type == "requirement":
                        req = content.replace("requirement:", "").strip()
                        self._process_new_requirement(req)
                        project_done = True
                        break

                    elif sender in self._known_roles:
                        result = self._handle_mark_task_done(sender, content)
                        print(result)
                        disp = self._handle_dispatch_ready_tasks()
                        print(disp)
                        if "所有任务已完成" in disp:
                            TASK_MGR.set_project_status("completed")
                            print("\n" + "=" * 70)
                            print(f"[DONE] 项目所有任务已完成！")
                            print(f"[DIR] 产物目录: {self._current_project_dir}")
                            print("=" * 70)
                            if not poll_forever:
                                return
                            project_done = True
                            break


def main():
    agent = LeadAgent()
    try:
        agent.run()
    except KeyboardInterrupt:
        print("\n\n[BYE] Lead Agent 停止")
        sys.exit(0)


if __name__ == "__main__":
    main()
