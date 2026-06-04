# Agent Team Demo — 开发报告

> **作者**：全鑫  
> **项目仓库**：[Agent_Team_Demo](https://github.com/sduqx/Agent_Team_Demo)

---

## 一、项目背景

### 1.1 实践题目

构建一个**多 Agent 协作开发系统**，多个 AI Agent 分别扮演不同开发角色，通过通信协作完成软件项目的全栈开发。

### 1.2 我的设计思路

- **多角色 Agent 动态组建**：v4.0 使用 5 个固定角色（Lead + Backend + Frontend + Test + DevOps），v5.0 升级为 LLM 按需组建任意数量的角色
- **每个 Agent 独立进程**：模拟真实团队中每人独立工作的场景
- **LLM 驱动自主决策**：Agent 基于 ReAct（Reasoning + Acting）循环，通过 Tool Calling 自主决定每一步操作
- **人工审查保障安全**：LLM 提方案，人类拍板，兼顾效率与可靠性
- **多后端 LLM 支持**：通过 Anthropic 兼容 API 接入 DeepSeek、智谱等
- **v5.0 不限技术栈**：从只能做 Python+HTML → 支持任意语言/框架组合

> 📎 AI 辅助说明：本报告中使用 🤖 标记 AI 直接辅助的环节，帮助读者理解 AI 工具在开发过程中的实际参与程度。

---

## 二、技术探索：基于 paperclip 的快速原型

### 2.1 目标

先在一个成熟的 Multi-Agent 框架（paperclip）上快速验证想法，积累经验后再从头自研。

### 2.2 过程记录

**Step 1 — 快速了解项目** 🤖 AI 辅助

使用 Claude Code 加载 paperclip 仓库，快速理解其架构设计。手动阅读源码+文档需耗费大量时间，AI 辅助大幅加速了对核心架构的理解。

<img src="img/img.png" width="400">

**Step 2 — 需求分析与方案设计** 🤖 AI 辅助

向 AI 描述需求：在 paperclip 基础上构建固定角色的开发团队 Agent。AI 分析 paperclip 的扩展点并给出改造方案。

<img src="img/img_1.png" width="400">

**Step 3 — AI 产出设计文档并实现**

AI 根据需求生成了设计文档，明确了每个 Agent 的职责、通信方式、任务流程，并直接修改了代码实现。

<img src="img/img_2.png" width="400">


**Step 4 — 验收测试** 🤖 AI 辅助

让 AI 给出可执行的测试验收方案，验证多 Agent 协作是否按预期工作。

**Step 5 — 多 Agent 实例**

创建多个 Agent 实例并验证它们之间的通信与协作。

<img src="img/img_3.png" width="400">

### 2.3 经验总结

| 收获 | 说明 |
|------|------|
| 架构理解 | 掌握了 Multi-Agent 的核心要素：消息通信、任务分配、状态同步 |
| 框架局限 | paperclip 是通用框架，定制成本高，固定团队场景更适合自研 |
| AI 效率 | AI 辅助理解陌生代码库和生成设计文档，大幅减少学习成本 |

**结论：基于 paperclip 的经验，决定从头自研一个更贴合需求的 Agent Team 系统。**

---

## 三、自主开发：从零搭建 Agent Team

### 3.1 v1.0 — 快速搭建项目框架 🤖 AI 辅助

**要解决的问题**：验证"多 Agent 协作"本身是否可行。

**实现方式**：
- 用 AI 快速生成项目骨架：5 个 Agent 文件 + 消息总线 + 启动脚本
- Lead Agent 分析需求后**广播**给所有 Worker
- Worker 并行生成代码，互不等待

AI 生成了初始代码骨架的主体部分，人工主要负责调试纠偏和模块整合。

<img src="img/img8.png" width="400">

**局限性**：前端可能在 API 规范出来之前就开始写代码，导致前后端接口不匹配。

---

### 3.2 v2.0 — 任务依赖管理

**要解决的问题**：Worker 之间没有依赖关系，执行顺序混乱。

**核心改进**：

| 改进 | 说明 |
|------|------|
| **TaskManager（任务依赖管理器）** | 维护任务的 `blockedBy` / `dependents`，完成后自动级联解锁下游 |
| **契约驱动** | Backend 先产出 `api_spec.json`，Frontend / Test 基于此生成代码 |
| **Lead 结构化输出** | Lead Agent 生成带依赖关系的任务 JSON |

<img src="img/img_4.png" width="400">

核心依赖图逻辑为手动设计和编码，AI 辅助部分为 system prompt 优化和边缘 case 修正。

**任务依赖图**：

```
backend（无依赖，最先执行）
   ├── frontend（依赖 backend 的 api_spec.json）
   ├── test（依赖 backend 的 api_spec.json）
   └── devops（依赖 frontend + test 都完成）
```

**成果展示** — 分析需求后生成带依赖的任务列表，同时产出 API 文档：

<img src="img/img_6.png" width="400">
<img src="img/img_5.png" width="400">

---

### 3.3 v3.0 — ReAct + Tool Calling 架构重构 🤖 AI 辅助

**要解决的问题**：v2.0 每个 Agent 内部逻辑固化，代码大量重复，且 Agent 不够"智能"——不能自主决定读什么文件、何时结束。

**核心变革**：

**① 提取 BaseAgent 通用基类**

将所有 Agent 的共性抽象为基类：ReAct 循环框架 + 7 个通用工具 + LLM 调用封装。子类只需重写 `get_system_prompt()` 和 `_setup_tools()`。

**② "工具是手脚，LLM 是大脑"**

工具 handler 中**零 LLM 调用**——所有智能行为完全由 ReAct 循环中的 LLM 自主发起。这是一种关键设计哲学。

**③ 代码精简 74%**

v3.0 vs v2.1：删除 1698 行，新增仅 374 行。能力反而更强。

架构重构为人工主导，AI 辅助做代码精简和 edge case 处理。

**各 Agent 运行截图**：

| Agent | 截图 |
|-------|------|
| **Lead Agent** | <img src="img/image.png" width="300"> |
| **Lead（任务分发）** | <img src="img/image-5.png" width="300"> |
| **Backend Agent** | <img src="img/image-3.png" width="300"> |
| **Frontend Agent** | <img src="img/image-2.png" width="300"> |
| **Test Agent** | <img src="img/image-4.png" width="300"> |


**生成的 Demo 产物**：

<img src="img/image-6.png" width="400">

---

### 3.4 v4.0 — 人工审查 + 安全护栏

**要解决的问题**：v3.0 中 Lead Agent 分析需求后直接创建并分发任务——LLM 误判会直接被无审查地执行。

**核心改进 — 三阶段工作流**：

```
Phase 1：LLM 规划      →    Phase 2：人工审查      →    Phase 3：程序化执行
┌──────────────────┐      ┌─────────────────┐      ┌──────────────────┐
│ • 分析需求         │      │ • 展示任务计划    │      │ • 批量创建任务     │
│ • ask_user 确认    │ ───→ │ • y=批准 n=拒绝   │ ───→ │ • 设置依赖关系     │
│ • submit_plan 提交 │      │ • m=修改后重试    │      │ • 分发就绪任务     │
│                    │      │                  │      │ • 事件循环监控     │
│  🤖 LLM 驱动       │      │  👤 人工决策      │      │  ⚙️ 纯程序化       │
└──────────────────┘      └─────────────────┘      └──────────────────┘
```

- **Phase 1**：LLM 通过 `ask_user` 确认模糊需求，通过 `submit_plan` 提交结构化任务 JSON
- **Phase 2**：任务计划展示给用户——这正是本系统**工作量最大的自研部分**：人工审查流程、计划格式化展示、y/n/m 交互逻辑、修改后重试机制，全部手动实现
- **Phase 3**：**完全程序化执行**，无 LLM 参与，避免幻觉导致的误操作

三阶段流程设计、ask_user 交互、多后端适配全部为人工主导实现。

---

### 3.5 v5.0 — 通用化 + 不限技术栈 + 质量保证 🤖 AI 辅助

**要解决的问题**：v4.0 只能做 Python Flask + 原生 HTML 项目，且 Worker 产出缺乏质量验证。

**核心变革**：

1. **通用 Worker Agent**：将 4 个固定 Agent（backend/frontend/test/devops）合并为 1 个 `worker_agent.py`，通过 CLI 参数 `--name` 和 `--tech` 动态注入角色和技术栈
2. **动态技术栈选择**：LLM 自主决定用 React/Vue/Go/Java/Node.js/Flutter 等任意技术
3. **Lead 自动孵化 Worker**：计划批准后自动创建新终端窗口运行 Worker 进程
4. **三层产出验证**：Worker 自验证（`run_command`）→ Lead 自动验收（`expectedFiles`）→ 人工审查

v5.0 架构重构为人工主导设计，AI 辅助代码实现和文档编写。

> 📘 v5.0 详细设计见 [`docs/v5.0-overview.md`](./v5.0-overview.md) 和 [`docs/v5.0-changelog.md`](./v5.0-changelog.md)

---

### 3.6 模糊需求处理 — ask_user 交互

当 Agent 遇到需求描述模糊时，通过 `ask_user` 暂停并等待用户输入。阻塞式用户输入、ReAct 循环恢复、消息上下文拼接均为手动实现。

<img src="img/image-7.png" width="400">
<img src="img/image-8.png" width="400">
<img src="img/image-9.png" width="400">


---

## 四、应用案例

### 4.1 多样化需求测试

系统已在多种需求上跑通，验证了通用性：

| 需求类型 | 项目目录 | 产物 |
|----------|---------|------|
| 用户管理系统（v4.0） | `.project（3.0demo）/` | Flask API + HTML 界面 + unittest |
| 人事管理（v4.0） | `.project（人事管理）/` | 员工 CRUD + 管理页面 |
| 小游戏（v4.0） | `.project（小游戏）/` | 前后端小游戏服务 |
| 模糊指令（v4.0） | `.project（模糊指令）/` | 经 ask_user 交互确认后产出 |
| 扫雷游戏（v5.0） | `v5.0/（扫雷）/` | 通用 Worker 协作产出 |

### 4.2 生成产物示例

<img src="img/img7.png" width="400">

---

## 五、AI 辅助使用总结

| 环节 | AI 角色 | 人工角色 |
|------|--------|---------|
| paperclip 探索 | 解读架构、生成改造方案 | 验证可行性、决策方向 |
| v1.0 框架搭建 | 生成初始代码骨架 | 调试纠偏、整合模块 |
| v2.0 依赖管理 | 优化 prompt、修正边缘 case | **核心 TaskManager 逻辑自研** |
| v3.0 架构重构 | 代码精简、工具注册表 | **BaseAgent 架构设计主导** |
| v4.0 审查机制 | 辅助 debug、多后端适配 | **三阶段流程完全自研** |
| v5.0 通用化重构 | 代码实现、文档编写 | **架构设计、Worker 参数化设计** |
| 文档编写 | 生成初稿、格式化 | 审核、补充、调整 |

### AI 使用的关键价值

- **代码生成**：快速产出框架代码，减少重复劳动
- **架构理解**：加速对陌生代码库（paperclip）的理解
- **Debug 辅助**：定位问题、提出修复思路
- **文档草稿**：生成文档骨架，人工补充核心内容

**但核心设计决策（ReAct 循环设计、三阶段流程、依赖管理算法、安全护栏、通用 Worker 参数化设计）均为人工主导，AI 作为效率工具辅助实现。**

---

## 六、总结与反思

### 6.1 核心成果

- ✅ 实现了 Multi-Agent 协作系统，从需求到代码全自动
- ✅ 经历了 5 次迭代，从广播式 → 依赖管理 → ReAct 自主决策 → 人工审查 → 通用化
- ✅ 代码量逆势精简 74%，能力却持续增强
- ✅ 支持多 LLM 后端（DeepSeek / 智谱 / 阿里百炼）
- ✅ 采用文件系统通信，零外部依赖，开箱即用
- ✅ v5.0 打破技术栈限制，支持任意语言/框架组合
- ✅ v5.0 三层产出验证体系，确保 Agent 产出质量

### 6.2 关键收获

1. **工具 handler 零 LLM 的设计哲学**是最有收获的架构决策——让"工具"回归工具，推理完全交给 ReAct
2. **人工审查在任务创建之前**是安全与效率的最佳平衡点
3. **通用 Worker 参数化设计**是保证系统扩展性的关键——1 个文件替代 N 个固定 Agent
4. **三层验证防线**让 Agent 从"能跑"到"能信"——自验证是 AI Agent 不可或缺的能力
5. AI 辅助开发最有效的用法是"AI 生成骨架 + 人工打磨核心"
6. 文件系统通信虽"简陋"，但足够可靠，无需引入 Kafka/RabbitMQ 等重量级依赖

### 6.3 Future Work

- Web UI 替代命令行交互
- 任务执行结果的深度质量评估（代码 review、性能分析）
- 跨 Agent 集成验证：test Agent 实际启动后端服务并运行 E2E 测试
- expectedFiles 严格模式：验证不通过则拒绝完成
- 多项目并行支持
