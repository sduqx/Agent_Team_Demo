#!/usr/bin/env python3
"""
BaseAgent v3.0 — 通用 Agent 基类，内置 ReAct 循环 + Tool 管理
参考 self_cc.py 的设计模式，为每个 Agent 提供：
  1. ReAct 循环 (Observe → Plan → Act → Observe)
  2. Tool 注册与自动分发
  3. 收件箱轮询 + 任务处理
  4. finish_task 工具控制何时结束
"""

import json
import re
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

from shared_context import BUS, TASK_MGR, API_SPEC, extract_text_from_response


# ============================================================
# BaseAgent — 所有 Agent 的基类
# ============================================================

class BaseAgent:
    """
    通用 Agent 基类，内置 ReAct 循环。

    用法:
        class BackendAgent(BaseAgent):
            def _setup_tools(self):
                self.register_tool(
                    name="generate_backend_code",
                    description="...",
                    input_schema={...},
                    handler=self._handle_generate_backend_code
                )
                # ... 更多 tools
    """

    def __init__(self, name: str, role: str, max_rounds: int = 15):
        self.name = name
        self.role = role
        self.max_rounds = max_rounds

        # Tool 注册表
        self._tools: List[dict] = []           # Anthropic tool schemas
        self._handlers: Dict[str, Callable] = {}  # name → handler

        # 项目目录
        self.project_dir = Path.cwd() / ".project"
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
            description="向其他 Agent 发送消息。",
            input_schema={
                "type": "object",
                "properties": {
                    "to": {"type": "string", "description": "接收者 (lead/backend/frontend/test/devops)"},
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
            name="finish_task",
            description="标记当前任务完成，并提交总结。调用此 tool 后 Agent 将结束当前工作循环。",
            input_schema={
                "type": "object",
                "properties": {
                    "summary": {"type": "string", "description": "任务完成总结"},
                },
                "required": ["summary"],
            },
            handler=self._handle_finish_task,
        )

    # ── 通用 tool handlers ──

    def _handle_write_file(self, path: str, content: str) -> str:
        try:
            fp = self.project_dir / path
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(content, encoding='utf-8')
            return f"✓ 已写入 {fp} ({len(content)} 字节)"
        except Exception as e:
            return f"❌ 写入失败: {e}"

    def _handle_read_file(self, path: str) -> str:
        try:
            fp = self.project_dir / path
            if not fp.exists():
                return f"⚠️ 文件不存在: {path}"
            content = fp.read_text(encoding='utf-8')
            # 返回摘要，避免超长
            if len(content) > 5000:
                return content[:5000] + f"\n... (截断，共 {len(content)} 字节)"
            return content
        except Exception as e:
            return f"❌ 读取失败: {e}"

    def _handle_list_directory(self, path: str = ".") -> str:
        try:
            fp = self.project_dir / path
            if not fp.exists():
                return f"⚠️ 目录不存在: {path}"
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
            return f"❌ 列出目录失败: {e}"

    def _handle_send_message(self, to: str, content: str, msg_type: str = "message") -> str:
        try:
            BUS.send(sender=self.name, to=to, content=content, msg_type=msg_type)
            return f"✓ 已发送 {msg_type} 消息给 {to}"
        except Exception as e:
            return f"❌ 发送失败: {e}"

    def _handle_read_inbox(self) -> str:
        msgs = BUS.read_inbox(self.name)
        if not msgs:
            return "(收件箱为空)"
        return json.dumps(msgs, indent=2, ensure_ascii=False)

    def _handle_finish_task(self, summary: str = "") -> str:
        """finish_task 在 react_loop 中有特殊处理，这里返回标记文本"""
        return f"✓ 任务完成: {summary}"

    # ── 通用辅助方法 ──

    @staticmethod
    def _extract_code_block(text: str, lang: str) -> str:
        """从 LLM 响应中提取指定语言的代码块"""
        pattern = rf'```{lang}\n(.*?)\n```'
        match = re.search(pattern, text, re.DOTALL)
        return match.group(1) if match else None

    # ── 需子类实现的方法 ──

    def _setup_tools(self):
        """子类重写此方法来注册自己的专属 tools"""
        pass

    def get_system_prompt(self) -> str:
        """子类重写以提供专属 system prompt"""
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
            print(f"⚠️ [{self.name}] LLM 不可用，跳过 ReAct 循环")
            return "LLM 不可用，任务未处理"

        system_prompt = self.get_system_prompt()

        # 构建初始消息
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
                print(f"  ❌ [{self.name}] LLM 调用失败: {e}")
                return f"LLM 调用失败: {e}"

            messages.append({"role": "assistant", "content": response.content})

            # 打印 LLM 的思考/回复
            for block in response.content:
                if hasattr(block, "text") and block.text:
                    print(f"  💬 [{self.name}] {block.text[:200]}")

            # 如果 LLM 决定结束（不再调用 tool），退出循环
            if response.stop_reason != "tool_use":
                final_result = extract_text_from_response(response)
                print(f"  ✅ [{self.name}] 完成（stop_reason={response.stop_reason}）")
                return final_result

            # ── 执行 Tools ──
            results = []
            finished = False

            for block in response.content:
                if block.type != "tool_use":
                    continue

                tool_name = block.name
                tool_input = block.input if hasattr(block.input, "items") else dict(block.input)

                # 兼容 LLM 的 raw_arguments 包装
                if "raw_arguments" in tool_input and len(tool_input) == 1:
                    try:
                        tool_input = json.loads(tool_input["raw_arguments"])
                    except (json.JSONDecodeError, TypeError):
                        pass  # 保持原样

                print(f"  🔧 [{self.name}] 调用工具: {tool_name}({json.dumps(tool_input, ensure_ascii=False)[:100]})")

                # 特殊处理 finish_task
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
                            output = f"❌ 工具执行出错: {e}"
                            import traceback
                            traceback.print_exc()
                    else:
                        output = f"❌ 未知工具: {tool_name}"

                results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": str(output),
                })

                print(f"     → {str(output)[:200]}")

            messages.append({"role": "user", "content": results})

            if finished:
                print(f"  ✅ [{self.name}] finish_task 被调用，退出循环")
                return final_result

        print(f"  ⚠️ [{self.name}] 达到最大轮数 {self.max_rounds}，强制退出")
        return f"达到最大轮数 ({self.max_rounds})，任务可能未完成"

    # ── 主运行循环 ──

    def run(self, poll_forever: bool = True):
        """
        主事件循环：轮询收件箱 → 处理任务 → ReAct 循环 → 汇报结果。
        poll_forever=True: 持续轮询 (用于长期运行的 worker)
        poll_forever=False: 处理一个任务后退出 (用于一次性任务)
        """
        print(f"[{self.name}] Agent 启动 (role={self.role}, max_rounds={self.max_rounds})")
        if not LLM_AVAILABLE:
            print(f"[{self.name}] ⚠️ LLM 不可用，将在无 AI 模式下运行")
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
                        print(f"[{self.name}] 📋 收到任务 #{task_id}")
                        print(f"[{self.name}] 内容: {task_content[:150]}...")
                        print(f"{'='*60}\n")

                        # ═══ 进入 ReAct 循环 ═══
                        result = self.react_loop(task_content)

                        # ── 汇报给 Lead ──
                        print(f"\n[{self.name}] 📤 向 Lead 汇报:")
                        print(f"  {result[:200]}")
                        BUS.send(
                            sender=self.name,
                            to="lead",
                            content=result,
                            msg_type="status",
                            extra={"task_id": task_id},
                        )
                        print(f"[{self.name}] ✓ 汇报完毕\n")

                        if not poll_forever:
                            return

                except Exception as e:
                    print(f"[{self.name}] ❌ 处理消息出错: {e}")
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
    # 简单测试
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
    print("\nTestAgent 就绪 ✓")
