#!/usr/bin/env python3
"""
向Lead Agent发送需求 - v2.0（使用增强MessageBus）
"""

from shared_context import BUS

if __name__ == "__main__":
    print("=" * 70)
    print("📝 需求提交系统 v2.0")
    print("=" * 70)
    print()
    print("💡 提示: 提交需求后，Lead Agent 会自动分析并创建带依赖关系的任务图")
    print("   后端 → 前端/测试 → DevOps (按依赖顺序执行)")
    print()

    requirement = input("请输入你的项目需求: ").strip()

    if requirement:
        BUS.send(
            sender="system",
            to="lead",
            content=f"requirement: {requirement}",
            msg_type="requirement"
        )
        print(f"\n✓ 需求已发送给 Lead Agent")
        print("\n📋 预期的执行顺序:")
        print("   1️⃣ Backend Agent - 创建 API，发布 API 规范")
        print("   2️⃣ Frontend Agent - 等待 API 规范 → 生成匹配的前端")
        print("   2️⃣ Test Agent - 等待 API 规范 → 生成匹配的测试")
        print("   3️⃣ DevOps Agent - 等待前端和测试完成 → 生成部署配置")
        print(f"\n📁 生成的代码将保存在 .project/ 目录中")
        print(f"📊 任务状态: .team/tasks/ 目录")
        print(f"💬 Agent 通信日志: .team/inbox/ 目录（通信后自动清空）")
    else:
        print("\n❌ 需求不能为空")
