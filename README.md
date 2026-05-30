# Agent Team Demo - 多Agent协作开发系统

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## 📋 项目概述

这是一个**固定的多Agent团队协作系统**，每个Agent负责不同的开发工作，通过消息队列进行通信，自动完成软件项目的全栈开发。

### 🎯 核心特性

- **5个独立Agent**：Lead（主控）、Backend（后端）、Frontend（前端）、Test（测试）、DevOps（运维）
- **每个Agent独立窗口**：清晰的输出，无混乱
- **异步通信**：基于文件队列的消息通信
- **共享上下文**：统一的项目状态管理
- **Windows原生支持**：无需WSL，直接运行
- **即插即用**：开箱即用的项目模板

## 🏗️ 架构设计

```
┌─────────────────────────────────────────────────────┐
│                    Main Process                      │
│                  (shared_context)                    │
└─────────────────────────────────────────────────────┘
         ↑              ↑              ↑              ↑
         │              │              │              │
    Lead │ Backend  Frontend │ Test   DevOps
   Agent │ Agent    Agent    │ Agent  Agent
    (UI) │ (API)    (HTML)   │(Unit) (Deploy)
         │              │              │              │
    🪟   │    🪟       🪟      │  🪟    🪟
  窗口1  │   窗口2    窗口3    │窗口4  窗口5
```

### 通信流程

```
用户输入需求
    ↓
Lead Agent 分析
    ↓
┌───────────────────────────┐
│ 分配任务给各Agent          │
└───────────────────────────┘
    ↓       ↓       ↓       ↓
  后端    前端    测试    DevOps
  创建    创建    创建    创建
  代码    代码    代码    配置
    ↓       ↓       ↓       ↓
└───────────────────────────┘
    ↓
 项目完成
```

## 🚀 快速开始

### 前置条件

- Python 3.8+
- Windows / Linux / macOS
- 约 50MB 磁盘空间

### 安装步骤

#### 1️⃣ 克隆仓库

```bash
git clone https://github.com/sduqx/Agent_Team_Demo.git
cd Agent_Team_Demo
```

#### 2️⃣ 创建虚拟环境（可选但推荐）

**Windows:**
```bash
python -m venv venv
venv\Scripts\activate
```

**Linux/Mac:**
```bash
python3 -m venv venv
source venv/bin/activate
```

#### 3️⃣ 安装依赖

```bash
pip install -r requirements.txt
```

#### 4️⃣ 配置环境变量（可选）

如果要使用Anthropic Claude API:

```bash
# 创建 .env 文件
echo "ANTHROPIC_API_KEY=your_key_here" > .env
echo "MODEL_ID=claude-3-opus-20240229" >> .env
```

#### 5️⃣ 启动Team

**Windows:**
```bash
run_team.bat
```

**Linux/Mac:**
```bash
chmod +x run_team.sh
./run_team.sh
```

### 💡 使用示例

启动后，在 **Lead Agent** 窗口输入你的需求，例如：

```
requirement: 构建一个TODO应用，支持增删改查任务
```

然后按回车，系统会自动：

1. ✅ **Backend Agent** 创建 Flask REST API
2. ✅ **Frontend Agent** 创建 HTML + JavaScript 界面
3. ✅ **Test Agent** 创建单元测试
4. ✅ **DevOps Agent** 创建 Docker 配置和文档

所有生成的代码存储在 `.project/` 目录中。

## 📁 项目结构

```
Agent_Team_Demo/
├── shared_context.py       # 共享通信模块（核心）
├── lead_agent.py          # Lead主控Agent
├── backend_agent.py       # Backend开发Agent
├── frontend_agent.py      # Frontend开发Agent
├── test_agent.py          # Test测试Agent
├── devops_agent.py        # DevOps部署Agent
├── run_team.bat           # Windows启动脚本
├── run_team.sh            # Linux/Mac启动脚本
├── requirements.txt       # Python依赖
├── .gitignore            # Git忽略配置
└── README.md             # 本文件

.project/                  # 生成的项目代码
├── app.py                # Flask后端
├── index.html            # 前端界面
├── requirements.txt      # 后端依赖
├── config.py            # 配置文件
├── Dockerfile           # Docker配置
├── docker-compose.yml   # Docker Compose
├── README.md            # 项目文档
└── tests/
    └── test_basic.py    # 测试用例

.team/                    # 团队协作文件
├── shared/
│   └── project.json     # 共享项目状态
└── inbox/
    ├── lead.jsonl       # Lead消息队列
    ├── backend.jsonl    # Backend消息队列
    ├── frontend.jsonl   # Frontend消息队列
    ├── test.jsonl       # Test消息队列
    └── devops.jsonl     # DevOps消息队列
```

## 🔧 Agent角色说明

### 👔 Lead Agent (主控)
- **职责**：接收用户需求、分析、分配任务
- **输出**：任务分配计划、进度追踪
- **通信**：发送任务给各Agent，接收完成通知

### 🔧 Backend Agent (后端)
- **职责**：设计和实现REST API
- **输出**：`app.py`（Flask应用）、`requirements.txt`、`config.py`
- **功能**：CRUD API、数据模型、业务逻辑

### 🎨 Frontend Agent (前端)
- **职责**：设计和实现用户界面
- **输出**：`index.html`（HTML/CSS/JavaScript）
- **功能**：响应式设计、表单、API集成

### 🧪 Test Agent (测试)
- **职责**：编写和执行测试
- **输出**：`tests/test_basic.py`（unittest）
- **功能**：单元测试、集成测试、覆盖率检查

### 📦 DevOps Agent (运维)
- **职责**：部署配置和文档
- **输出**：`Dockerfile`、`docker-compose.yml`、`README.md`
- **功能**：容器化、部署脚本、API文档

## 📊 项目状态查看

所有Agent的进度保存在 `.team/shared/project.json`：

```json
{
  "name": "Demo Project",
  "description": "构建一个TODO应用，支持增删改查任务",
  "status": "in_progress",
  "tasks": {
    "backend": {"status": "completed", "output": "Flask应用已创建"},
    "frontend": {"status": "completed", "output": "HTML UI已创建"},
    "test": {"status": "in_progress", "output": ""},
    "devops": {"status": "pending", "output": ""}
  }
}
```

## 🎯 典型工作流

### 场景1：构建TODO应用

```
输入: requirement: 构建一个TODO应用，支持增删改查任务

流程:
1. Lead Agent 分析需求
2. Backend Agent 创建 Flask API (POST/GET/PUT/DELETE)
3. Frontend Agent 创建 HTML 表单和列表
4. Test Agent 创建 API 测试
5. DevOps Agent 创建 Docker 配置

输出: .project/ 目录下的完整应用
```

### 场景2：构建计算器应用

```
输入: requirement: 构建一个在线计算器，支持四则运算

流程:
1. Lead Agent 分析需求
2. Backend Agent 创建计算 API
3. Frontend Agent 创建计算器界面
4. Test Agent 创建数学运算测试
5. DevOps Agent 创建部署配置

输出: 可直接部署的在线计算器
```

## 🐳 Docker部署

生成的项目已包含Docker支持：

```bash
# 进入项目目录
cd .project

# 构建镜像
docker build -t todo-app .

# 运行容器
docker run -p 5000:5000 todo-app

# 或使用Docker Compose
docker-compose up
```

## 📝 API文档

### REST API 示例

生成的Flask应用提供以下API：

```bash
# 获取所有TODO
GET http://localhost:5000/api/todos

# 创建TODO
POST http://localhost:5000/api/todos
Body: {"title": "完成项目"}

# 更新TODO
PUT http://localhost:5000/api/todos/1
Body: {"completed": true}

# 删除TODO
DELETE http://localhost:5000/api/todos/1
```

## 🔍 调试

### 查看Agent日志

每个Agent窗口显示实时日志：

```
[Lead Agent] 📊 分析需求: 构建一个TODO应用
[Lead Agent] ✓ 已分配任务给 backend
[Backend Agent] 📋 收到任务来自 lead
[Backend Agent] ✓ Flask应用已创建
```

### 查看项目状态

```bash
# 查看 .team/shared/project.json
cat .team/shared/project.json
```

### 查看生成的代码

```bash
# 列出所有生成的文件
dir .project\   # Windows
ls -la .project/  # Linux/Mac
```

## ⚠️ 常见问题

### Q: 窗口启动后立即关闭

**A:** 可能是Python路径问题，尝试：
```bash
python --version  # 确认Python已安装
python lead_agent.py  # 直接运行测试
```

### Q: "Flask未安装"错误

**A:** 确保安装了依赖：
```bash
pip install -r requirements.txt
```

### Q: Windows中文显示乱码

**A:** `run_team.bat` 已包含 `chcp 65001` 处理，如仍有问题：
```bash
# 手动设置
chcp 65001
```

### Q: 多个项目冲突

**A:** `.project` 和 `.team` 是每次运行独立的，不会冲突。重新运行 `run_team.bat` 会覆盖之前的内容。

## 📚 学习资源

- [Flask 官方文档](https://flask.palletsprojects.com/)
- [HTML/CSS/JavaScript 参考](https://developer.mozilla.org/)
- [Docker 入门指南](https://docs.docker.com/)
- [Python unittest 文档](https://docs.python.org/3/library/unittest.html)

## 🤝 贡献

欢迎提交Issue和Pull Request！

## 📄 许可证

MIT License - 详见 [LICENSE](LICENSE)

## 👤 作者

**sduqx** - [@GitHub](https://github.com/sduqx)

## 🌟 Star History

如果觉得这个项目有用，欢迎给个Star ⭐

---

**最后更新**: 2026-05-30
**版本**: 1.0.0
