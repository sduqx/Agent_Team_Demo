"""
共享上下文模块 - 所有Agent共享的全局状态

用于Agent间通信和状态同步
"""

import json
from pathlib import Path
import threading
from typing import Dict, Any

TEAM_DIR = Path.cwd() / ".team"
SHARED_DIR = TEAM_DIR / "shared"
INBOX_DIR = TEAM_DIR / "inbox"

for d in [TEAM_DIR, SHARED_DIR, INBOX_DIR]:
    d.mkdir(parents=True, exist_ok=True)


class SharedContext:
    """所有Agent共享的上下文"""
    
    _lock = threading.Lock()
    
    def __init__(self):
        self.project_file = SHARED_DIR / "project.json"
        self.project_data = self._load_project()
    
    def _load_project(self) -> Dict[str, Any]:
        if self.project_file.exists():
            return json.loads(self.project_file.read_text(encoding='utf-8'))
        return {
            "name": "Untitled Project",
            "description": "",
            "status": "pending",
            "tasks": {
                "backend": {"status": "pending", "output": ""},
                "frontend": {"status": "pending", "output": ""},
                "test": {"status": "pending", "output": ""},
                "devops": {"status": "pending", "output": ""}
            }
        }
    
    def save_project(self):
        with self._lock:
            self.project_file.write_text(
                json.dumps(self.project_data, indent=2, ensure_ascii=False),
                encoding='utf-8'
            )
    
    def update_task(self, agent_name: str, status: str, output: str = ""):
        with self._lock:
            if agent_name in self.project_data["tasks"]:
                self.project_data["tasks"][agent_name]["status"] = status
                if output:
                    self.project_data["tasks"][agent_name]["output"] = output
            self.save_project()
    
    def set_project(self, name: str, description: str):
        with self._lock:
            self.project_data["name"] = name
            self.project_data["description"] = description
            self.project_data["status"] = "in_progress"
            self.save_project()
    
    def get_status(self) -> str:
        tasks = self.project_data["tasks"]
        lines = [
            f"📋 项目: {self.project_data['name']}",
            f"📝 描述: {self.project_data['description']}",
            f"🎯 状态: {self.project_data['status']}",
            "--- 各Agent进度 ---",
        ]
        for agent, info in tasks.items():
            icon = "✓" if info["status"] == "completed" else "⏳" if info["status"] == "in_progress" else "⏸"
            lines.append(f"{agent:10s}: {icon} {info['status']:12s} | {info['output'][:30]}")
        return "\n".join(lines)


def send_message(from_agent: str, to_agent: str, message: str):
    """发送消息给指定Agent"""
    msg = {"from": from_agent, "to": to_agent, "content": message}
    inbox_file = INBOX_DIR / f"{to_agent}.jsonl"
    with open(inbox_file, "a", encoding='utf-8') as f:
        f.write(json.dumps(msg, ensure_ascii=False) + "\n")


def read_messages(agent_name: str) -> list:
    """读取该Agent的消息"""
    inbox_file = INBOX_DIR / f"{agent_name}.jsonl"
    if not inbox_file.exists():
        return []
    
    messages = []
    with open(inbox_file, "r", encoding='utf-8') as f:
        for line in f:
            if line.strip():
                messages.append(json.loads(line))
    
    # 清空消息
    inbox_file.write_text("", encoding='utf-8')
    return messages
