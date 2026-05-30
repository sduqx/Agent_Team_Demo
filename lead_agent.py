#!/usr/bin/env python3
"""
Lead Agent - 主控Agent
负责：接收需求、分析、分配任务
"""

import sys
import time
from pathlib import Path
from shared_context import SharedContext, send_message, read_messages

context = SharedContext()
PROJECT_DIR = Path.cwd() / ".project"
PROJECT_DIR.mkdir(exist_ok=True)


def main():
    print("=" * 70)
    print("👔 Lead Agent 已启动")
    print("=" * 70)
    print("\n等待需求输入或任务完成通知...\n")
    
    iteration = 0
    
    while True:
        iteration += 1
        
        # 读取消息
        messages = read_messages("lead")
        
        for msg in messages:
            print(f"\n📬 收到来自 {msg['from']} 的消息:")
            print(f"   {msg['content']}\n")
            
            # 如果是项目需求（来自外部），分配任务
            if msg['from'] == "system" and "requirement:" in msg['content'].lower():
                requirement = msg['content'].replace("requirement:", "").strip()
                
                print(f"📊 分析需求: {requirement}\n")
                
                # 分配任务给各Agent
                tasks = {
                    "backend": f"创建Flask REST API来实现: {requirement}",
                    "frontend": f"创建HTML/Vue前端界面来实现: {requirement}",
                    "test": f"为这个功能编写测试: {requirement}",
                    "devops": f"创建部署配置和文档: {requirement}"
                }
                
                for agent, task in tasks.items():
                    send_message("lead", agent, task)
                    print(f"✓ 已分配任务给 {agent}")
                    time.sleep(0.5)
                
                context.set_project("Demo Project", requirement)
                print("\n✓ 所有任务已分配！\n")
        
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
