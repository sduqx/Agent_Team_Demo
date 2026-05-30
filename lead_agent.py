#!/usr/bin/env python3
"""
Lead Agent - 主控Agent，使用LLM分析需求
"""

import sys
import time
import json
from pathlib import Path
from shared_context import SharedContext, send_message, read_messages, extract_text_from_response

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

context = SharedContext()
PROJECT_DIR = Path.cwd() / ".project"
PROJECT_DIR.mkdir(exist_ok=True)


def analyze_requirement_with_llm(requirement: str) -> dict:
    """
    使用LLM分析需求，生成任务分配
    """
    if client is None:
        print("⚠️ LLM不可用，使用默认分析")
        return {
            "backend": f"创建Flask REST API: {requirement}",
            "frontend": f"创建前端界面: {requirement}",
            "test": f"编写测试: {requirement}",
            "devops": f"创建部署配置: {requirement}"
        }

    prompt = f"""
你是一个项目主管Agent。用户提出了这个需求：
{requirement}

请深入分析这个需求，并为以下团队分配具体、清晰、可独立执行的任务：
1. backend: 后端需要实现什么API、数据模型、业务逻辑？
2. frontend: 前端需要实现什么页面、组件、功能？
3. test: 测试应该覆盖哪些场景？
4. devops: DevOps应该准备什么部署配置和文档？

返回JSON格式，key必须严格为：backend、frontend、test、devops。
例如：
{{"backend": "使用Flask创建REST API，包含以下端点...", "frontend": "创建HTML页面...", "test": "编写pytest测试...", "devops": "编写Dockerfile..."}}
"""

    try:
        response = client.messages.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2000
        )

        # 提取文本内容
        result_text = extract_text_from_response(response)

        # 提取JSON
        start = result_text.find('{')
        end = result_text.rfind('}') + 1
        if start >= 0 and end > start:
            json_str = result_text[start:end]
            return json.loads(json_str)
        else:
            print(f"⚠️ 无法找到JSON: {result_text[:100]}")
            return None
    except json.JSONDecodeError as e:
        print(f"❌ JSON解析失败: {e}")
        return None
    except Exception as e:
        print(f"❌ LLM分析失败: {e}")
        import traceback
        traceback.print_exc()

    return None


def main():
    print("=" * 70)
    print("👔 Lead Agent 已启动 (LLM驱动)")
    print("=" * 70)
    print("\n等待需求输入...\n")

    iteration = 0
    all_completed_reported = False

    while True:
        iteration += 1

        # 读取消息
        messages = read_messages("lead")

        for msg in messages:
            print(f"\n📬 收到来自 {msg['from']} 的消息:")
            print(f"   {msg['content']}\n")

            # 如果是项目需求（来自外部），用LLM分析并分配
            if msg['from'] == "system" and "requirement:" in msg['content'].lower():
                requirement = msg['content'].replace("requirement:", "").strip()

                print(f"🤖 Lead Agent 使用LLM分析需求...\n")
                tasks = analyze_requirement_with_llm(requirement)

                if tasks:
                    # key 映射容错：backend_task -> backend 等
                    agent_map = {
                        "backend_task": "backend",
                        "frontend_task": "frontend",
                        "test_task": "test",
                        "devops_task": "devops"
                    }
                    normalized_tasks = {}
                    for k, v in tasks.items():
                        normalized_key = agent_map.get(k, k)
                        normalized_tasks[normalized_key] = v

                    print(f"✓ 需求分析完成，任务分配如下：\n")
                    for agent, task in normalized_tasks.items():
                        if agent not in ("backend", "frontend", "test", "devops"):
                            print(f"  ⚠️ 未知Agent: {agent}，跳过")
                            continue
                        print(f"  → {agent}: {task[:60]}...")
                        send_message("lead", agent, task)
                        time.sleep(0.5)

                    context.set_project("Demo Project", requirement)
                    print("\n✓ 所有任务已分配给Agent!\n")
                else:
                    print("❌ 需求分析失败，使用默认任务分配\n")
                    default_tasks = {
                        "backend": f"创建Flask REST API: {requirement}",
                        "frontend": f"创建前端界面: {requirement}",
                        "test": f"编写测试: {requirement}",
                        "devops": f"创建部署配置: {requirement}"
                    }
                    for agent, task in default_tasks.items():
                        send_message("lead", agent, task)
                    context.set_project("Demo Project", requirement)

            # 如果是子Agent发来的完成消息，更新任务状态
            elif msg['from'] in ("backend", "frontend", "test", "devops"):
                agent_name = msg['from']
                status_info = "completed" if "完成" in msg['content'] else "in_progress"
                context.update_task(agent_name, status_info, msg['content'])
                print(f"📊 任务进度已更新: {agent_name} → {status_info}")

        # 定期打印状态
        if iteration % 5 == 0:
            status_text = context.get_status()
            print("\n" + status_text + "\n")

            # 检查是否所有任务都完成了
            tasks = context.project_data.get("tasks", {})
            all_done = all(
                info["status"] == "completed"
                for info in tasks.values()
            )
            if all_done and not all_completed_reported:
                print("=" * 70)
                print("🎉 所有Agent已完成任务！")
                print(f"📁 输出文件位于: .project/ 目录")
                print("=" * 70)
                all_completed_reported = True

        time.sleep(2)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Lead Agent 停止")
        sys.exit(0)
