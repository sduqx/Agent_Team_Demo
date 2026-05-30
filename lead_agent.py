#!/usr/bin/env python3
"""
Lead Agent - 主控Agent，使用LLM分析需求
"""

import sys
import time
import json
from pathlib import Path
from shared_context import SharedContext, send_message, read_messages

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

请深入分析这个需求，并为以下团队分配具体、可执行的任务：
1. backend_task: 后端需要实现什么API、数据模型、业务逻辑？
2. frontend_task: 前端需要实现什么页面、组件、功能？
3. test_task: 测试应该覆盖哪些场景？
4. devops_task: DevOps应该准备什么部署配置和文档？

返回JSON格式，每个任务都应该是具体、清晰、可独立执行的。
"""
    
    try:
        response = client.messages.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2000
        )
        
        result_text = response.content[0].text
        # 提取JSON
        start = result_text.find('{')
        end = result_text.rfind('}') + 1
        if start >= 0 and end > start:
            return json.loads(result_text[start:end])
    except Exception as e:
        print(f"❌ LLM分析失败: {e}")
    
    return None


def main():
    print("="*70)
    print("👔 Lead Agent 已启动 (LLM驱动)")
    print("="*70)
    print("\n等待需求输入...\n")
    
    iteration = 0
    
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
                    print(f"✓ 需求分析完成，任务分配如下:\n")
                    for agent, task in tasks.items():
                        print(f"  → {agent}: {task[:60]}...")
                        send_message("lead", agent, task)
                        time.sleep(0.5)
                    
                    context.set_project("Demo Project", requirement)
                    print("\n✓ 所有任务已分配给Agent!\n")
        
        # 定期打印状态
        if iteration % 5 == 0:
            print("\n" + context.get_status() + "\n")
        
        time.sleep(2)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Lead Agent 停止")
        sys.exit(0)
