<template>
  <div class="ai-assistant">
    <div class="ai-header">
      <h3>AI助手</h3>
      <div class="ai-actions">
        <button class="btn btn-outline" @click="showConfig = !showConfig">
          <i class="fas fa-cog"></i> {{ showConfig ? '收起配置' : '配置' }}
        </button>
        <button class="btn btn-outline" @click="clearChat">
          <i class="fas fa-trash"></i> 清空
        </button>
      </div>
    </div>

    <div v-if="showConfig" class="ai-config-panel">
      <h4>AI服务配置</h4>
      
      <div class="config-item">
        <label>API Key</label>
        <input 
          type="password" 
          v-model="config.api_key" 
          placeholder="输入您的API密钥"
        />
      </div>

      <div class="config-item">
        <label>API地址 (兼容OpenAI格式)</label>
        <input 
          type="text" 
          v-model="config.base_url" 
          placeholder="https://api.openai.com/v1"
        />
      </div>

      <div class="config-item">
        <label>模型名称</label>
        <input 
          type="text" 
          v-model="config.model" 
          placeholder="gpt-3.5-turbo"
        />
      </div>

      <div class="config-item">
        <label>
          <input type="checkbox" v-model="config.includeContext" />
          包含项目上下文（AI会先读取当前项目内容再回答）
        </label>
      </div>

      <div class="config-actions">
        <button class="btn btn-primary" @click="saveConfig" :disabled="saving">
          <i v-if="saving" class="fas fa-spinner fa-spin"></i>
          {{ saving ? '保存中...' : '保存配置' }}
        </button>
      </div>

      <div v-if="configMessage" :class="['config-message', configMessage.type]">
        {{ configMessage.text }}
      </div>
    </div>

    <div class="ai-chat">
      <div class="chat-messages" ref="chatMessagesRef">
        <div class="chat-message bot">
          <div class="chat-bubble">
            <i class="fas fa-robot" style="margin-right: 8px;"></i>
            <template v-if="!aiEnabled">
              AI服务未启用，请先配置API密钥
            </template>
            <template v-else>
              您好！我是AI助手，我可以帮助您分析模型、生成建议和代码。
              <span v-if="config.includeContext && hasProjectContext" style="display:block;margin-top:8px;font-size:12px;color:#666;">
                <i class="fas fa-info-circle"></i> 当前已关联项目上下文
              </span>
            </template>
          </div>
        </div>
        
        <div 
          v-for="msg in messages" 
          :key="msg.id" 
          :class="['chat-message', msg.type]"
        >
          <div class="chat-bubble">
            <div v-if="msg.type === 'bot'" class="bot-avatar">
              <i class="fas fa-robot"></i>
            </div>
            <div class="message-content">{{ msg.content }}</div>
          </div>
        </div>

        <div v-if="isTyping && !streamStarted" class="chat-message bot">
          <div class="chat-bubble">
            <i class="fas fa-spinner fa-spin"></i> AI正在思考...
          </div>
        </div>
      </div>

      <div class="chat-input">
        <textarea 
          v-model="inputMessage" 
          placeholder="请输入您的问题..." 
          @keydown.enter.exact.prevent="sendMessage"
          rows="2"
        ></textarea>
        <button @click="sendMessage" :disabled="!inputMessage.trim() || isTyping || !aiEnabled">
          <i class="fas fa-paper-plane"></i>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, nextTick, computed } from 'vue'
import { getAIConfig, updateAIConfig, chatWithAIStream } from './aiService'
import { ProjectContext, buildMessagesWithContext } from './projectContext'

const props = defineProps<{
  projectContext?: ProjectContext
}>()

const messages = ref<Array<{id: number; type: string; content: string}>>([])
const inputMessage = ref('')
const isTyping = ref(false)
const streamStarted = ref(false)  // 是否已收到首个流式分片（用于隐藏“思考中”提示）
const showConfig = ref(false)
const saving = ref(false)
const configMessage = ref<{type: string; text: string} | null>(null)
const chatMessagesRef = ref<HTMLElement | null>(null)
const aiEnabled = ref(false)
const chatSessionId = ref<string>('')
// 多轮对话历史（role/content），随消息累积并回传给大模型
const conversationHistory = ref<Array<{ role: string; content: string }>>([])

const config = reactive({
  api_key: '',
  base_url: 'https://api.openai.com/v1',
  model: 'gpt-3.5-turbo',
  includeContext: true
})

const hasProjectContext = computed(() => {
  if (!props.projectContext) return false
  const ctx = props.projectContext
  return ctx.umlElements.length > 0 || 
         ctx.archimateElements.length > 0 || 
         ctx.erEntities.length > 0
})

onMounted(async () => {
  await loadConfig()
})

const loadConfig = async () => {
  try {
    const result = await getAIConfig()
    if (result.config) {
      config.api_key = result.config.api_key || ''
      config.base_url = result.config.base_url || 'https://api.openai.com/v1'
      config.model = result.config.model || 'gpt-3.5-turbo'
      config.includeContext = result.config.includeContext !== false
      aiEnabled.value = result.config.enabled || false
    }
  } catch (e) {
    console.error('Failed to load config:', e)
  }
}

const saveConfig = async () => {
  saving.value = true
  configMessage.value = null

  try {
    // 后端出于安全不回显 api_key，输入框刷新后恒为空。
    // 只有用户输入了新的 Key 才提交，避免把空串回写后端清空已保存的密钥。
    const payload: {
      api_key?: string
      base_url: string
      model: string
      includeContext: boolean
    } = {
      base_url: config.base_url,
      model: config.model,
      includeContext: config.includeContext
    }
    if (config.api_key && config.api_key.trim()) {
      payload.api_key = config.api_key.trim()
    }
    const result = await updateAIConfig(payload)
    if (result.error) {
      configMessage.value = { type: 'error', text: result.error }
    } else {
      configMessage.value = { type: 'success', text: '配置保存成功' }
      aiEnabled.value = result.config?.enabled || false
      // 保留输入框内已填的内容，避免保存后清空用户刚输入的 Key
      showConfig.value = false
    }
  } catch (error) {
    configMessage.value = { type: 'error', text: '保存失败，请重试' }
  } finally {
    saving.value = false
  }
}

const sendMessage = async () => {
  if (!inputMessage.value.trim() || isTyping.value) return

  // 与发送按钮的 disabled 状态保持一致：AI 未启用时不发送 mock 假回复
  if (!aiEnabled.value) {
    messages.value.push({
      id: Date.now(),
      type: 'bot',
      content: 'AI服务未启用，请先点击右上角「配置」填写API密钥后再提问。'
    })
    return
  }

  const message = inputMessage.value.trim()

  messages.value.push({
    id: Date.now(),
    type: 'user',
    content: message
  })

  inputMessage.value = ''
  isTyping.value = true
  scrollToBottom()

  try {
    await sendNormalMessage(message)
  } catch (error) {
    messages.value.push({
      id: Date.now(),
      type: 'bot',
      content: `错误: ${error instanceof Error ? error.message : '发送失败'}`
    })
  } finally {
    isTyping.value = false
    scrollToBottom()
  }
}

const buildMessages = (message: string): Array<{ role: string; content: string }> => {
  let systemContent = '你是一个专业的企业架构AI助手，擅长分析UML类图、ArchiMate架构模型和ER数据模型。'

  if (config.includeContext && props.projectContext) {
    const built = buildMessagesWithContext(message, props.projectContext)
    systemContent = built[0].content
  }

  const result: Array<{ role: string; content: string }> = [
    { role: 'system', content: systemContent }
  ]
  // 追加历史对话（限制最近 20 轮，避免请求过长），实现多轮记忆
  result.push(...conversationHistory.value.slice(-20))
  result.push({ role: 'user', content: message })
  return result
}

const sendNormalMessage = async (message: string) => {
  const conversationMessages = buildMessages(message)

  // 先放一个空的 bot 气泡，流式内容实时往里面填
  const botMsgId = Date.now()
  messages.value.push({ id: botMsgId, type: 'bot', content: '' })
  streamStarted.value = false

  let fullContent = ''
  let streamError: string | null = null

  await chatWithAIStream(
    conversationMessages,
    (chunk) => {
      streamStarted.value = true
      fullContent += chunk
      const idx = messages.value.findIndex((m) => m.id === botMsgId)
      if (idx >= 0) {
        messages.value[idx].content = fullContent
      }
      scrollToBottom()
    },
    (error) => {
      streamError = error
    },
    chatSessionId.value
  )

  const idx = messages.value.findIndex((m) => m.id === botMsgId)

  if (streamError) {
    // 失败：占位气泡直接显示错误，不写入对话历史
    if (idx >= 0) {
      messages.value[idx].content = `错误: ${streamError}`
    } else {
      messages.value.push({ id: Date.now(), type: 'bot', content: `错误: ${streamError}` })
    }
    return
  }

  // 成功：填充完成内容并记录历史，供下一轮作为上下文回传
  const finalContent = fullContent || '（无回复）'
  if (idx >= 0) {
    messages.value[idx].content = finalContent
  }
  conversationHistory.value.push({ role: 'user', content: message })
  conversationHistory.value.push({ role: 'assistant', content: finalContent })
}

const clearChat = () => {
  messages.value = []
  chatSessionId.value = ''
  conversationHistory.value = []
}

const scrollToBottom = () => {
  nextTick(() => {
    if (chatMessagesRef.value) {
      chatMessagesRef.value.scrollTop = chatMessagesRef.value.scrollHeight
    }
  })
}
</script>

<style scoped>
.ai-assistant {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: white;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}

.ai-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  border-bottom: 1px solid #e8ecf0;
}

.ai-header h3 {
  margin: 0;
  font-size: 18px;
  color: #333;
}

.ai-actions {
  display: flex;
  gap: 8px;
}

.ai-config-panel {
  padding: 16px;
  background: #f8f9fa;
  border-bottom: 1px solid #e8ecf0;
}

.ai-config-panel h4 {
  margin: 0 0 16px 0;
  font-size: 16px;
  color: #333;
}

.config-item {
  margin-bottom: 12px;
}

.config-item label {
  display: block;
  margin-bottom: 4px;
  font-size: 14px;
  color: #666;
}

.config-item input[type="text"],
.config-item input[type="password"] {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 14px;
}

.config-item input[type="checkbox"] {
  margin-right: 8px;
}

.config-actions {
  display: flex;
  gap: 8px;
  margin-top: 16px;
}

.config-message {
  margin-top: 12px;
  padding: 8px 12px;
  border-radius: 4px;
  font-size: 14px;
}

.config-message.success {
  background: #d4edda;
  color: #155724;
  border: 1px solid #c3e6cb;
}

.config-message.error {
  background: #f8d7da;
  color: #721c24;
  border: 1px solid #f5c6cb;
}

.ai-chat {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.chat-message {
  display: flex;
  max-width: 80%;
}

.chat-message.user {
  align-self: flex-end;
  flex-direction: row-reverse;
}

.chat-message.bot {
  align-self: flex-start;
}

.chat-bubble {
  padding: 12px 16px;
  border-radius: 12px;
  line-height: 1.5;
  font-size: 14px;
}

.chat-message.user .chat-bubble {
  background: #007bff;
  color: white;
  border-bottom-right-radius: 4px;
}

.chat-message.bot .chat-bubble {
  background: #f1f3f5;
  color: #333;
  border-bottom-left-radius: 4px;
}

.bot-avatar {
  display: inline-block;
  margin-right: 8px;
  color: #666;
}

.message-content {
  white-space: pre-wrap;
  word-break: break-word;
}

.chat-input {
  display: flex;
  gap: 8px;
  padding: 16px;
  border-top: 1px solid #e8ecf0;
  background: white;
}

.chat-input textarea {
  flex: 1;
  padding: 12px;
  border: 1px solid #ddd;
  border-radius: 8px;
  resize: none;
  font-size: 14px;
  font-family: inherit;
}

.chat-input textarea:focus {
  outline: none;
  border-color: #007bff;
}

.chat-input button {
  padding: 12px 24px;
  background: #007bff;
  color: white;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  font-size: 16px;
  transition: background 0.2s;
}

.chat-input button:hover:not(:disabled) {
  background: #0056b3;
}

.chat-input button:disabled {
  background: #ccc;
  cursor: not-allowed;
}
</style>
