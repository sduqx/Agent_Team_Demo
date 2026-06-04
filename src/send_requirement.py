#!/usr/bin/env python3
"""
向Lead Agent发送需求 - v2.1
支持两种方式:
  1. 直接运行此脚本，交互式输入需求
  2. 在 Lead Agent 窗口直接输入需求（推荐）
"""

from .shared_context import BUS

if __name__ == "__main__":
    print("=" * 70)
    print("[INPUT] 需求提交系统 v2.1")
    print("=" * 70)
    print()
    print("[TIP] 提示:")
    print("   • 推荐方式: 直接在 Lead Agent 窗口输入需求（支持交互式输入）")
    print("   • 备选方式: 在此窗口输入需求，通过消息总线发送给 Lead Agent")
    print()
    print("   Lead Agent 会自动分析需求 -> 创建任务依赖图 -> 按序分配:")
    print("   1. Backend Agent - 生成 API + 发布完整 API 契约")
    print("   2. Frontend Agent - 等待 API 契约 -> 生成匹配的前端")
    print("   3. Test Agent - 等待 API 契约 -> 生成匹配的测试")
    print("   4. DevOps Agent - 等待前端+测试完成 -> 生成部署配置")
    print()

    requirement = input("[INPUT] 请输入你的项目需求（直接回车退出）: ").strip()

    if requirement:
        BUS.send(
            sender="system",
            to="lead",
            content=f"requirement: {requirement}",
            msg_type="requirement"
        )
        print(f"\n[OK] 需求已发送给 Lead Agent")
        print(f"\n[DIR] 生成的代码将保存在 .project/ 目录中")
        print(f"[STATUS] 任务状态: .team/tasks/ 目录")
        print(f"[LOG] Agent 通信日志: .team/inbox/ 目录（通信后自动清空）")
        print(f"\n[WAIT] 请查看各 Agent 窗口的输出以跟踪进度...")
    else:
        print("\n[FAIL] 需求不能为空")
        print("[TIP] 提示: 你也可以直接在 Lead Agent 的窗口输入需求")
