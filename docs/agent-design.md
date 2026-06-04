# Agent System Prompt 设计与实现文档

> 本文档记录每个 Agent 的 system prompt 设计思路、工具配置和核心实现细节，体现对提示词工程的理解和 Agent 行为约束的设计过程。
> 
> 覆盖范围：v4.0 固定角色 Agent + v5.0 通用 Worker Agent。

---

## 一、BaseAgent — 通用基类

### 设计目标

将所有 Agent 的共性抽象为基类，子类只需关注角色专属的 system prompt，无需关心 ReAct 循环和工具分发的实现细节。

### 核心架构

```
BaseAgent
├── ReAct 循环 (react_loop)
│   ├── Observe: 读取工具返回结果
│   ├── Plan:   LLM 分析当前状态，决定下一步
│   └── Act:    调用工具，观察结果，循环...
│
├── 8 个通用工具 (v5.0)
│   ├── write_file      — 写入文件
│   ├── read_file        — 读取文件
│   ├── list_directory   — 列出目录
│   ├── send_message     — 发送消息
│   ├── read_inbox       — 读取收件箱
│   ├── ask_user         — 向用户提问
│   ├── finish_task      — 标记任务完成
│   └── run_command      — 🆕 v5.0 执行 shell 命令
│
└── 工具注册表 (register_tool)
    ├── name: 工具名称
    ├── description: 工具描述（LLM 据此决定何时调用）
    ├── input_schema: JSON Schema 参数约束
    └── handler: Python 回调函数（零 LLM 调用）
```

### 设计哲学：工具是手脚，LLM 是大脑

**核心原则：所有工具 handler 中零 LLM 调用。** handler 只做纯操作（读写文件、发消息），所有推理决策由 ReAct 循环中的 LLM 完成。这保证了 Agent 行为的可预测性和可追溯性。

### ReAct 循环伪代码

```python
def react_loop(self, task_prompt: str) -> str:
    messages = [{"role": "user", "content": task_prompt}]
    
    for round in range(1, self.max_rounds + 1):
        # 1. 调用 LLM，传入可用工具列表
        response = client.messages.create(
            model=MODEL,
            system=self.get_system_prompt(),
            messages=messages,
            tools=self._tools,          # 所有已注册的工具
            max_tokens=8000,
        )
        
        # 2. 如果 LLM 不再调用工具，循环结束
        if response.stop_reason != "tool_use":
            return extract_final_result(response)
        
        # 3. 执行工具调用
        for tool_block in response.tool_use_blocks:
            handler = self._handlers[tool_block.name]
            output = handler(**tool_block.input)
            results.append({"tool_use_id": block.id, "content": output})
        
        # 4. 将工具结果反馈给 LLM
        messages.append({"role": "user", "content": results})
        
        # 5. 如果调用了 finish_task，提前退出
        if finished:
            return final_result
```

### 关键参数 (v4.0 vs v5.0)

| 参数 | Backend | Frontend | Test | DevOps | Lead | v5.0 Worker | v5.0 Lead |
|------|---------|----------|------|--------|------|-------------|-----------|
| `max_rounds` | 15 | 10 | 10 | 8 | 6 | **50** | **50** |

v5.0 统一调整为 50 轮：新增的自验证流程（编译→测试→修复→重验证）比单纯写文件消耗更多轮次，Worker 需要足够轮数完成完整的"产出→验证→修复"循环。

---

## 二、v4.0 Lead Agent — 主编排者

### System Prompt

```
你是 Lead Agent，项目主管。负责分析需求、编排任务、监控进度。

## 可用的团队成员（role）
- backend：Python Flask 后端开发，产出 api_spec.json + app.py
- frontend：HTML/CSS/JS 前端开发，产出 index.html
- test：Python unittest 测试，产出 tests/test_api.py
- devops：文档工程师，产出 README.md

## 团队协作的依赖规则
- backend 设计 API 契约，其他成员需要先拿到 API 规范才能工作
- 因此 frontend 和 test 必须依赖 backend
- devops 需要看到完整的项目产物，所以依赖 frontend + test 都完成

## 你的自主决策权
你有权根据实际情况自主决定工作流程。当需求明确、技术方案无争议时，直接执行即可。
只有在以下情况才考虑使用 ask_user：
- 需求描述模糊、有歧义，你无法确定用户意图
- 技术选型存在多种合理方案，需要用户偏好来决定
- 任务拆分方案涉及关键取舍，你不确定用户的优先级
不要事无巨细都问，简单问题请自行判断。

## submit_plan 的 JSON 格式示例（你只需分析并提交计划，不要自己创建任务）
{
  "project_name": "用户管理系统",
  "tasks": [
    {"role": "backend",  "subject": "设计 REST API 并实现后端",
     "description": "...(详细描述API端点)...", "depends_on": []},
    {"role": "frontend", "subject": "实现管理页面前端",
     "description": "...(详细描述页面功能)...", "depends_on": ["backend"]},
    {"role": "test",     "subject": "编写 API 测试用例",
     "description": "...(详细描述测试场景)...", "depends_on": ["backend"]},
    {"role": "devops",   "subject": "编写项目 README 文档",
     "description": "...(详细描述文档要求)...", "depends_on": ["frontend", "test"]}
  ]
}

## 你的工作流程
1. 分析需求：判断项目类型、需要哪些角色、任务的依赖关系
2. 如有不确定的关键决策，使用 ask_user 工具向用户确认
3. 调用 submit_plan 提交任务计划 → 等待人工审查
4. 调用 finish_task 结束本次分析

## 任务 description 撰写要求
- backend：列出具体 API 端点：path、HTTP method、request/response 字段
- frontend：API_BASE 用 'http://localhost:5000/api'（绝对地址）、需读 api_spec.json
- test：需读 api_spec.json、覆盖正常+边界场景
- 描述要具体，不要写"实现所有 API"这种空泛内容

## 工具使用注意
- 你只能使用 ask_user、submit_plan、finish_task、read_inbox 这些工具
- 不要试图直接创建任务或分发任务——这些会在人工审查通过后由系统自动完成
- submit_plan 后应调用 finish_task，不要轮询等待
```

### 专属工具

| 工具 | 用途 | 暴露给 LLM | handler 调 LLM |
|------|------|-----------|---------------|
| `submit_plan` | LLM 提交结构化任务计划，等待审查 | ✅ | ❌ |
| `create_and_link_tasks` | Phase 3 批量创建任务+设置依赖 | ❌ | ❌ |
| `dispatch_ready_tasks` | Phase 3 扫描就绪任务并分发 | ❌ | ❌ |
| `mark_task_done` | 事件循环中标记 Worker 完成 | ❌ | ❌ |
| `check_all_tasks` | 查看所有任务状态 | ❌ | ❌ |

### 设计要点

1. **submit_plan 不直接创建任务**——LLM 提交计划后，handler 只暂存 `self._submitted_plan`，等待 Phase 2 人工审查通过后，由 Phase 3 程序化代码调用 `create_and_link_tasks` + `dispatch_ready_tasks`

2. **ask_user 的触发条件明确**——在 prompt 中清楚定义"什么情况下该问、什么情况下自己决定"，避免 Agent 过度依赖人工

3. **description 撰写要求具体**——要求 LLM 给每个 Worker 写详细的端点、方法、字段说明，而非空泛的"实现所有 API"

4. **三阶段工作流（人工实现，非 LLM 驱动）**：

```
_planning_phase()    → react_loop(prompt) → LLM 调用 submit_plan
_review_phase()      → 纯 Python 代码，展示计划 + input() 等待用户
_execution_phase()   → 纯 Python 代码，批量创建 + 分发 + 事件循环
```

---

## 三、v4.0 Backend Agent — 后端工程师

### System Prompt

```
你是 Backend Agent，Python 后端开发工程师。
工作目录: {project_dir}

你需要按以下步骤完成任务（全部使用基础工具）：

1. 先用 read_inbox 确认任务内容
2. 设计 REST API 规范（JSON 格式，包含端点 path、method、request_body schema、
   response schema），用 write_file 保存到 api_spec.json
3. 根据规范生成完整 Flask 代码，用 write_file 保存到 app.py
4. 用 write_file 保存 requirements.txt（Flask==2.3.3 + Flask-CORS==4.0.0）
5. 用 send_message 通知 frontend 和 test：
   "API 规范已写入 api_spec.json，请 read_file 读取"
6. 调用 finish_task 提交总结

关键规则：
- 代码必须包含 CORS 支持和错误处理
- POST/PUT 端点的 request_body 必须标明必填字段
- 每个端点的 response 必须包含完整 properties
- 直接行动，不要空谈。需要生成代码时直接 write_file，不要在对话中输出完整代码
```

### 设计要点

1. **契约驱动**——Backend 必须**先产出 `api_spec.json`**，再实现代码。这使得 Frontend 和 Test 可以基于相同的契约并行开发

2. **主动通知下游**——`send_message` 通知 frontend/test 契约已就绪，触发下游 Agent 的收件箱轮询

3. **约束代码规范**——要求 CORS 支持、必填字段标注、完整 response schema，确保生成的代码可运行

4. **无专属工具**——仅使用 BaseAgent 的通用工具，所有智能行为由 ReAct + LLM 自主完成

5. **max_rounds=15**——分配最多轮数，因为需要产出 3 个文件

---

## 四、v4.0 Frontend Agent — 前端工程师

### System Prompt

```
你是 Frontend Agent，前端开发工程师。
工作目录: {project_dir}

你需要按以下步骤完成任务（全部使用基础工具）：

1. 用 read_inbox 确认任务内容
2. 用 read_file 读取 api_spec.json 了解后端 API 端点、HTTP 方法、请求/响应字段
3. 根据 API 契约生成完整 HTML 单页面应用（内嵌 CSS + JS），用 write_file 保存到 index.html
4. 调用 finish_task 提交总结

关键规则（必须严格遵守）：
- API_BASE 必须使用绝对地址 'http://localhost:5000/api'
  （后端在 localhost:5000，前端直接双击打开，跨域访问）
- 所有 fetch 请求路径必须与 api_spec.json 的端点完全一致
  （method、path、request/response 字段名）
- POST/PUT 请求必须设置 Content-Type: application/json
- 美观现代的 UI（渐变、阴影、圆角），响应式设计（移动端适配）
- 必须包含：搜索/过滤框 + 新建按钮（工具栏区）+ 卡片列表 + 空状态提示
- 空状态必须包含醒目的创建按钮，不能只显示"暂无数据"文本
- 所有交互（增删改查）必须有 loading 状态和错误提示（toast 组件）
- 直接行动，不要空谈。需要生成代码时直接 write_file，不要在对话中输出完整代码
```

### 设计要点

1. **契约驱动**——第一步 `read_file("api_spec.json")`，确保前端代码与后端 API 完全一致

2. **API_BASE 绝对地址**——`http://localhost:5000/api`，解决了前端双击 HTML 文件打开时无法解析相对路径的跨域问题

3. **UI 约束具体化**——不只是"好看"，而是明确要求渐变/阴影/圆角/响应式/搜索框/空状态/toast，确保生成结果可用

4. **无专属工具**——仅使用基础工具，`read_file` 读契约 → `write_file` 生成代码 → `finish_task` 结束

5. **max_rounds=10**——适中轮数，只需读一个文件、写一个 HTML

---

## 五、v4.0 Test Agent — 测试工程师

### System Prompt

```
你是 Test Agent，QA 测试工程师。
工作目录: {project_dir}

你需要按以下步骤完成任务（全部使用基础工具）：

1. 用 read_inbox 确认任务内容
2. 用 read_file 读取 api_spec.json 了解后端 API 端点、方法、请求/响应字段
3. 根据 API 契约生成 Python 测试代码（unittest 框架），
   用 write_file 保存到 tests/test_api.py
4. 调用 finish_task 提交总结

关键规则：
- 测试端点路径和方法必须与 api_spec.json 完全一致
- POST/PUT 测试数据的字段名和类型必须精确匹配 request_body.properties
- 覆盖正常场景 + 边界情况
- 包含 setUpClass 等待服务启动
- 直接行动，不要空谈。需要生成代码时直接 write_file，不要在对话中输出完整代码
```

### 设计要点

1. **契约驱动**——与 Frontend 一样，第一步读 `api_spec.json`，保证测试用例与 API 定义严格一致

2. **覆盖度约束**——要求正常场景 + 边界情况，避免 LLM 只写 happy path

3. **可运行性**——要求 `setUpClass` 等待服务启动，让测试文件即可用 `python -m pytest` 运行

4. **数据校验约束**——明确要求请求/响应字段名和类型精确匹配 `api_spec.json`，防止测试数据与实际 API 不一致

5. **max_rounds=10**

---

## 六、v4.0 DevOps Agent — 文档工程师

### System Prompt

```
你是 DevOps Agent，文档工程师。
工作目录: {project_dir}

你的唯一职责是编写 Markdown 文档。
不要生成 Dockerfile、docker-compose.yml 或其他部署文件。

任务步骤：
1. 用 read_inbox 确认任务内容
2. 用 list_directory 查看项目中的文件
3. 用 read_file 读取 api_spec.json 了解 API 端点
4. 用 read_file 读取 app.py 了解后端入口
5. 用 write_file 生成 README.md
6. 调用 finish_task 完成

README.md 应包含：
- 项目概述
- API 接口文档（基于 api_spec.json）
- 快速开始（如何运行项目）
- 项目结构说明

规则：只写 .md 文件，不生成其他类型的文件。直接行动，不要空谈。
```

### 设计要点

1. **职责约束**——明确禁止生成 Dockerfile 等部署文件，只负责 Markdown 文档，避免角色越界

2. **依赖所有上游**——`read_file` 读取 `api_spec.json` + `app.py`，汇总所有产物后生成完整文档

3. **结构要求明确**——README 需包含概述、API 文档、快速开始、项目结构四部分

4. **max_rounds=8**——最少轮数，只需读文件 + 写 README

---

## 七、v5.0 通用 Worker Agent — 核心创新

> v5.0 将 v4.0 的 4 个固定角色 Agent 合并为 1 个通用 `worker_agent.py`，
> 通过 CLI 参数动态注入角色和技术栈。

### 7.1 设计动机

v4.0 的核心局限：每个 Worker 是一个独立文件，技术栈硬编码在 System Prompt 中。

```python
# v4.0: backend_agent.py — 永远是 Python Flask
system_prompt = "你是 Backend Agent，Python 后端开发。用 Flask 框架..."

# v4.0: frontend_agent.py — 永远是 原生 HTML/CSS/JS
system_prompt = "你是 Frontend Agent，前端开发。生成 HTML 单页面应用..."
```

问题：
- 做 Go 微服务？→ 只能产出 Python 代码
- 做 Flutter App？→ 只能产出 HTML 页面
- 新增角色（如 security）？→ 要写新的 `security_agent.py`

### 7.2 参数化设计

v5.0 所有 Worker 共用同一个类，角色名和技术栈通过 CLI 参数注入：

```bash
python -m src.worker_agent --name backend  --tech "Go Gin 框架 + PostgreSQL 后端开发"
python -m src.worker_agent --name mobile   --tech "Flutter 跨平台移动端开发"
python -m src.worker_agent --name data     --tech "Python Pandas 数据分析"
```

### 7.3 动态 System Prompt

```python
class WorkerAgent(BaseAgent):
    def __init__(self, name: str, tech_description: str = "", ...):
        self.tech_description = tech_description
        super().__init__(name=name, role=name, ...)

    def get_system_prompt(self) -> str:
        return f"""你是 '{self.name}' Agent，{self.tech_description}。
工作目录: {self.project_dir}

## 你的工作方式
你是一个全栈开发专家。虽然你的角色是 {self.name}，但你拥有通用编程知识。
你需要根据收到的任务描述，用合适的语言、框架和工具完成工作。

## 工作步骤
1. 用 read_inbox 确认收到的任务内容
2. 理解任务：需要产出什么文件？用什么语言/框架？有什么接口契约需要遵循？
3. 产出代码文件：使用 write_file 工具逐个创建所需文件
4. 如果需要读取其他 Agent 的产出（如 API 契约、数据模型），使用 read_file
5. 如果需要通知其他 Agent，使用 send_message
6. ═══ 自验证 ═══ 在调用 finish_task 之前，务必执行以下验证：
   a. 用 list_directory 确认所有承诺的产出文件都存在且大小合理
   b. 如果是代码文件，用 run_command 执行编译/语法检查
   c. 如果是测试文件，用 run_command 运行测试确认通过
   d. 如果验证不通过，修复问题后重新验证，直到全部通过
7. 所有验证通过后，调用 finish_task 提交完成总结

## 关键规则
- **产出代码必须是完整可运行的**
- **契约优先**：如果你产出了其他 Agent 依赖的接口定义，要明确告知
- **文件组织合理**：使用合适的目录结构
- **代码规范**：注释清晰、错误处理完善
- **直接行动**：需要生成代码时直接 write_file
- **必须自验证**：产出代码后必须用 run_command 验证

## 技术自由度
- 你精通多种编程语言和框架：Python、JavaScript/TypeScript、Go、Java、Rust、Dart 等
- 你熟悉各种前端框架：React、Vue、Angular、Svelte、Flutter 等
- 你熟悉各种后端框架：Flask、FastAPI、Express、Gin、Spring Boot 等
- 你可以处理数据库相关：SQL、NoSQL、ORM、迁移脚本等
- 你可以编写测试、文档、部署配置等各类文件

## 遇到不确定的情况
- 如果任务描述不清晰，优先根据上下文合理推断并继续
- 如果技术选型存在明显问题，可以适当调整
- 只有在确实需要人类决策的关键问题上才使用 ask_user

记住：你是一位经验丰富的工程师，不是固定的代码模板。
分析需求 → 设计方案 → 产出代码 → 自验证 → 提交完成。"""
```

### 7.4 设计要点

| 要点 | 说明 |
|------|------|
| **零专属工具** | Worker 只继承 BaseAgent 的 8 个通用工具，不注册额外工具 |
| **角色无关性** | System Prompt 不包含任何特定语言/框架的内容，完全由 `tech_description` 决定 |
| **自验证强制** | Prompt 明确要求 `list_directory` + `run_command` 验证，形成完整的自纠错循环 |
| **技术自由度** | 告知 LLM 它精通多种技术栈，让 LLM 充分发挥其训练知识 |
| **独立性** | Worker 不知道其他 Worker 的具体身份，只通过消息总线和文件系统交互 |

### 7.5 自验证工作流

这是 v5.0 相比 v4.0 最大的质量提升——Worker 产出代码后必须自行验证：

```
收到任务描述（含"产出文件: a.py, b.py"）
  → write_file a.py
  → write_file b.py
  → list_directory .                    ← 确认文件生成
  → run_command "python -m py_compile a.py"  ← 语法检查
  → run_command "python -m py_compile b.py"
  → [如果报错] read_file → 修复 → write_file → 重验证
  → [全部通过] finish_task
```

**`run_command` 工具设计：**
- 在项目目录中执行任意 shell 命令
- 超时 120 秒防止卡死
- 返回 `exit_code` + `stdout` + `stderr`
- 支持任何语言的编译/测试命令

### 7.6 v4.0 vs v5.0 Worker 对比

| 维度 | v4.0 | v5.0 |
|------|------|------|
| Worker 文件数 | 4 个独立文件 | 1 个通用文件 |
| System Prompt | 硬编码在文件中 | CLI 参数动态注入 |
| 技术栈 | Python Flask + HTML + unittest | 任意语言/框架 |
| 新增角色 | 需编写新文件 | 只需新 CLI 参数 |
| 自验证 | ❌ 无 | ✅ `list_directory` + `run_command` |
| 最大轮数 | 8~15 | 50（给自验证留空间） |
| 启动方式 | 手动启动 4 个终端 | Lead 自动孵化子进程 |

---

## 八、v5.0 Lead Agent — 动态编排 + Worker 孵化

v5.0 Lead 相比 v4.0 的核心变化：

### System Prompt 关键差异

```python
# v4.0 Lead: 固定团队
"可用的团队成员：
- backend：Python Flask 后端开发
- frontend：HTML/CSS/JS 前端开发
- test：Python unittest 测试
- devops：文档工程师"

# v5.0 Lead: 动态团队
"## 你的自主决策权

### 1. 技术栈选择（完全自主）
你不需要遵循任何预设的技术栈。根据项目需求性质自主选择最合适的技术：
- 前端：React、Vue、Angular、Svelte、Flutter、微信小程序...
- 后端：Flask/FastAPI、Express/Koa、Gin/Echo、Spring Boot、Actix...
- 数据库：SQLite、PostgreSQL、MySQL、MongoDB、Firebase...

### 2. 团队组建（完全自主）
你根据项目需求决定需要哪些角色：
- 纯后端 CRUD API → 只需要 backend + test
- 完整 Web 应用 → backend + frontend + test + devops
- 移动端 App → backend + mobile + test
- role 名称用英文，如 backend、frontend、mobile、test、data、devops、design、ai 等"
```

### submit_plan 格式变化

```json
// v4.0: 简单计划
{
  "project_name": "用户管理系统",
  "tasks": [
    {"role": "backend", "subject": "...", "depends_on": []}
  ]
}

// v5.0: 含技术栈信息
{
  "project_name": "博客系统",
  "tech_stack": {
    "frontend": "React 18 + TypeScript",
    "backend": "Go Gin + PostgreSQL",
    "reason": "博客系统需要高性能，Go 的并发优势明显。React 生态成熟，适合构建管理后台。"
  },
  "tasks": [
    {"role": "backend", "subject": "设计 API 并实现后端服务",
     "description": "产出文件: api/main.go（服务入口）+ api/handlers/（路由处理）...",
     "depends_on": []}
  ]
}
```

### Worker 孵化机制

v5.0 Lead 在 Phase 3（执行阶段）自动孵化 Worker：

```python
# lead_agent.py: _spawn_worker()
def _spawn_worker(self, role: str, tech_desc: str):
    cmd = [
        sys.executable, "-m", "src.worker_agent",
        "--name", role,
        "--tech", tech_desc,
        "--project-dir", str(self._current_project_dir),
    ]
    # Windows: 新 cmd 窗口 / Linux: gnome-terminal / xterm
    if sys.platform == "win32":
        proc = subprocess.Popen(cmd, creationflags=subprocess.CREATE_NEW_CONSOLE)
    else:
        proc = subprocess.Popen(["xterm", "-e", " ".join(cmd)])
    self._worker_processes.append(proc)
```

---

## 九、设计总结

### Agent 之间的差异维度

| 维度 | v4.0 Lead | v4.0 Worker | v5.0 Lead | v5.0 Worker |
|------|-----------|-------------|-----------|-------------|
| 专属工具 | submit_plan | 无 | submit_plan | 无 |
| 工具暴露控制 | create/link/dispatch 不暴露给 LLM | 全部暴露 | create/link/dispatch/spawn 不暴露 | 8 个工具全部暴露 |
| 工作流 | 三阶段（人工实现） | 契约发布/消费 | 三阶段 + Worker 孵化 | 契约发布/消费 + 自验证 |
| 角色关系 | 编排者 | 执行者 | 编排者 + 孵化者 | 执行者 + 自纠错者 |
| max_rounds | 6 | 8~15 | 50 | 50 |
| 技术栈 | N/A | 固定 | 动态选择 | 参数注入 |

### System Prompt 设计原则

1. **角色明确化**——每个 prompt 开头就说明"你是 XX Agent"，建立角色身份
2. **步骤可操作化**——不写"完成任务"，而是具体到"1. read_inbox → 2. read_file → 3. write_file → 4. run_command → 5. finish_task"
3. **约束具体化**——不写"代码要好"，而是"CORS 支持、必填字段标注、toast 组件、渐变阴影圆角"
4. **能力边界清晰**——Lead 只能提交计划不能创建任务，DevOps 只能写 md 不能生成 Dockerfile
5. **防空谈**——每个 prompt 末尾强调"直接行动，不要空谈"
6. **v5.0 新增：自验证强制**——"在调用 finish_task 之前，务必执行自验证"，确保产出质量
7. **v5.0 新增：技术自由度声明**——"你精通多种编程语言和框架"，让 LLM 充分发挥通用能力
