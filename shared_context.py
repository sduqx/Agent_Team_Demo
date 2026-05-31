"""
共享上下文模块 v2.0 - 所有Agent共享的全局状态
新增: 任务依赖管理 + 增强消息总线 + API spec 传递
"""

import json
import re
import threading
import time
from pathlib import Path
from typing import Dict, Any, List, Optional

# ============================================================
# 工具函数
# ============================================================

def extract_text_from_response(response) -> str:
    """从LLM响应中提取文本内容（兼容 ThinkingBlock）"""
    text_parts = []
    if hasattr(response.content, '__iter__'):
        for block in response.content:
            if hasattr(block, 'type') and block.type == 'thinking':
                continue
            if hasattr(block, 'text'):
                text_parts.append(block.text)
    else:
        return str(response.content)
    return "".join(text_parts)


# ============================================================
# 目录结构
# ============================================================

TEAM_DIR = Path.cwd() / ".team"
SHARED_DIR = TEAM_DIR / "shared"
INBOX_DIR = TEAM_DIR / "inbox"
TASKS_DIR = TEAM_DIR / "tasks"

for d in [TEAM_DIR, SHARED_DIR, INBOX_DIR, TASKS_DIR]:
    d.mkdir(parents=True, exist_ok=True)


# ============================================================
# TaskManager - 带依赖关系的任务管理器
# ============================================================

class TaskManager:
    """
    持久化任务管理器，支持依赖关系 (blockedBy)。
    设计参考 self_cc.py 的 TaskManager，核心特性：
    1. 任务创建时指定 blockedBy = [前置任务ID列表]
    2. 任务完成时自动从所有依赖它的任务中移除阻塞
    3. is_ready(task_id) 检查是否所有前置任务都已完成
    """

    def __init__(self):
        self._lock = threading.Lock()
        TASKS_DIR.mkdir(exist_ok=True)
        self._ensure_project_file()

    def _ensure_project_file(self):
        """确保 project.json 存在"""
        pf = SHARED_DIR / "project.json"
        if not pf.exists():
            pf.write_text(json.dumps({
                "name": "Untitled Project",
                "description": "",
                "status": "pending",
            }, indent=2, ensure_ascii=False), encoding='utf-8')

    def _next_id(self) -> int:
        ids = [int(f.stem) for f in TASKS_DIR.glob("*.json") if f.stem.isdigit()]
        return max(ids, default=0) + 1

    def _task_path(self, tid: int) -> Path:
        return TASKS_DIR / f"{tid}.json"

    def _load(self, tid: int) -> dict:
        p = self._task_path(tid)
        if not p.exists():
            raise ValueError(f"Task #{tid} not found")
        return json.loads(p.read_text(encoding='utf-8'))

    def _save(self, task: dict):
        self._task_path(task["id"]).write_text(
            json.dumps(task, indent=2, ensure_ascii=False),
            encoding='utf-8'
        )

    def create(self, subject: str, description: str = "",
               role: str = "", blocked_by: List[int] = None) -> dict:
        """
        创建任务
        - subject: 任务名称
        - description: 任务详细描述
        - role: 预期的执行角色 (backend/frontend/test/devops)
        - blocked_by: 前置任务ID列表，这些任务完成前本任务不可执行
        """
        with self._lock:
            task = {
                "id": self._next_id(),
                "subject": subject,
                "description": description,
                "role": role,
                "status": "pending",
                "owner": None,
                "blockedBy": blocked_by or [],
                "output": "",
                "dependents": [],  # 依赖本任务的其他任务ID（自动维护）
            }
            # 注册反向依赖
            for bid in task["blockedBy"]:
                try:
                    dep_task = self._load(bid)
                    if task["id"] not in dep_task.get("dependents", []):
                        dep_task.setdefault("dependents", []).append(task["id"])
                        self._save(dep_task)
                except ValueError:
                    pass  # 前置任务尚未创建
            self._save(task)
            return task

    def get(self, tid: int) -> dict:
        return self._load(tid)

    def update(self, tid: int, status: str = None,
               owner: str = None, output: str = None,
               add_blocked_by: List[int] = None,
               remove_blocked_by: List[int] = None) -> dict:
        """
        更新任务状态。
        当 status 设为 "completed" 时，自动解锁所有依赖此任务的其他任务。
        """
        with self._lock:
            task = self._load(tid)
            if status:
                old_status = task["status"]
                task["status"] = status

                # 任务完成：自动解锁所有 dependents
                if status == "completed" and old_status != "completed":
                    for dep_id in task.get("dependents", []):
                        try:
                            dep_task = self._load(dep_id)
                            if tid in dep_task.get("blockedBy", []):
                                dep_task["blockedBy"].remove(tid)
                                self._save(dep_task)
                                print(f"  🔓 Task #{dep_id} 解锁（前置 #{tid} 已完成）")
                        except ValueError:
                            pass

            if owner is not None:
                task["owner"] = owner
                if status is None:
                    task["status"] = "in_progress"
            if output is not None:
                task["output"] = output
            if add_blocked_by:
                task["blockedBy"] = list(set(task["blockedBy"] + add_blocked_by))
                for bid in add_blocked_by:
                    try:
                        dep_task = self._load(bid)
                        if tid not in dep_task.get("dependents", []):
                            dep_task.setdefault("dependents", []).append(tid)
                            self._save(dep_task)
                    except ValueError:
                        pass
            if remove_blocked_by:
                task["blockedBy"] = [x for x in task["blockedBy"] if x not in remove_blocked_by]
            self._save(task)
            return task

    def is_ready(self, tid: int) -> bool:
        """检查任务是否已就绪（所有前置任务已完成）"""
        task = self._load(tid)
        if task["status"] != "pending":
            return False
        if task.get("owner"):
            return False
        return len(task.get("blockedBy", [])) == 0

    def claim(self, tid: int, owner: str) -> dict:
        """认领任务"""
        return self.update(tid, owner=owner)

    def get_ready_tasks(self, role: str = None) -> List[dict]:
        """获取所有就绪（可认领）的任务"""
        ready = []
        for f in sorted(TASKS_DIR.glob("*.json")):
            if not f.stem.isdigit():
                continue
            task = json.loads(f.read_text(encoding='utf-8'))
            if task["status"] == "pending" and len(task.get("blockedBy", [])) == 0:
                if role is None or task.get("role") == role:
                    ready.append(task)
        return ready

    def list_all(self) -> str:
        tasks = []
        for f in sorted(TASKS_DIR.glob("*.json")):
            if not f.stem.isdigit():
                continue
            tasks.append(json.loads(f.read_text(encoding='utf-8')))
        if not tasks:
            return "No tasks."
        lines = []
        for t in tasks:
            m = {"pending": "[ ]", "in_progress": "[>]", "completed": "[x]"}.get(t["status"], "[?]")
            owner = f" @{t['owner']}" if t.get("owner") else ""
            role = f" ({t.get('role', '')})" if t.get("role") else ""
            blocked = f" ← 等待 #{t['blockedBy']}" if t.get("blockedBy") else ""
            lines.append(f"  {m} #{t['id']}: {t['subject']}{role}{owner}{blocked}")
        return "\n".join(lines)

    def set_project(self, name: str, description: str):
        pf = SHARED_DIR / "project.json"
        data = json.loads(pf.read_text(encoding='utf-8')) if pf.exists() else {}
        data["name"] = name
        data["description"] = description
        data["status"] = "in_progress"
        pf.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')

    def all_completed(self) -> bool:
        """检查是否所有任务都已完成"""
        tasks = [f for f in TASKS_DIR.glob("*.json") if f.stem.isdigit()]
        if not tasks:
            return False
        for f in tasks:
            t = json.loads(f.read_text(encoding='utf-8'))
            if t.get("status") != "completed":
                return False
        return True


# ============================================================
# MessageBus - 增强消息总线
# ============================================================

class MessageBus:
    """
    增强消息总线，支持不同类型消息：
    - "task": 任务分配消息
    - "api_spec": 后端向前端/测试发布的 API 规范
    - "status": 状态汇报消息
    - "coordination": Agent 间协调消息
    """

    def __init__(self):
        self._lock = threading.Lock()
        INBOX_DIR.mkdir(parents=True, exist_ok=True)

    def send(self, sender: str, to: str, content: str,
             msg_type: str = "message", extra: dict = None):
        """发送消息"""
        msg = {
            "type": msg_type,
            "from": sender,
            "to": to,
            "content": content,
            "timestamp": time.time(),
        }
        if extra:
            msg.update(extra)
        with self._lock:
            with open(INBOX_DIR / f"{to}.jsonl", "a", encoding='utf-8') as f:
                f.write(json.dumps(msg, ensure_ascii=False) + "\n")

    def read_inbox(self, name: str) -> list:
        """读取并清空收件箱"""
        path = INBOX_DIR / f"{name}.jsonl"
        if not path.exists():
            return []
        with self._lock:
            lines = path.read_text(encoding='utf-8').strip().splitlines()
            msgs = [json.loads(l) for l in lines if l.strip()]
            path.write_text("", encoding='utf-8')
        return msgs

    def broadcast(self, sender: str, content: str, names: list,
                  msg_type: str = "broadcast"):
        """广播消息给多个 Agent"""
        for n in names:
            if n != sender:
                self.send(sender, n, content, msg_type)


# ============================================================
# API Spec Store - 结构化 API 信息存储
# ============================================================

class APISpecStore:
    """存储后端发布的 API 规范，供前端和测试 Agent 查询"""

    def __init__(self):
        self._lock = threading.Lock()
        self._spec_file = SHARED_DIR / "api_spec.json"

    def publish(self, spec: dict):
        """发布 API 规范"""
        with self._lock:
            self._spec_file.write_text(
                json.dumps(spec, indent=2, ensure_ascii=False),
                encoding='utf-8'
            )

    def get_spec(self) -> Optional[dict]:
        """获取 API 规范"""
        if not self._spec_file.exists():
            return None
        return json.loads(self._spec_file.read_text(encoding='utf-8'))

    def wait_for_spec(self, timeout: int = 120) -> Optional[dict]:
        """阻塞等待直到 API 规范可用"""
        start = time.time()
        while time.time() - start < timeout:
            spec = self.get_spec()
            if spec:
                return spec
            time.sleep(2)
        return None


# ============================================================
# 全局单例（兼容旧接口 + 新接口）
# ============================================================

# 兼容旧代码的 SharedContext
class SharedContext:
    """兼容旧接口"""
    def __init__(self):
        self.project_file = SHARED_DIR / "project.json"
        self.project_data = self._load_project()

    def _load_project(self):
        if self.project_file.exists():
            return json.loads(self.project_file.read_text(encoding='utf-8'))
        return {
            "name": "Untitled Project",
            "description": "",
            "status": "pending",
            "tasks": {},
        }

    def save_project(self):
        self.project_file.write_text(
            json.dumps(self.project_data, indent=2, ensure_ascii=False),
            encoding='utf-8'
        )

    def update_task(self, agent_name, status, output=""):
        if "tasks" not in self.project_data:
            self.project_data["tasks"] = {}
        self.project_data["tasks"][agent_name] = {"status": status, "output": output}
        self.save_project()

    def set_project(self, name, description):
        self.project_data["name"] = name
        self.project_data["description"] = description
        self.project_data["status"] = "in_progress"
        self.save_project()

    def update_backend_spec(self, spec):
        self.project_data["backend_spec"] = spec
        self.save_project()

    def get_status(self):
        tasks = self.project_data.get("tasks", {})
        lines = [
            f"📋 项目: {self.project_data.get('name', 'N/A')}",
            f"📝 描述: {self.project_data.get('description', '')}",
            f"🎯 状态: {self.project_data.get('status', 'unknown')}",
            "--- 各Agent进度 ---",
        ]
        for agent, info in tasks.items():
            icon = "✓" if info.get("status") == "completed" else "⏳"
            lines.append(f"{agent:10s}: {icon} {info.get('status', 'unknown'):12s}")
        return "\n".join(lines)


# 兼容旧代码的 send/read 函数
def send_message(from_agent: str, to_agent: str, message: str):
    msg = {"from": from_agent, "to": to_agent, "content": message, "type": "message"}
    inbox_file = INBOX_DIR / f"{to_agent}.jsonl"
    with open(inbox_file, "a", encoding='utf-8') as f:
        f.write(json.dumps(msg, ensure_ascii=False) + "\n")


def read_messages(agent_name: str) -> list:
    inbox_file = INBOX_DIR / f"{agent_name}.jsonl"
    if not inbox_file.exists():
        return []
    messages = []
    with open(inbox_file, "r", encoding='utf-8') as f:
        for line in f:
            if line.strip():
                messages.append(json.loads(line))
    inbox_file.write_text("", encoding='utf-8')
    return messages


# 全局实例
TASK_MGR = TaskManager()
BUS = MessageBus()
API_SPEC = APISpecStore()


if __name__ == "__main__":
    # 简单自测
    print("TaskManager 自测:")
    t1 = TASK_MGR.create("创建后端 API", "Flask REST API", role="backend")
    t2 = TASK_MGR.create("创建前端 UI", "HTML 页面", role="frontend", blocked_by=[t1["id"]])
    t3 = TASK_MGR.create("编写测试", "pytest", role="test", blocked_by=[t1["id"]])
    t4 = TASK_MGR.create("部署配置", "Docker", role="devops", blocked_by=[t2["id"], t3["id"]])

    print(f"\n初始状态:")
    print(TASK_MGR.list_all())

    print(f"\nTask #2 就绪? {TASK_MGR.is_ready(t2['id'])}  (应为 False, 被 #1 阻塞)")
    print(f"Task #1 就绪? {TASK_MGR.is_ready(t1['id'])}  (应为 True, 无阻塞)")

    TASK_MGR.update(t1["id"], status="completed", output="Flask app 已生成")
    print(f"\n#1 完成后:")
    print(TASK_MGR.list_all())
    print(f"Task #2 就绪? {TASK_MGR.is_ready(t2['id'])}  (应为 True, 阻塞已解除)")

    print(f"\n全部完成? {TASK_MGR.all_completed()}")
