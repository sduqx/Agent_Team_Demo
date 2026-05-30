#!/bin/bash
echo "========================================================================"
echo "🚀 多Agent团队启动脚本"
echo "========================================================================"
echo ""
echo "正在启动5个Agent工作线程..."
echo ""

# 启动Lead Agent
echo "✓ 正在启动 Lead Agent (主控)..."
python lead_agent.py &
sleep 2

# 启动Backend Agent
echo "✓ 正在启动 Backend Agent (后端开发)..."
python backend_agent.py &
sleep 1

# 启动Frontend Agent
echo "✓ 正在启动 Frontend Agent (前端开发)..."
python frontend_agent.py &
sleep 1

# 启动Test Agent
echo "✓ 正在启动 Test Agent (测试)..."
python test_agent.py &
sleep 1

# 启动DevOps Agent
echo "✓ 正在启动 DevOps Agent (部署)..."
python devops_agent.py &

echo ""
echo "========================================================================"
echo "✅ 所有Agent已启动！"
echo "========================================================================"
echo ""
echo "📋 使用说明:"
echo "   1. 在 Lead Agent 窗口输入你的项目需求"
echo "   2. 其他Agent会自动分配任务并完成工作"
echo "   3. 所有生成的代码在 .project 目录中"
echo "   4. 状态信息保存在 .team/shared/project.json"
echo ""
echo "Ctrl+C 停止所有Agent"
echo ""

# 等待所有后台进程
wait
