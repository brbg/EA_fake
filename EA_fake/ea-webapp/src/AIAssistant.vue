<template>
  <div class="ai-assistant">
    <div class="ai-header">
      <!-- 左上角 ☰：项目管理（项目列表 / 新建 / 打开 / 删除） -->
      <button class="hamburger" @click="showProjects = true" title="项目管理">
        <i class="fas fa-bars"></i>
      </button>
      <span class="ai-current-project" v-if="projectId">{{ (models || []).find(m => m.id === projectId)?.name }}</span>
      <!-- 居中标题：点击「>」进入账号管理 -->
      <div class="ai-title-wrap">
        <button class="ai-title-btn" @click="showAccount = true" title="账号管理">
          AI 智能体 <i class="fas fa-chevron-right ai-title-arrow"></i>
        </button>
        <span class="ai-disclaimer">AI 生成内容可能有误，请加以判断后再部署</span>
      </div>
      <div class="ai-actions">
        <button class="switch-page-btn" data-tab="studio" @click="emit('open-studio')" title="切换到专业编辑（UML / ArchiMate / ER 等）">
          <i class="fas fa-drafting-compass"></i> 专业编辑
        </button>
        <button class="icon-btn" @click="showMemory = !showMemory" :class="{ active: showMemory }" title="记忆库">
          <i class="fas fa-brain"></i>
        </button>
        <button class="icon-btn" @click="showConfig = !showConfig" :class="{ active: showConfig }" title="配置">
          <i class="fas fa-cog"></i>
        </button>
        <button class="icon-btn" @click="clearChat" title="清空对话">
          <i class="fas fa-trash"></i>
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
        <label>推理模型（复杂任务专用，可留空）</label>
        <input
          type="text"
          v-model="config.reasoning_model"
          placeholder="如 deepseek-reasoner；架构评审/校验/AI编辑会用它"
        />
        <span style="font-size:12px; color:#999; display:block; margin-top:4px;">留空则所有任务都用上面的模型</span>
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

    <div v-if="showMemory" class="ai-memory-panel">
      <h4><i class="fas fa-brain"></i> 项目记忆库</h4>
      <p style="color:#999; font-size:12px; margin:0 0 12px 0;">
        记忆会随每个问题注入给 AI。可手动添加，也可在对话中说「记住：xxx」自动保存。
      </p>
      <div v-if="memories.length === 0" style="color:#999; font-size:13px; padding: 8px 0;">
        暂无记忆。
      </div>
      <div v-for="mem in memories" :key="mem.id" class="memory-item">
        <span>{{ mem.content }}</span>
        <button class="memory-del" @click="deleteMemory(mem.id)" title="删除">
          <i class="fas fa-trash"></i>
        </button>
      </div>
      <div class="memory-add">
        <input
          v-model="newMemory"
          placeholder="添加一条项目记忆…"
          @keydown.enter.prevent="addMemory"
        />
        <button class="btn btn-primary" @click="addMemory" :disabled="savingMemory || !newMemory.trim()">
          <i v-if="savingMemory" class="fas fa-spinner fa-spin"></i> 保存
        </button>
      </div>
      <div v-if="memoryMsg" :class="['config-message', memoryMsg.type]">
        {{ memoryMsg.text }}
      </div>
    </div>

    <!-- ☰ 左侧项目抽屉（豆包式列表交互）：项目列表 + 新建 / 切换 / 删除。
         用 Teleport 挂到 body：避免祖先的 backdrop-filter 创建 containing block 导致 fixed 定位偏移 -->
    <Teleport to="body">
    <Transition name="fade">
      <div v-if="showProjects" class="drawer-overlay" @click="showProjects = false"></div>
    </Transition>
    <Transition name="slide-left">
      <aside v-if="showProjects" class="drawer">
        <div class="drawer-head">
          <b><i class="fas fa-folder-open" style="color:#1f5eff;"></i> 项目管理</b>
          <button class="btn btn-primary drawer-new" @click="emit('new-project')"><i class="fas fa-plus"></i> 新建项目</button>
        </div>
        <div class="drawer-list">
          <div v-for="m in (models || [])" :key="m.id" class="drawer-item" :class="{ active: m.id === projectId }"
               @click="pickProject(m.id)">
            <span class="di-icon"><i class="fas fa-folder"></i></span>
            <span class="di-name">{{ m.name }}</span>
            <span class="di-role" v-if="m.role === 'editor'">协作</span>
            <button class="di-del" @click.stop="emit('delete-project', m.id)" title="删除项目"><i class="fas fa-trash"></i></button>
          </div>
          <p v-if="!(models || []).length" class="drawer-empty">还没有项目——点「新建项目」开始，或直接在下方描述业务让我自动新建。</p>
        </div>
      </aside>
    </Transition>
    </Teleport>

    <!-- 账号管理抽屉（点标题旁「>」进入） -->
    <Teleport to="body">
    <Transition name="fade">
      <div v-if="showAccount" class="drawer-overlay" @click="showAccount = false"></div>
    </Transition>
    <Transition name="slide-left">
      <aside v-if="showAccount" class="drawer account-drawer">
        <div class="drawer-head">
          <b><i class="fas fa-circle-user" style="color:#1f5eff;"></i> 账号管理</b>
        </div>
        <div class="account-body">
          <div class="account-row">
            <span class="account-label">当前账号</span>
            <span class="account-value">{{ userInfo.username || '—' }}</span>
          </div>
          <div class="account-row">
            <span class="account-label">绑定邮箱</span>
            <span class="account-value">{{ userInfo.email || '—' }}</span>
          </div>
        </div>
        <div class="account-actions">
          <button class="btn btn-outline account-btn" @click="emit('logout')"><i class="fas fa-right-from-bracket"></i> 退出账号</button>
          <button class="btn btn-outline account-btn" @click="emit('switch-account')"><i class="fas fa-arrows-rotate"></i> 切换账号</button>
        </div>
      </aside>
    </Transition>
    </Teleport>

    <div class="ai-chat">
      <div class="chat-messages" ref="chatMessagesRef">
        <!-- 初始态：居中标语（GPT / 豆包式首页） -->
        <div class="ai-hero" v-if="!messages.length && !agentSteps.length">
          <h1>{{ aiEnabled ? '有什么我能帮你的吗？' : 'AI 服务未启用' }}</h1>
          <p v-if="aiEnabled">一句话描述业务，我自动生成 UML + ArchiMate + ER 整套企业架构</p>
          <p v-else>请点右上角「配置」填写 API 密钥后开始</p>
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
            <div>
              <details v-if="msg.thinking" class="think-block">
                <summary><i class="fas fa-brain"></i> 深度思考过程</summary>
                <div class="think-content">{{ msg.thinking }}</div>
              </details>
              <div class="message-content">{{ msg.content }}</div>
            </div>
          </div>
        </div>
      </div>

      <AgentRunSteps v-if="agentSteps.length" :steps="agentSteps" @close="agentSteps = []" />

      <div class="agent-chips" v-if="aiEnabled">
        <button class="agent-chip" @click="inputMessage = '设计一个智慧农业平台：涵盖农田种植、农机调度、农产品溯源、订单销售'" :disabled="isTyping"><i class="fas fa-wand-magic-sparkles"></i> ⚡ 一键生成架构</button>
        <button class="agent-chip" @click="inputMessage = '先体检当前项目，再按建议自动优化'" :disabled="isTyping"><i class="fas fa-heart-pulse"></i> 体检并优化</button>
        <button class="agent-chip" @click="inputMessage = '给模型添加一个 '" :disabled="isTyping"><i class="fas fa-pen"></i> 帮我改模型</button>
      </div>

      <div class="agent-box" v-if="aiEnabled">
        <textarea
          v-model="inputMessage"
          rows="1"
          placeholder="给智能体发消息…（一句话描述业务可自动生成整套架构）"
          @keydown.enter.exact.prevent="sendMessage"
          :disabled="isTyping"
        ></textarea>
        <button class="send-btn" @click="sendMessage" :disabled="!inputMessage.trim() || isTyping" title="发送">
          <i v-if="isTyping" class="fas fa-spinner fa-spin"></i>
          <i v-else class="fas fa-arrow-up"></i>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onActivated, nextTick, watch } from 'vue'
import { getAIConfig, updateAIConfig } from './aiService'
import { aiApi } from './api/ai'
import { ProjectContext } from './projectContext'
import { runAgentChat, fetchAgentHistory, clearAgentHistory } from './agentService'
import type { AgentStepView } from './agentService'
import AgentRunSteps from './components/AgentRunSteps.vue'

const props = defineProps<{
  projectContext?: ProjectContext
  projectId?: string
  models?: Array<{ id: string; name: string }>
  user?: { username?: string; email?: string } | null
}>()
const emit = defineEmits<{
  (e: 'refresh-model', p: { relayout: boolean }): void
  (e: 'model-created', p: { id: string; name: string }): void
  (e: 'open-project', id: string): void
  (e: 'new-project'): void
  (e: 'delete-project', id: string): void
  (e: 'open-studio'): void
  (e: 'logout'): void
  (e: 'switch-account'): void
}>()

// 项目管理弹窗（左上角 ☰ 打开）
const showProjects = ref(false)
// 账号管理（当前账号 / 邮箱 / 退出 / 切换）
const showAccount = ref(false)
const userInfo = computed(() => {
  if (props.user && props.user.username) return props.user
  try { return JSON.parse(sessionStorage.getItem('ea_user') || '{}') } catch { return {} }
})

// 智能体工具轨迹（由工具循环事件驱动）
const agentSteps = ref<AgentStepView[]>([])

const messages = ref<Array<{id: number; type: string; content: string; thinking?: string}>>([])
// 消息 id 用单调递增计数器（Date.now() 毫秒级会与用户消息/占位气泡撞 id，导致流式写入错位）
let msgIdCounter = 0
const nextMsgId = () => ++msgIdCounter
const inputMessage = ref('')
const isTyping = ref(false)
const showConfig = ref(false)
const saving = ref(false)
const configMessage = ref<{type: string; text: string} | null>(null)

// 项目专属记忆库
const showMemory = ref(false)
const memories = ref<Array<{ id: string; content: string; created_at: string }>>([])
const newMemory = ref('')
const savingMemory = ref(false)
const memoryMsg = ref<{type: string; text: string} | null>(null)
const chatMessagesRef = ref<HTMLElement | null>(null)
const aiEnabled = ref(false)
const chatSessionId = ref<string>('')
// 多轮对话历史由后端按项目保存（/api/v1/ai/agent/history），前端不再自持

const config = reactive({
  api_key: '',
  base_url: 'https://api.openai.com/v1',
  model: 'gpt-3.5-turbo',
  reasoning_model: '',
  includeContext: true
})

onMounted(async () => {
  await loadConfig()
  if (props.projectId) {
    await loadMemories()
    await loadAgentHistory(props.projectId)
  }
})

// KeepAlive 保活：从专业编辑切回时对话记录原样保留，只需滚到最新一条
onActivated(() => {
  scrollToBottom()
})

// 用户主动点项目切换（需要恢复该项目的历史对话）；智能体内部创建/绑定项目时不重置对话
let userSwitching = false
const pickProject = (id: string) => {
  userSwitching = true
  emit('open-project', id)
  showProjects.value = false
}

// 项目切换时同步加载记忆 +（用户主动切换时）该项目的历史对话
watch(() => props.projectId, (pid) => {
  if (pid) {
    loadMemories()
    if (userSwitching) {
      userSwitching = false
      loadAgentHistory(pid)  // 用户切换项目：恢复该项目的历史对话
    }
    // 智能体内部创建/绑定项目：保留当前对话，不重置（否则会闪出空态页）
  } else {
    memories.value = []
    messages.value = []
    agentSteps.value = []
  }
})

// 加载某项目的历史对话（点项目即恢复该项目的对话；历史由后端按项目保存）
const loadAgentHistory = async (pid: string) => {
  const hist = await fetchAgentHistory(pid)
  messages.value = hist
    .filter((m) => m.role === 'user' || m.role === 'assistant')
    .map((m) => ({ id: nextMsgId(), type: m.role === 'user' ? 'user' : 'bot', content: m.content }))
  agentSteps.value = []
  await nextTick()
  scrollToBottom()
}

const loadMemories = async () => {
  if (!props.projectId) {
    memories.value = []
    return
  }
  try {
    const { data } = await aiApi.memoryList(props.projectId)
    if (data?.memories) {
      memories.value = data.memories
    }
  } catch (e) {
    // 网络异常静默处理
  }
}

const addMemory = async () => {
  const content = newMemory.value.trim()
  if (!content || !props.projectId) return
  savingMemory.value = true
  memoryMsg.value = null
  try {
    const { ok, data } = await aiApi.memoryAdd(props.projectId, { content })
    if (data?.error || !ok) {
      memoryMsg.value = { type: 'error', text: data?.error || '保存失败' }
    } else {
      memories.value = data?.memories || memories.value
      newMemory.value = ''
      memoryMsg.value = { type: 'success', text: '已记入记忆库' }
    }
  } catch (e) {
    memoryMsg.value = { type: 'error', text: '保存失败，请检查后端服务' }
  } finally {
    savingMemory.value = false
  }
}

const deleteMemory = async (id: string) => {
  if (!props.projectId) return
  try {
    const { data } = await aiApi.memoryDelete(props.projectId, id)
    if (data?.memories) {
      memories.value = data.memories
    }
  } catch (e) {
    // 忽略
  }
}

// 对话中「记住：xxx」→ 静默写入记忆库
const saveMemorySilently = async (content: string) => {
  if (!props.projectId || !content) return
  try {
    await aiApi.memoryAdd(props.projectId, { content })
    await loadMemories()
    memoryMsg.value = { type: 'success', text: '已记入项目记忆库' }
  } catch (e) {
    // 忽略
  }
}

const loadConfig = async () => {
  try {
    const result = await getAIConfig()
    if (result.config) {
      config.api_key = result.config.api_key || ''
      config.base_url = result.config.base_url || 'https://api.openai.com/v1'
      config.model = result.config.model || 'gpt-3.5-turbo'
      config.reasoning_model = result.config.reasoning_model || ''
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
      reasoning_model: string
      includeContext: boolean
    } = {
      base_url: config.base_url,
      model: config.model,
      reasoning_model: config.reasoning_model.trim(),
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
      id: nextMsgId(),
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
    // 全面智能体：所有消息统一走工具调用循环（architect 一键按钮仍是快捷入口）
    await sendNormalMessage(message)
  } catch (error) {
    messages.value.push({
      id: nextMsgId(),
      type: 'bot',
      content: `错误: ${error instanceof Error ? error.message : '发送失败'}`
    })
  } finally {
    isTyping.value = false
    scrollToBottom()
  }
}

const TOOL_LABEL: Record<string, string> = {
  create_project: '新建项目',
  generate_architecture: '生成完整企业架构',
  edit_model: '修改模型',
  get_health: '健康度体检',
  optimize_from_health: '按体检优化模型'
}
// 工具调用进行时，智能体「说的话」（让用户知道正在做什么）
const TOOL_SAY: Record<string, string> = {
  create_project: '好的，我先把项目创建出来…',
  generate_architecture: '正在为你生成整套企业架构（UML + ArchiMate + ER）…',
  edit_model: '正在按你的要求修改模型…',
  get_health: '正在体检当前项目…',
  optimize_from_health: '正在按体检结果优化模型…'
}
// 会产生写操作（改模型/生成/优化）的工具——事后需刷新前端画布
const WRITE_TOOLS = ['generate_architecture', 'edit_model', 'optimize_from_health']

// 全面智能体：所有消息都走工具调用循环（不再有普通聊天助手）
const sendNormalMessage = async (message: string) => {
  await runAgentChatMessage(message)
}

const runAgentChatMessage = async (message: string): Promise<void> => {
  const botMsgId = nextMsgId()
  messages.value.push({ id: botMsgId, type: 'bot', content: '收到，正在处理…' })
  const steps: AgentStepView[] = []
  agentSteps.value = []
  let finalText = ''
  let fatal = ''
  let sawWrite = false
  let sawGenerate = false
  try {
    await runAgentChat(props.projectId, message, memories.value.map((m) => m.content), (ev) => {
      if (ev.type === 'tool_call') {
        steps.push({ key: 't' + steps.length, title: TOOL_LABEL[ev.name || ''] || ev.name || '工具', status: 'running', detail: ev.args })
        agentSteps.value = steps.slice()
        // 智能体「说」一句正在做什么（过程可见）
        const bi = messages.value.findIndex((m) => m.id === botMsgId)
        if (bi >= 0) messages.value[bi].content = TOOL_SAY[ev.name || ''] || '正在处理…'
      } else if (ev.type === 'tool_result') {
        const s = steps[steps.length - 1]
        if (s) { s.status = ev.ok ? 'ok' : 'error'; s.detail = { args: s.detail, result: ev.summary } }
        agentSteps.value = steps.slice()
        // 写操作成功 → 结束后刷新前端画布，保证与后端一致
        if (ev.ok && ev.name && WRITE_TOOLS.includes(ev.name)) sawWrite = true
        if (ev.ok && ev.name === 'generate_architecture') sawGenerate = true
        // 智能体新建/绑定了项目 → 通知父级绑定该项目（无需用户预先打开项目）
        if (ev.ok && ev.project && ev.project.project_id) {
          emit('model-created', { id: ev.project.project_id, name: ev.project.project_name || '' })
        }
      } else if (ev.type === 'final') {
        finalText = ev.content || ''
      } else if (ev.type === 'fatal') {
        fatal = ev.error || 'agent 失败'
      }
      scrollToBottom()
    })
  } catch (e) {
    fatal = e instanceof Error ? e.message : 'agent 请求失败'
  }
  if (fatal) {
    const i = messages.value.findIndex((m) => m.id === botMsgId)
    if (i >= 0) messages.value[i].content = `智能体执行失败：${fatal}`
    scrollToBottom()
    return
  }
  const idx = messages.value.findIndex((m) => m.id === botMsgId)
  if (idx >= 0) messages.value[idx].content = finalText || '（已完成）'
  // （历史对话已由后端按项目保存，无需前端维护）
  // 自动记忆：说「记住：xxx」时写入项目记忆库
  const rememberMatch = message.match(/记住[：:，,、\s]*(.+)/)
  if (rememberMatch && rememberMatch[1] && rememberMatch[1].trim()) {
    await saveMemorySilently(rememberMatch[1].trim())
  }
  // 智能体在后端改了库 → 通知父级重载当前项目（生成类操作额外重排一次防重叠）
  if (sawWrite) emit('refresh-model', { relayout: sawGenerate })
  scrollToBottom()
}

const clearChat = async () => {
  messages.value = []
  agentSteps.value = []
  chatSessionId.value = ''
  // 同步清空后端该项目的历史对话
  if (props.projectId) await clearAgentHistory(props.projectId)
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
/* ☰ 左侧会话抽屉（对话列表） */
.drawer-overlay { position: fixed; inset: 0; background: rgba(15, 23, 42, .35); z-index: 3000; }
.drawer { position: fixed; top: 0; left: 0; bottom: 0; width: 300px; max-width: 84vw; background: #fff; z-index: 3001; box-shadow: 6px 0 30px rgba(0, 0, 0, .12); display: flex; flex-direction: column; }
.drawer-head { display: flex; align-items: center; gap: 8px; padding: 14px; border-bottom: 1px solid #eef1f6; }
.drawer-head b { margin-right: auto; font-size: 14px; color: #222; }
.drawer-new { padding: 6px 10px; font-size: 12px; }
.drawer-list { flex: 1; overflow-y: auto; padding: 8px; }
.drawer-item { display: flex; align-items: center; gap: 8px; padding: 9px 10px; border-radius: 9px; cursor: pointer; font-size: 13px; color: #334155; transition: background .15s; }
.drawer-item:hover { background: #f4f7ff; }
.drawer-item.active { background: #eef4ff; color: #1f5eff; }
.di-icon { color: #94a3b8; }
.drawer-item.active .di-icon { color: #1f5eff; }
.di-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.di-role { font-size: 10px; color: #16a34a; background: #e8f7ee; padding: 1px 6px; border-radius: 999px; }
.di-del { border: none; background: transparent; color: #cbd5e1; cursor: pointer; opacity: 0; transition: opacity .15s; }
.drawer-item:hover .di-del { opacity: 1; }
.di-del:hover { color: #dc2626; }
.drawer-empty { color: #8b98ab; font-size: 12px; text-align: center; padding: 20px 10px; }
/* 抽屉过渡动画 */
.fade-enter-active, .fade-leave-active { transition: opacity .25s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
.slide-left-enter-active, .slide-left-leave-active { transition: transform .28s cubic-bezier(.22, 1, .36, 1); }
.slide-left-enter-from, .slide-left-leave-to { transform: translateX(-100%); }

/* 账号管理抽屉（点标题「>」进入）：只读账号信息 + 退出 / 切换账号 */
.account-drawer { width: 320px; }
.account-body { flex: 1; overflow-y: auto; padding: 14px; display: flex; flex-direction: column; gap: 10px; }
.account-row { display: flex; flex-direction: column; gap: 5px; padding: 12px 14px; border: 1px solid #eef1f6; border-radius: 10px; background: #fafbfd; }
.account-label { font-size: 12px; color: #8b98ab; }
.account-value { font-size: 14px; font-weight: 500; color: #1f2937; word-break: break-all; }
.account-actions { padding: 14px; border-top: 1px solid #eef1f6; display: flex; flex-direction: column; gap: 8px; }
.account-btn { width: 100%; justify-content: center; padding: 9px 12px; font-size: 13px; border-radius: 9px; }

.agent-launch { display: flex; align-items: center; gap: 8px; padding: 6px 2px 10px; flex-wrap: wrap; }
.agent-launch-btn { background: linear-gradient(135deg, #1f5eff, #6a5acd); border: none; color: #fff; }
.agent-hint { font-size: 11px; color: #8b98ab; }
/* 输入条：紧凑圆角矩形（单行、右侧圆形发送），宽度居中 */
.agent-box {
  max-width: 760px;
  width: calc(100% - 32px);
  margin: 0 auto 16px;
  background: #fff;
  border: 1px solid #e3e8f1;
  border-radius: 18px;
  box-shadow: 0 2px 10px rgba(15, 23, 42, .06);
  display: flex;
  align-items: flex-end;
  gap: 8px;
  padding: 7px 8px 7px 16px;
  transition: border-color .2s, box-shadow .2s;
}
.agent-box:focus-within { border-color: #1f5eff; box-shadow: 0 2px 14px rgba(31, 94, 255, .14); }
.agent-box textarea {
  flex: 1;
  border: none;
  outline: none;
  background: transparent;
  resize: none;
  font-family: inherit;
  font-size: 14px;
  line-height: 1.5;
  color: #1f2937;
  padding: 7px 0;
  max-height: 120px;
}
.agent-box .send-btn {
  width: 34px;
  height: 34px;
  border-radius: 50%;
  border: none;
  background: #1f5eff;
  color: #fff;
  font-size: 14px;
  cursor: pointer;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background .2s;
}
.agent-box .send-btn:hover:not(:disabled) { background: #1749c9; }
.agent-box .send-btn:disabled { background: #c9d6f5; cursor: not-allowed; }
.agent-actions { display: flex; align-items: center; gap: 8px; padding: 4px 2px 8px; }
.agent-delete { color: #dc2626; border-color: #f3c6c6; }
.agent-chips { display: flex; gap: 6px; flex-wrap: wrap; justify-content: center; max-width: 760px; margin: 0 auto; padding: 0 2px 10px; }
.agent-chip { font-size: 12px; padding: 3px 10px; border: 1px solid #d8e0ee; background: #fff; color: #4a5568; border-radius: 999px; cursor: pointer; transition: all .2s; }
.agent-chip:hover:not(:disabled) { border-color: #1f5eff; color: #1f5eff; }
.agent-chip:disabled { opacity: .5; cursor: not-allowed; }

.ai-assistant {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: white;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}

.ai-header {
  position: relative;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 14px;
  border-bottom: 1px solid #e8ecf0;
}
.hamburger { width: 36px; height: 36px; border-radius: 9px; border: 1px solid #e3e8f1; background: #fff; color: #334155; font-size: 15px; cursor: pointer; transition: all .2s; }
.hamburger:hover { border-color: #1f5eff; color: #1f5eff; background: #f4f7ff; }
/* 居中标题块：标题（可点进账号管理）+ 下方免责小字 */
.ai-title-wrap {
  position: absolute;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1px;
  pointer-events: none;
}
.ai-title-btn {
  pointer-events: auto;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  border: none;
  background: transparent;
  padding: 2px 8px;
  border-radius: 8px;
  font-size: 15px;
  font-weight: 600;
  color: #1f2937;
  cursor: pointer;
  transition: all .2s;
}
.ai-title-btn:hover { background: #f1f5f9; color: #1f5eff; }
.ai-title-arrow { font-size: 11px; color: #94a3b8; }
.ai-title-btn:hover .ai-title-arrow { color: #1f5eff; }
.ai-disclaimer {
  pointer-events: auto;
  font-size: 11px;
  color: #94a3b8;
}
.ai-current-project { font-size: 12px; color: #1f5eff; background: #eef4ff; padding: 2px 10px; border-radius: 999px; max-width: 240px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ai-actions { display: flex; gap: 6px; margin-left: auto; }
.switch-page-btn { display: inline-flex; align-items: center; gap: 6px; padding: 6px 12px; border-radius: 999px; border: 1px solid #dbe4ff; background: #f4f7ff; color: #1f5eff; font-size: 12px; cursor: pointer; transition: all .2s; }
.switch-page-btn:hover { background: #1f5eff; color: #fff; border-color: #1f5eff; }
.icon-btn { width: 34px; height: 34px; border-radius: 9px; border: 1px solid #e3e8f1; background: #fff; color: #64748b; cursor: pointer; transition: all .2s; }
.icon-btn:hover, .icon-btn.active { border-color: #1f5eff; color: #1f5eff; background: #f4f7ff; }
.ai-hero { margin: auto; text-align: center; padding: 24px; }
.ai-hero h1 { font-size: 30px; font-weight: 700; color: #1f2937; margin: 0 0 12px; letter-spacing: .5px; }
.ai-hero p { font-size: 13px; color: #8b98ab; margin: 0; }

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

.ai-memory-panel {
  padding: 16px;
  background: #f8f9fa;
  border-bottom: 1px solid #e8ecf0;
}

.ai-memory-panel h4 {
  margin: 0 0 4px 0;
  font-size: 16px;
  color: #333;
}

.memory-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  background: #fff;
  border: 1px solid #e8ecf0;
  border-radius: 6px;
  padding: 8px 12px;
  margin-bottom: 8px;
  font-size: 13px;
  color: #444;
}

.memory-del {
  border: none;
  background: transparent;
  color: #999;
  cursor: pointer;
  font-size: 13px;
}

.memory-del:hover {
  color: #d33;
}

.memory-add {
  display: flex;
  gap: 8px;
  margin-top: 12px;
}

.memory-add input {
  flex: 1;
  padding: 8px 12px;
  border: 1px solid #ddd;
  border-radius: 6px;
  font-size: 13px;
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
  background: var(--glass-bg);
  backdrop-filter: blur(var(--glass-blur)) saturate(var(--glass-saturation));
  -webkit-backdrop-filter: blur(var(--glass-blur)) saturate(var(--glass-saturation));
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
  border: 1px solid rgba(255, 255, 255, 0.6);
  box-shadow: 0 4px 16px rgba(15, 23, 42, 0.06);
}

.chat-message.user .chat-bubble {
  background: linear-gradient(135deg, #1f5eff, #4a7bff);
  color: white;
  border-bottom-right-radius: 4px;
  border: none;
  box-shadow: 0 4px 14px rgba(31, 94, 255, 0.28);
}

.chat-message.bot .chat-bubble {
  background: rgba(255, 255, 255, 0.78);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
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

/* 深度思考过程（可折叠） */
.think-block {
  margin-bottom: 8px;
  border: 1px dashed #d0c7f0;
  border-radius: 8px;
  background: #f7f5ff;
  font-size: 12px;
}
.think-block summary {
  padding: 6px 10px;
  cursor: pointer;
  color: #6a5acd;
  user-select: none;
}
.think-block summary i {
  margin-right: 4px;
}
.think-content {
  padding: 0 10px 8px;
  color: #7a6fb0;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 200px;
  overflow-y: auto;
}

.chat-input {
  display: flex;
  gap: 8px;
  padding: 16px;
  border-top: 1px solid var(--glass-border);
  background: var(--glass-bg);
  backdrop-filter: blur(var(--glass-blur)) saturate(var(--glass-saturation));
  -webkit-backdrop-filter: blur(var(--glass-blur)) saturate(var(--glass-saturation));
}

.chat-input textarea {
  flex: 1;
  padding: 12px;
  border: 1px solid var(--glass-border);
  border-radius: 8px;
  resize: none;
  font-size: 14px;
  font-family: inherit;
  background: rgba(255, 255, 255, 0.8);
}

.chat-input textarea:focus {
  outline: none;
  border-color: #1f5eff;
}

.chat-input button {
  padding: 12px 24px;
  background: #1f5eff;
  color: white;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  font-size: 16px;
  transition: background 0.2s;
}

.chat-input button:hover:not(:disabled) {
  background: #1749cc;
}

.chat-input button:disabled {
  background: #ccc;
  cursor: not-allowed;
}

/* 深度思考开关 */
.chat-input .think-toggle {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 12px 12px;
  background: #fff;
  color: #6a5acd;
  border: 1px solid #d0c7f0;
  border-radius: 8px;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
}
.chat-input .think-toggle:hover:not(:disabled) {
  background: #f7f5ff;
}
.chat-input .think-toggle.active {
  background: #6a5acd;
  color: #fff;
  border-color: #6a5acd;
}
</style>
