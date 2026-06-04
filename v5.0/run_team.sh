#!/usr/bin/env bash
# Multi-Agent Team v5.0 启动脚本 (Linux/macOS)
# 只需启动 Lead Agent，Worker 由 Lead 自动孵化

echo ""
echo "================================================================"
echo "  Multi-Agent Team v5.0 — 动态技术栈 + 自动团队孵化"
echo "================================================================"
echo ""
echo "  [INFO] v5.0 相比 v4.0 的核心升级:"
echo "    1. 不再预设固定技术栈（Python+Flask），由 LLM 按需选择"
echo "    2. 不再预设固定团队，LLM 根据需求组建角色"
echo "    3. 计划批准后自动孵化 Worker 进程"
echo ""
echo "================================================================"
echo "  正在启动 Lead Agent..."
echo "================================================================"

cd "$(dirname "$0")"

# v5.0 只需启动 Lead Agent，Worker 由 Lead 自动孵化
python -m src.lead_agent

echo ""
echo "Lead Agent v2.0 已退出。"
