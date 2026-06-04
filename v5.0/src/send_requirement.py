#!/usr/bin/env python3
"""
向 Lead Agent v2.0 发送需求。
支持两种方式:
  1. 直接运行此脚本交互式输入
  2. 在 Lead Agent 窗口直接输入需求（推荐）
"""

from .shared_context import BUS

if __name__ == "__main__":
    print("=" * 70)
    print("[INPUT] 需求提交系统 v2.0")
    print("=" * 70)
    print()
    print("[TIP] 推荐方式: 直接在 Lead Agent 窗口输入需求（支持交互式输入）")
    print("[TIP] 备选方式: 在此窗口输入需求，通过消息总线发送")
    print()
    print("   v2.0 特性: Lead 将根据需求自主决定技术栈和团队构成")
    print("   支持的示例需求:")
    print('     "做一个 React + Go 的任务管理Web应用"')
    print('     "做一个 Flutter 跨平台日记App"')
    print('     "做一个纯后端的微服务，用 Node.js Express"')
    print()

    requirement = input("[INPUT] 请输入项目需求（直接回车退出）: ").strip()

    if requirement:
        BUS.send(
            sender="system",
            to="lead",
            content=f"requirement: {requirement}",
            msg_type="requirement"
        )
        print(f"\n[OK] 需求已发送给 Lead Agent v2.0")
        print(f"[WAIT] 请查看 Lead Agent 窗口以审查计划和跟踪进度...")
    else:
        print("\n[FAIL] 需求不能为空")
        print("[TIP] 你也可以直接在 Lead Agent 窗口输入需求")
