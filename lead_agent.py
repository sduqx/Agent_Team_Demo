#!/usr/bin/env python3
"""
Lead Agent v2.0 - 主控Agent，任务依赖图驱动
核心改进:
  1. 使用 LLM 分析需求 → 生成带依赖关系的任务图
  2. 按依赖顺序分配: Backend → Frontend/Test → DevOps
  3. 通过 APISpecStore 确保 API 一致性
  4. 监控全流程，依赖自动解锁
"""

import sys
import time
import json
from pathlib import Path
from shared_context import (
    TASK_MGR, BUS, API_SPEC,
    send_message, read_messages, extract_text_from_response
)

try:
    from anthropic import Anthropic
    from dotenv import load_dotenv
    import os

    load_dotenv(override=True)
    client = Anthropic(base_url=os.getenv("ANTHROPIC_BASE_URL"))
    MODEL = os.environ["MODEL_ID"]
except:
    print("⚠️ Anthropic 库未安装或未配置")
    client = None
    MODEL = None

PROJECT_DIR = Path.cwd() / ".project"
PROJECT_DIR.mkdir(exist_ok=True)


def analyze_requirement_with_llm(requirement: str) -> dict:
    """
    使用 LLM 分析需求，生成带依赖关系的任务分配。
    返回格式:
    {
        "project_name": "项目名称",
        "tasks": [
            {"role": "backend", "subject": "...", "description": "...", "depends_on": []},
            {"role": "frontend", "subject": "...", "description": "...", "depends_on": ["backend"]},
            {"role": "test", "subject": "...", "description": "...", "depends_on": ["backend"]},
            {"role": "devops", "subject": "...", "description": "...", "depends_on": ["frontend", "test"]},
        ]
    }
    """
    if client is None:
        print("⚠️ LLM 不可用，使用默认分析")
        return _default_analysis(requirement)

    prompt = f"""
你是一个项目主管Agent。用户提出了这个需求：
{requirement}

请深入分析需求，并为 Team 创建带依赖关系的任务计划。任务必须遵守严格的依赖顺序：

**依赖规则：**
- backend 最先执行（无依赖），需要定义完整的 API 接口规范（包括端点、请求/响应格式）
- frontend 依赖 backend（需要知道 API 端点才能对接）
- test 依赖 backend（需要知道 API 端点才能编写测试）
- devops 最后执行（依赖 frontend 和 test 都完成）

**返回JSON格式：**
{{
  "project_name": "项目名称",
  "tasks": [
    {{"role": "backend", "subject": "创建后端API", "description": "详细的API实现描述...", "depends_on": []}},
    {{"role": "frontend", "subject": "创建前端界面", "description": "详细的前端需求描述...", "depends_on": ["backend"]}},
    {{"role": "test", "subject": "编写API测试", "description": "详细的测试需求描述...", "depends_on": ["backend"]}},
    {{"role": "devops", "subject": "创建部署配置", "description": "详细的DevOps需求...", "depends_on": ["frontend", "test"]}}
  ]
}}

注意:
- description 中要包含足够的技术细节，让 Agent 可以独立工作
- backend 的 description 中请 明确列出所有 API 端点和数据格式
- frontend 的 description 中说明需要对接后端 API
- 只返回JSON，不要其他文字
"""

    try:
        response = client.messages.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=3000
        )
        result_text = extract_text_from_response(response)
        start = result_text.find('{')
        end = result_text.rfind('}') + 1
        if start >= 0 and end > start:
            json_str = result_text[start:end]
            return json.loads(json_str)
        else:
            print(f"⚠️ 无法找到JSON，使用默认分析")
            return _default_analysis(requirement)
    except json.JSONDecodeError as e:
        print(f"❌ JSON 解析失败: {e}")
        return _default_analysis(requirement)
    except Exception as e:
        print(f"❌ LLM 分析失败: {e}")
        import traceback
        traceback.print_exc()
        return _default_analysis(requirement)


def _default_analysis(requirement: str) -> dict:
    """默认任务分析（LLM 不可用时的回退）"""
    return {
        "project_name": requirement[:40],
        "tasks": [
            {
                "role": "backend",
                "subject": "创建Flask REST API",
                "description": f"使用Flask创建REST API: {requirement}\n\n要求:\n- 数据模型定义清晰\n- 包含 CRUD 端点\n- 返回结构化 JSON\n- 启用 CORS",
                "depends_on": []
            },
            {
                "role": "frontend",
                "subject": "创建前端界面",
                "description": f"创建单页面HTML应用: {requirement}\n\n要求:\n- 美观的 UI 设计\n- 对接后端 API（参考 API spec）\n- 响应式布局\n- 错误处理和加载状态",
                "depends_on": ["backend"]
            },
            {
                "role": "test",
                "subject": "编写API测试",
                "description": f"为后端API编写测试: {requirement}\n\n要求:\n- 使用pytest\n- 覆盖所有端点\n- 包含正常和异常场景",
                "depends_on": ["backend"]
            },
            {
                "role": "devops",
                "subject": "创建部署配置",
                "description": f"创建部署配置: {requirement}\n\n要求:\n- Dockerfile\n- docker-compose.yml\n- README.md 完整文档",
                "depends_on": ["frontend", "test"]
            },
        ]
    }


def create_task_graph(analysis: dict) -> dict:
    """
    将分析结果转换为带依赖的任务图。
    返回 role -> task_id 的映射。
    """
    role_to_id = {}

    # 第一遍：创建所有任务（先记录ID映射）
    for t in analysis["tasks"]:
        task = TASK_MGR.create(
            subject=t["subject"],
            description=t["description"],
            role=t["role"],
            blocked_by=[]  # 先不设依赖，等所有 ID 确定后再设
        )
        role_to_id[t["role"]] = task["id"]
        print(f"  📋 创建 Task #{task['id']}: [{t['role']}] {t['subject']}")

    # 第二遍：设置依赖关系
    for t in analysis["tasks"]:
        tid = role_to_id[t["role"]]
        blocked_ids = [role_to_id[dep] for dep in t["depends_on"] if dep in role_to_id]
        if blocked_ids:
            TASK_MGR.update(tid, add_blocked_by=blocked_ids)
            deps = [f"#{bid}" for bid in blocked_ids]
            print(f"    ↳ Task #{tid} 依赖: {', '.join(deps)}")

    return role_to_id


def dispatch_ready_tasks(role_to_id: dict, dispatched: set):
    """
    检查并分配就绪的任务给对应 Agent。
    返回新分配的任务列表。
    """
    newly_dispatched = []

    for role, tid in role_to_id.items():
        if tid in dispatched:
            continue
        if TASK_MGR.is_ready(tid):
            task = TASK_MGR.get(tid)
            # 发送任务给对应 Agent
            BUS.send(
                sender="lead",
                to=role,
                content=task["description"],
                msg_type="task",
                extra={"task_id": tid, "subject": task["subject"]}
            )
            TASK_MGR.claim(tid, role)
            dispatched.add(tid)
            newly_dispatched.append((role, tid, task["subject"]))
            print(f"  🚀 分配 Task #{tid} → {role}: {task['subject']}")

    return newly_dispatched


def main():
    print("=" * 70)
    print("👔 Lead Agent v2.0 - 任务依赖图驱动")
    print("=" * 70)
    print("\n等待需求输入...\n")

    role_to_id = {}
    dispatched = set()
    iteration = 0
    all_completed_reported = False

    while True:
        iteration += 1

        # 1. 检查收件箱
        inbox = BUS.read_inbox("lead")
        for msg in inbox:
            sender = msg.get("from", "unknown")
            msg_type = msg.get("type", "")
            content = msg.get("content", "")

            print(f"\n📬 收到来自 {sender} 的消息 [{msg_type}]:")
            print(f"   {content[:120]}...")

            # 收到需求 → LLM 分析 → 创建任务图
            if sender == "system" and "requirement:" in content.lower():
                requirement = content.replace("requirement:", "").strip()
                project_name = requirement[:50]

                print(f"\n🤖 Lead Agent 使用 LLM 分析需求...")
                analysis = analyze_requirement_with_llm(requirement)
                project_name = analysis.get("project_name", project_name)

                TASK_MGR.set_project(project_name, requirement)
                print(f"\n📁 项目: {project_name}")

                print(f"\n📊 创建任务依赖图:")
                role_to_id = create_task_graph(analysis)

                print(f"\n📋 当前任务状态:")
                print(TASK_MGR.list_all())
                print()

                # 立即分配第一批就绪任务（backend）
                dispatch_ready_tasks(role_to_id, dispatched)

            # 子 Agent 完成汇报
            elif sender in ("backend", "frontend", "test", "devops"):
                # 更新任务状态
                for tid in dispatched:
                    task = TASK_MGR.get(tid)
                    if task.get("owner") == sender and task.get("status") == "in_progress":
                        TASK_MGR.update(tid, status="completed", output=content)
                        print(f"  ✅ Task #{tid} ({sender}) 完成!")
                        break

                # 分配新解锁的任务
                new_tasks = dispatch_ready_tasks(role_to_id, dispatched)
                if new_tasks:
                    print(f"  🔓 依赖解锁，新任务可分配!")

        # 2. 定期打印状态
        if iteration % 5 == 0:
            print("\n" + "─" * 50)
            print("📊 当前任务状态:")
            print(TASK_MGR.list_all())
            print("─" * 50 + "\n")

            if not all_completed_reported and TASK_MGR.all_completed():
                print("=" * 70)
                print("🎉 所有任务已完成！")
                print(f"📁 输出文件位于: .project/ 目录")
                print("📊 任务详情:")
                print(TASK_MGR.list_all())
                print("=" * 70)
                all_completed_reported = True

        time.sleep(2)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Lead Agent 停止")
        sys.exit(0)
