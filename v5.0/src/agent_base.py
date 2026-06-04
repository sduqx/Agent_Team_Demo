#!/usr/bin/env python3
"""
BaseAgent v2.0 — 通用 Agent 基类，内置 ReAct 循环 + Tool 管理
v2.0 改进：
  1. 支持注入自定义 project_dir（多项目隔离）
  2. 支持通过命令行参数定制 Agent
  3. 增强 ask_user，支持多项选择的场景
"""

import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Dict, List, Any, Optional

try:
    from anthropic import Anthropic
    from dotenv import load_dotenv
    import os

    load_dotenv(override=True)
    _client = Anthropic(base_url=os.getenv("ANTHROPIC_BASE_URL"))
    _MODEL = os.environ["MODEL_ID"]
    LLM_AVAILABLE = True
except Exception:
    _client = None
    _MODEL = None
    LLM_AVAILABLE = False

from .shared_context import BUS, TASK_MGR, API_SPEC, extract_text_from_response


# ============================================================
# BaseAgent — 所有 Agent 的基类 (v2.0)
# ============================================================

class BaseAgent:
    """
    通用 Agent 基类，内置 ReAct 循环。

    v2.0 新增：
    - project_dir 可通过构造函数注入
    - 支持 from_cli() 工厂方法
    - 更灵活的系统提示词注入

    用法:
        class MyAgent(BaseAgent):
            def _setup_tools(self):
                self.register_tool(...)
    """

    def __init__(self, name: str, role: str, max_rounds: int = 50,
                 project_dir: Path = None, system_prompt: str = None):
        self.name = name
        self.role = role
        self.max_rounds = max_rounds
        self._custom_system_prompt = system_prompt

        # Tool 注册表
        self._tools: List[dict] = []           # Anthropic tool schemas
        self._handlers: Dict[str, Callable] = {}  # name → handler

        # 项目目录
        self.project_dir = project_dir or Path.cwd() / ".project"
        self.project_dir.mkdir(exist_ok=True)

        # 注册通用 tools
        self._register_common_tools()

        # 子类注册专属 tools
        self._setup_tools()

    # ── Tool 注册 API ──

    def register_tool(self, name: str, description: str,
                      input_schema: dict, handler: Callable):
        """注册一个 tool"""
        tool_def = {
            "name": name,
            "description": description,
            "input_schema": input_schema,
        }
        self._tools.append(tool_def)
        self._handlers[name] = handler

    def _register_common_tools(self):
        """注册所有 Agent 通用的基础 tools"""
        self.register_tool(
            name="write_file",
            description="写入文件内容。path 为相对于项目根目录的路径。",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径"},
                    "content": {"type": "string", "description": "文件内容"},
                },
                "required": ["path", "content"],
            },
            handler=self._handle_write_file,
        )

        self.register_tool(
            name="read_file",
            description="读取文件内容。",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径"},
                },
                "required": ["path"],
            },
            handler=self._handle_read_file,
        )

        self.register_tool(
            name="list_directory",
            description="列出目录中的文件。",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "目录路径，默认 '.'"},
                },
            },
            handler=self._handle_list_directory,
        )

        self.register_tool(
            name="send_message",
            description="向其他 Agent 发送消息。to 为目标 Agent 名称。",
            input_schema={
                "type": "object",
                "properties": {
                    "to": {"type": "string", "description": "接收者 Agent 名称"},
                    "content": {"type": "string", "description": "消息内容"},
                    "msg_type": {"type": "string", "description": "消息类型", "default": "message"},
                },
                "required": ["to", "content"],
            },
            handler=self._handle_send_message,
        )

        self.register_tool(
            name="read_inbox",
            description="读取本 Agent 的收件箱消息。",
            input_schema={"type": "object", "properties": {}},
            handler=self._handle_read_inbox,
        )

        self.register_tool(
            name="ask_user",
            description="当遇到需要人类决策的问题时，向用户提问并等待回复。只在确实需要人类判断时才调用。",
            input_schema={
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "向用户提出的问题"},
                    "context": {"type": "string", "description": "补充上下文信息"},
                },
                "required": ["question"],
            },
            handler=self._handle_ask_user,
        )

        self.register_tool(
            name="finish_task",
            description="标记当前任务完成，并提交总结。调用后 Agent 将结束当前工作循环。",
            input_schema={
                "type": "object",
                "properties": {
                    "summary": {"type": "string", "description": "任务完成总结"},
                },
                "required": ["summary"],
            },
            handler=self._handle_finish_task,
        )

        self.register_tool(
            name="run_command",
            description=(
                "在项目目录中执行 shell 命令并获取输出。"
                "用于编译代码、运行测试、检查语法、安装依赖等自验证操作。"
                "命令超时 120 秒。"
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "要执行的 shell 命令"},
                },
                "required": ["command"],
            },
            handler=self._handle_run_command,
        )

    # ── 通用 tool handlers ──

    def _handle_write_file(self, path: str, content: str) -> str:
        try:
            fp = self.project_dir / path
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(content, encoding='utf-8')
            return f"[OK] 已写入 {fp} ({len(content)} 字节)"
        except Exception as e:
            return f"[FAIL] 写入失败: {e}"

    def _handle_read_file(self, path: str) -> str:
        try:
            fp = self.project_dir / path
            if not fp.exists():
                return f"[WARN] 文件不存在: {path}"
            content = fp.read_text(encoding='utf-8')
            if len(content) > 5000:
                return content[:5000] + f"\n... (截断，共 {len(content)} 字节)"
            return content
        except Exception as e:
            return f"[FAIL] 读取失败: {e}"

    def _handle_list_directory(self, path: str = ".") -> str:
        try:
            fp = self.project_dir / path
            if not fp.exists():
                return f"[WARN] 目录不存在: {path}"
            items = sorted(fp.rglob("*"))
            lines = []
            for item in items:
                rel = item.relative_to(self.project_dir)
                mark = "/" if item.is_dir() else ""
                size = f" ({item.stat().st_size}B)" if item.is_file() else ""
                lines.append(f"  {rel}{mark}{size}")
            if not lines:
                return "(空目录)"
            return "\n".join(lines[:50])
        except Exception as e:
            return f"[FAIL] 列出目录失败: {e}"

    def _handle_send_message(self, to: str, content: str, msg_type: str = "message") -> str:
        try:
            BUS.send(sender=self.name, to=to, content=content, msg_type=msg_type)
            return f"[OK] 已发送 {msg_type} 消息给 {to}"
        except Exception as e:
            return f"[FAIL] 发送失败: {e}"

    def _handle_read_inbox(self) -> str:
        msgs = BUS.read_inbox(self.name)
        if not msgs:
            return "(收件箱为空)"
        return json.dumps(msgs, indent=2, ensure_ascii=False)

    def _handle_finish_task(self, summary: str = "") -> str:
        return f"[OK] 任务完成: {summary}"

    def _handle_run_command(self, command: str) -> str:
        """在项目目录中执行 shell 命令，返回 stdout/stderr/exit_code。"""
        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=str(self.project_dir),
                capture_output=True,
                text=True,
                timeout=120,
            )
            output_parts = []
            if result.stdout.strip():
                output_parts.append(f"[stdout]\n{result.stdout.strip()}")
            if result.stderr.strip():
                output_parts.append(f"[stderr]\n{result.stderr.strip()}")
            output_parts.insert(0, f"[exit_code: {result.returncode}]")
            return "\n\n".join(output_parts)
        except subprocess.TimeoutExpired:
            return "[FAIL] 命令执行超时（120s）"
        except Exception as e:
            return f"[FAIL] 命令执行失败: {e}"

    def _handle_ask_user(self, question: str, context: str = "") -> str:
        print()
        print("=" * 60)
        print("[THINK] Agent 需要你的决策：")
        if context:
            print(f"   [TASK] 背景: {context}")
        print(f"   [?] {question}")
        print("=" * 60)
        try:
            reply = input("[USER] 请输入你的决定（直接回车跳过）: ").strip()
        except (EOFError, KeyboardInterrupt):
            reply = ""
        if not reply:
            reply = "(用户未提供输入，请基于默认方案自行决定并继续)"
        print(f"   [OK] 已回复\n")
        return reply

    # ── 通用辅助方法 ──

    @staticmethod
    def _extract_code_block(text: str, lang: str) -> str:
        pattern = rf'```{lang}\n(.*?)\n```'
        match = re.search(pattern, text, re.DOTALL)
        return match.group(1) if match else None

    # ── 需子类实现的方法 ──

    def _setup_tools(self):
        """子类重写此方法来注册自己的专属 tools"""
        pass

    def get_system_prompt(self) -> str:
        """子类重写以提供专属 system prompt。
        v2.0: 支持通过构造函数注入自定义 prompt。"""
        if self._custom_system_prompt:
            return self._custom_system_prompt
        return f"""你是 '{self.name}'，角色: {self.role}。
工作目录: {self.project_dir}
直接行动，不要空谈。每一步都基于实际获取到的信息。完成后调用 finish_task。"""

    # ── ReAct 循环核心 ──

    def react_loop(self, task_prompt: str, extra_context: str = "") -> str:
        """
        ReAct 循环：Observe → Plan → Act → Observe → ...
        返回最终的任务总结。
        """
        if not LLM_AVAILABLE or _client is None:
            print(f"[WARN] [{self.name}] LLM 不可用，跳过 ReAct 循环")
            return "LLM 不可用，任务未处理"

        system_prompt = self.get_system_prompt()

        context = f"<task>\n{task_prompt}\n</task>"
        if extra_context:
            context += f"\n\n<context>\n{extra_context}\n</context>"
        context += "\n\n请使用你的工具逐步完成此任务。完成后调用 finish_task。"

        messages = [{"role": "user", "content": context}]
        final_result = ""

        for round_num in range(1, self.max_rounds + 1):
            print(f"  [{self.name}] ReAct 第 {round_num} 轮...")

            try:
                response = _client.messages.create(
                    model=_MODEL,
                    system=system_prompt,
                    messages=messages,
                    tools=self._tools,
                    max_tokens=8000,
                )
            except Exception as e:
                print(f"  [FAIL] [{self.name}] LLM 调用失败: {e}")
                return f"LLM 调用失败: {e}"

            messages.append({"role": "assistant", "content": response.content})

            for block in response.content:
                if hasattr(block, "text") and block.text:
                    print(f"  [MSG] [{self.name}] {block.text[:200]}")

            if response.stop_reason != "tool_use":
                final_result = extract_text_from_response(response)
                print(f"  [OK] [{self.name}] 完成（stop_reason={response.stop_reason}）")
                return final_result

            # ── 执行 Tools ──
            results = []
            finished = False

            for block in response.content:
                if block.type != "tool_use":
                    continue

                tool_name = block.name
                tool_input = block.input if hasattr(block.input, "items") else dict(block.input)

                if "raw_arguments" in tool_input and len(tool_input) == 1:
                    try:
                        tool_input = json.loads(tool_input["raw_arguments"])
                    except (json.JSONDecodeError, TypeError):
                        pass

                print(f"  [TOOL] [{self.name}] 调用工具: {tool_name}({json.dumps(tool_input, ensure_ascii=False)[:100]})")

                if tool_name == "finish_task":
                    finished = True
                    final_result = tool_input.get("summary", "任务已完成")
                    output = final_result
                else:
                    handler = self._handlers.get(tool_name)
                    if handler:
                        try:
                            output = handler(**tool_input)
                        except Exception as e:
                            output = f"[FAIL] 工具执行出错: {e}"
                            import traceback
                            traceback.print_exc()
                    else:
                        output = f"[FAIL] 未知工具: {tool_name}"

                results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": str(output),
                })
                print(f"     → {str(output)[:200]}")

            messages.append({"role": "user", "content": results})

            if finished:
                print(f"  [OK] [{self.name}] finish_task 被调用，退出循环")
                return final_result

        print(f"  [WARN] [{self.name}] 达到最大轮数 {self.max_rounds}，强制退出")
        return f"达到最大轮数 ({self.max_rounds})，任务可能未完成"

    # ── 主运行循环 ──

    def run(self, poll_forever: bool = True):
        """
        主事件循环：轮询收件箱 → 处理任务 → ReAct 循环 → 汇报结果。
        """
        print(f"[{self.name}] Agent 启动 (role={self.role}, max_rounds={self.max_rounds})")
        if not LLM_AVAILABLE:
            print(f"[{self.name}] [WARN] LLM 不可用，将在无 AI 模式下运行")
        print(f"[{self.name}] 等待任务...\n")

        while True:
            inbox = BUS.read_inbox(self.name)

            for msg in inbox:
                try:
                    msg_type = msg.get("type", "")
                    sender = msg.get("from", "")

                    if msg_type == "task" and sender == "lead":
                        task_id = msg.get("extra", {}).get("task_id", "?")
                        task_content = msg.get("content", "")

                        print(f"\n{'='*60}")
                        print(f"[{self.name}] [TASK] 收到任务 #{task_id}")
                        print(f"[{self.name}] 内容: {task_content[:150]}...")
                        print(f"{'='*60}\n")

                        result = self.react_loop(task_content)

                        print(f"\n[{self.name}] [SEND] 向 Lead 汇报:")
                        print(f"  {result[:200]}")
                        BUS.send(
                            sender=self.name,
                            to="lead",
                            content=result,
                            msg_type="status",
                            extra={"task_id": task_id},
                        )
                        print(f"[{self.name}] [OK] 汇报完毕\n")

                        if not poll_forever:
                            return

                except Exception as e:
                    print(f"[{self.name}] [FAIL] 处理消息出错: {e}")
                    import traceback
                    traceback.print_exc()

            time.sleep(2)


# ============================================================
# 便捷工厂函数
# ============================================================

def make_agent(cls, **kwargs) -> BaseAgent:
    """实例化 Agent 并返回"""
    return cls(**kwargs)


if __name__ == "__main__":
    class TestAgent(BaseAgent):
        def _setup_tools(self):
            self.register_tool(
                name="echo",
                description="回显消息",
                input_schema={
                    "type": "object",
                    "properties": {"msg": {"type": "string"}},
                    "required": ["msg"],
                },
                handler=lambda msg: f"Echo: {msg}",
            )

    agent = TestAgent(name="test", role="tester")
    print(f"已注册 {len(agent._tools)} 个 tools:")
    for t in agent._tools:
        print(f"  - {t['name']}: {t['description']}")
    print("\nAgentBase v2.0 就绪 [OK]")
