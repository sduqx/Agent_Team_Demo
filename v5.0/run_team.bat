@echo off
chcp 65001 >nul
echo.
echo ========================================================================
echo   Multi-Agent Team v5.0 — 动态技术栈 + 自动团队孵化
echo ========================================================================
echo.
echo   [INFO] v5.0 相比 v4.0 的核心升级:
echo     1. 不再预设固定技术栈（Python+Flask），由 LLM 按需选择
echo     2. 不再预设固定团队，LLM 根据需求组建角色
echo     3. 计划批准后自动孵化 Worker 进程
echo.
echo ========================================================================
echo   正在启动 Lead Agent...
echo ========================================================================

REM v5.0 只需启动 Lead Agent，Worker 由 Lead 自动孵化
start "Lead Agent v5.0" python -m src.lead_agent

echo.
echo ========================================================================
echo   Lead Agent v5.0 已启动！
echo ========================================================================
echo.
echo   使用说明:
echo   1. 在 Lead Agent 窗口输入项目需求（支持任意技术栈）
echo   2. Lead 将分析需求并生成任务计划
echo   3. 审查计划后按 y 批准，Worker 会自动孵化
echo   4. 所有产物在 .project 目录
echo.
echo   需求示例:
echo     "做一个 React + Go 的任务管理Web应用"
echo     "做一个 Flutter 跨平台日记App，后端用 FastAPI"
echo     "做一个纯后端的用户认证微服务，用 Node.js Express"
echo     "做一个 Vue3 + Java Spring Boot 的员工管理系统"
echo.
pause
