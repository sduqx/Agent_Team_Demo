@echo off
chcp 65001 >nul
echo.
echo ========================================================================
echo 🚀 多Agent团队启动脚本
echo ========================================================================
echo.
echo 正在启动5个Agent工作线程...
echo.

REM 启动Lead Agent
echo ✓ 正在启动 Lead Agent (主控)...
start "Lead Agent" python lead_agent.py

timeout /t 2 /nobreak

REM 启动Backend Agent
echo ✓ 正在启动 Backend Agent (后端开发)...
start "Backend Agent" python backend_agent.py

timeout /t 1 /nobreak

REM 启动Frontend Agent
echo ✓ 正在启动 Frontend Agent (前端开发)...
start "Frontend Agent" python frontend_agent.py

timeout /t 1 /nobreak

REM 启动Test Agent
echo ✓ 正在启动 Test Agent (测试)...
start "Test Agent" python test_agent.py

timeout /t 1 /nobreak

REM 启动DevOps Agent
echo ✓ 正在启动 DevOps Agent (部署)...
start "DevOps Agent" python devops_agent.py

echo.
echo ========================================================================
echo ✅ 所有Agent已启动！
echo ========================================================================
echo.
echo 📋 使用说明:
echo   1. 在 Lead Agent 窗口输入你的项目需求
echo   2. 其他Agent会自动分配任务并完成工作
echo   3. 所有生成的代码在 .project 目录中
echo   4. 状态信息保存在 .team/shared/project.json
echo.
echo 📁 查看日志:
echo   - 查看共享状态: 打开 .team/shared/project.json
echo   - 查看生成代码: 打开 .project 目录
echo.
pause
