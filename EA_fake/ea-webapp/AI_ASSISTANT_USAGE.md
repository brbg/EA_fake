# AI助手使用指南

## 智能体能做什么（19 个工具）

主界面就是智能体：直接说一句话，它自己决定调哪些工具。工具清单如下
（声明在 `backend/agent.py` 的 `TOOL_SPECS`，执行体在 `backend/app.py` 的
`_agent_tool_executors`）。

| 类别 | 工具 | 说明 |
|---|---|---|
| 项目 | `create_project` / `rename_project` / `delete_project` | 建/改名/删（删除需确认） |
| 架构 | `generate_architecture` / `edit_model` | 一句话出整套图；自然语言增量改某套图 |
| 质量 | `get_health` / `optimize_from_health` / `review_model` | 体检 / 按体检优化 / 结构校验（含 ArchiMate 白名单与「技术层缺可部署元素」） |
| 交付物 | `generate_code` / `generate_ruoyi_module` / `reverse_code` / `generate_document` | 生成代码 / 若依整套模块 / 代码反推模型 / 设计文档 |
| 版本 | `version_control` | `list` 列版本、`save` 存快照、`restore` 回滚（回滚需确认） |
| 记忆 | `remember` | 记一条项目级长期约束，后续生成会遵循 |
| 研发管理 | `dev_list` / `dev_create` / `dev_update` / `dev_delete` / `dev_ai_generate` | 5 个通用工具覆盖 4 类实体（需求/测试用例/缺陷/任务）× CRUD + AI 生成（缺陷无 AI 生成） |

**不在列的能力**：撤销/重做/清空/导出图片/手工拖拽这类**纯前端操作**没有后端接口，
原理上无法由对话触发；协作、后台管理、账号设置也未纳入（避免误操作面过大）。

### 破坏性操作需要二次确认

`delete_project` / `dev_delete` / `version_control(restore)` 是**不可逆**的。
它们的调用约定是：

1. 模型**先不带 `confirm`** 调用 → 后端**零副作用**，只返回「将影响什么」的待确认信息；
2. 模型把这个影响**复述给用户**并得到肯定答复；
3. 再以 `confirm=true` 重调，才真正执行。

`delete_project` 真删前会把模型 JSON 落一份到 `data/deleted/`，误删可人工捞回；
`version_control(restore)` 回滚前会先存一份当前状态。

> **残余风险（如实说明）**：这依赖模型遵守指令——它有可能直接传 `confirm=true`。
> 最强保护是「前端审批闸」（智能体发起破坏性调用时前端弹确认、批准后才回传），
> 需要新增客户端→服务端的审批消息，目前**未实现**。

### 预算

`run_tool_agent(max_steps=12, max_tokens=4096)`；工具结果回喂给模型时截断到 8000 字符
（大产物工具只回摘要 + 前 1500 字符，不把整篇代码/文档塞回去）。

---

## 前端接入说明

### 1. 创建的API调用模块

已在 `src/aiService.ts` 创建了完整的AI服务API调用模块，提供以下功能：

- `getAIConfig()` - 获取AI配置
- `updateAIConfig(config)` - 更新AI配置
- `getAIProviders()` - 获取支持的AI提供商列表
- `chatWithAI(messages, sessionId?)` - 非流式对话
- `chatWithAIStream(messages, onMessage, onError, sessionId?)` - 流式对话

### 2. 创建的AI助手组件

已在 `src/AIAssistant.vue` 创建了完整的AI助手对话组件，功能包括：

- 实时对话界面
- AI服务配置面板
- 支持多种AI提供商（OpenAI、Anthropic、Azure等）
- 流式/非流式输出切换
- 配置保存和测试连接

### 3. 使用方式

#### 方式一：使用现成的AI助手组件

在任意Vue组件中导入使用：

```vue
<template>
  <AIAssistant />
</template>

<script setup lang="ts">
import AIAssistant from './AIAssistant.vue'
</script>
```

#### 方式二：在其他页面调用API

```vue
<script setup lang="ts">
import { chatWithAI, chatWithAIStream } from './aiService'

// 非流式对话
const handleNormalChat = async () => {
  try {
    const response = await chatWithAI([
      { role: 'system', content: '你是一个有帮助的助手' },
      { role: 'user', content: '你好' }
    ])
    console.log('AI回复:', response.response.content)
  } catch (error) {
    console.error('对话失败:', error)
  }
}

// 流式对话
const handleStreamChat = async () => {
  await chatWithAIStream(
    [
      { role: 'user', content: '给我讲个故事' }
    ],
    (content) => {
      // 实时接收AI的回复内容
      console.log('收到内容:', content)
    },
    (error) => {
      console.error('错误:', error)
    }
  )
}
</script>
```

### 4. 配置AI服务

在AI助手界面点击"配置"按钮，可以：

1. **选择AI提供商**：OpenAI、Anthropic、Azure、自定义API
2. **输入API Key**：您的AI服务API密钥
3. **设置API地址**（可选）：自定义的API端点
4. **选择模型**：根据提供商显示可用的模型列表
5. **调整参数**：温度、流式输出等

### 5. 重新构建前端

由于代码已修改，需要重新构建前端才能生效：

```bash
cd d:\项目\EA_fake\EA_fake\ea-webapp
npm install  # 安装依赖（如果还没有安装）
npm run build  # 构建生产版本
```

或者开发模式：

```bash
npm run dev  # 启动开发服务器
```

### 6. 注意事项

1. **后端服务必须运行**：确保Flask后端服务在 `http://127.0.0.1:8080` 运行
2. **配置API密钥**：首次使用需要在AI助手界面配置您的API密钥
3. **用户登录**：部分API需要登录状态，会自动使用sessionId
4. **网络问题**：如果遇到跨域问题，确保后端CORS配置正确

### 7. 示例：在其他业务中使用AI

#### 生成代码建议

```typescript
import { chatWithAI } from './aiService'

const getCodeSuggestion = async (umlModel: any) => {
  const response = await chatWithAI([
    {
      role: 'user',
      content: `根据以下UML模型生成Java代码：${JSON.stringify(umlModel)}`
    }
  ])
  return response.response.content
}
```

#### 模型分析

```typescript
import { chatWithAI } from './aiService'

const analyzeModel = async (modelElements: any[]) => {
  const response = await chatWithAI([
    {
      role: 'system',
      content: '你是一个软件架构师，分析以下模型并给出改进建议'
    },
    {
      role: 'user',
      content: `分析这个UML模型：${JSON.stringify(modelElements)}`
    }
  ])
  return response.response.content
}
```
