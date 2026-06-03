# Agent Team Demo — 多 Agent 协作开发系统

## 项目简介

Agent Team Demo 是一个基于 LLM 的**多智能体协作开发系统**。系统模拟一个真实的软件开发团队，由 5 个不同角色的 Agent 组成（Lead、Backend、Frontend、Test、DevOps），通过消息总线进行异步通信，自动完成从需求分析到代码生成的全栈开发流程。

核心特点：
- **每个 Agent 独立进程**运行，模拟团队中每个人都有独立的工作窗口
- **完全由 LLM 驱动**，Agent 在 ReAct（Reasoning + Acting）循环中自主决策每一步操作
- **任务依赖图**管理，保证执行顺序的正确性，支持级联解锁
- **三阶段工作流**：LLM 规划 → 人工审查 → 程序化执行，兼顾效率与安全
- **`ask_user` 人类介入机制**：Agent 遇到模糊需求时自动暂停，等待用户决策
- **多 LLM 后端支持**：通过 Anthropic 兼容 API 接入 DeepSeek、智谱、阿里百炼等
- **文件系统通信**，无需外部消息队列，通过 JSONL 文件传递消息，线程安全

---

## 四次迭代演进

### 迭代一：起步 — 简单的广播式多智能体 (v1.0)

**时间：** 2026年5月29日 - 5月30日

**核心思路：** 先搭起骨架，让多个 Agent 能"跑起来"。

这一阶段的目标是验证"多个 AI Agent 协作完成一个开发任务"这个想法是否可行。架构非常简单：

```
用户输入需求
    │
    ▼
Lead Agent（分析需求）
    │
    ├── 广播 → Backend Agent（生成 Flask API）
    ├── 广播 → Frontend Agent（生成 HTML 界面）
    ├── 广播 → Test Agent（生成测试代码）
    └── 广播 → DevOps Agent（生成部署配置）
```

**实现方式：**
- 每个 Agent 都是独立的 Python 文件，各自硬编码了 LLM 调用逻辑
- 通过 `shared_context.py` 实现简单的消息总线（基于 JSONL 文件）
- Lead Agent 收到需求后，一次性广播给所有 Worker Agent
- 所有 Worker **并行工作**，互不等待

**局限性：**
- ⚠️ 协同通信不完整：Worker 之间没有依赖关系，前端的生成不等待后端 API 规范，可能导致接口不匹配
- ⚠️ Worker Agent 内部逻辑固化：每个 Agent 的 LLM 交互方式各不相同，代码大量重复

**关键提交：**
| 提交 | 说明 |
|------|------|
| `dea3581` | Initial commit |
| `5f98750` | 添加 shared_context 消息总线 |
| `b51cc21` | 添加 Lead Agent 主编排器 |
| `0a72d95` | 添加全部 Agent 和文档，系统初具雏形 |
| `7039868` | 重写：为每个角色定制 LLM 驱动逻辑 |
| `86ccb2c` | 简化的多智能体协同（任务级通信尚未完成） |

---

### 迭代二：进化 — 任务依赖管理 (v2.0 / v2.1)

**时间：** 2026年5月31日

**核心思路：** 引入**任务依赖图**，让 Agent 按正确顺序协作。

v1.0 的最大问题是 Worker 之间没有先后顺序——前端可能在 API 规范出来之前就开始写代码，导致前后端不匹配。v2.0 解决了这个问题。

**关键变革：**

1. **TaskManager（任务依赖管理器）**
   - 维护每项任务的 `blockedBy`（前置依赖）和 `dependents`（反向依赖）
   - 任务完成后**自动级联解锁**下游任务
   - 支持 `is_ready()` / `claim()` / `update()` 等操作

2. **契约驱动的协作模式**
   - Backend Agent 先产出 `api_spec.json`（API 接口规范）
   - Frontend 和 Test 基于 `api_spec.json` 生成代码，保证接口一致性
   - 依赖规则：`backend → frontend/test → devops`

```
任务依赖图：

backend
   ├── frontend  (依赖 backend 的 api_spec.json)
   ├── test      (依赖 backend 的 api_spec.json)
   └── (frontend + test 都完成) → devops
```

3. **增强的 Worker Agent**
   - 每个 Worker 获得了更详细的 system prompt 和工作指引
   - Lead 的 ReAct 循环能生成结构化任务 JSON（包含依赖关系）

**v2.1 改进：** 进一步优化了 Worker Agent 的 prompt 和工作流程，强化了 API 文档生成和规范约束。

**关键提交：**
| 提交 | 说明 |
|------|------|
| `0080687` | v2.0：引入 TaskManager，7 个文件大规模重构 (+1266/-541) |
| `4f466fd` | v2.1：优化 Worker prompt 和工作流 (+738/-278) |

---

### 迭代三：升华 — ReAct + Tool Calling，真正的 Agent (v3.0)

**时间：** 2026年5月31日

**核心思路：** 将 Agent 从"固化逻辑"升华为"自主决策的智能体"。

v2.0 虽然解决了依赖问题，但每个 Agent 内部仍然有大量硬编码的工作流程。v3.0 做了一次彻底的架构重构，核心就是引入 **ReAct 循环** 和 **工具调用（Tool Calling）机制**。

**关键变革：**

1. **BaseAgent — 通用 Agent 基类**
   - 所有 Agent 继承自 `BaseAgent`，共享 ReAct 循环框架
   - 核心循环：`Observe → Plan → Act → Observe → ...`
   - 提供 7 个通用工具：`write_file`、`read_file`、`list_directory`、`send_message`、`read_inbox`、`ask_user`、`finish_task`
   - `ask_user` 是阻塞式用户交互工具：当 Agent 遇到模糊需求或关键决策时，暂停执行并等待用户输入
   - 子类只需重写 `get_system_prompt()` 和 `_setup_tools()`，不必关心执行流程

2. **纯工具 Agent 设计哲学**
   - 工具 handler 中**零 LLM 调用**——所有智能行为完全由 ReAct 循环中的 LLM 自主发起
   - LLM 在 ReAct 中自己决定：读什么文件、写什么代码、通知谁、何时结束、是否询问用户
   - 这是一种"工具是手脚，LLM 是大脑"的设计

3. **Anthropic 原生 Tool-Use**
   - 使用 Anthropic 兼容 API 的原生 tool_use 机制，LLM 返回结构化的工具调用请求
   - 相较于经典 ReAct（需正则解析文本中的 Action 标签），原生 Tool-Use 更可靠、更结构化
   - 支持通过 `ANTHROPIC_BASE_URL` 接入多种 LLM 后端（DeepSeek、智谱、阿里百炼等）

4. **代码量大幅减少**
   - v3.0 相比 v2.1：**删除 1698 行，新增仅 374 行**
   - 代码精简约 74%，但能力更强、更灵活

```
v3.0 ReAct 循环示意：

  ┌──────────────────────────────────┐
  │  BaseAgent.react_loop()          │
  │                                  │
  │  LLM (大脑)                      │
  │    │                             │
  │    ├── Plan: "我需要读取 api     │
  │    │   规范，然后生成前端代码..."  │
  │    │                             │
  │    ├── Act: tool_use →           │
  │    │   read_file("api_spec.json")│
  │    │   write_file("index.html")  │
  │    │   ask_user("用React还是Vue?")│
  │    │                             │
  │    ├── Observe: 查看工具返回结果  │
  │    │                             │
  │    └── 循环，直到 finish_task     │
  └──────────────────────────────────┘
```

**关键提交：**
| 提交 | 说明 |
|------|------|
| `4cf626d` | v3.0：引入 ReAct 循环和 Tool Calling，代码精简 74% |

---

### 迭代四：成熟 — 人工审查 + 安全护栏 (v4.0)

**时间：** 2026年6月1日 — 6月3日

**核心思路：** 在 LLM 自主决策和人工控制之间找到平衡点，确保任务编排的可靠性。

v3.0 的 Agent 已经能自主决策，但 Lead Agent 在分析需求后**直接创建并分发任务**——这意味着如果 LLM 对需求理解偏差，整个任务计划就会在无人审查的情况下执行。v4.0 通过引入**三阶段工作流**和**人工审查机制**解决了这个问题。

**关键变革：**

**1. Lead Agent 三阶段工作流**

```
Phase 1: 规划 (LLM 驱动)         Phase 2: 审查 (人工)          Phase 3: 执行 (程序化)
┌─────────────────────┐         ┌──────────────────┐         ┌──────────────────┐
│ LLM 分析需求         │         │ 展示任务计划       │         │ 批量创建任务       │
│ • 判断项目类型       │  ────→  │ • 角色、主题       │  ────→ │ 设置依赖关系       │
│ • 选择需要的角色     │         │ • 依赖关系         │         │ 自动分发就绪任务   │
│ • ask_user 确认      │         │ y=批准 / n=拒绝    │         │ 事件循环监控       │
│ • submit_plan 提交   │         │ m=修改后重新规划   │         │ (无 LLM 参与)     │
└─────────────────────┘         └──────────────────┘         └──────────────────┘
```

- **Phase 1（planning_phase）**：LLM 通过 ReAct 循环分析需求，可调用 `ask_user` 确认模糊点，最终调用 `submit_plan` 提交换器化的任务计划 JSON
- **Phase 2（review_phase）**：任务计划展示给用户，用户可选择批准（y）、拒绝（n）或修改后重试（m）。修改时会带上用户的反馈重新走 Phase 1
- **Phase 3（execution_phase）**：**完全程序化**执行——批量创建任务、设置依赖、分发就绪任务。无 LLM 参与，避免模型幻觉导致的误操作

**2. submit_plan 工具 — 任务计划的结构化提交**

LLM 通过该工具提交标准化的 JSON 计划：
```json
{
  "project_name": "用户管理系统",
  "tasks": [
    {"role": "backend",  "subject": "设计 REST API 并实现后端", "depends_on": []},
    {"role": "frontend", "subject": "实现管理页面前端",         "depends_on": ["backend"]},
    {"role": "test",     "subject": "编写 API 测试用例",        "depends_on": ["backend"]},
    {"role": "devops",   "subject": "编写项目 README 文档",     "depends_on": ["frontend", "test"]}
  ]
}
```

该工具的 handler **不立即创建任务**，而是暂存计划等待人工审查。

**3. ask_user — 模糊需求的人类介入**

当 Agent 遇到以下情况时，通过 `ask_user` 暂停执行并等待用户输入：
- 需求描述模糊、有歧义
- 技术选型存在多种合理方案（如"用 React 还是 Vue？"）
- 任务拆分方案涉及关键取舍

用户的回复会直接返回给 LLM，继续 ReAct 循环。这种设计让人类成为 Agent 协作的一部分，而非纯旁观者。

**4. 多 LLM 后端支持**

通过 `.env` 中的 `ANTHROPIC_BASE_URL` 配置，支持接入多种 LLM 服务商：
| 服务商 | 模型 | BASE_URL |
|--------|------|----------|
| DeepSeek | deepseek-v4-flash | `https://api.deepseek.com/anthropic` |
| 智谱 AI | GLM-4.7-Flash | `https://open.bigmodel.cn/api/anthropic` |
| 阿里百炼 | qwen3.6-flash | `https://dashscope.aliyuncs.com/apps/anthropic` |

**5. 若干 Bug 修复**
- 修复 `raw_arguments` 嵌套兼容问题：部分 LLM 将参数包装在 `raw_arguments` 字段中，增加了 JSON 解析兼容逻辑
- 修复 `finish_task` 后继续轮询的问题：Worker 完成任务后正确汇报状态并退出
- 优化消息截断和工具输出显示

**关键提交：**
| 提交 | 说明 |
|------|------|
| `b6a86d9` | v4.0：人工审查机制 + ask_user 工具 + 多后端适配 + Bug 修复（9 文件 +381/-191） |

---

## 架构总览

### Agent 角色

| Agent | 角色 | 产出 | 关键工具 |
|-------|------|------|----------|
| **Lead** | 主编排者 | 需求分析 → 人工审查 → 任务分发 → 监控 | `submit_plan`、`ask_user`、`finish_task` |
| **Backend** | 后端工程师 | `api_spec.json`、`app.py`（Flask）、`requirements.txt` | 全部 7 个通用工具 |
| **Frontend** | 前端工程师 | `index.html`（内嵌 CSS + JS 的单页应用） | 全部 7 个通用工具 |
| **Test** | 测试工程师 | `tests/test_api.py`（unittest） | 全部 7 个通用工具 |
| **DevOps** | 文档工程师 | `README.md`（项目文档） | 全部 7 个通用工具 |

### 通信架构

```
                  用户 / send_requirement.py
                         │
                         ▼
              ┌──────────────────────────────────────┐
              │    Lead Agent v5.0 (三阶段)           │
              │                                      │
              │  Phase 1: react_loop() → LLM 分析    │
              │           → ask_user 模糊确认         │
              │           → submit_plan 提交计划      │
              │                                      │
              │  Phase 2: 人工审查 (y=批准/n=拒绝     │
              │           /m=修改后重试)              │
              │                                      │
              │  Phase 3: 程序化创建任务 → 分发       │
              │  事件循环 → 监控 Worker → 级联解锁    │
              └──────────────────┬───────────────────┘
                                 │ BUS.send(msg_type="task")
        ┌────────────────────────┼──────────────────────────┐
        ▼                        ▼                ▼         ▼
   Backend                  Frontend           Test     DevOps
    Agent                    Agent             Agent     Agent
   (ReAct)                  (ReAct)           (ReAct)   (ReAct)
        │                        │                │         │
        └────────────────────────┴────────────────┴─────────┘
                                 │ BUS.send(msg_type="status") → Lead
```

### 任务依赖规则

```
backend（无依赖，最先执行）
   ├── frontend（依赖 backend，等待 api_spec.json）
   ├── test（依赖 backend，等待 api_spec.json）
   └── devops（依赖 frontend + test 都完成）
```

### Lead Agent 三阶段工作流详解

Lead Agent 是整个系统的核心编排器，v5.0 采用三阶段设计：

**Phase 1 — 规划阶段（`_planning_phase`）**
- 将用户需求包装为 prompt 传入 ReAct 循环
- LLM 在循环中分析需求，可通过 `ask_user` 确认模糊点
- 最终调用 `submit_plan` 提交换机化的 JSON 任务计划
- 任务计划暂存于 `_submitted_plan`，不立即执行

**Phase 2 — 审查阶段（`_review_phase`）**
- 格式化展示所有任务：角色、主题、依赖关系、描述摘要
- 用户三种选择：
  - `y`：批准，进入执行阶段
  - `n`：拒绝，放弃该计划
  - `m`：修改，输入补充需求，系统带上反馈重新走 Phase 1

**Phase 3 — 执行阶段（`_execution_phase`）**
- **纯程序化操作，无 LLM 参与**（避免模型幻觉导致误操作）
- 批量创建任务 → 设置依赖关系 → 分发就绪任务
- 进入事件循环：每 2 秒轮询 Worker 的 status 汇报
- Worker 完成任务 → `mark_task_done` → `dispatch_ready_tasks`（级联解锁并分发新任务）
- 所有任务完成后输出总结

---

## 核心技术栈

- **LLM：** Anthropic 兼容 API（通过 `ANTHROPIC_BASE_URL` 接入 DeepSeek / 智谱 / 阿里百炼等多后端）
- **工具调用：** Anthropic 原生 Tool-Use（结构化 `tool_use` block，非文本解析式 ReAct）
- **语言：** Python 3.8+
- **通信：** 基于 JSONL 文件的消息总线（线程安全，无需外部消息队列）
- **任务管理：** DAG 有向无环图依赖管理器（自动级联解锁）
- **设计模式：** 模板方法、ReAct 循环、工具注册表、单例、编排器
- **人工介入：** `ask_user` 阻塞式交互 + Phase 2 人工审查机制

---

## 关键设计决策

| 决策 | 说明 |
|------|------|
| **工具 handler 零 LLM 调用** | handler 只做纯操作（读写文件、发消息），推理完全由 ReAct 循环中的 LLM 完成 |
| **Phase 3 纯程序化** | 任务创建和分发不经过 LLM，避免模型幻觉导致的误操作 |
| **文件系统而非消息队列** | JSONL 文件简单可靠，无需部署 RabbitMQ/Kafka，适合单机多进程场景 |
| **Anthropic 原生 Tool-Use** | 比经典 ReAct（解析文本 Action 标签）更可靠，结构性更强 |
| **人工审查在任务创建前** | 在 LLM 和程序化执行之间插入人类决策点，兼具效率和安全 |

---

## 总结

| 迭代 | 核心能力 | 主要局限 | 关键提交 |
|------|---------|---------|----------|
| **v1.0** | 多个 Agent 并行工作，广播式协作 | 无依赖管理，前端/后端可能不匹配 | `dea3581` ~ `86ccb2c` |
| **v2.0** | 任务依赖图，契约驱动，按序执行 | Agent 内部逻辑固化，代码量大 | `0080687`、`4f466fd` |
| **v3.0** | ReAct 循环 + Tool Calling，Agent 自主决策 | 无人工审查，LLM 误判可能直接执行 | `4cf626d` |
| **v4.0** | 三阶段工作流 + 人工审查 + ask_user 交互 | — | `b6a86d9` |

整个项目的演进脉络清晰体现了从"能跑起来"→"正确运行"→"优雅运行"→"安全运行"的四段式进化。

- **v1.0** 验证了"多 Agent 协作"的可行性
- **v2.0** 引入任务依赖图，解决了协作的**正确性**
- **v3.0** 通过 ReAct + Tool Calling，让每个 Agent 成为**真正的自主智能体**
- **v4.0** 引入人工审查机制，在**效率与安全**之间找到平衡点——LLM 负责"提方案"，人类负责"拍板"
