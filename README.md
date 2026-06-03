# Agent Team Demo — 多 Agent 协作开发系统

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> **本文档是快速启动指南。**  
> 📘 详细项目介绍与架构设计 → [`doc/Agent_team_demo.md`](doc/Agent_team_demo.md)  
> 📋 开发过程与作业报告 → [`doc/报告.md`](doc/报告.md)

## 📋 项目概述

一个基于 LLM 的**多智能体协作开发系统**，模拟真实软件开发团队：5 个不同角色的 Agent（Lead、Backend、Frontend、Test、DevOps）通过消息总线异步通信，自动完成从需求分析到代码生成的全栈开发流程。

### 🎯 核心特性

- **5 个独立 Agent 进程**，每个 Agent 在 ReAct 循环中自主决策
- **三阶段工作流**：LLM 规划 → 人工审查 → 程序化执行
- **`ask_user` 人类介入**：Agent 遇模糊需求时自动暂停，等待用户决策
- **Anthropic 原生 Tool-Use**：结构化工具调用，比文本解析式 ReAct 更可靠
- **多 LLM 后端**：支持 DeepSeek / 智谱 / 阿里百炼等
- **任务依赖图**：DAG 管理，支持级联解锁，保证执行顺序
- **文件系统通信**：JSONL 消息总线，无需外部消息队列

## 🏗️ 工作流

```
用户输入需求
    │
    ▼
┌─ Phase 1：LLM 规划 ───────────────────┐
│  Lead Agent 分析需求 → ask_user 确认   │
│  → submit_plan 提交结构化任务计划      │
└──────────────┬────────────────────────┘
               ▼
┌─ Phase 2：人工审查 ───────────────────┐
│  展示计划（角色/主题/依赖）            │
│  y=批准 / n=拒绝 / m=修改后重新规划     │
└──────────────┬────────────────────────┘
               ▼
┌─ Phase 3：程序化执行（无 LLM）─────────┐
│  创建任务 → 设置依赖 → 分发就绪任务     │
│  事件循环监控 → 级联解锁 → 汇总输出     │
└──────────────────────────────────────┘
               │
    ┌──────────┼──────────┬──────────┐
    ▼          ▼          ▼          ▼
 Backend    Frontend    Test      DevOps
  Agent      Agent      Agent      Agent
 (ReAct)    (ReAct)    (ReAct)    (ReAct)
```

### 任务依赖规则

```
backend（无依赖，最先执行 → 产出 api_spec.json）
   ├── frontend（依赖 backend）
   ├── test（依赖 backend）
   └── devops（依赖 frontend + test 都完成）
```

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

Windows 双击 `run_team.bat` 或：

```powershell
.\run_team.bat
```

Linux/Mac：

```bash
chmod +x run_team.sh && ./run_team.sh
```

### 4. 提交需求

启动后在 **Lead Agent** 窗口直接输入需求，例如：

```
帮我构建一个用户管理系统，支持增删改查
```

或通过 `send_requirement.py` 提交：

```bash
python send_requirement.py
```

系统会自动完成：需求分析 → 人工审查任务计划 → Worker Agent 协作开发 → 代码生成。

生成的项目代码保存在 `.project/` 目录中。

## 📁 项目结构

```
Agent_Team_Demo/
├── agent_base.py           # Agent 基类（ReAct 循环 + Tool 注册 + LLM 调用）
├── lead_agent.py           # Lead 主控 Agent（三阶段工作流）
├── backend_agent.py        # Backend 开发 Agent
├── frontend_agent.py       # Frontend 开发 Agent
├── test_agent.py           # Test 测试 Agent
├── devops_agent.py         # DevOps/文档 Agent
├── shared_context.py       # 共享通信模块（消息总线 + 任务管理器）
├── send_requirement.py     # 需求提交脚本
├── self_cc.py              # 单 Agent 参考实现
├── run_team.bat / .sh      # 启动脚本
├── requirements.txt        # Python 依赖
├── .env                    # LLM 配置（需自行创建）
├── doc/                    # 📘 文档目录
│   ├── Agent_team_demo.md  # 详细项目介绍（架构、迭代演进）
│   └── 报告.md              # 开发过程与作业报告
└── .project/               # 生成的项目代码（运行后创建）
```

## 🔧 Agent 角色

| Agent | 角色 | 产出 | 专属工具 |
|-------|------|------|----------|
| **Lead** | 主编排者 | 需求分析 → 人工审查 → 任务分发 → 监控 | `submit_plan`、`ask_user` |
| **Backend** | 后端工程师 | `api_spec.json`、`app.py`（Flask）、`requirements.txt` | 全部 7 个通用工具 |
| **Frontend** | 前端工程师 | `index.html`（内嵌 CSS + JS 单页应用） | 全部 7 个通用工具 |
| **Test** | 测试工程师 | `tests/test_api.py`（unittest） | 全部 7 个通用工具 |
| **DevOps** | 文档工程师 | `README.md`（项目文档） | 全部 7 个通用工具 |

每个 Worker Agent 均继承 `BaseAgent`，共享 ReAct 循环和 7 个通用工具：`write_file`、`read_file`、`list_directory`、`send_message`、`read_inbox`、`ask_user`、`finish_task`。

## 🎯 使用示例

启动后，在 Lead Agent 窗口输入：

```
构建一个TODO应用，支持增删改查任务
```

流程：
1. Lead Agent 分析需求 → 确认模糊点 → 提交任务计划
2. 人工审查：展示计划 → 批准（y）
3. 程序化执行：
   - Backend Agent 创建 Flask REST API + `api_spec.json`
   - Frontend Agent 基于 API 规范创建 HTML 界面
   - Test Agent 创建 unittest 测试用例
   - DevOps Agent 创建项目文档
4. 所有代码输出到 `.project/`

## ⚠️ 常见问题

### API 调用失败

确认 `.env` 中的 `ANTHROPIC_API_KEY` 和 `ANTHROPIC_BASE_URL` 配置正确。

### Worker 无响应

确认 `run_team.bat` 启动时所有窗口正常打开，检查 `.team/inbox/` 中的消息日志。

### Python 版本问题

```bash
python --version  # 确认 Python 3.8+
```

## 📚 详细文档

| 文档 | 内容 |
|------|------|
| [`doc/Agent_team_demo.md`](doc/Agent_team_demo.md) | 完整项目介绍：四次迭代演进、架构总览、通信机制、Agent 详解、关键设计决策 |
| [`doc/报告.md`](doc/报告.md) | 开发过程记录：基于 paperclip 的初步探索 → 自主开发 Agent Team 的全过程 |

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📄 许可证

MIT License

---

**版本**: v4.0 | **最后更新**: 2026-06-03
