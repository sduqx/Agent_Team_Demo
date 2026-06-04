# Agent Team Demo — 多 Agent 协作开发系统

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> **本文档是项目总入口和快速启动指南。**  
> 📘 完整项目介绍与架构演进 → [`docs/architecture.md`](docs/architecture.md)  
> 📋 开发过程与作业报告 → [`docs/report.md`](docs/report.md)  
> 🤖 AI 工具使用详情 → [`docs/ai-usage-log.md`](docs/ai-usage-log.md)

---

## 📋 项目概述

一个基于 LLM 的**多智能体协作开发系统**，模拟真实软件开发团队：多个不同角色的 Agent（Lead + 动态 Worker）通过消息总线异步通信，自动完成从需求分析到代码生成的全栈开发流程。

**当前版本：v5.0 — 通用多 Agent 协作框架**，核心技术栈不受限制，LLM 自主选择任何语言/框架组合。

### 🎯 核心特性

- **通用 Worker Agent**：1 个文件替代 N 个固定角色，通过 CLI 参数动态注入技术栈
- **不限技术栈**（v5.0）：LLM 自主选择 React/Vue/Flutter/Go/Java/Node.js 等任意组合
- **Lead 自动孵化 Worker**：计划批准后自动创建终端窗口运行 Worker 进程
- **三层产出验证**：Worker 自验证 → Lead 自动验收 → 人工审查
- **三阶段工作流**：LLM 规划 → 人工审查 → 程序化执行
- **`ask_user` 人类介入**：Agent 遇模糊需求时自动暂停，等待用户决策
- **Anthropic 原生 Tool-Use**：结构化工具调用，比文本解析式 ReAct 更可靠
- **多 LLM 后端**：支持 DeepSeek / 智谱 / 阿里百炼等
- **任务依赖图**：DAG 管理，支持级联解锁，保证执行顺序
- **文件系统通信**：JSONL 消息总线，无需外部消息队列

---

## 🚀 快速开始

### 前置条件

- Python 3.8+
- 可用的 LLM API Key（支持 Anthropic 兼容接口的服务商）

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

创建 `.env` 文件：

```bash
ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic    # 或其他兼容后端
ANTHROPIC_API_KEY=your_api_key_here
MODEL_ID=deepseek-v4-flash
```

支持的 LLM 后端：

| 服务商 | BASE_URL | 模型示例 |
|--------|----------|----------|
| DeepSeek | `https://api.deepseek.com/anthropic` | `deepseek-v4-flash` |
| 智谱 AI | `https://open.bigmodel.cn/api/anthropic` | `GLM-4.7-Flash` |
| 阿里百炼 | `https://dashscope.aliyuncs.com/apps/anthropic` | `qwen3.6-flash` |

### 3. 启动 Team

#### v5.0（推荐 — 通用框架）

```bash
cd v5.0

# Windows
.\run_team.bat

# Linux/Mac
bash run_team.sh
```

只启动 Lead Agent，Worker 由 Lead 自动孵化。

#### v4.0（经典 — 固定 Python Flask 技术栈）

```bash
# Windows
.\run_team.bat

# Linux/Mac
bash run_team.sh
```

手动启动 5 个 Agent 进程。

### 4. 提交需求

启动后在 **Lead Agent** 窗口直接输入需求：

```bash
# v5.0 — 支持任意技术栈
做一个 React + Go Gin 的博客系统
做一个 Flutter 跨平台日记 App，后端用 FastAPI

# v4.0 — Python Flask + HTML 全栈
帮我构建一个用户管理系统，支持增删改查
```

系统会自动完成：需求分析 → 人工审查任务计划 → Worker Agent 协作开发 → 代码生成。

---

## 📁 项目结构

```
Agent_Team_Demo/
├── src/                         # v4.0 代码（固定 5 角色 Agent）
│   ├── agent_base.py            # BaseAgent（ReAct 循环 + Tool 注册 + LLM 调用）
│   ├── lead_agent.py            # Lead 主控 Agent（三阶段工作流）
│   ├── backend_agent.py         # Backend 开发 Agent（Flask）
│   ├── frontend_agent.py        # Frontend 开发 Agent（HTML/JS）
│   ├── test_agent.py            # Test 测试 Agent（unittest）
│   ├── devops_agent.py          # DevOps 文档 Agent
│   └── shared_context.py        # 共享通信模块（消息总线 + 任务管理器）
│
├── v5.0/                        # v5.0 代码（通用框架）
│   ├── src/
│   │   ├── agent_base.py        # BaseAgent v2.0（8 工具 + run_command）
│   │   ├── shared_context.py    # 消息总线 + expectedFiles 验证
│   │   ├── lead_agent.py        # Lead Agent v2.0（动态技术栈 + Worker 孵化）
│   │   ├── worker_agent.py      # 🌟 通用 Worker Agent（唯一通用文件）
│   │   └── send_requirement.py  # 需求发送工具
│   ├── run_team.bat / .sh       # 启动脚本
│   ├── README.md                # v5.0 说明
│   └── 更新说明.md / 测试验证指南.md
│
├── docs/                        # 📘 统一文档目录
│   ├── architecture.md          # 完整项目介绍（五次迭代演进）
│   ├── report.md                # 开发过程与作业报告
│   ├── agent-design.md          # Agent System Prompt 设计（v4.0 + v5.0）
│   ├── ai-usage-log.md          # AI 工具使用详细记录
│   ├── v5.0-overview.md         # v5.0 快速入门
│   ├── v5.0-changelog.md        # v5.0 版本更新说明
│   ├── v5.0-verification.md     # 三层验证体系详细文档
│   └── img/                     # 文档截图
│
├── run_team.bat / .sh           # v4.0 启动脚本
├── send_requirement.py          # v4.0 需求提交脚本
├── requirements.txt             # Python 依赖
└── .env                         # LLM 配置（需自行创建）
```

## 🔧 v4.0 vs v5.0 对比

| 维度 | v4.0 | v5.0 |
|------|------|------|
| **技术栈** | 固定 Python Flask + HTML/JS | **任意语言/框架** |
| **Worker 数量** | 4 个固定角色 | **LLM 按需决定** |
| **Worker 文件** | 4 个独立 `.py` 文件 | **1 个通用文件** |
| **新增角色** | 需写新 Agent 文件 | **只需新 CLI 参数** |
| **启动方式** | 手动启动 5 个进程 | **只启 Lead，自动孵化** |
| **质量验证** | 无 | **三层防线** |
| **max_rounds** | 6~15 | **50**（自验证需求） |
| **适用场景** | Python Web 全栈 | **任何软件项目** |

---

## 🎯 使用示例

### v5.0 示例

```bash
cd v5.0 && .\run_team.bat
# 输入：做一个 React + Go Gin 的待办事项管理系统
# Lead 分析 → 推荐技术栈 → 人工审查(y) → 自动孵化 3 个 Worker → 协作完成
```

### v4.0 示例

```bash
.\run_team.bat
# 输入：构建一个TODO应用，支持增删改查任务
# Lead 分析 → 人工审查(y) → Backend/Frontend/Test/DevOps 协作开发
```

流程：
1. Lead Agent 分析需求 → 确认模糊点 → 提交任务计划
2. 人工审查：展示计划 → 批准（y）
3. 程序化执行：
   - Worker Agent 根据角色生成代码
   - 所有代码输出到 `.project/`

---

## ⚠️ 常见问题

### API 调用失败

确认 `.env` 中的 `ANTHROPIC_API_KEY` 和 `ANTHROPIC_BASE_URL` 配置正确。

### Worker 无响应

确认启动脚本正常打开了所有 Agent 窗口，检查 `.team/inbox/` 中的消息日志。

### v5.0 Worker 没有自验证

检查 Worker 窗口日志是否调用了 `run_command`，确保 System Prompt 中包含验证要求。

### Python 版本问题

```bash
python --version  # 确认 Python 3.8+
```

---

## 📚 文档导航

| 文档 | 内容 |
|------|------|
| [`docs/architecture.md`](docs/architecture.md) | 🏗️ 完整项目介绍：五次迭代演进、架构总览、通信机制、关键设计决策 |
| [`docs/report.md`](docs/report.md) | 📋 开发过程记录：paperclip 探索 → v1.0~v5.0 开发全过程 |
| [`docs/agent-design.md`](docs/agent-design.md) | 🧠 Agent System Prompt 设计文档（v4.0 固定角色 + v5.0 通用 Worker） |
| [`docs/ai-usage-log.md`](docs/ai-usage-log.md) | 🤖 AI 工具使用详细记录：关键 Prompt、对话片段、反思总结 |
| [`docs/v5.0-overview.md`](docs/v5.0-overview.md) | 🚀 v5.0 快速入门（动态技术栈 + 自动孵化 + 三层验证） |
| [`docs/v5.0-changelog.md`](docs/v5.0-changelog.md) | 📝 v5.0 版本更新说明（完整的架构重构记录） |
| [`docs/v5.0-verification.md`](docs/v5.0-verification.md) | ✅ 三层产出验证体系：Worker 自验证 → Lead 验收 → 人工审查 |

---

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📄 许可证

MIT License

---

**当前版本**: v5.0 | **最后更新**: 2026-06-04
