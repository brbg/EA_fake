# AI 原生 Enterprise Architect（Web 版）

基于 Web 技术栈的企业级建模与软件工程平台，目标是复刻桌面端 Enterprise Architect（EA）的核心能力，并深度融合大模型，实现全流程 AI 赋能。

> 详细设计见 [`EA_fake/AI 原生 Enterprise Architect（Web 版）软件详细设计文档.docx`](EA_fake/AI%20原生%20Enterprise%20Architect（Web%20版）软件详细设计文档.docx)（13 个功能模块）。

## 功能概览

- **UML 全图建模**：类图、接口、关系（继承/实现/关联/组合/聚合/依赖），画布拖拽、双击编辑、撤销/重做（Ctrl+Z / Ctrl+Y）
- **企业架构建模（ArchiMate）**：业务 / 应用 / 技术三层，角色、流程、服务、组件、节点等
- **数据建模（ER 图）**：实体、字段、主/外键、关系，SQL 生成
- **代码生成**：Java / Python / TypeScript，实体 / Controller / Service 多输出类型
- **AI 助手**：基于大模型的项目上下文问答、模型分析、代码生成建议
- **实时协作**：基于 Socket.IO 的多人在线协同（元素更新广播）
- **项目/版本管理**：项目增删改查、模型保存与加载

## 技术栈

| 层 | 技术 |
|---|---|
| 前端 | Vue 3 + TypeScript + Vite，原生 Canvas 2D 画布 |
| 后端 | Flask + Flask-SocketIO（Python） |
| 存储 | JSON 文件 + 内存缓存（原型阶段，生产建议换数据库） |
| AI | 兼容 OpenAI 格式的大模型 API（可配置 base_url / model / api_key） |

## 目录结构

```
EA_fake/
├── AI 原生 Enterprise Architect（Web 版）软件详细设计文档.docx   # 详细设计文档
└── ea-webapp/
    ├── backend/
    │   └── app.py                 # Flask 后端（单文件，约 1.5 万行）
    ├── src/                       # Vue 3 前端源码
    │   ├── App.vue                # 主界面（仪表盘/建模画布/代码生成）
    │   ├── AIAssistant.vue        # AI 助手组件
    │   ├── aiService.ts           # AI API 封装
    │   └── projectContext.ts      # 项目上下文 → prompt
    ├── requirements.txt           # Python 依赖
    ├── package.json               # 前端依赖
    └── start.bat                  # Windows 一键启动脚本
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

AI 助手依赖兼容 OpenAI 格式的大模型接口。二选一：

1. **环境变量**（后端启动前设置）：

   ```bash
   export OPENAI_API_KEY=sk-xxx
   export OPENAI_BASE_URL=https://api.openai.com/v1   # 可选，默认 OpenAI
   export OPENAI_MODEL=gpt-4                            # 可选
   ```

2. **界面配置**：前端 AI 助手页右上角「配置」，填写 API Key、API 地址、模型名称。

> 注意：后端出于安全不回显 API Key（刷新后输入框为空），**只有在需要修改 Key 时才重新填写**，否则直接保存会保留已配置的 Key。

## 数据存储

模型、用户、上传、版本数据默认存储在 `ea-webapp/` 下的 `models/`、`users/`、`uploads/`、`versions/` 目录（JSON 文件 + 内存缓存）。这些目录已在 `.gitignore` 中忽略，属于运行时数据，不会提交到仓库。
