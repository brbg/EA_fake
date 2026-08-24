# AI 原生 Enterprise Architect（Web 版）

基于 Web 技术栈的企业级建模与软件工程平台，目标是复刻桌面端 Enterprise Architect（EA）的核心能力，并深度融合大模型，实现全流程 AI 赋能。

> 详细设计见 [`EA_fake/AI 原生 Enterprise Architect（Web 版）软件详细设计文档.docx`](EA_fake/AI%20原生%20Enterprise%20Architect（Web%20版）软件详细设计文档.docx)（13 个功能模块）。

## 功能概览

- **账号体系**：注册 / 登录 / 退出，项目按用户隔离（不同账号互不可见），密码 bcrypt 哈希存储
- **UML 全图建模**：类图、接口、关系（继承/实现/关联/组合/聚合/依赖），画布拖拽、双击编辑、撤销/重做（Ctrl+Z / Ctrl+Y）
- **企业架构建模（ArchiMate）**：业务 / 应用 / 技术三层，角色、流程、服务、组件、节点等
- **数据建模（ER 图）**：实体、字段、主/外键、关系，SQL 生成
- **代码生成**：Java / Python / TypeScript，实体 / Controller / Service 多输出类型
- **AI 助手**：基于大模型的多轮上下文问答，**流式输出**（SSE），配置（api_key / 地址 / 模型）落库持久化，重启不丢失
- **AI 校验**：UML 模型一键校验，结构规则 + LLM 语义分析（命名、关系、职责等）
- **AI 架构评审**：ArchiMate 画布一键评审，结构检查 + LLM 语义分析（层间依赖、缺失组件等）
- **AI 元素分析**：UML / ArchiMate / ER 画布选中单个元素，AI 给出总体评价、优点、问题与改进建议
- **实时协作**：基于 Socket.IO 的多人在线协同（元素更新广播）
- **项目/版本管理**：项目增删改查、模型保存与加载

## 技术栈

| 层 | 技术 |
|---|---|
| 前端 | Vue 3 + TypeScript + Vite，原生 Canvas 2D 画布 |
| 后端 | Flask + Flask-SocketIO（Python） |
| 存储 | SQLite（轻量 KV 层 `db.py`）+ 模型/项目等结构化数据 |
| 认证 | 会话（`X-Session-Id`）+ bcrypt 密码哈希 |
| AI | 兼容 OpenAI 格式的大模型 API（默认 DeepSeek：`https://api.deepseek.com`，模型 `deepseek-chat`） |

## 目录结构

```
EA_fake/
├── AI 原生 Enterprise Architect（Web 版）软件详细设计文档.docx   # 详细设计文档
├── docs/
│   └── dev-logs/                # 每日开发日志（YYYY-MM-DD.md）
└── ea-webapp/
    ├── backend/
    │   ├── app.py               # Flask 后端（路由 + 业务逻辑）
    │   ├── db.py                # SQLite 轻量持久化层
    │   ├── models.py            # Project / SimpleModel 数据类
    │   ├── prompts.py           # LLM 系统提示词集中管理
    │   └── constants.py         # 元素/关系类型、颜色等常量
    ├── src/                     # Vue 3 前端源码
    │   ├── App.vue              # 主界面（登录门禁 + 仪表盘/建模画布）
    │   ├── LoginView.vue        # 登录 / 注册页
    │   ├── AIAssistant.vue      # AI 助手组件（流式对话）
    │   ├── aiService.ts         # AI API 封装（含 SSE 流式解析）
    │   └── projectContext.ts    # 项目上下文 → prompt
    ├── requirements.txt         # Python 依赖
    ├── package.json             # 前端依赖
    └── start.bat                # Windows 一键启动脚本
```

## 快速开始

### 环境要求

- **Python** 3.10+（需 `pip`）
- **Node.js** 18+（需 `npm`）

### Windows 一键启动

双击 `EA_fake/ea-webapp/start.bat`，脚本会自动：

1. 检查 Python / Node 环境
2. 首次运行自动安装前后端依赖
3. 分别启动后端（8080）和前端（5173）两个窗口
4. 打开浏览器 http://localhost:5173

### 手动启动

**后端**（必须在 `backend` 目录下运行，因为代码里的相对路径以它为基准）：

```bash
cd EA_fake/ea-webapp/backend
pip install -r ../requirements.txt
python app.py
# 运行于 http://localhost:8080
```

**前端**（开发模式，Vite 已配置代理到后端）：

```bash
cd EA_fake/ea-webapp
npm install
npm run dev
# 运行于 http://localhost:5173
```

**生产模式**：先 `npm run build` 构建到 `dist/`，再启动后端，Flask 会直接托管 `dist/`，只访问 `http://localhost:8080` 即可。

## AI 配置

AI 助手 / 校验 / 评审 / 元素分析均依赖兼容 OpenAI 格式的大模型接口，二选一配置：

1. **环境变量**（后端启动前设置）：

   ```bash
   export OPENAI_API_KEY=sk-xxx
   export OPENAI_BASE_URL=https://api.deepseek.com   # 可选，默认 OpenAI
   export OPENAI_MODEL=deepseek-chat                  # 可选
   ```

2. **界面配置**：AI 助手页右上角「配置」，填写 API Key、API 地址、模型名称。保存后写入本地 SQLite，**重启后端自动恢复**，无需重复填写。

> 注意：后端出于安全不回显 API Key（刷新后输入框为空），**只有在需要修改 Key 时才重新填写**，否则直接保存会保留已配置的 Key。

## 数据存储

运行时数据统一存入本地 SQLite（`ea-webapp/data/ea.db`），包括：用户、模型/项目、AI 配置（含 api_key）、应用数据。该目录已在 `.gitignore` 中忽略，属于运行时数据，不会提交到仓库。

## 开发日志

每日开发进展见 [docs/dev-logs/](docs/dev-logs/)，按 `YYYY-MM-DD.md` 记录完成事项、Bug 修复、待办与验证情况。
