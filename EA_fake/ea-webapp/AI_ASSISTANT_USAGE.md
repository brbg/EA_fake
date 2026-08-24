# AI助手使用指南

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
