#!/usr/bin/env python3
"""
向Lead Agent发送需求
"""

from shared_context import send_message

if __name__ == "__main__":
    print("="*70)
    print("📝 需求提交系统")
    print("="*70)
    print()
    
    requirement = input("请输入你的项目需求: ").strip()
    
    if requirement:
        send_message("system", "lead", f"requirement: {requirement}")
        print(f"\n✓ 需求已发送给Lead Agent")
        print("\n请查看各个Agent窗口的执行进度...")
        print(f"生成的代码将保存在 .project/ 目录中")
    else:
        print("\n❌ 需求不能为空")
