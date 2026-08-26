<script setup lang="ts">
import { ref, onMounted, nextTick, watch, computed } from 'vue'
import { io } from 'socket.io-client'
import AIAssistant from './AIAssistant.vue'
import LoginView from './LoginView.vue'
import type { ProjectContext } from './projectContext'
import { getAIConfig } from './aiService'
import { setupCanvasTransform, toLogical, LOGICAL_W, LOGICAL_H } from './canvasUtils'
// 统一 API 层（借鉴 AI_EA_Web 分层：request.ts + 按域 api 模块）
import { authApi } from './api/auth'
import { modelApi } from './api/models'
import { aiApi, codeApi } from './api/ai'
import { devApi } from './api/dev'
import { adminApi } from './api/admin'

// === 登录门禁状态 ===
const authUser = ref<{ username: string; email: string; role?: string; id?: string } | null>(null)
const authChecked = ref(false)
const isAdmin = computed(() => authUser.value?.role === 'admin')

// 进入主界面（登录成功 or 会话恢复有效）
const enterApp = () => {
  nextTick(async () => {
    await loadModels()
    initCanvasEvents()
    initArchimateCanvas()
    initErCanvas()
    updateStats()
  })
}

// 启动时校验本地保存的会话是否仍有效
const checkAuth = async () => {
  const sid = sessionStorage.getItem('sessionId')
  if (!sid) {
    authChecked.value = true
    return
  }
  try {
    const { ok, data } = await authApi.validate()
    if (ok) {
      let saved = null
      try {
        saved = JSON.parse(sessionStorage.getItem('ea_user') || 'null')
      } catch (e) {
        saved = null
      }
      authUser.value = {
        username: data?.user?.username || saved?.username || '用户',
        email: saved?.email || '',
        role: data?.user?.role || saved?.role || '',
        id: data?.user?.id || saved?.id || ''
      }
      enterApp()
    } else {
      sessionStorage.removeItem('sessionId')
      sessionStorage.removeItem('ea_user')
    }
  } catch (e) {
    // 后端未启动等异常：清掉会话，落到登录页
    sessionStorage.removeItem('sessionId')
    sessionStorage.removeItem('ea_user')
  }
  authChecked.value = true
}

const onAuthenticated = (user: { username: string; email: string; role?: string; id?: string; is_new?: boolean }) => {
  authUser.value = user
  enterApp()
  // 首次注册后的首次登录：自动弹出引导（仅一次）
  if (user.is_new) {
    setTimeout(() => startTour(), 700)
  }
}

const logout = async () => {
  try {
    await authApi.logout()
  } catch (e) {
    // 忽略登出接口异常，前端仍然清理本地会话
  }
  sessionStorage.removeItem('sessionId')
  sessionStorage.removeItem('ea_user')
  authUser.value = null
  activeTab.value = 'dashboard'
  // 重置内存中的模型数据，避免下一个账号看到上一个账号的内容
  models.value = []
  elements = []
  connections = []
  archimateElements = []
  archimateConnections = []
  erEntities = []
  erRelations = []
  currentModelId.value = ''
  currentModelName.value = ''
  updateStats()
}

const activeTab = ref('dashboard')
const showCreateModal = ref(false)
const selectedTool = ref('select')
const selectedToolName = computed(() => tools.find((t) => t.id === selectedTool.value)?.name || '选择')
const selectedArchimateToolName = computed(() => archimateTools.find((t) => t.id === selectedArchimateTool.value)?.name || '选择')
const selectedErToolName = computed(() => erTools.find((t) => t.id === selectedErTool.value)?.name || '选择')
const stats = ref({
  models: 0,
  elements: 0,
  relationships: 0,
  views: 0
})

const tabs = [
  { id: 'dashboard', name: '仪表盘', icon: 'fas fa-gauge-high' },
  { id: 'projects', name: '项目管理', icon: 'fas fa-folder-open' },
  { id: 'uml', name: 'UML建模', icon: 'fas fa-diagram-project' },
  { id: 'archimate', name: 'ArchiMate', icon: 'fas fa-cubes' },
  { id: 'data', name: '数据建模', icon: 'fas fa-database' },
  { id: 'code', name: '代码生成', icon: 'fas fa-code' },
  { id: 'dev', name: '研发管理', icon: 'fas fa-tasks' },
  { id: 'ai', name: 'AI助手', icon: 'fas fa-robot' }
]
// 管理员专属 tab（非 admin 不显示）
const navTabs = computed(() => (isAdmin.value ? [...tabs, { id: 'admin', name: '后台管理', icon: 'fas fa-shield-halved' }] : tabs))

const tools = [
  { id: 'select', name: '选择', icon: 'fas fa-mouse-pointer' },
  { id: 'class', name: '类', icon: 'fas fa-box' },
  { id: 'interface', name: '接口', icon: 'fas fa-plug' },
  { id: 'association', name: '关联', icon: 'fas fa-link' },
  { id: 'inheritance', name: '继承', icon: 'fas fa-arrow-up' },
  { id: 'realization', name: '实现', icon: 'fas fa-arrow-right' },
  { id: 'dependency', name: '依赖', icon: 'fas fa-arrow-down' },
  { id: 'composition', name: '组合', icon: 'fas fa-layer-group' },
  { id: 'aggregation', name: '聚合', icon: 'fas fa-object-group' }
]

// ArchiMate 工具定义
const archimateTools = [
  { id: 'select', name: '选择', icon: 'fas fa-mouse-pointer' },
  { id: 'actor', name: '角色', icon: 'fas fa-user' },
  { id: 'process', name: '流程', icon: 'fas fa-cogs' },
  { id: 'service', name: '服务', icon: 'fas fa-concierge-bell' },
  { id: 'component', name: '组件', icon: 'fas fa-puzzle-piece' },
  { id: 'node', name: '节点', icon: 'fas fa-server' },
  { id: 'artifact', name: '制品', icon: 'fas fa-file-alt' },
  { id: 'association', name: '关联', icon: 'fas fa-link' },
  { id: 'realization', name: '实现', icon: 'fas fa-arrow-down' },
  { id: 'serving', name: '服务', icon: 'fas fa-hands-helping' },
]

// ER图工具定义
const erTools = [
  { id: 'select', name: '选择', icon: 'fas fa-mouse-pointer' },
  { id: 'entity', name: '实体', icon: 'fas fa-table' },
  { id: 'oneToOne', name: '1:1', icon: 'fas fa-exchange-alt' },
  { id: 'oneToMany', name: '1:N', icon: 'fas fa-arrow-right' },
  { id: 'manyToMany', name: 'M:N', icon: 'fas fa-arrows-alt-h' },
]

interface Model {
  id: string
  name: string
  description: string
  elements_count: number
  relationships_count: number
  views_count: number
}

const models = ref<Model[]>([])
const newModel = ref({ name: '', description: '' })

// 项目图标：按项目名哈希取渐变色 + 首字母（Notion/Linear 式专业图标）
const PROJECT_GRADIENTS = [
  'linear-gradient(135deg, #6366f1, #8b5cf6)',
  'linear-gradient(135deg, #0ea5e9, #06b6d4)',
  'linear-gradient(135deg, #f59e0b, #f97316)',
  'linear-gradient(135deg, #10b981, #059669)',
  'linear-gradient(135deg, #ef4444, #f43f5e)',
  'linear-gradient(135deg, #ec4899, #a855f7)',
  'linear-gradient(135deg, #14b8a6, #0d9488)',
  'linear-gradient(135deg, #8b5cf6, #d946ef)',
]
const projectIconStyle = (name: string) => {
  let h = 0
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) >>> 0
  return { background: PROJECT_GRADIENTS[h % PROJECT_GRADIENTS.length] }
}
const projectInitial = (name: string) => (name || '?').charAt(0).toUpperCase()

// ArchiMate 建模相关变量
const archimateCanvas = ref<HTMLCanvasElement | null>(null)
let archimateCtx: CanvasRenderingContext2D | null = null
let archimateElements: any[] = []
let archimateConnections: any[] = []
let archimateSelectedElement: any = null
let archimateIsDragging = false
let archimateDragOffset = { x: 0, y: 0 }
let archimateIsConnecting = false
let archimateConnectStartElement: any = null
const selectedArchimateTool = ref('select')
const archimateLayer = ref('business')
const archimateEditingElement = ref<any>(null)
const showArchimateEditModal = ref(false)

// ER图建模相关变量
const erCanvas = ref<HTMLCanvasElement | null>(null)
let erCtx: CanvasRenderingContext2D | null = null
let erEntities: any[] = []
let erRelations: any[] = []
let erSelectedEntity: any = null
let erIsDragging = false
let erDragOffset = { x: 0, y: 0 }
let erIsConnecting = false
let erConnectStartEntity: any = null
const selectedErTool = ref('select')
const erEditingEntity = ref<any>(null)
const showErEditModal = ref(false)
const erSqlResult = ref('')

const codeConfig = ref({ language: 'java', framework: 'spring', source: 'uml', outputType: 'entity' })
const generatedCode = ref('// 选择模型源和输出类型，然后点击生成代码按钮')
const codeGenerating = ref(false)

// 代码反向工程（代码 → 模型）
const reverseConfig = ref({ code: '', language: 'auto', target: 'uml' })

// AI 从描述生成图（UML/ER）
const showGenDiagramModal = ref(false)
const genDiagramKind = ref<'uml' | 'er'>('uml')
const genDiagramText = ref('')
const genDiagramViewType = ref('class')
const genDiagramLoading = ref(false)
const genDiagramError = ref('')
const reversing = ref(false)
const reverseError = ref('')

// AI 文档/报表生成
const docConfig = ref({ docType: 'architecture', format: 'markdown' })
const docGenerating = ref(false)
const generatedDoc = ref('')
const docError = ref('')

const showValidateModal = ref(false)
const validating = ref(false)
const validateResult = ref<any>(null)
const validateError = ref('')

// ArchiMate AI 架构评审
const showReviewModal = ref(false)
const reviewing = ref(false)
const reviewResult = ref<any>(null)
const reviewError = ref('')

// 选中元素 AI 分析
const showAnalyzeModal = ref(false)
const analyzing = ref(false)
const analyzeResult = ref<any>(null)
const analyzeError = ref('')

// 对话式编辑（自然语言改模型）
const showEditModelModal = ref(false)
const editingModelKind = ref<'uml' | 'archimate' | 'er'>('uml')
const editModelInstruction = ref('')
const editModelSubmitting = ref(false)
const editModelError = ref('')
const editModelSuccess = ref('')

// 新手教程引导
const showHelpModal = ref(false)

// === 引导式使用教学（tour）===
const showTour = ref(false)
const tourStep = ref(0)
const tourHighlightStyle = ref<Record<string, string>>({})
const tourSteps = [
  { target: '.header', tab: 'dashboard', title: '欢迎使用 👋', desc: '这是你的建模工作台。右上角是账号信息、帮助入口与退出；顶部是各个功能模块的导航。' },
  { target: '[data-tab="projects"]', tab: 'projects', title: '项目管理', desc: '在这里创建或打开项目。每个项目是一套独立的模型，项目之间互不可见。' },
  { target: '[data-tab="uml"]', tab: 'uml', title: 'UML 建模', desc: '用类图设计系统结构：在工具栏选图形再点画布添加，双击编辑，右键删除。' },
  { target: '[data-tour="ai"]', tab: 'uml', title: 'AI 功能', desc: '画布顶部的「AI」按钮包含：校验、架构评审、元素分析、对话式编辑、从描述生成图。' },
  { target: '[data-tab="code"]', tab: 'code', title: '代码生成', desc: '模型一键转代码、粘贴代码反推模型、AI 生成设计文档/报表。' },
  { target: '[data-tab="ai"]', tab: 'ai', title: 'AI 助手', desc: '和 AI 对话提问，说「记住：xxx」会把内容存入项目记忆库。' },
  { target: '[data-tab="dev"]', tab: 'dev', title: '研发管理', desc: '管理项目的需求、测试用例、缺陷与任务，支持 AI 一键生成。' },
  { target: '', tab: '', title: '完成 🎉', desc: '你已经掌握了基本用法。点击下方「开始探索」进入工作台，随时可在右上角「帮助」里重新引导。' },
]
const currentTourStep = computed(() => tourSteps[tourStep.value])
const isLastTourStep = computed(() => tourStep.value >= tourSteps.length - 1)

let tourOpenedAt = 0  // 打开时刻，用于吸收开启瞬间的误触点击
const positionTourHighlight = () => {
  nextTick(() => {
    const step = tourSteps[tourStep.value]
    if (!step || !step.target) {
      tourHighlightStyle.value = {}
      return
    }
    if (step.tab) activeTab.value = step.tab
    nextTick(() => {
      const el = document.querySelector(step.target)
      if (el) {
        const r = el.getBoundingClientRect()
        tourHighlightStyle.value = {
          left: `${r.left - 6}px`,
          top: `${r.top - 6}px`,
          width: `${r.width + 12}px`,
          height: `${r.height + 12}px`
        }
        // nearest：元素已在视口内就不滚动，避免打开瞬间页面跳动
        el.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
      } else {
        tourHighlightStyle.value = {}
      }
    })
  })
}

const startTour = () => {
  tourStep.value = 0
  tourOpenedAt = Date.now()
  showTour.value = true
  showHelpModal.value = false
  positionTourHighlight()
}
const nextTourStep = () => {
  // 打开后 500ms 内的点击视为误触（吸收开启按钮的残余点击），防止第一步瞬间跳过
  if (Date.now() - tourOpenedAt < 500) return
  if (isLastTourStep.value) return finishTour()
  tourStep.value++
  positionTourHighlight()
}
const prevTourStep = () => {
  if (tourStep.value > 0) {
    tourStep.value--
    positionTourHighlight()
  }
}
const skipTour = () => finishTour()
const finishTour = () => {
  showTour.value = false
  if (authUser.value?.id) localStorage.setItem('tour_seen_' + authUser.value.id, '1')
}

// AI 功能下拉菜单（每画布一个入口）
const openAiMenu = ref<'uml' | 'archimate' | 'er' | null>(null)
const toggleAiMenu = (kind: 'uml' | 'archimate' | 'er') => {
  openAiMenu.value = openAiMenu.value === kind ? null : kind
}
const runAiAction = (kind: 'uml' | 'archimate' | 'er', action: string) => {
  openAiMenu.value = null
  if (action === 'validate') return aiValidateModel()
  if (action === 'review') return aiReviewArchimate()
  if (action === 'analyze') return aiAnalyzeElement(kind)
  if (action === 'edit') return openAiEditModel(kind)
}

let canvas: HTMLCanvasElement | null = null
let ctx: CanvasRenderingContext2D | null = null
// 画布元素/关系 id 用单调递增计数器（Date.now() 毫秒级会在连续创建时撞 id）
let eidCounter = 0
const nextEid = () => ++eidCounter
let elements: any[] = []
let connections: any[] = []
let selectedElement: any = null
let isDragging = false
let dragOffset = { x: 0, y: 0 }
let lastClickTime = 0
let lastClickPos = { x: 0, y: 0 }
let archimateLastClickTime = 0
let archimateLastClickPos = { x: 0, y: 0 }
let erLastClickTime = 0
let erLastClickPos = { x: 0, y: 0 }
let isConnecting = false
let connectStartElement: any = null
let showEditModal = ref(false)
let editingElement = ref<any>(null)
let currentModelId = ref('')
let currentModelName = ref('')
// AI 上下文刷新标记：画布数据是非响应式的普通数组，切换进 AI 页时手动触发一次重建
let contextRefreshKey = ref(0)

// === 研发管理（需求/测试/缺陷/任务） ===
type DevKind = 'requirement' | 'testcase' | 'defect' | 'task'
const devTabs: Array<{ id: DevKind; name: string; icon: string }> = [
  { id: 'requirement', name: '需求', icon: 'fas fa-list-check' },
  { id: 'testcase', name: '测试用例', icon: 'fas fa-vial' },
  { id: 'defect', name: '缺陷', icon: 'fas fa-bug' },
  { id: 'task', name: '任务', icon: 'fas fa-tasks' },
]
const activeDevTab = ref<DevKind>('requirement')
const devList = ref<any[]>([])
const devLoading = ref(false)
const devError = ref('')
const showDevModal = ref(false)
const editingDev = ref<any>(null)
const devForm = ref<Record<string, string>>({})

// 每个实体的字段配置（label → 表单键）
const DEV_FIELDS: Record<DevKind, Array<{ key: string; label: string }>> = {
  requirement: [
    { key: 'name', label: '名称' },
    { key: 'description', label: '描述' },
    { key: 'type', label: '类型' },
    { key: 'priority', label: '优先级' },
    { key: 'status', label: '状态' },
    { key: 'assignee_id', label: '指派人' },
  ],
  testcase: [
    { key: 'name', label: '名称' },
    { key: 'description', label: '描述' },
    { key: 'level', label: '级别' },
    { key: 'req_id', label: '关联需求' },
    { key: 'assignee_id', label: '指派人' },
    { key: 'status', label: '状态' },
  ],
  defect: [
    { key: 'name', label: '标题' },
    { key: 'description', label: '描述' },
    { key: 'level', label: '严重度' },
    { key: 'assignee_id', label: '指派人' },
    { key: 'status', label: '状态' },
  ],
  task: [
    { key: 'name', label: '名称' },
    { key: 'description', label: '描述' },
    { key: 'type', label: '类型' },
    { key: 'priority', label: '优先级' },
    { key: 'assignee_id', label: '指派人' },
    { key: 'status', label: '状态' },
    { key: 'work_hours', label: '工时' },
  ],
}
// 列表接口返回的数组键名
const DEV_LIST_KEY: Record<DevKind, string> = {
  requirement: 'requirements',
  testcase: 'test_cases',
  defect: 'defects',
  task: 'tasks',
}
const loadDevList = async () => {
  const k = activeDevTab.value
  if (!currentModelId.value) { devList.value = []; return }
  devLoading.value = true
  devError.value = ''
  try {
    const { ok, status, data } = await devApi.list(k, currentModelId.value)
    if (!ok || data?.error) { devError.value = data?.error || `加载失败: HTTP ${status}`; return }
    devList.value = (data as any)?.[DEV_LIST_KEY[k]] || []
  } catch (e: any) {
    devError.value = e?.message || '加载失败'
  } finally { devLoading.value = false }
}
// 切到研发管理页时自动加载当前子 tab 的列表（默认需求），避免首屏空白
watch(activeTab, (v) => {
  if (v === 'dev') loadDevList()
  if (v === 'admin') loadAdminUsers()
})

const openDevModal = (item: any | null) => {
  editingDev.value = item
  devForm.value = item ? { ...item } : {}
  showDevModal.value = true
}
const saveDev = async () => {
  const k = activeDevTab.value
  const body = editingDev.value ? { ...devForm.value, id: editingDev.value.id } : devForm.value
  try {
    const { ok, status, data } = await devApi.crud(k, currentModelId.value, body)
    if (!ok || data?.error) { devError.value = data?.error || `保存失败: HTTP ${status}`; return }
    showDevModal.value = false
    loadDevList()
  } catch (e: any) { devError.value = e?.message || '保存失败' }
}
const removeDev = async (item: any) => {
  const k = activeDevTab.value
  if (!confirm(`确定删除「${item.name || item.id}」？`)) return
  try {
    const { ok, status, data } = await devApi.remove(k, currentModelId.value, item.id)
    if (!ok || data?.error) {
      devError.value = data?.error || `删除失败: HTTP ${status}`
      return
    }
    loadDevList()
  } catch (e: any) {
    devError.value = e?.message || '删除失败'
  }
}

// === 研发管理：AI 生成（需求/测试/任务；缺陷无 AI） ===
const showDevAiModal = ref(false)

// 后台管理（仅 admin）
const adminUsers = ref<any[]>([])
const adminLoading = ref(false)
const adminError = ref('')
const showAdminUserModal = ref(false)
const editingAdminUser = ref<any>(null)
const adminUserForm = ref({ username: '', email: '', password: '', role: 'user' })
const showAdminProjectsModal = ref(false)
const viewingAdminUser = ref<any>(null)
const adminProjects = ref<any[]>([])
const devAiText = ref('')
const devAiGenerating = ref(false)
// 测试/任务生成时选择的关联需求（保留原始 id 类型，便于后端匹配）
const devAiReqId = ref<any>('')
const devAiReqIds = ref<any[]>([])
// AI 弹窗里的需求选项（独立从需求接口拉取，不依赖当前 tab 的列表数据）
const devReqOptions = ref<any[]>([])

const canGenerateDevAi = computed(() => {
  const k = activeDevTab.value
  if (k === 'requirement') return devAiText.value.trim() !== ''
  if (k === 'testcase') return devAiReqId.value !== '' && devAiText.value.trim() !== ''
  if (k === 'task') return devAiReqIds.value.length > 0
  return false
})

const loadDevReqOptions = async () => {
  if (!currentModelId.value) { devReqOptions.value = []; return }
  try {
    const { ok, data } = await devApi.list('requirement', currentModelId.value)
    devReqOptions.value = (!ok || data?.error) ? [] : ((data as any)?.requirements || [])
  } catch {
    devReqOptions.value = []
  }
}

const openDevAi = () => {
  devAiText.value = ''
  devAiReqId.value = ''
  devAiReqIds.value = []
  showDevAiModal.value = true
  if (activeDevTab.value !== 'requirement') {
    loadDevReqOptions()
  }
}

const generateDevAi = async () => {
  const k = activeDevTab.value
  const pid = currentModelId.value
  devAiGenerating.value = true
  devError.value = ''
  try {
    let resp: { ok: boolean; status: number; data: any }
    if (k === 'requirement') {
      resp = await devApi.aiGenerate('requirement', pid, { requirement_text: devAiText.value })
    } else if (k === 'testcase') {
      resp = await devApi.aiGenerate('testcase', pid, { req_id: devAiReqId.value, requirement_text: devAiText.value })
    } else if (k === 'task') {
      resp = await devApi.aiPlan(pid, { req_ids: devAiReqIds.value })
    } else {
      return
    }
    if (!resp.ok || resp.data?.error) { devError.value = resp.data?.error || '生成失败'; return }
    showDevAiModal.value = false
    loadDevList()
  } catch (e: any) { devError.value = e?.message || '生成失败' }
  finally { devAiGenerating.value = false }
}

// 后台管理函数
const loadAdminUsers = async () => {
  adminLoading.value = true
  adminError.value = ''
  try {
    const { ok, data } = await adminApi.users()
    if (!ok || data?.error) { adminError.value = data?.error || '加载失败'; return }
    adminUsers.value = data?.users || []
  } catch (e: any) { adminError.value = e?.message || '加载失败' }
  finally { adminLoading.value = false }
}

const openAdminUserModal = (u: any | null) => {
  editingAdminUser.value = u
  adminUserForm.value = u ? { username: u.username, email: u.email, password: '', role: u.role || 'user' } : { username: '', email: '', password: '', role: 'user' }
  showAdminUserModal.value = true
}

const saveAdminUser = async () => {
  const f = adminUserForm.value
  adminError.value = ''
  try {
    const body: Record<string, unknown> = { ...f }
    const resp = editingAdminUser.value
      ? await adminApi.updateUser(editingAdminUser.value.id, body)
      : await adminApi.createUser(body as { username: string; email: string; password: string; role: string })
    if (!resp.ok || resp.data?.error) { adminError.value = resp.data?.error || '保存失败'; return }
    showAdminUserModal.value = false
    loadAdminUsers()
  } catch (e: any) { adminError.value = e?.message || '保存失败' }
}

const removeAdminUser = async (u: any) => {
  if (!confirm(`删除用户「${u.username}」将级联删除其所有项目，确定？`)) return
  adminError.value = ''
  try {
    const { ok, status, data } = await adminApi.deleteUser(u.id)
    if (!ok || data?.error) { adminError.value = data?.error || `删除失败: HTTP ${status}`; return }
    loadAdminUsers()
  } catch (e: any) { adminError.value = e?.message || '删除失败' }
}

const viewUserProjects = async (u: any) => {
  viewingAdminUser.value = u
  adminProjects.value = []
  adminError.value = ''
  try {
    const { ok, data } = await adminApi.userProjects(u.id)
    if (!ok || data?.error) { adminError.value = data?.error || '加载失败'; return }
    adminProjects.value = data?.projects || []
    showAdminProjectsModal.value = true
  } catch (e: any) { adminError.value = e?.message || '加载失败' }
}

const removeAdminProject = async (p: any) => {
  if (!confirm(`确定删除项目「${p.name || p.id}」？`)) return
  adminError.value = ''
  try {
    const { ok, status, data } = await adminApi.deleteProject(p.id)
    if (!ok || data?.error) { adminError.value = data?.error || `删除失败: HTTP ${status}`; return }
    if (viewingAdminUser.value) viewUserProjects(viewingAdminUser.value)
    loadAdminUsers()
  } catch (e: any) { adminError.value = e?.message || '删除失败' }
}

const projectContext = computed<ProjectContext>(() => {
  // 作为响应式依赖，使切到 AI 页时能重建最新上下文
  void contextRefreshKey.value
  return {
  currentModelName: currentModelName.value,
  currentModelId: currentModelId.value,
  umlElements: elements.map(el => ({
    id: el.id,
    name: el.name,
    type: el.type,
    attributes: el.attributes || [],
    x: el.x,
    y: el.y,
    width: el.width,
    height: el.height
  })),
  umlRelationships: connections.map(conn => ({
    id: conn.id,
    sourceId: conn.startElement,
    targetId: conn.endElement,
    type: conn.type || 'association'
  })),
  archimateElements: archimateElements.map(el => ({
    id: el.id,
    name: el.name,
    type: el.type,
    layer: el.layer,
    x: el.x,
    y: el.y,
    width: el.width,
    height: el.height
  })),
  archimateRelationships: archimateConnections.map(conn => ({
    id: conn.id,
    sourceId: conn.startElement,
    targetId: conn.endElement,
    type: conn.type || 'association'
  })),
  erEntities: erEntities.map(entity => ({
    id: entity.id,
    name: entity.name,
    attributes: (entity.fields || []).map((attr: any, idx: number) => ({
      id: attr.id || idx,
      name: attr.name,
      type: attr.type,
      isPrimaryKey: attr.isPrimary,
      isForeignKey: attr.isForeign
    })),
    x: entity.x,
    y: entity.y,
    width: entity.width,
    height: entity.height
  })),
  erRelationships: erRelations.map(rel => ({
    id: rel.id,
    sourceId: rel.startEntity,
    targetId: rel.endEntity,
    type: rel.type
  }))
  }
})

// 撤销/重做历史记录
interface HistoryState {
  elements: any[]
  connections: any[]
}

let umlHistory: HistoryState[] = []
let umlRedo: HistoryState[] = []

let archimateHistory: HistoryState[] = []
let archimateRedo: HistoryState[] = []

interface ErHistoryState {
  entities: any[]
  relations: any[]
}
let erHistory: ErHistoryState[] = []
let erRedo: ErHistoryState[] = []

const loadModels = async () => {
  try {
    const { ok, data } = await modelApi.list()
    if (!ok) {
      console.error('Failed to load models:', data)
      alert('加载项目列表失败，请检查后端服务是否运行')
      return
    }
    models.value = Array.isArray(data?.models) ? data.models : []
    updateStats()
  } catch (e) {
    console.error('Failed to load models:', e)
    alert('加载项目列表失败，请检查后端服务是否运行')
  }
}

const updateStats = () => {
  stats.value.models = models.value.length
  // 根据当前激活的标签页统计元素和关系数量
  if (activeTab.value === 'uml') {
    stats.value.elements = elements.length
    stats.value.relationships = connections.length
  } else if (activeTab.value === 'archimate') {
    stats.value.elements = archimateElements.length
    stats.value.relationships = archimateConnections.length
  } else if (activeTab.value === 'data') {
    stats.value.elements = erEntities.length
    stats.value.relationships = erRelations.length
  } else {
    // 其他标签页使用项目数据统计
    stats.value.elements = models.value.reduce((acc, m) => acc + m.elements_count, 0)
    stats.value.relationships = models.value.reduce((acc, m) => acc + m.relationships_count, 0)
  }
  stats.value.views = models.value.reduce((acc, m) => acc + m.views_count, 0)
}

const createModel = async () => {
  if (!newModel.value.name) {
    alert('请输入项目名称')
    return
  }
  const modelName = newModel.value.name
  try {
    const { ok, status, data } = await modelApi.create(newModel.value)
    if (!ok || !data?.id) {
      console.error('Create failed:', status, data)
      alert(data?.error || `创建失败: HTTP ${status}`)
      return
    }
    showCreateModal.value = false
    newModel.value = { name: '', description: '' }
    await loadModels()
    currentModelId.value = data.id
    currentModelName.value = modelName
    joinProjectRoom()
    elements = []
    connections = []
    archimateElements = []
    archimateConnections = []
    erEntities = []
    erRelations = []
    generatedCode.value = '// 选择模型源和输出类型，然后点击生成代码按钮'
    umlHistory = []
    umlRedo = []
    archimateHistory = []
    archimateRedo = []
    erHistory = []
    erRedo = []
    selectedElement = null
    archimateSelectedElement = null
    erSelectedEntity = null
    activeTab.value = 'uml'
    updateStats()
    alert('项目创建成功')
  } catch (e: any) {
    console.error('Failed to create model:', e)
    const errorMsg = e?.message || '未知错误'
    alert(`创建失败: ${errorMsg}\n请检查后端服务是否运行`)
  }
}

const deleteModel = async (id: string) => {
  if (!confirm('确定要删除这个项目吗？')) return
  try {
    const { ok, status, data } = await modelApi.remove(id)
    if (ok) {
      await loadModels()
      if (currentModelId.value === id) {
        leaveProjectRoom(id)
        currentModelId.value = ''
        currentModelName.value = ''
        // 清空三套画布数据，避免删除项目后残留旧内容
        clearCanvas()
        archimateElements = []
        archimateConnections = []
        erEntities = []
        erRelations = []
        archimateSelectedElement = null
        erSelectedEntity = null
        redrawArchimateCanvas()
        redrawErCanvas()
      }
      alert('项目删除成功')
    } else {
      console.error('Delete failed:', status, data)
      alert(data?.error || `删除失败: HTTP ${status}`)
    }
  } catch (e: any) {
    console.error('Failed to delete model:', e)
    const errorMsg = e?.message || '未知错误'
    alert(`删除失败: ${errorMsg}\n请检查后端服务是否运行`)
  }
}

const openModel = async (model: Model) => {
  elements = []
  connections = []
  archimateElements = []
  archimateConnections = []
  erEntities = []
  erRelations = []
  generatedCode.value = '// 选择模型源和输出类型，然后点击生成代码按钮'
  umlHistory = []
  umlRedo = []
  archimateHistory = []
  archimateRedo = []
  erHistory = []
  erRedo = []
  selectedElement = null
  archimateSelectedElement = null
  erSelectedEntity = null
  activeTab.value = 'uml'
  currentModelId.value = model.id
  currentModelName.value = model.name
  joinProjectRoom()
  await loadModelFromServer(model.id)
}

const generateCode = async () => {
  const { language, framework, source, outputType } = codeConfig.value

  // 优先 AI 语义级生成（AI 启用时），失败/未启用回退本地模板
  try {
    const aiCfg = await getAIConfig()
    if (aiCfg?.config?.enabled) {
      codeGenerating.value = true
      generatedCode.value = '// AI 正在生成代码，请稍候...'
      const payload: Record<string, unknown> = { source, language, framework, outputType }
      if (source === 'uml') {
        payload.elements = elements
      } else {
        payload.erEntities = erEntities
        payload.erRelations = erRelations
      }
      const { ok, data } = await codeApi.generate(payload)
      if (ok && data?.code) {
        generatedCode.value = data.code
        codeGenerating.value = false
        return
      }
    }
  } catch {
    // 网络异常等，回退本地模板
  }
  codeGenerating.value = false

  if (source === 'uml') {
    if (elements.length === 0) {
      generatedCode.value = '// 请先在UML建模页面创建类或接口'
      return
    }
    
    if (outputType === 'entity') {
      generatedCode.value = generateEntityCode(language, framework)
    } else if (outputType === 'controller') {
      generatedCode.value = generateControllerCode(language, framework)
    } else if (outputType === 'service') {
      generatedCode.value = generateServiceCode(language, framework)
    }
  } else if (source === 'er') {
    if (erEntities.length === 0) {
      generatedCode.value = '// 请先在数据建模页面创建实体'
      return
    }
    
    if (outputType === 'entity') {
      generatedCode.value = generateEntityCodeFromEr(language, framework)
    } else if (outputType === 'sql') {
      generateErSql()
      generatedCode.value = erSqlResult.value
    }
  }

  // 不支持的语言×框架×输出组合会返回空字符串，给出明确提示而不是空白
  if (!generatedCode.value || generatedCode.value.trim() === '') {
    generatedCode.value = `// 当前暂不支持 语言=${language} / 框架=${framework} / 输出=${outputType} 的组合\n// 可尝试 Java+Spring、Python+Django、TypeScript+NestJS 等组合`
  }
}

// 代码反向工程：粘贴代码 → AI 反推模型 → 画到画布
const reverseCode = async () => {
  const code = reverseConfig.value.code.trim()
  if (!code) {
    reverseError.value = '请先粘贴源代码'
    return
  }
  if (!currentModelId.value) {
    reverseError.value = '请先创建或选择一个项目'
    return
  }
  const { language, target } = reverseConfig.value
  reverseError.value = ''
  reversing.value = true
  try {
    const { ok, status, data } = await codeApi.reverse({ code, language, target })
    if (!ok || data?.error) {
      reverseError.value = data?.error || `反推失败: HTTP ${status}`
      return
    }
    if (target === 'uml') {
      saveUmlHistory()
      elements = data?.elements || []
      connections = data?.relationships || []
      selectedElement = null
      activeTab.value = 'uml'
      redraw()
    } else {
      saveErHistory()
      erEntities = data?.entities || []
      erRelations = data?.relationships || []
      erSelectedEntity = null
      activeTab.value = 'data'
      redrawErCanvas()
    }
    updateStats()
    alert(`反推成功：${target === 'uml' ? 'UML 类图' : 'ER 模型'}已生成到画布，记得点「保存」落盘`)
  } catch (e: any) {
    reverseError.value = e?.message || '反推请求失败，请检查后端服务'
  } finally {
    reversing.value = false
  }
}

// AI 从描述生成图（UML/ER）
const openGenerateDiagram = (kind: 'uml' | 'er') => {
  openAiMenu.value = null
  genDiagramKind.value = kind
  genDiagramText.value = ''
  genDiagramViewType.value = 'class'
  genDiagramError.value = ''
  showGenDiagramModal.value = true
}

const generateDiagram = async () => {
  const text = genDiagramText.value.trim()
  if (!text) {
    genDiagramError.value = '请输入业务描述'
    return
  }
  if (!currentModelId.value) {
    genDiagramError.value = '请先创建或选择一个项目'
    return
  }
  const kind = genDiagramKind.value
  genDiagramError.value = ''
  genDiagramLoading.value = true
  try {
    const { ok, status, data } = await aiApi.generateDiagram(currentModelId.value, {
      text, kind, view_type: genDiagramViewType.value
    })
    if (!ok || data?.error) {
      genDiagramError.value = data?.error || `生成失败: HTTP ${status}`
      return
    }
    if (kind === 'uml') {
      saveUmlHistory()
      elements = data?.elements || []
      connections = data?.relationships || []
      selectedElement = null
      activeTab.value = 'uml'
      redraw()
    } else {
      saveErHistory()
      erEntities = data?.entities || []
      erRelations = data?.relationships || []
      erSelectedEntity = null
      activeTab.value = 'data'
      redrawErCanvas()
    }
    updateStats()
    showGenDiagramModal.value = false
    alert(`生成成功：已画到${kind === 'uml' ? 'UML' : 'ER'}画布，记得点「保存」落盘`)
  } catch (e: any) {
    genDiagramError.value = e?.message || '生成请求失败，请检查后端服务'
  } finally {
    genDiagramLoading.value = false
  }
}

// AI 文档/报表生成
const generateDoc = async () => {
  if (!currentModelId.value) {
    docError.value = '请先创建或选择一个项目'
    return
  }
  const { docType, format } = docConfig.value
  docError.value = ''
  generatedDoc.value = ''
  docGenerating.value = true
  try {
    const { ok, status, data } = await aiApi.document(currentModelId.value, { doc_type: docType, format })
    if (!ok || data?.error) {
      docError.value = data?.error || `生成失败: HTTP ${status}`
      return
    }
    generatedDoc.value = data?.content || '（生成结果为空）'
  } catch (e: any) {
    docError.value = e?.message || '生成请求失败，请检查后端服务'
  } finally {
    docGenerating.value = false
  }
}

const copyDoc = async () => {
  if (!generatedDoc.value) return
  try {
    await navigator.clipboard.writeText(generatedDoc.value)
    alert('文档已复制到剪贴板')
  } catch {
    const textarea = document.createElement('textarea')
    textarea.value = generatedDoc.value
    document.body.appendChild(textarea)
    textarea.select()
    document.execCommand('copy')
    document.body.removeChild(textarea)
    alert('文档已复制到剪贴板')
  }
}

const downloadDoc = () => {
  if (!generatedDoc.value) return
  const ext = docConfig.value.format === 'html' ? 'html' : 'md'
  const blob = new Blob([generatedDoc.value], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${currentModelName.value || 'model'}-${docConfig.value.docType}.${ext}`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

const copyCode = async () => {
  if (!generatedCode.value || generatedCode.value.startsWith('//')) return
  try {
    await navigator.clipboard.writeText(generatedCode.value)
    alert('代码已复制到剪贴板')
  } catch {
    const textarea = document.createElement('textarea')
    textarea.value = generatedCode.value
    document.body.appendChild(textarea)
    textarea.select()
    document.execCommand('copy')
    document.body.removeChild(textarea)
    alert('代码已复制到剪贴板')
  }
}

const downloadCode = () => {
  if (!generatedCode.value || generatedCode.value.startsWith('//')) return
  
  const { language, outputType } = codeConfig.value
  const extMap: Record<string, string> = {
    java: 'java',
    python: 'py',
    typescript: 'ts',
    csharp: 'cs',
    sql: 'sql'
  }
  
  let filename = 'generated.'
  if (outputType === 'sql') {
    filename = 'schema.sql'
  } else {
    filename += extMap[language] || 'txt'
  }
  
  const blob = new Blob([generatedCode.value], { type: 'text/plain' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

const generateEntityCode = (language: string, framework: string): string => {
  let code = ''
  
  if (language === 'java') {
    code = 'package com.example.entity;\n\n'
    if (framework === 'spring') {
      code += 'import jakarta.persistence.*;\nimport lombok.Data;\n\n'
    }
    
    elements.forEach((elem: any) => {
      if (elem.type === 'class') {
        code += `@Entity\n@Table(name = "${elem.name.toLowerCase()}")\n`
        code += '@Data\n'
        code += `public class ${elem.name} {\n`
        
        const attrs = elem.attributes || []
        if (attrs.length === 0) {
          code += '    @Id\n    @GeneratedValue(strategy = GenerationType.IDENTITY)\n    private Long id;\n'
        } else {
          attrs.forEach((attr: string) => {
            const parts = attr.split(':')
            const fieldName = parts[0].trim().replace(/[+-]/g, '').trim()
            const fieldType = parts[1]?.trim() || 'String'
            
            if (fieldName.toLowerCase() === 'id') {
              code += '    @Id\n    @GeneratedValue(strategy = GenerationType.IDENTITY)\n'
            }
            
            const javaType = mapTypeToJava(fieldType)
            code += `    private ${javaType} ${fieldName};\n`
          })
        }
        
        code += '}\n\n'
      }
    })
  } else if (language === 'python') {
    if (framework === 'django') {
      code += 'from django.db import models\n\n\n'
      elements.forEach((elem: any) => {
        if (elem.type === 'class') {
          code += `class ${elem.name}(models.Model):\n`
          const attrs = elem.attributes || []
          if (attrs.length === 0) {
            code += '    id = models.AutoField(primary_key=True)\n'
          } else {
            attrs.forEach((attr: string) => {
              const parts = attr.split(':')
              const fieldName = parts[0].trim().replace(/[+-]/g, '').trim()
              const fieldType = parts[1]?.trim() || 'String'
              
              const djangoType = mapTypeToDjango(fieldType)
              if (fieldName.toLowerCase() === 'id') {
                code += `    ${fieldName} = models.AutoField(primary_key=True)\n`
              } else {
                code += `    ${fieldName} = models.${djangoType}()\n`
              }
            })
          }
          code += '\n    class Meta:\n        db_table = "lowercase_table_name"\n\n'
        }
      })
    } else {
      elements.forEach((elem: any) => {
        if (elem.type === 'class') {
          code += `class ${elem.name}:\n`
          const attrs = elem.attributes || []
          code += '    def __init__(self):\n'
          if (attrs.length === 0) {
            code += '        self.id = None\n'
          } else {
            attrs.forEach((attr: string) => {
              const parts = attr.split(':')
              const fieldName = parts[0].trim().replace(/[+-]/g, '').trim()
              code += `        self.${fieldName} = None\n`
            })
          }
          code += '\n'
        }
      })
    }
  } else if (language === 'typescript') {
    if (framework === 'nestjs') {
      code += 'import { Entity, Column, PrimaryGeneratedColumn } from "typeorm";\n\n'
      elements.forEach((elem: any) => {
        if (elem.type === 'class') {
          code += `@Entity()\n`
          code += `export class ${elem.name} {\n`
          const attrs = elem.attributes || []
          if (attrs.length === 0) {
            code += '    @PrimaryGeneratedColumn()\n    id: number;\n'
          } else {
            attrs.forEach((attr: string) => {
              const parts = attr.split(':')
              const fieldName = parts[0].trim().replace(/[+-]/g, '').trim()
              const fieldType = parts[1]?.trim() || 'string'
              
              if (fieldName.toLowerCase() === 'id') {
                code += '    @PrimaryGeneratedColumn()\n'
              } else {
                code += '    @Column()\n'
              }
              const tsType = mapTypeToTypeScript(fieldType)
              code += `    ${fieldName}: ${tsType};\n`
            })
          }
          code += '}\n\n'
        }
      })
    } else {
      elements.forEach((elem: any) => {
        if (elem.type === 'class') {
          code += `export class ${elem.name} {\n`
          const attrs = elem.attributes || []
          if (attrs.length === 0) {
            code += '    id: number;\n'
          } else {
            attrs.forEach((attr: string) => {
              const parts = attr.split(':')
              const fieldName = parts[0].trim().replace(/[+-]/g, '').trim()
              const fieldType = parts[1]?.trim() || 'string'
              const tsType = mapTypeToTypeScript(fieldType)
              code += `    ${fieldName}: ${tsType};\n`
            })
          }
          code += '}\n\n'
        }
      })
    }
  } else if (language === 'csharp') {
    code += 'using System;\n'
    if (framework !== 'none') {
      code += 'using Microsoft.EntityFrameworkCore;\n'
    }
    code += '\n'
    elements.forEach((elem: any) => {
      if (elem.type === 'class') {
        code += `public class ${elem.name} {\n`
        const attrs = elem.attributes || []
        if (attrs.length === 0) {
          code += '    public int Id { get; set; }\n'
        } else {
          attrs.forEach((attr: string) => {
            const parts = attr.split(':')
            const fieldName = parts[0].trim().replace(/[+-]/g, '').trim()
            const fieldType = parts[1]?.trim() || 'string'
            const csType = mapTypeToCSharp(fieldType)
            code += `    public ${csType} ${fieldName} { get; set; }\n`
          })
        }
        code += '}\n\n'
      }
    })
  }
  
  return code
}

const generateEntityCodeFromEr = (language: string, framework: string): string => {
  let code = ''
  
  if (language === 'java') {
    code = 'package com.example.entity;\n\n'
    if (framework === 'spring') {
      code += 'import jakarta.persistence.*;\nimport lombok.Data;\n\n'
    }
    
    erEntities.forEach((entity: any) => {
      code += `@Entity\n@Table(name = "${entity.name.toLowerCase()}")\n`
      code += '@Data\n'
      code += `public class ${entity.name} {\n`
      
      entity.fields.forEach((field: any) => {
        if (field.isPrimary) {
          code += '    @Id\n    @GeneratedValue(strategy = GenerationType.IDENTITY)\n'
        } else if (field.isForeign) {
          code += '    @ManyToOne\n    @JoinColumn(name = "' + field.name.toLowerCase() + '_id")\n'
        }
        
        const javaType = mapTypeToJava(field.type)
        code += `    private ${javaType} ${field.name};\n`
      })
      
      code += '}\n\n'
    })
  } else if (language === 'python') {
    if (framework === 'django') {
      code += 'from django.db import models\n\n\n'
      erEntities.forEach((entity: any) => {
        code += `class ${entity.name}(models.Model):\n`
        entity.fields.forEach((field: any) => {
          const djangoType = mapTypeToDjango(field.type)
          if (field.isPrimary) {
            code += `    ${field.name} = models.AutoField(primary_key=True)\n`
          } else if (field.isForeign) {
            code += `    ${field.name} = models.ForeignKey('${field.name.replace('Id', '')}', on_delete=models.CASCADE)\n`
          } else {
            code += `    ${field.name} = models.${djangoType}()\n`
          }
        })
        code += '\n    class Meta:\n        db_table = "' + entity.name.toLowerCase() + '"\n\n'
      })
    }
  } else if (language === 'typescript') {
    if (framework === 'nestjs') {
      code += 'import { Entity, Column, PrimaryGeneratedColumn, ManyToOne, JoinColumn } from "typeorm";\n\n'
      erEntities.forEach((entity: any) => {
        code += `@Entity()\n`
        code += `export class ${entity.name} {\n`
        entity.fields.forEach((field: any) => {
          if (field.isPrimary) {
            code += '    @PrimaryGeneratedColumn()\n'
          } else if (field.isForeign) {
            code += `    @ManyToOne(() => ${field.name.replace('Id', '')})\n`
            code += `    @JoinColumn({ name: '${field.name.toLowerCase()}_id' })\n`
          } else {
            code += '    @Column()\n'
          }
          const tsType = mapTypeToTypeScript(field.type)
          code += `    ${field.name}: ${tsType};\n`
        })
        code += '}\n\n'
      })
    }
  } else if (language === 'csharp') {
    code += 'using System;\nusing Microsoft.EntityFrameworkCore;\n\n'
    erEntities.forEach((entity: any) => {
      code += `public class ${entity.name} {\n`
      entity.fields.forEach((field: any) => {
        const csType = mapTypeToCSharp(field.type)
        code += `    public ${csType} ${field.name} { get; set; }\n`
      })
      code += '}\n\n'
    })
  }
  
  return code
}

const generateControllerCode = (language: string, framework: string): string => {
  let code = ''
  
  if (language === 'java' && framework === 'spring') {
    code = 'package com.example.controller;\n\n'
    code += 'import com.example.entity.*;\n'
    code += 'import com.example.service.*;\n'
    code += 'import org.springframework.web.bind.annotation.*;\n'
    code += 'import java.util.List;\n\n'
    
    elements.forEach((elem: any) => {
      if (elem.type === 'class') {
        const entityName = elem.name
        const lowerName = entityName.toLowerCase()
        code += `@RestController\n@RequestMapping("/api/${lowerName}")\n`
        code += `public class ${entityName}Controller {\n\n`
        code += `    private final ${entityName}Service ${lowerName}Service;\n\n`
        code += `    public ${entityName}Controller(${entityName}Service ${lowerName}Service) {\n`
        code += `        this.${lowerName}Service = ${lowerName}Service;\n`
        code += '    }\n\n'
        code += `    @GetMapping\n    public List<${entityName}> getAll() {\n`
        code += `        return ${lowerName}Service.findAll();\n`
        code += '    }\n\n'
        code += `    @GetMapping("/{id}")\n`
        code += `    public ${entityName} getById(@PathVariable Long id) {\n`
        code += `        return ${lowerName}Service.findById(id);\n`
        code += '    }\n\n'
        code += `    @PostMapping\n`
        code += `    public ${entityName} create(@RequestBody ${entityName} ${lowerName}) {\n`
        code += `        return ${lowerName}Service.save(${lowerName});\n`
        code += '    }\n\n'
        code += `    @PutMapping("/{id}")\n`
        code += `    public ${entityName} update(@PathVariable Long id, @RequestBody ${entityName} ${lowerName}) {\n`
        code += `        return ${lowerName}Service.update(id, ${lowerName});\n`
        code += '    }\n\n'
        code += `    @DeleteMapping("/{id}")\n`
        code += `    public void delete(@PathVariable Long id) {\n`
        code += `        ${lowerName}Service.delete(id);\n`
        code += '    }\n\n'
        code += '}\n\n'
      }
    })
  } else if (language === 'typescript' && framework === 'nestjs') {
    code += 'import { Controller, Get, Post, Put, Delete, Body, Param } from "@nestjs/common";\n'
    code += 'import { InjectRepository } from "@nestjs/typeorm";\n'
    code += 'import { Repository } from "typeorm";\n'
    
    elements.forEach((elem: any) => {
      if (elem.type === 'class') {
        const entityName = elem.name
        const lowerName = entityName.toLowerCase()
        code += `import { ${entityName} } from "../entity/${lowerName}.entity";\n`
      }
    })
    code += '\n'
    
    elements.forEach((elem: any) => {
      if (elem.type === 'class') {
        const entityName = elem.name
        const lowerName = entityName.toLowerCase()
        code += `@Controller('${lowerName}')\n`
        code += `export class ${entityName}Controller {\n`
        code += `    constructor(\n`
        code += `        @InjectRepository(${entityName})\n`
        code += `        private readonly ${lowerName}Repository: Repository<${entityName}>,\n`
        code += `    ) {}\n\n`
        code += `    @Get()\n`
        code += `    findAll(): Promise<${entityName}[]> {\n`
        code += `        return this.${lowerName}Repository.find();\n`
        code += `    }\n\n`
        code += `    @Get(':id')\n`
        code += `    findOne(@Param('id') id: string): Promise<${entityName}> {\n`
        code += `        return this.${lowerName}Repository.findOneBy({ id: parseInt(id) });\n`
        code += `    }\n\n`
        code += `    @Post()\n`
        code += `    create(@Body() ${lowerName}: ${entityName}): Promise<${entityName}> {\n`
        code += `        return this.${lowerName}Repository.save(${lowerName});\n`
        code += `    }\n\n`
        code += `    @Put(':id')\n`
        code += `    async update(@Param('id') id: string, @Body() ${lowerName}: ${entityName}): Promise<${entityName}> {\n`
        code += `        await this.${lowerName}Repository.update(id, ${lowerName});\n`
        code += `        return this.${lowerName}Repository.findOneBy({ id: parseInt(id) });\n`
        code += `    }\n\n`
        code += `    @Delete(':id')\n`
        code += `    remove(@Param('id') id: string): Promise<void> {\n`
        code += `        this.${lowerName}Repository.delete(id);\n`
        code += `        return;\n`
        code += `    }\n}\n\n`
      }
    })
  }
  
  return code
}

const generateServiceCode = (language: string, framework: string): string => {
  let code = ''
  
  if (language === 'java' && framework === 'spring') {
    code = 'package com.example.service;\n\n'
    code += 'import com.example.entity.*;\n'
    code += 'import com.example.repository.*;\n'
    code += 'import org.springframework.stereotype.Service;\n'
    code += 'import java.util.List;\n\n'
    
    elements.forEach((elem: any) => {
      if (elem.type === 'class') {
        const entityName = elem.name
        const lowerName = entityName.toLowerCase()
        code += `@Service\n`
        code += `public class ${entityName}Service {\n\n`
        code += `    private final ${entityName}Repository ${lowerName}Repository;\n\n`
        code += `    public ${entityName}Service(${entityName}Repository ${lowerName}Repository) {\n`
        code += `        this.${lowerName}Repository = ${lowerName}Repository;\n`
        code += '    }\n\n'
        code += `    public List<${entityName}> findAll() {\n`
        code += `        return ${lowerName}Repository.findAll();\n`
        code += '    }\n\n'
        code += `    public ${entityName} findById(Long id) {\n`
        code += `        return ${lowerName}Repository.findById(id).orElse(null);\n`
        code += '    }\n\n'
        code += `    public ${entityName} save(${entityName} ${lowerName}) {\n`
        code += `        return ${lowerName}Repository.save(${lowerName});\n`
        code += '    }\n\n'
        code += `    public ${entityName} update(Long id, ${entityName} ${lowerName}) {\n`
        code += `        ${entityName} existing = ${lowerName}Repository.findById(id).orElse(null);\n`
        code += `        if (existing != null) {\n`
        code += `            // Update fields\n`
        code += `            return ${lowerName}Repository.save(existing);\n`
        code += `        }\n`
        code += `        return null;\n`
        code += '    }\n\n'
        code += `    public void delete(Long id) {\n`
        code += `        ${lowerName}Repository.deleteById(id);\n`
        code += '    }\n\n'
        code += '}\n\n'
      }
    })
  }
  
  return code
}

const mapTypeToJava = (type: string): string => {
  const mappings: Record<string, string> = {
    'int': 'Integer',
    'Integer': 'Integer',
    'long': 'Long',
    'Long': 'Long',
    'float': 'Float',
    'double': 'Double',
    'boolean': 'Boolean',
    'String': 'String',
    'date': 'LocalDate',
    'Date': 'LocalDateTime',
    'datetime': 'LocalDateTime'
  }
  return mappings[type] || 'String'
}

const mapTypeToDjango = (type: string): string => {
  const mappings: Record<string, string> = {
    'int': 'IntegerField',
    'Integer': 'IntegerField',
    'long': 'BigIntegerField',
    'Long': 'BigIntegerField',
    'float': 'FloatField',
    'double': 'DecimalField',
    'boolean': 'BooleanField',
    'String': 'CharField',
    'string': 'CharField',
    'date': 'DateField',
    'Date': 'DateField',
    'datetime': 'DateTimeField'
  }
  return mappings[type] || 'CharField'
}

const mapTypeToTypeScript = (type: string): string => {
  const mappings: Record<string, string> = {
    'int': 'number',
    'Integer': 'number',
    'long': 'number',
    'Long': 'number',
    'float': 'number',
    'double': 'number',
    'boolean': 'boolean',
    'Boolean': 'boolean',
    'String': 'string',
    'string': 'string',
    'date': 'Date',
    'Date': 'Date',
    'datetime': 'Date'
  }
  return mappings[type] || 'string'
}

const mapTypeToCSharp = (type: string): string => {
  const mappings: Record<string, string> = {
    'int': 'int',
    'Integer': 'int',
    'long': 'long',
    'Long': 'long',
    'float': 'float',
    'double': 'double',
    'boolean': 'bool',
    'Boolean': 'bool',
    'String': 'string',
    'string': 'string',
    'date': 'DateTime',
    'Date': 'DateTime',
    'datetime': 'DateTime'
  }
  return mappings[type] || 'string'
}

const initCanvas = () => {
  canvas = document.getElementById('canvas') as HTMLCanvasElement
  if (canvas) {
    setupCanvasTransform(canvas)
    ctx = canvas.getContext('2d')
    drawGrid()
    // 切回 UML 标签时 canvas 会被 v-if 重建，需重新绘制内存中的元素
    redraw()
  }
}

const drawGrid = () => {
  if (!ctx || !canvas) return
  ctx.strokeStyle = '#e0e0e0'
  ctx.lineWidth = 0.5
  const gridSize = 20
  
  for (let x = 0; x < LOGICAL_W; x += gridSize) {
    ctx.beginPath()
    ctx.moveTo(x, 0)
    ctx.lineTo(x, LOGICAL_H)
    ctx.stroke()
  }

  for (let y = 0; y < LOGICAL_H; y += gridSize) {
    ctx.beginPath()
    ctx.moveTo(0, y)
    ctx.lineTo(LOGICAL_W, y)
    ctx.stroke()
  }
}

// roundRect 兼容助手：优先用原生 API，旧浏览器退化为手绘圆角矩形路径
const roundRectPath = (ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number | number[]) => {
  if (typeof (ctx as any).roundRect === 'function') {
    ;(ctx as any).roundRect(x, y, w, h, r)
    return
  }
  const radii = (Array.isArray(r) ? [...r] : [r, r, r, r]) as number[]
  const [tl = 0, tr = tl, br = tl, bl = tl] = radii
  ctx.beginPath()
  ctx.moveTo(x + tl, y)
  ctx.lineTo(x + w - tr, y)
  ctx.arcTo(x + w, y, x + w, y + tr, tr)
  ctx.lineTo(x + w, y + h - br)
  ctx.arcTo(x + w, y + h, x + w - br, y + h, br)
  ctx.lineTo(x + bl, y + h)
  ctx.arcTo(x, y + h, x, y + h - bl, bl)
  ctx.lineTo(x, y + tl)
  ctx.arcTo(x, y, x + tl, y, tl)
  ctx.closePath()
}

const drawElement = (elem: any) => {
  if (!ctx) return
  
  ctx.fillStyle = elem.color || '#ffffff'
  ctx.strokeStyle = selectedElement?.id === elem.id ? '#1f5eff' : '#333'
  ctx.lineWidth = selectedElement?.id === elem.id ? 3 : 2
  
  ctx.beginPath()
  roundRectPath(ctx, elem.x, elem.y, elem.width, elem.height, 8)
  ctx.fill()
  ctx.stroke()

  ctx.fillStyle = elem.headerColor || '#1f5eff'
  ctx.beginPath()
  roundRectPath(ctx, elem.x, elem.y, elem.width, 25, [8, 8, 0, 0])
  ctx.fill()
  
  ctx.fillStyle = '#ffffff'
  ctx.font = 'bold 12px Arial'
  ctx.textAlign = 'center'
  ctx.fillText(elem.name, elem.x + elem.width / 2, elem.y + 17)
  
  ctx.fillStyle = '#333'
  ctx.font = '11px Arial'
  ctx.textAlign = 'left'
  let y = elem.y + 35
  ;(elem.attributes || []).forEach((attr: string) => {
    ctx!.fillText(attr, elem.x + 8, y)
    y += 14
  })
}

const drawArrow = (x1: number, y1: number, x2: number, y2: number, type: string) => {
  if (!ctx) return
  
  const headLen = 12
  const dx = x2 - x1
  const dy = y2 - y1
  const angle = Math.atan2(dy, dx)
  
  ctx.save()
  
  // 根据关系类型设置线条样式
  ctx.strokeStyle = '#333'
  ctx.lineWidth = 2
  
  if (type === 'realization' || type === 'dependency') {
    ctx.setLineDash([5, 5])
  } else {
    ctx.setLineDash([])
  }
  
  ctx.beginPath()
  ctx.moveTo(x1, y1)
  ctx.lineTo(x2, y2)
  ctx.stroke()
  
  ctx.setLineDash([])
  
  // 绘制箭头
  if (type === 'association') {
    ctx.beginPath()
    ctx.moveTo(x2, y2)
    ctx.lineTo(x2 - headLen * Math.cos(angle - Math.PI / 6), y2 - headLen * Math.sin(angle - Math.PI / 6))
    ctx.moveTo(x2, y2)
    ctx.lineTo(x2 - headLen * Math.cos(angle + Math.PI / 6), y2 - headLen * Math.sin(angle + Math.PI / 6))
    ctx.stroke()
  } else if (type === 'inheritance' || type === 'realization') {
    ctx.beginPath()
    ctx.moveTo(x2, y2)
    ctx.lineTo(x2 - headLen * Math.cos(angle - Math.PI / 6), y2 - headLen * Math.sin(angle - Math.PI / 6))
    ctx.lineTo(x2 - headLen * Math.cos(angle + Math.PI / 6), y2 - headLen * Math.sin(angle + Math.PI / 6))
    ctx.closePath()
    ctx.fillStyle = 'white'
    ctx.fill()
    ctx.stroke()
  } else if (type === 'dependency') {
    ctx.beginPath()
    ctx.moveTo(x2, y2)
    ctx.lineTo(x2 - headLen * Math.cos(angle - Math.PI / 6), y2 - headLen * Math.sin(angle - Math.PI / 6))
    ctx.moveTo(x2, y2)
    ctx.lineTo(x2 - headLen * Math.cos(angle + Math.PI / 6), y2 - headLen * Math.sin(angle + Math.PI / 6))
    ctx.stroke()
  } else if (type === 'composition') {
    const diamondSize = 8
    ctx.beginPath()
    ctx.moveTo(x2 - diamondSize * Math.cos(angle), y2 - diamondSize * Math.sin(angle))
    ctx.lineTo(x2 - headLen * Math.cos(angle - Math.PI / 6), y2 - headLen * Math.sin(angle - Math.PI / 6))
    ctx.lineTo(x2 - headLen * Math.cos(angle + Math.PI / 6), y2 - headLen * Math.sin(angle + Math.PI / 6))
    ctx.closePath()
    ctx.fillStyle = '#333'
    ctx.fill()
  } else if (type === 'aggregation') {
    const diamondSize = 8
    ctx.beginPath()
    ctx.moveTo(x2 - diamondSize * Math.cos(angle), y2 - diamondSize * Math.sin(angle))
    ctx.lineTo(x2 - headLen * Math.cos(angle - Math.PI / 6), y2 - headLen * Math.sin(angle - Math.PI / 6))
    ctx.lineTo(x2 - headLen * Math.cos(angle + Math.PI / 6), y2 - headLen * Math.sin(angle + Math.PI / 6))
    ctx.closePath()
    ctx.fillStyle = 'white'
    ctx.fill()
    ctx.stroke()
  }
  
  ctx.restore()
}

const drawConnection = (conn: any) => {
  if (!ctx) return
  
  const startElem = elements.find(e => e.id === conn.startElement)
  const endElem = elements.find(e => e.id === conn.endElement)
  
  if (!startElem || !endElem) return
  
  let startX = startElem.x + startElem.width / 2
  let startY = startElem.y + startElem.height / 2
  let endX = endElem.x + endElem.width / 2
  let endY = endElem.y + endElem.height / 2
  
  const dx = endX - startX
  const dy = endY - startY
  
  if (Math.abs(dx) > Math.abs(dy)) {
    startY = startElem.y + startElem.height / 2
    endY = endElem.y + endElem.height / 2
    if (dx > 0) {
      startX = startElem.x + startElem.width
      endX = endElem.x
    } else {
      startX = startElem.x
      endX = endElem.x + endElem.width
    }
  } else {
    startX = startElem.x + startElem.width / 2
    endX = endElem.x + endElem.width / 2
    if (dy > 0) {
      startY = startElem.y + startElem.height
      endY = endElem.y
    } else {
      startY = startElem.y
      endY = endElem.y + endElem.height
    }
  }
  
  drawArrow(startX, startY, endX, endY, conn.type)
}

const handleCanvasClick = (e: MouseEvent) => {
  if (!canvas) return
  const p = toLogical(e, canvas)
  let x = p.x
  let y = p.y
  // 钳制坐标，避免在画布边缘点击时把元素创建到可见区域之外
  x = Math.max(0, Math.min(LOGICAL_W - 120, x))
  y = Math.max(0, Math.min(LOGICAL_H - 100, y))

  // 防止双击时重复创建元素（双击会在300ms内触发两次点击）
  const now = Date.now()
  if (now - lastClickTime < 300 && 
      Math.abs(x - lastClickPos.x) < 10 && 
      Math.abs(y - lastClickPos.y) < 10) {
    return
  }
  lastClickTime = now
  lastClickPos = { x, y }
  
  // 检查是否点击了现有元素，如果是则不创建新元素
  for (const elem of elements) {
    if (x >= elem.x && x <= elem.x + elem.width &&
        y >= elem.y && y <= elem.y + elem.height) {
      // 点击了现有元素，不创建新元素
      return
    }
  }
  
  // 只有选中 'class' 或 'interface' 工具时才能创建元素
  // 其他工具（select, association, inheritance, composition）用于选择和连线
  const currentTool = selectedTool.value
  if (currentTool === 'class') {
    saveUmlHistory()
    elements.push({
      id: nextEid(),
      type: 'class',
      name: 'NewClass',
      x,
      y,
      width: 120,
      height: 100,
      color: '#ffffff',
      headerColor: '#1f5eff',
      attributes: ['- name: String', '- age: int']
    })
    redraw()
    updateStats()
  } else if (currentTool === 'interface') {
    saveUmlHistory()
    elements.push({
      id: nextEid(),
      type: 'interface',
      name: 'NewInterface',
      x,
      y,
      width: 120,
      height: 80,
      color: '#e8f5e9',
      headerColor: '#4caf50',
      attributes: ['+ method(): void']
    })
    redraw()
    updateStats()
  }
  // 选择工具（select）和连线工具（association, inheritance, composition）不会创建元素
}

const handleMouseDown = (e: MouseEvent) => {
  if (!canvas) return
  const p = toLogical(e, canvas)
  const x = p.x
  const y = p.y
  
  if (selectedTool.value === 'association' || selectedTool.value === 'inheritance' || selectedTool.value === 'composition' || selectedTool.value === 'realization' || selectedTool.value === 'dependency' || selectedTool.value === 'aggregation') {
    for (let i = elements.length - 1; i >= 0; i--) {
      const elem = elements[i]
      if (x >= elem.x && x <= elem.x + elem.width &&
          y >= elem.y && y <= elem.y + elem.height) {
        isConnecting = true
        connectStartElement = elem
        return
      }
    }
    return
  }
  
  for (let i = elements.length - 1; i >= 0; i--) {
    const elem = elements[i]
    if (x >= elem.x && x <= elem.x + elem.width &&
        y >= elem.y && y <= elem.y + elem.height) {
      selectedElement = elem
      isDragging = true
      dragOffset = { x: x - elem.x, y: y - elem.y }
      return
    }
  }
  
  selectedElement = null
  // 点击空白取消选中后立即重绘，清除残留的高亮边框
  redraw()
}

const handleMouseMove = (e: MouseEvent) => {
  if (!canvas) return
  const p = toLogical(e, canvas)
  const x = p.x
  const y = p.y
  
  if (isDragging && selectedElement) {
    selectedElement.x = Math.max(0, Math.min(LOGICAL_W - selectedElement.width, x - dragOffset.x))
    selectedElement.y = Math.max(0, Math.min(LOGICAL_H - selectedElement.height, y - dragOffset.y))
    redraw()
  }
}

const handleMouseUp = (e: MouseEvent) => {
  if (!canvas) return
  const p = toLogical(e, canvas)
  const x = p.x
  const y = p.y
  
  if (isConnecting && connectStartElement) {
    for (let i = elements.length - 1; i >= 0; i--) {
      const elem = elements[i]
      if (elem.id !== connectStartElement.id &&
          x >= elem.x && x <= elem.x + elem.width &&
          y >= elem.y && y <= elem.y + elem.height) {
        saveUmlHistory()
        connections.push({
          id: nextEid(),
          type: selectedTool.value,
          startElement: connectStartElement.id,
          endElement: elem.id
        })
        break
      }
    }
    isConnecting = false
    connectStartElement = null
    redraw()
    updateStats()
    return
  }
  
  isDragging = false
}

const initCanvasEvents = () => {
  initCanvas()
  document.removeEventListener('mousemove', handleMouseMove)
  document.removeEventListener('mouseup', handleMouseUp)
  document.addEventListener('mousemove', handleMouseMove)
  document.addEventListener('mouseup', handleMouseUp)
}

const handleDoubleClick = (e: MouseEvent) => {
  if (!canvas) return
  const p = toLogical(e, canvas)
  const x = p.x
  const y = p.y
  
  for (let i = elements.length - 1; i >= 0; i--) {
    const elem = elements[i]
    if (x >= elem.x && x <= elem.x + elem.width &&
        y >= elem.y && y <= elem.y + elem.height) {
      editingElement.value = JSON.parse(JSON.stringify(elem))
      showEditModal.value = true
      return
    }
  }
}

const saveEdit = () => {
  if (!editingElement.value) return
  const index = elements.findIndex(e => e.id === editingElement.value.id)
  if (index !== -1) {
    elements[index] = JSON.parse(JSON.stringify(editingElement.value))
    redraw()
  }
  showEditModal.value = false
}

const redraw = () => {
  if (!ctx || !canvas) return
  ctx.clearRect(0, 0, LOGICAL_W, LOGICAL_H)
  drawGrid()
  connections.forEach(drawConnection)
  elements.forEach(drawElement)
}

const clearCanvas = () => {
  saveUmlHistory()
  elements = []
  connections = []
  selectedElement = null
  redraw()
}

// UML 撤销/重做函数（双栈：umlHistory 撤销栈 / umlRedo 重做栈）
const saveUmlHistory = () => {
  umlHistory.push({
    elements: JSON.parse(JSON.stringify(elements)),
    connections: JSON.parse(JSON.stringify(connections))
  })
  if (umlHistory.length > 50) umlHistory.shift()
  umlRedo = []
}

const undoUml = () => {
  if (umlHistory.length > 0) {
    umlRedo.push({
      elements: JSON.parse(JSON.stringify(elements)),
      connections: JSON.parse(JSON.stringify(connections))
    })
    const state = umlHistory.pop()!
    elements = JSON.parse(JSON.stringify(state.elements))
    connections = JSON.parse(JSON.stringify(state.connections))
    redraw()
  }
}

const redoUml = () => {
  if (umlRedo.length > 0) {
    umlHistory.push({
      elements: JSON.parse(JSON.stringify(elements)),
      connections: JSON.parse(JSON.stringify(connections))
    })
    const state = umlRedo.pop()!
    elements = JSON.parse(JSON.stringify(state.elements))
    connections = JSON.parse(JSON.stringify(state.connections))
    redraw()
  }
}

// UML 右键删除
const handleUmlContextMenu = (e: MouseEvent) => {
  e.preventDefault()
  if (!canvas) return
  const p = toLogical(e, canvas)
  const x = p.x
  const y = p.y
  
  for (let i = elements.length - 1; i >= 0; i--) {
    const elem = elements[i]
    if (x >= elem.x && x <= elem.x + elem.width &&
        y >= elem.y && y <= elem.y + elem.height) {
      saveUmlHistory()
      elements.splice(i, 1)
      connections = connections.filter(c => c.startElement !== elem.id && c.endElement !== elem.id)
      redraw()
      updateStats()
      return
    }
  }
  
  for (let i = connections.length - 1; i >= 0; i--) {
    const conn = connections[i]
    const startElem = elements.find(e => e.id === conn.startElement)
    const endElem = elements.find(e => e.id === conn.endElement)
    if (startElem && endElem) {
      const startX = startElem.x + startElem.width / 2
      const startY = startElem.y + startElem.height / 2
      const endX = endElem.x + endElem.width / 2
      const endY = endElem.y + endElem.height / 2
      const dist = pointToLineDistance(x, y, startX, startY, endX, endY)
      if (dist < 10) {
        saveUmlHistory()
        connections.splice(i, 1)
        redraw()
        updateStats()
        return
      }
    }
  }
}

const pointToLineDistance = (px: number, py: number, x1: number, y1: number, x2: number, y2: number) => {
  const A = px - x1
  const B = py - y1
  const C = x2 - x1
  const D = y2 - y1
  const dot = A * C + B * D
  const lenSq = C * C + D * D
  let param = -1
  if (lenSq !== 0) param = dot / lenSq
  let xx, yy
  if (param < 0) {
    xx = x1
    yy = y1
  } else if (param > 1) {
    xx = x2
    yy = y2
  } else {
    xx = x1 + param * C
    yy = y1 + param * D
  }
  const dx = px - xx
  const dy = py - yy
  return Math.sqrt(dx * dx + dy * dy)
}

// ArchiMate 建模函数
const initArchimateCanvas = () => {
  const canvasEl = document.getElementById('archimateCanvas') as HTMLCanvasElement
  if (canvasEl) {
    archimateCanvas.value = canvasEl
    setupCanvasTransform(canvasEl)
    archimateCtx = canvasEl.getContext('2d')
    redrawArchimateCanvas()
    // 先移除再添加，避免切换标签页时监听器重复累积
    document.removeEventListener('mousemove', handleArchimateMouseMove)
    document.removeEventListener('mouseup', handleArchimateMouseUp)
    document.addEventListener('mousemove', handleArchimateMouseMove)
    document.addEventListener('mouseup', handleArchimateMouseUp)
  }
}

const redrawArchimateCanvas = () => {
  if (!archimateCtx || !archimateCanvas.value) return
  archimateCtx.clearRect(0, 0, LOGICAL_W, LOGICAL_H)
  
  // 绘制网格背景
  archimateCtx.strokeStyle = '#e8e8e8'
  archimateCtx.lineWidth = 1
  for (let x = 0; x < LOGICAL_W; x += 20) {
    archimateCtx.beginPath()
    archimateCtx.moveTo(x, 0)
    archimateCtx.lineTo(x, LOGICAL_H)
    archimateCtx.stroke()
  }
  for (let y = 0; y < LOGICAL_H; y += 20) {
    archimateCtx.beginPath()
    archimateCtx.moveTo(0, y)
    archimateCtx.lineTo(LOGICAL_W, y)
    archimateCtx.stroke()
  }
  
  // 绘制连接
  archimateConnections.forEach((conn: any) => {
    const startElem = archimateElements.find((e: any) => e.id === conn.startElement)
    const endElem = archimateElements.find((e: any) => e.id === conn.endElement)
    if (startElem && endElem) {
      drawArchimateConnection(startElem, endElem, conn.type)
    }
  })
  
  // 绘制元素
  archimateElements.forEach((elem: any) => {
    drawArchimateElement(elem)
  })
}

const drawArchimateElement = (elem: any) => {
  if (!archimateCtx) return
  const ctx = archimateCtx
  
  ctx.save()
  
  // 根据元素类型绘制不同形状
  if (elem.type === 'actor') {
    // 绘制角色（人物图标形状）
    const cx = elem.x + elem.width / 2
    const cy = elem.y + 15
    ctx.beginPath()
    ctx.arc(cx, cy, 10, 0, Math.PI * 2)
    ctx.fillStyle = elem.color || '#3498db'
    ctx.fill()
    ctx.strokeStyle = '#2c3e50'
    ctx.lineWidth = 2
    ctx.stroke()
    
    // 身体
    ctx.beginPath()
    ctx.moveTo(cx, cy + 10)
    ctx.lineTo(cx, cy + 35)
    ctx.strokeStyle = '#2c3e50'
    ctx.lineWidth = 2
    ctx.stroke()
    
    // 手臂
    ctx.beginPath()
    ctx.moveTo(cx - 15, cy + 20)
    ctx.lineTo(cx + 15, cy + 20)
    ctx.stroke()
    
    // 腿
    ctx.beginPath()
    ctx.moveTo(cx, cy + 35)
    ctx.lineTo(cx - 12, cy + 50)
    ctx.moveTo(cx, cy + 35)
    ctx.lineTo(cx + 12, cy + 50)
    ctx.stroke()
    
    // 名称
    ctx.fillStyle = '#2c3e50'
    ctx.font = '12px Arial'
    ctx.textAlign = 'center'
    ctx.fillText(elem.name, cx, elem.y + elem.height + 15)
    
    elem.width = 30
    elem.height = 50
  } else {
    // 绘制矩形元素
    ctx.fillStyle = elem.color || '#ecf0f1'
    ctx.fillRect(elem.x, elem.y, elem.width, elem.height)
    
    // 头部颜色
    ctx.fillStyle = elem.headerColor || getLayerColor(elem.layer)
    ctx.fillRect(elem.x, elem.y, elem.width, 25)
    
    // 边框
    ctx.strokeStyle = '#2c3e50'
    ctx.lineWidth = 2
    ctx.strokeRect(elem.x, elem.y, elem.width, elem.height)
    
    // 类型标签
    ctx.fillStyle = 'white'
    ctx.font = 'bold 10px Arial'
    ctx.textAlign = 'center'
    ctx.fillText(elem.type.toUpperCase(), elem.x + elem.width / 2, elem.y + 17)
    
    // 名称
    ctx.fillStyle = '#2c3e50'
    ctx.font = '12px Arial'
    ctx.fillText(elem.name, elem.x + elem.width / 2, elem.y + elem.height / 2)
  }
  
  ctx.restore()
}

const getLayerColor = (layer: string) => {
  switch (layer) {
    case 'business': return '#3498db'
    case 'application': return '#2ecc71'
    case 'technology': return '#e67e22'
    default: return '#95a5a6'
  }
}

const drawArchimateConnection = (start: any, end: any, type: string) => {
  if (!archimateCtx) return
  const ctx = archimateCtx
  
  const startX = start.x + start.width / 2
  const startY = start.y + start.height / 2
  const endX = end.x + end.width / 2
  const endY = end.y + end.height / 2
  
  ctx.beginPath()
  ctx.moveTo(startX, startY)
  ctx.lineTo(endX, endY)
  ctx.strokeStyle = '#7f8c8d'
  ctx.lineWidth = 2
  
  // 根据关系类型绘制不同箭头
  if (type === 'association') {
    ctx.setLineDash([])
  } else if (type === 'realization') {
    ctx.setLineDash([5, 5])
  } else if (type === 'serving') {
    ctx.setLineDash([10, 3])
  }
  
  ctx.stroke()
  
  // 箭头
  const angle = Math.atan2(endY - startY, endX - startX)
  const headLen = 12
  ctx.beginPath()
  ctx.moveTo(endX, endY)
  ctx.lineTo(endX - headLen * Math.cos(angle - Math.PI / 6), endY - headLen * Math.sin(angle - Math.PI / 6))
  ctx.lineTo(endX - headLen * Math.cos(angle + Math.PI / 6), endY - headLen * Math.sin(angle + Math.PI / 6))
  ctx.closePath()
  ctx.fillStyle = '#7f8c8d'
  ctx.fill()
}

const handleArchimateClick = (e: MouseEvent) => {
  if (!archimateCanvas.value) return
  const p = toLogical(e, archimateCanvas.value)
  let x = p.x
  let y = p.y
  // 钳制坐标，避免在画布边缘点击时把元素创建到可见区域之外
  x = Math.max(0, Math.min(LOGICAL_W - 120, x))
  y = Math.max(0, Math.min(LOGICAL_H - 80, y))

  // 防止双击时重复创建元素（与 UML 一致的防抖）
  const now = Date.now()
  if (now - archimateLastClickTime < 300 &&
      Math.abs(x - archimateLastClickPos.x) < 10 &&
      Math.abs(y - archimateLastClickPos.y) < 10) {
    return
  }
  archimateLastClickTime = now
  archimateLastClickPos = { x, y }

  const currentTool = selectedArchimateTool.value

  // 检查是否点击了现有元素
  for (const elem of archimateElements) {
    if (x >= elem.x && x <= elem.x + elem.width &&
        y >= elem.y && y <= elem.y + elem.height) {
      return
    }
  }
  
  // 创建新元素
  const layer = archimateLayer.value
  const colors = {
    business: { header: '#3498db', body: '#ecf0f1' },
    application: { header: '#2ecc71', body: '#e8f8f5' },
    technology: { header: '#e67e22', body: '#fef5e7' }
  }
  
  if (currentTool === 'actor' || currentTool === 'process' || currentTool === 'service' ||
      currentTool === 'component' || currentTool === 'node' || currentTool === 'artifact') {
    saveArchimateHistory()
    const isActor = currentTool === 'actor'
    archimateElements.push({
      id: nextEid(),
      type: currentTool,
      name: getElementName(currentTool),
      layer,
      x,
      y,
      width: isActor ? 30 : 120,
      height: isActor ? 50 : 80,
      color: colors[layer as keyof typeof colors].body,
      headerColor: colors[layer as keyof typeof colors].header
    })
    redrawArchimateCanvas()
    updateStats()
  }
}

const getElementName = (type: string) => {
  const names: Record<string, string> = {
    actor: 'Business Actor',
    process: 'Business Process',
    service: 'Business Service',
    component: 'Application Component',
    node: 'Technology Node',
    artifact: 'Artifact'
  }
  return names[type] || type
}

const handleArchimateMouseDown = (e: MouseEvent) => {
  if (!archimateCanvas.value) return
  const p = toLogical(e, archimateCanvas.value)
  const x = p.x
  const y = p.y
  
  const currentTool = selectedArchimateTool.value
  
  // 连线工具
  if (currentTool === 'association' || currentTool === 'realization' || currentTool === 'serving') {
    for (let i = archimateElements.length - 1; i >= 0; i--) {
      const elem = archimateElements[i]
      if (x >= elem.x && x <= elem.x + elem.width &&
          y >= elem.y && y <= elem.y + elem.height) {
        archimateIsConnecting = true
        archimateConnectStartElement = elem
        return
      }
    }
    return
  }
  
  // 选择工具 - 拖拽元素
  for (let i = archimateElements.length - 1; i >= 0; i--) {
    const elem = archimateElements[i]
    if (x >= elem.x && x <= elem.x + elem.width &&
        y >= elem.y && y <= elem.y + elem.height) {
      archimateSelectedElement = elem
      archimateIsDragging = true
      archimateDragOffset = { x: x - elem.x, y: y - elem.y }
      return
    }
  }
  
  archimateSelectedElement = null
}

const handleArchimateMouseMove = (e: MouseEvent) => {
  if (!archimateCanvas.value) return
  const p = toLogical(e, archimateCanvas.value)
  const x = p.x
  const y = p.y
  
  if (archimateIsDragging && archimateSelectedElement) {
    archimateSelectedElement.x = Math.max(0, Math.min(LOGICAL_W - archimateSelectedElement.width, x - archimateDragOffset.x))
    archimateSelectedElement.y = Math.max(0, Math.min(LOGICAL_H - archimateSelectedElement.height, y - archimateDragOffset.y))
    redrawArchimateCanvas()
  }
}

const handleArchimateMouseUp = (e: MouseEvent) => {
  if (!archimateCanvas.value) return
  const p = toLogical(e, archimateCanvas.value)
  const x = p.x
  const y = p.y
  
  if (archimateIsConnecting && archimateConnectStartElement) {
    for (let i = archimateElements.length - 1; i >= 0; i--) {
      const elem = archimateElements[i]
      if (elem.id !== archimateConnectStartElement.id &&
          x >= elem.x && x <= elem.x + elem.width &&
          y >= elem.y && y <= elem.y + elem.height) {
        // 与 UML/ER 一致，连线也要入撤销历史
        saveArchimateHistory()
        archimateConnections.push({
          id: nextEid(),
          type: selectedArchimateTool.value,
          startElement: archimateConnectStartElement.id,
          endElement: elem.id
        })
        break
      }
    }
    archimateIsConnecting = false
    archimateConnectStartElement = null
    redrawArchimateCanvas()
    updateStats()
    return
  }
  
  archimateIsDragging = false
}

const handleArchimateDoubleClick = (e: MouseEvent) => {
  if (!archimateCanvas.value) return
  const p = toLogical(e, archimateCanvas.value)
  const x = p.x
  const y = p.y
  
  for (let i = archimateElements.length - 1; i >= 0; i--) {
    const elem = archimateElements[i]
    if (x >= elem.x && x <= elem.x + elem.width &&
        y >= elem.y && y <= elem.y + elem.height) {
      archimateEditingElement.value = JSON.parse(JSON.stringify(elem))
      showArchimateEditModal.value = true
      return
    }
  }
}

const saveArchimateEdit = () => {
  if (!archimateEditingElement.value) return
  const index = archimateElements.findIndex((e: any) => e.id === archimateEditingElement.value.id)
  if (index !== -1) {
    archimateElements[index] = JSON.parse(JSON.stringify(archimateEditingElement.value))
    redrawArchimateCanvas()
  }
  showArchimateEditModal.value = false
}

const clearArchimateCanvas = () => {
  saveArchimateHistory()
  archimateElements = []
  archimateConnections = []
  archimateSelectedElement = null
  redrawArchimateCanvas()
}

// ArchiMate 撤销/重做函数（双栈：archimateHistory 撤销栈 / archimateRedo 重做栈）
const saveArchimateHistory = () => {
  archimateHistory.push({
    elements: JSON.parse(JSON.stringify(archimateElements)),
    connections: JSON.parse(JSON.stringify(archimateConnections))
  })
  if (archimateHistory.length > 50) archimateHistory.shift()
  archimateRedo = []
}

const undoArchimate = () => {
  if (archimateHistory.length > 0) {
    archimateRedo.push({
      elements: JSON.parse(JSON.stringify(archimateElements)),
      connections: JSON.parse(JSON.stringify(archimateConnections))
    })
    const state = archimateHistory.pop()!
    archimateElements = JSON.parse(JSON.stringify(state.elements))
    archimateConnections = JSON.parse(JSON.stringify(state.connections))
    redrawArchimateCanvas()
  }
}

const redoArchimate = () => {
  if (archimateRedo.length > 0) {
    archimateHistory.push({
      elements: JSON.parse(JSON.stringify(archimateElements)),
      connections: JSON.parse(JSON.stringify(archimateConnections))
    })
    const state = archimateRedo.pop()!
    archimateElements = JSON.parse(JSON.stringify(state.elements))
    archimateConnections = JSON.parse(JSON.stringify(state.connections))
    redrawArchimateCanvas()
  }
}

// ArchiMate 右键删除
const handleArchimateContextMenu = (e: MouseEvent) => {
  e.preventDefault()
  if (!archimateCanvas.value) return
  const p = toLogical(e, archimateCanvas.value)
  const x = p.x
  const y = p.y
  
  for (let i = archimateElements.length - 1; i >= 0; i--) {
    const elem = archimateElements[i]
    if (x >= elem.x && x <= elem.x + elem.width &&
        y >= elem.y && y <= elem.y + elem.height) {
      saveArchimateHistory()
      archimateElements.splice(i, 1)
      archimateConnections = archimateConnections.filter(c => c.startElement !== elem.id && c.endElement !== elem.id)
      redrawArchimateCanvas()
      updateStats()
      return
    }
  }
  
  for (let i = archimateConnections.length - 1; i >= 0; i--) {
    const conn = archimateConnections[i]
    const startElem = archimateElements.find(e => e.id === conn.startElement)
    const endElem = archimateElements.find(e => e.id === conn.endElement)
    if (startElem && endElem) {
      const startX = startElem.x + startElem.width / 2
      const startY = startElem.y + startElem.height / 2
      const endX = endElem.x + endElem.width / 2
      const endY = endElem.y + endElem.height / 2
      const dist = pointToLineDistance(x, y, startX, startY, endX, endY)
      if (dist < 10) {
        saveArchimateHistory()
        archimateConnections.splice(i, 1)
        redrawArchimateCanvas()
        updateStats()
        return
      }
    }
  }
}

const saveArchimateModel = async () => {
  try {
    const modelData = {
      name: 'ArchiMate Model',
      description: 'ArchiMate Enterprise Architecture',
      elements: archimateElements,
      connections: archimateConnections
    }
    alert('ArchiMate 模型保存成功！\n（模型已保存到本地）')
    console.log('ArchiMate Model:', modelData)
  } catch (e) {
    console.error('Failed to save Archimate model:', e)
    alert('保存失败')
  }
}

const exportArchimateImage = () => {
  if (!archimateCanvas.value) return
  const link = document.createElement('a')
  link.download = `archimate-diagram-${Date.now()}.png`
  link.href = archimateCanvas.value.toDataURL()
  link.click()
}

// ER图建模函数
const initErCanvas = () => {
  const canvasEl = document.getElementById('erCanvas') as HTMLCanvasElement
  if (canvasEl) {
    erCanvas.value = canvasEl
    setupCanvasTransform(canvasEl)
    erCtx = canvasEl.getContext('2d')
    redrawErCanvas()
    // 先移除再添加，避免切换标签页时监听器重复累积
    document.removeEventListener('mousemove', handleErMouseMove)
    document.removeEventListener('mouseup', handleErMouseUp)
    document.addEventListener('mousemove', handleErMouseMove)
    document.addEventListener('mouseup', handleErMouseUp)
  }
}

const redrawErCanvas = () => {
  if (!erCtx || !erCanvas.value) return
  erCtx.clearRect(0, 0, LOGICAL_W, LOGICAL_H)
  
  // 绘制网格背景
  erCtx.strokeStyle = '#e8e8e8'
  erCtx.lineWidth = 1
  for (let x = 0; x < LOGICAL_W; x += 20) {
    erCtx.beginPath()
    erCtx.moveTo(x, 0)
    erCtx.lineTo(x, LOGICAL_H)
    erCtx.stroke()
  }
  for (let y = 0; y < LOGICAL_H; y += 20) {
    erCtx.beginPath()
    erCtx.moveTo(0, y)
    erCtx.lineTo(LOGICAL_W, y)
    erCtx.stroke()
  }
  
  // 绘制关系线
  erRelations.forEach((rel: any) => {
    const startEntity = erEntities.find((e: any) => e.id === rel.startEntity)
    const endEntity = erEntities.find((e: any) => e.id === rel.endEntity)
    if (startEntity && endEntity) {
      drawErRelation(startEntity, endEntity, rel.type)
    }
  })
  
  // 绘制实体
  erEntities.forEach((entity: any) => {
    drawErEntity(entity)
  })
}

const drawErEntity = (entity: any) => {
  if (!erCtx) return
  const ctx = erCtx
  const { x, y, width, name, fields } = entity
  
  // 计算实体高度（基础高度 + 字段高度）
  const headerHeight = 30
  const fieldHeight = 20
  const totalHeight = headerHeight + fields.length * fieldHeight + 10
  
  ctx.save()
  
  // 绘制表头背景
  ctx.fillStyle = '#3498db'
  ctx.fillRect(x, y, width, headerHeight)
  
  // 绘制表头文字
  ctx.fillStyle = 'white'
  ctx.font = 'bold 12px Arial'
  ctx.textAlign = 'center'
  ctx.fillText(name, x + width / 2, y + headerHeight / 2 + 4)
  
  // 绘制表体背景
  ctx.fillStyle = 'white'
  ctx.fillRect(x, y + headerHeight, width, totalHeight - headerHeight)
  
  // 绘制边框
  ctx.strokeStyle = '#2c3e50'
  ctx.lineWidth = 2
  ctx.strokeRect(x, y, width, totalHeight)
  
  // 绘制分隔线
  ctx.beginPath()
  ctx.moveTo(x, y + headerHeight)
  ctx.lineTo(x + width, y + headerHeight)
  ctx.stroke()
  
  // 绘制字段
  ctx.font = '11px Arial'
  ctx.textAlign = 'left'
  fields.forEach((field: any, index: number) => {
    const fieldY = y + headerHeight + index * fieldHeight + 15
    
    // 主键标记
    if (field.isPrimary) {
      ctx!.fillStyle = '#f39c12'
      ctx!.fillText('🔑', x + 5, fieldY)
    }
    
    // 字段名称和类型
    ctx!.fillStyle = '#2c3e50'
    ctx!.fillText(`${field.name}`, x + 25, fieldY)
    ctx!.fillStyle = '#7f8c8d'
    ctx!.fillText(` ${field.type}`, x + 25 + ctx!.measureText(field.name).width + 5, fieldY)
    
    // 外键标记
    if (field.isForeign) {
      ctx!.fillStyle = '#e74c3c'
      ctx!.fillText(' FK', x + width - 25, fieldY)
    }
  })
  
  ctx.restore()
  
  // 更新实体高度
  entity.displayHeight = totalHeight
}

const drawErRelation = (start: any, end: any, type: string) => {
  if (!erCtx) return
  const ctx = erCtx
  
  // displayHeight 在 drawErEntity 里才计算，首帧可能缺失；加兜底避免 NaN 导致连线错位
  const startH = start.displayHeight || 80
  const endH = end.displayHeight || 80
  const startX = start.x + start.width / 2
  const startY = start.y + startH / 2
  const endX = end.x + end.width / 2
  const endY = end.y + endH / 2
  
  ctx.beginPath()
  ctx.moveTo(startX, startY)
  ctx.lineTo(endX, endY)
  ctx.strokeStyle = '#7f8c8d'
  ctx.lineWidth = 2
  ctx.stroke()
  
  // 绘制关系标签
  const midX = (startX + endX) / 2
  const midY = (startY + endY) / 2
  
  const labels: Record<string, string> = {
    oneToOne: '1:1',
    oneToMany: '1:N',
    manyToMany: 'M:N'
  }
  
  ctx.fillStyle = '#2c3e50'
  ctx.font = 'bold 12px Arial'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  
  // 添加背景框使标签更清晰
  const labelText = labels[type] || type
  const textWidth = ctx.measureText(labelText).width
  ctx.fillStyle = 'rgba(255, 255, 255, 0.9)'
  ctx.fillRect(midX - textWidth / 2 - 6, midY - 10, textWidth + 12, 20)
  ctx.strokeStyle = '#2c3e50'
  ctx.lineWidth = 1
  ctx.strokeRect(midX - textWidth / 2 - 6, midY - 10, textWidth + 12, 20)
  
  ctx.fillStyle = '#2c3e50'
  ctx.fillText(labelText, midX, midY)
  
  // 根据关系类型绘制不同的末端符号
  const angle = Math.atan2(endY - startY, endX - startX)
  const arrowLen = 10
  
  if (type === 'oneToOne') {
    ctx.beginPath()
    ctx.moveTo(startX - 8, startY - 5)
    ctx.lineTo(startX, startY)
    ctx.lineTo(startX - 8, startY + 5)
    ctx.strokeStyle = '#2c3e50'
    ctx.lineWidth = 2
    ctx.stroke()
    
    ctx.beginPath()
    ctx.moveTo(endX - 8, endY - 5)
    ctx.lineTo(endX, endY)
    ctx.lineTo(endX - 8, endY + 5)
    ctx.stroke()
  } else if (type === 'oneToMany') {
    ctx.beginPath()
    ctx.moveTo(startX - 8, startY - 5)
    ctx.lineTo(startX, startY)
    ctx.lineTo(startX - 8, startY + 5)
    ctx.strokeStyle = '#2c3e50'
    ctx.lineWidth = 2
    ctx.stroke()
    
    ctx.beginPath()
    for (let i = -1; i <= 1; i++) {
      const branchX = endX - 15 * Math.cos(angle)
      const branchY = endY - 15 * Math.sin(angle)
      ctx.moveTo(branchX, branchY)
      ctx.lineTo(endX - arrowLen * Math.cos(angle - Math.PI / 6 + i * 0.3), 
                  endY - arrowLen * Math.sin(angle - Math.PI / 6 + i * 0.3))
    }
    ctx.stroke()
  } else if (type === 'manyToMany') {
    ctx.beginPath()
    for (let i = -1; i <= 1; i++) {
      const branchX = startX + 15 * Math.cos(angle)
      const branchY = startY + 15 * Math.sin(angle)
      ctx.moveTo(branchX, branchY)
      ctx.lineTo(startX + arrowLen * Math.cos(angle - Math.PI / 6 + i * 0.3), 
                  startY + arrowLen * Math.sin(angle - Math.PI / 6 + i * 0.3))
    }
    ctx.strokeStyle = '#2c3e50'
    ctx.lineWidth = 2
    ctx.stroke()
    
    ctx.beginPath()
    for (let i = -1; i <= 1; i++) {
      const branchX = endX - 15 * Math.cos(angle)
      const branchY = endY - 15 * Math.sin(angle)
      ctx.moveTo(branchX, branchY)
      ctx.lineTo(endX - arrowLen * Math.cos(angle - Math.PI / 6 + i * 0.3), 
                  endY - arrowLen * Math.sin(angle - Math.PI / 6 + i * 0.3))
    }
    ctx.stroke()
  }
}

const handleErClick = (e: MouseEvent) => {
  if (!erCanvas.value) return
  const p = toLogical(e, erCanvas.value)
  let x = p.x
  let y = p.y
  // 钳制坐标，避免在画布边缘点击时把实体创建到可见区域之外
  x = Math.max(0, Math.min(LOGICAL_W - 150, x))
  y = Math.max(0, Math.min(LOGICAL_H - 80, y))

  // 防止双击时重复创建实体（与 UML 一致的防抖）
  const now = Date.now()
  if (now - erLastClickTime < 300 &&
      Math.abs(x - erLastClickPos.x) < 10 &&
      Math.abs(y - erLastClickPos.y) < 10) {
    return
  }
  erLastClickTime = now
  erLastClickPos = { x, y }

  const currentTool = selectedErTool.value

  // 检查是否点击了现有实体
  for (const entity of erEntities) {
    if (x >= entity.x && x <= entity.x + entity.width &&
        y >= entity.y && y <= entity.y + (entity.displayHeight || 80)) {
      return
    }
  }
  
  // 创建新实体
  if (currentTool === 'entity') {
    saveErHistory()
    erEntities.push({
      id: nextEid(),
      name: `Table_${erEntities.length + 1}`,
      x,
      y,
      width: 150,
      displayHeight: 80,
      fields: [
        { name: 'id', type: 'INT', isPrimary: true, isForeign: false },
        { name: 'created_at', type: 'DATETIME', isPrimary: false, isForeign: false }
      ]
    })
    redrawErCanvas()
    updateStats()
  }
}

const handleErMouseDown = (e: MouseEvent) => {
  if (!erCanvas.value) return
  const p = toLogical(e, erCanvas.value)
  const x = p.x
  const y = p.y
  
  const currentTool = selectedErTool.value
  
  // 关系工具
  if (currentTool === 'oneToOne' || currentTool === 'oneToMany' || currentTool === 'manyToMany') {
    for (let i = erEntities.length - 1; i >= 0; i--) {
      const entity = erEntities[i]
      if (x >= entity.x && x <= entity.x + entity.width &&
          y >= entity.y && y <= entity.y + (entity.displayHeight || 80)) {
        erIsConnecting = true
        erConnectStartEntity = entity
        return
      }
    }
    return
  }
  
  // 选择工具 - 拖拽实体
  for (let i = erEntities.length - 1; i >= 0; i--) {
    const entity = erEntities[i]
    if (x >= entity.x && x <= entity.x + entity.width &&
        y >= entity.y && y <= entity.y + (entity.displayHeight || 80)) {
      erSelectedEntity = entity
      erIsDragging = true
      erDragOffset = { x: x - entity.x, y: y - entity.y }
      return
    }
  }
  
  erSelectedEntity = null
}

const handleErMouseMove = (e: MouseEvent) => {
  if (!erCanvas.value) return
  const p = toLogical(e, erCanvas.value)
  const x = p.x
  const y = p.y
  
  if (erIsDragging && erSelectedEntity) {
    erSelectedEntity.x = Math.max(0, Math.min(LOGICAL_W - erSelectedEntity.width, x - erDragOffset.x))
    erSelectedEntity.y = Math.max(0, Math.min(LOGICAL_H - erSelectedEntity.displayHeight, y - erDragOffset.y))
    redrawErCanvas()
  }
}

const handleErMouseUp = (e: MouseEvent) => {
  if (!erCanvas.value) return
  const p = toLogical(e, erCanvas.value)
  const x = p.x
  const y = p.y
  
  if (erIsConnecting && erConnectStartEntity) {
    for (let i = erEntities.length - 1; i >= 0; i--) {
      const entity = erEntities[i]
      if (entity.id !== erConnectStartEntity.id &&
          x >= entity.x && x <= entity.x + entity.width &&
          y >= entity.y && y <= entity.y + (entity.displayHeight || 80)) {
        // 检查是否已存在相同的关系
        const exists = erRelations.some(r => 
          (r.startEntity === erConnectStartEntity.id && r.endEntity === entity.id) ||
          (r.startEntity === entity.id && r.endEntity === erConnectStartEntity.id)
        )
        if (!exists) {
          saveErHistory()
          erRelations.push({
            id: nextEid(),
            type: selectedErTool.value,
            startEntity: erConnectStartEntity.id,
            endEntity: entity.id
          })
        }
        break
      }
    }
    erIsConnecting = false
    erConnectStartEntity = null
    redrawErCanvas()
    updateStats()
    return
  }
  
  erIsDragging = false
}

const handleErDoubleClick = (e: MouseEvent) => {
  if (!erCanvas.value) return
  const p = toLogical(e, erCanvas.value)
  const x = p.x
  const y = p.y
  
  for (let i = erEntities.length - 1; i >= 0; i--) {
    const entity = erEntities[i]
    if (x >= entity.x && x <= entity.x + entity.width &&
        y >= entity.y && y <= entity.y + (entity.displayHeight || 80)) {
      erEditingEntity.value = JSON.parse(JSON.stringify(entity))
      showErEditModal.value = true
      return
    }
  }
}

const addErField = () => {
  if (erEditingEntity.value) {
    erEditingEntity.value.fields.push({
      name: `field_${erEditingEntity.value.fields.length + 1}`,
      type: 'VARCHAR(255)',
      isPrimary: false,
      isForeign: false
    })
  }
}

const removeErField = (index: number) => {
  if (erEditingEntity.value && erEditingEntity.value.fields.length > 1) {
    erEditingEntity.value.fields.splice(index, 1)
  }
}

const saveErEdit = () => {
  if (!erEditingEntity.value) return
  const index = erEntities.findIndex((e: any) => e.id === erEditingEntity.value.id)
  if (index !== -1) {
    erEntities[index] = JSON.parse(JSON.stringify(erEditingEntity.value))
    redrawErCanvas()
  }
  showErEditModal.value = false
}

const clearErCanvas = () => {
  saveErHistory()
  erEntities = []
  erRelations = []
  erSelectedEntity = null
  redrawErCanvas()
}

// ER图 撤销/重做函数（双栈：erHistory 撤销栈 / erRedo 重做栈）
const saveErHistory = () => {
  erHistory.push({
    entities: JSON.parse(JSON.stringify(erEntities)),
    relations: JSON.parse(JSON.stringify(erRelations))
  })
  if (erHistory.length > 50) erHistory.shift()
  erRedo = []
}

const undoEr = () => {
  if (erHistory.length > 0) {
    erRedo.push({
      entities: JSON.parse(JSON.stringify(erEntities)),
      relations: JSON.parse(JSON.stringify(erRelations))
    })
    const state = erHistory.pop()!
    erEntities = JSON.parse(JSON.stringify(state.entities))
    erRelations = JSON.parse(JSON.stringify(state.relations))
    redrawErCanvas()
  }
}

const redoEr = () => {
  if (erRedo.length > 0) {
    erHistory.push({
      entities: JSON.parse(JSON.stringify(erEntities)),
      relations: JSON.parse(JSON.stringify(erRelations))
    })
    const state = erRedo.pop()!
    erEntities = JSON.parse(JSON.stringify(state.entities))
    erRelations = JSON.parse(JSON.stringify(state.relations))
    redrawErCanvas()
  }
}

// ER图 右键删除
const handleErContextMenu = (e: MouseEvent) => {
  e.preventDefault()
  if (!erCanvas.value) return
  const p = toLogical(e, erCanvas.value)
  const x = p.x
  const y = p.y
  
  for (let i = erEntities.length - 1; i >= 0; i--) {
    const entity = erEntities[i]
    if (x >= entity.x && x <= entity.x + entity.width &&
        y >= entity.y && y <= entity.y + (entity.displayHeight || 80)) {
      saveErHistory()
      erEntities.splice(i, 1)
      erRelations = erRelations.filter(r => r.startEntity !== entity.id && r.endEntity !== entity.id)
      redrawErCanvas()
      updateStats()
      return
    }
  }
  
  for (let i = erRelations.length - 1; i >= 0; i--) {
    const rel = erRelations[i]
    const startEntity = erEntities.find((e: any) => e.id === rel.startEntity)
    const endEntity = erEntities.find((e: any) => e.id === rel.endEntity)
    if (startEntity && endEntity) {
      const startX = startEntity.x + startEntity.width / 2
      const startY = startEntity.y + startEntity.displayHeight / 2
      const endX = endEntity.x + endEntity.width / 2
      const endY = endEntity.y + endEntity.displayHeight / 2
      const dist = pointToLineDistance(x, y, startX, startY, endX, endY)
      if (dist < 10) {
        saveErHistory()
        erRelations.splice(i, 1)
        redrawErCanvas()
        updateStats()
        return
      }
    }
  }
}

const saveErModel = async () => {
  try {
    const modelData = {
      name: 'ER Model',
      description: 'Database Entity Relationship Model',
      entities: erEntities,
      relations: erRelations
    }
    alert('ER 模型保存成功！\n（模型已保存到本地）')
    console.log('ER Model:', modelData)
  } catch (e) {
    console.error('Failed to save ER model:', e)
    alert('保存失败')
  }
}

const exportErImage = () => {
  if (!erCanvas.value) return
  const link = document.createElement('a')
  link.download = `er-diagram-${Date.now()}.png`
  link.href = erCanvas.value.toDataURL()
  link.click()
}

const generateErSql = () => {
  if (erEntities.length === 0) {
    alert('请先创建实体')
    return
  }
  
  let sql = '-- ER Diagram SQL Schema\n-- Generated automatically\n\n'
  
  erEntities.forEach((entity: any) => {
    sql += `CREATE TABLE ${entity.name} (\n`
    
    const fieldLines: string[] = []
    entity.fields.forEach((field: any) => {
      let line = `  ${field.name} ${field.type}`
      if (field.isPrimary) line += ' PRIMARY KEY'
      fieldLines.push(line)
    })
    
    sql += fieldLines.join(',\n')
    sql += '\n);\n\n'
  })
  
  // 添加关系的外键约束
  erRelations.forEach((rel: any) => {
    const startEntity = erEntities.find((e: any) => e.id === rel.startEntity)
    const endEntity = erEntities.find((e: any) => e.id === rel.endEntity)
    
    if (startEntity && endEntity) {
      const relationType = rel.type
      
      if (relationType === 'oneToMany') {
        sql += `-- ${startEntity.name} 1:N ${endEntity.name}\n`
        sql += `ALTER TABLE ${endEntity.name} ADD COLUMN ${startEntity.name.toLowerCase()}_id INT;\n`
        sql += `ALTER TABLE ${endEntity.name} ADD CONSTRAINT fk_${endEntity.name}_${startEntity.name} FOREIGN KEY (${startEntity.name.toLowerCase()}_id) REFERENCES ${startEntity.name}(id);\n\n`
      } else if (relationType === 'oneToOne') {
        sql += `-- ${startEntity.name} 1:1 ${endEntity.name}\n`
        sql += `ALTER TABLE ${endEntity.name} ADD COLUMN ${startEntity.name.toLowerCase()}_id INT UNIQUE;\n`
        sql += `ALTER TABLE ${endEntity.name} ADD CONSTRAINT fk_${endEntity.name}_${startEntity.name} FOREIGN KEY (${startEntity.name.toLowerCase()}_id) REFERENCES ${startEntity.name}(id);\n\n`
      } else if (relationType === 'manyToMany') {
        sql += `-- ${startEntity.name} M:N ${endEntity.name}\n`
        const joinTableName = `${startEntity.name.toLowerCase()}_${endEntity.name.toLowerCase()}`
        sql += `CREATE TABLE ${joinTableName} (\n`
        sql += `  ${startEntity.name.toLowerCase()}_id INT,\n`
        sql += `  ${endEntity.name.toLowerCase()}_id INT,\n`
        sql += `  PRIMARY KEY (${startEntity.name.toLowerCase()}_id, ${endEntity.name.toLowerCase()}_id),\n`
        sql += `  FOREIGN KEY (${startEntity.name.toLowerCase()}_id) REFERENCES ${startEntity.name}(id),\n`
        sql += `  FOREIGN KEY (${endEntity.name.toLowerCase()}_id) REFERENCES ${endEntity.name}(id)\n`
        sql += `);\n\n`
      }
    }
  })
  
  erSqlResult.value = sql

  // 显示SQL结果
  alert('SQL 已生成！\n\n' + sql.substring(0, 500) + (sql.length > 500 ? '...\n\n(完整SQL已复制到控制台)' : ''))
  console.log('Generated SQL:', sql)

  // 复制到剪贴板（捕获非安全上下文下的拒绝，避免未处理 rejection）
  navigator.clipboard.writeText(sql).then(() => {
    alert('SQL 已复制到剪贴板！')
  }).catch(() => {
    // 剪贴板不可用时静默降级，SQL 已在弹窗中展示
  })
}

const saveModel = async () => {
  if (!currentModelId.value) {
    alert('请先创建或选择一个项目')
    return
  }
  try {
    const { ok, status, data } = await modelApi.save(currentModelId.value, {
      elements,
      connections,
      archimateElements,
      archimateConnections,
      erEntities,
      erRelations
    })
    if (!ok) {
      console.error('Save failed:', status, data)
      alert(data?.error || `保存失败: HTTP ${status}`)
      return
    }
    alert('模型保存成功')
    await loadModels()
    updateStats()
    broadcastElementUpdate()
  } catch (e: any) {
    console.error('Failed to save model:', e)
    const errorMsg = e?.message || '未知错误'
    alert(`保存失败: ${errorMsg}\n请检查后端服务是否运行`)
  }
}

const aiValidateModel = async () => {
  if (!currentModelId.value) {
    alert('请先创建或选择一个项目')
    return
  }
  validating.value = true
  validateError.value = ''
  validateResult.value = null
  showValidateModal.value = true
  try {
    // 校验读的是后端保存的模型，先把画布当前状态同步过去
    await modelApi.save(currentModelId.value, { elements, connections })
    const { ok, status, data } = await aiApi.validateUml(currentModelId.value, { view_id: null })
    if (!ok || data?.error) {
      validateError.value = data?.error || `校验失败: HTTP ${status}`
    } else {
      validateResult.value = data
    }
  } catch (e: any) {
    validateError.value = e?.message || '校验请求失败，请检查后端服务'
  } finally {
    validating.value = false
  }
}

const aiReviewArchimate = async () => {
  if (!currentModelId.value) {
    alert('请先创建或选择一个项目')
    return
  }
  reviewing.value = true
  reviewError.value = ''
  reviewResult.value = null
  showReviewModal.value = true
  try {
    // 评审读的是后端保存的模型，先把 ArchiMate 画布当前状态同步过去
    await fetch(`/api/models/${currentModelId.value}`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        'X-Session-Id': sessionStorage.getItem('sessionId') || ''
      },
      body: JSON.stringify({ archimateElements, archimateConnections })
    })
    const { ok, status, data } = await aiApi.reviewArchimate(currentModelId.value)
    if (!ok || data?.error) {
      reviewError.value = data?.error || `评审失败: HTTP ${status}`
    } else {
      reviewResult.value = data
    }
  } catch (e: any) {
    reviewError.value = e?.message || '评审请求失败，请检查后端服务'
  } finally {
    reviewing.value = false
  }
}

// 选中元素 AI 分析（UML / ArchiMate / ER 三套画布共用）
const aiAnalyzeElement = async (kind: 'uml' | 'archimate' | 'er') => {
  if (!currentModelId.value) {
    alert('请先创建或选择一个项目')
    return
  }
  let element: any = null
  let ctxElements: any[] = []
  let ctxRelationships: any[] = []
  if (kind === 'uml') {
    element = selectedElement
    ctxElements = elements
    ctxRelationships = connections
  } else if (kind === 'archimate') {
    element = archimateSelectedElement
    ctxElements = archimateElements
    ctxRelationships = archimateConnections
  } else {
    element = erSelectedEntity
    ctxElements = erEntities
    ctxRelationships = erRelations
  }
  if (!element) {
    alert('请先在画布上选中一个元素')
    return
  }

  analyzing.value = true
  analyzeError.value = ''
  analyzeResult.value = null
  showAnalyzeModal.value = true
  try {
    const { ok, status, data } = await aiApi.analyzeElement(currentModelId.value, {
      kind,
      element,
      context: { elements: ctxElements, relationships: ctxRelationships }
    })
    if (!ok || data?.error) {
      analyzeError.value = data?.error || `分析失败: HTTP ${status}`
    } else {
      analyzeResult.value = data
    }
  } catch (e: any) {
    analyzeError.value = e?.message || '分析请求失败，请检查后端服务'
  } finally {
    analyzing.value = false
  }
}

// 对话式编辑：打开弹窗（UML / ArchiMate / ER 画布共用）
const openAiEditModel = (kind: 'uml' | 'archimate' | 'er') => {
  if (!currentModelId.value) {
    alert('请先创建或选择一个项目')
    return
  }
  editingModelKind.value = kind
  editModelInstruction.value = ''
  editModelError.value = ''
  editModelSuccess.value = ''
  showEditModelModal.value = true
}

// 对话式编辑：提交指令 → 应用修改 → 刷新画布
const submitAiEditModel = async () => {
  const instruction = editModelInstruction.value.trim()
  if (!instruction) {
    editModelError.value = '请输入修改指令'
    return
  }
  editModelError.value = ''
  editModelSuccess.value = ''
  editModelSubmitting.value = true
  try {
    const kind = editingModelKind.value
    const payload: Record<string, unknown> = { kind, instruction }
    if (kind === 'uml') {
      payload.elements = elements
      payload.connections = connections
    } else if (kind === 'archimate') {
      payload.archimateElements = archimateElements
      payload.archimateConnections = archimateConnections
    } else {
      payload.erEntities = erEntities
      payload.erRelations = erRelations
    }
    const { ok, status, data } = await aiApi.editModel(currentModelId.value, payload)
    if (!ok || data?.error) {
      editModelError.value = data?.error || `编辑失败: HTTP ${status}`
      return
    }
    if (kind === 'uml') {
      saveUmlHistory()
      elements = data?.elements || elements
      connections = data?.connections || connections
      selectedElement = null
      redraw()
    } else if (kind === 'archimate') {
      saveArchimateHistory()
      archimateElements = data?.archimateElements || archimateElements
      archimateConnections = data.archimateConnections || archimateConnections
      archimateSelectedElement = null
      redrawArchimateCanvas()
    } else {
      saveErHistory()
      erEntities = data?.erEntities || erEntities
      erRelations = data?.erRelations || erRelations
      erSelectedEntity = null
      redrawErCanvas()
    }
    updateStats()
    editModelSuccess.value = `修改完成（应用了 ${data?.applied_ops ?? 0} 步操作），画布已刷新。记得点「保存」落盘。`
  } catch (e: any) {
    editModelError.value = e?.message || '编辑请求失败，请检查后端服务'
  } finally {
    editModelSubmitting.value = false
  }
}

const loadModelFromServer = async (modelId: string) => {
  try {
    const { data } = await modelApi.get(modelId)
    elements = data?.elements || []
    connections = data?.relationships || data?.connections || []
    archimateElements = data?.archimate_elements || []
    archimateConnections = data?.archimate_connections || []
    erEntities = data?.er_entities || []
    erRelations = data?.er_relations || []
    redraw()
    updateStats()
  } catch (e) {
    console.error('Failed to load model:', e)
  }
}

const exportImage = () => {
  if (!canvas) return
  const link = document.createElement('a')
  link.download = `uml-diagram-${Date.now()}.png`
  link.href = canvas.toDataURL()
  link.click()
}

const addAttribute = () => {
  if (editingElement.value) {
    editingElement.value.attributes.push('- newAttr: Type')
  }
}

const removeAttribute = (index: number) => {
  if (editingElement.value && editingElement.value.attributes.length > 0) {
    editingElement.value.attributes.splice(index, 1)
  }
}

watch(activeTab, (newTab) => {
  updateStats()
  if (newTab === 'uml') {
    // 切换到 UML 标签时，默认选择选择工具
    selectedTool.value = 'select'
    nextTick(() => {
      initCanvasEvents()
    })
  } else if (newTab === 'archimate') {
    // 切换到 ArchiMate 标签时，默认选择选择工具
    selectedArchimateTool.value = 'select'
    nextTick(() => {
      initArchimateCanvas()
    })
  } else if (newTab === 'data') {
    // 切换到数据建模标签时，默认选择选择工具
    selectedErTool.value = 'select'
    nextTick(() => {
      initErCanvas()
    })
  } else if (newTab === 'ai') {
    // 切到 AI 页时重建一次项目上下文（画布数组是非响应式的普通数组）
    contextRefreshKey.value++
  }
})

// === 实时协作（Socket.IO） ===
let socket: any = null
let joinedProjectId = ''
// 在线协作
const onlineUsers = ref<string[]>([])
const collabToast = ref('')
let collabToastTimer: number | null = null
const showCollabToast = (text: string) => {
  collabToast.value = text
  if (collabToastTimer) window.clearTimeout(collabToastTimer)
  collabToastTimer = window.setTimeout(() => { collabToast.value = '' }, 3000)
}

const initSocket = () => {
  if (socket) return
  socket = io({
    transports: ['websocket', 'polling']
  })
  socket.on('connect', () => {
    if (currentModelId.value) {
      socket.emit('join_project', { project_id: currentModelId.value, session_id: sessionStorage.getItem('sessionId') || '' })
      joinedProjectId = currentModelId.value
    }
  })
  // 在线协作：在线用户列表 / 加入离开 / 他人更新
  socket.on('collab_users', (d: any) => {
    onlineUsers.value = d?.users || []
  })
  socket.on('user_joined', (d: any) => {
    showCollabToast(`${d?.username || '协作者'} 加入了协作`)
  })
  socket.on('user_left', (d: any) => {
    showCollabToast(`${d?.username || '协作者'} 离开了协作`)
  })
  socket.on('element_updated', (d: any) => {
    // 其他协作者有改动：提示并重新拉取当前模型
    showCollabToast(`${d?.username || '协作者'} 更新了模型，已自动同步`)
    if (currentModelId.value) {
      loadModelFromServer(currentModelId.value)
    }
  })
  socket.on('disconnect', () => {
    joinedProjectId = ''
    onlineUsers.value = []
  })
}

const joinProjectRoom = () => {
  if (!socket || !currentModelId.value) return
  if (joinedProjectId && joinedProjectId !== currentModelId.value) {
    socket.emit('leave_project', { project_id: joinedProjectId, session_id: sessionStorage.getItem('sessionId') || '' })
  }
  socket.emit('join_project', { project_id: currentModelId.value, session_id: sessionStorage.getItem('sessionId') || '' })
  joinedProjectId = currentModelId.value
}

const leaveProjectRoom = (projectId: string) => {
  if (!socket) return
  socket.emit('leave_project', { project_id: projectId, session_id: sessionStorage.getItem('sessionId') || '' })
  if (joinedProjectId === projectId) joinedProjectId = ''
}

const broadcastElementUpdate = () => {
  if (!socket || !currentModelId.value) return
  socket.emit('element_update', { project_id: currentModelId.value, session_id: sessionStorage.getItem('sessionId') || '' })
}

// 键盘快捷键：Ctrl+Z 撤销 / Ctrl+Y（或 Ctrl+Shift+Z）重做，按当前画布分派
const handleKeyboardShortcut = (e: KeyboardEvent) => {
  const isUndo = (e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z' && !e.shiftKey
  const isRedo = (e.ctrlKey || e.metaKey) && (e.key.toLowerCase() === 'y' || (e.key.toLowerCase() === 'z' && e.shiftKey))
  if (!isUndo && !isRedo) return
  e.preventDefault()
  if (activeTab.value === 'uml') {
    isUndo ? undoUml() : redoUml()
  } else if (activeTab.value === 'archimate') {
    isUndo ? undoArchimate() : redoArchimate()
  } else if (activeTab.value === 'data') {
    isUndo ? undoEr() : redoEr()
  }
}

// 三画布统一 resize：防抖 150ms，容器尺寸变化后重建物理像素尺寸与变换并重绘
let canvasResizeTimer: number | null = null
const resizeAllCanvases = () => {
  if (canvasResizeTimer) window.clearTimeout(canvasResizeTimer)
  canvasResizeTimer = window.setTimeout(() => {
    const c1 = document.getElementById('canvas') as HTMLCanvasElement | null
    if (c1) { setupCanvasTransform(c1); redraw() }
    const c2 = archimateCanvas.value as HTMLCanvasElement | null
    if (c2) { setupCanvasTransform(c2); redrawArchimateCanvas() }
    const c3 = erCanvas.value as HTMLCanvasElement | null
    if (c3) { setupCanvasTransform(c3); redrawErCanvas() }
  }, 150)
}
window.addEventListener('resize', resizeAllCanvases)

onMounted(() => {
  initSocket()
  window.addEventListener('keydown', handleKeyboardShortcut)
  checkAuth()
})
</script>

<template>
  <!-- 液态玻璃背景光斑（在登录页与主界面下方） -->
  <div class="bg-blobs" aria-hidden="true"></div>

  <!-- 协作提示 toast -->
  <transition name="fade">
    <div v-if="collabToast" class="collab-toast"><i class="fas fa-people-group"></i> {{ collabToast }}</div>
  </transition>

  <!-- 登录门禁：未认证前不渲染主界面 -->
  <div v-if="!authChecked" class="app-loading">
    <i class="fas fa-spinner fa-spin"></i> 正在加载...
  </div>

  <LoginView v-else-if="!authUser" @authenticated="onAuthenticated" />

  <div v-else class="container">
    <div class="header">
      <div class="header-left">
        <div class="header-logo"><i class="fas fa-project-diagram"></i></div>
        <div class="header-text">
          <h1>AI原生Enterprise Architect</h1>
          <p>智能企业架构建模平台</p>
        </div>
      </div>
      <div class="header-right">
        <button class="btn-help" @click="showHelpModal = true" title="新手教程">
          <i class="fas fa-circle-question"></i>
          <span>帮助</span>
        </button>
        <div class="user-chip">
          <div class="user-avatar">{{ (authUser?.username || 'U').charAt(0).toUpperCase() }}</div>
          <span class="user-name">{{ authUser?.username }}</span>
        </div>
        <button class="btn-logout" @click="logout" title="退出登录">
          <i class="fas fa-sign-out-alt"></i>
          <span>退出</span>
        </button>
      </div>
    </div>

    <div class="stats-row">
      <!-- 主页面显示项目数量 -->
      <template v-if="activeTab === 'projects' || activeTab === 'ai'">
        <div class="stat-card">
          <div class="stat-value">{{ stats.models }}</div>
          <div class="stat-label">项目模型</div>
        </div>
      </template>
      <!-- 视图编辑页面显示项目名称、元素和关系数量 -->
      <template v-else>
        <div class="stat-card">
          <div class="stat-value" style="font-size: 14px;">{{ currentModelName || '未选择项目' }}</div>
          <div class="stat-label">当前项目</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ stats.elements }}</div>
          <div class="stat-label">架构元素</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ stats.relationships }}</div>
          <div class="stat-label">关系连接</div>
        </div>
      </template>
    </div>

    <div class="nav-tabs">
      <button 
        v-for="tab in navTabs"
        :key="tab.id"
        :class="['nav-tab', { active: activeTab === tab.id }]"
        :data-tab="tab.id"
        @click="activeTab = tab.id"
      >
        <i :class="tab.icon"></i> {{ tab.name }}
      </button>
    </div>

    <div class="ribbon" v-if="activeTab === 'uml' || activeTab === 'archimate' || activeTab === 'data'">
  <template v-if="activeTab === 'uml'">
    <div class="ribbon-group">
      <div class="ribbon-group-label">建模工具</div>
      <button v-for="tool in tools" :key="tool.id"
        :class="['toolbar-btn', { active: selectedTool === tool.id }]"
        @click="selectedTool = tool.id" :title="tool.name">
        <i :class="tool.icon"></i> {{ tool.name }}
      </button>
    </div>
    <div class="ribbon-group">
      <div class="ribbon-group-label">编辑</div>
      <button class="toolbar-btn" @click="undoUml" title="撤销 (Ctrl+Z)"><i class="fas fa-undo"></i> 撤销</button>
      <button class="toolbar-btn" @click="redoUml" title="重做 (Ctrl+Y)"><i class="fas fa-redo"></i> 重做</button>
      <button class="toolbar-btn" @click="saveModel"><i class="fas fa-save"></i> 保存</button>
      <button class="toolbar-btn" @click="clearCanvas"><i class="fas fa-trash"></i> 清空</button>
    </div>
    <div class="ribbon-group">
      <div class="ribbon-group-label">AI</div>
      <div style="position:relative; display:inline-block;">
        <button class="toolbar-btn" @click="toggleAiMenu('uml')" :class="{ active: openAiMenu === 'uml' }" title="AI 功能" data-tour="ai">
          <i class="fas fa-robot"></i> AI <i class="fas fa-chevron-down" style="font-size:10px;"></i>
        </button>
        <div v-if="openAiMenu === 'uml'" class="ai-dropdown">
          <div class="ai-dropdown-title">UML 模型</div>
          <button class="ai-dropdown-item" @click="runAiAction('uml', 'validate')" :disabled="validating">
            <i class="fas fa-magnifying-glass-chart"></i> {{ validating ? '校验中...' : 'AI校验整个模型' }}
          </button>
          <button class="ai-dropdown-item" @click="runAiAction('uml', 'analyze')" :disabled="analyzing">
            <i class="fas fa-wand-magic-sparkles"></i> {{ analyzing ? '分析中...' : 'AI分析选中元素' }}
          </button>
          <button class="ai-dropdown-item" @click="runAiAction('uml', 'edit')">
            <i class="fas fa-comment-dots"></i> AI对话式编辑
          </button>
          <button class="ai-dropdown-item" @click="openGenerateDiagram('uml')">
            <i class="fas fa-wand-magic-sparkles"></i> 从描述生成图
          </button>
        </div>
      </div>
    </div>
    <div class="ribbon-group">
      <div class="ribbon-group-label">导出</div>
      <button class="toolbar-btn" @click="exportImage"><i class="fas fa-download"></i> 导出图片</button>
    </div>
  </template>
<template v-if="activeTab === 'archimate'">
  <div class="ribbon-group">
    <div class="ribbon-group-label">建模工具</div>
    <button v-for="tool in archimateTools" :key="tool.id"
      :class="['toolbar-btn', { active: selectedArchimateTool === tool.id }]"
      @click="selectedArchimateTool = tool.id" :title="tool.name">
      <i :class="tool.icon"></i> {{ tool.name }}
    </button>
  </div>
  <div class="ribbon-group">
    <div class="ribbon-group-label">层次</div>
    <label style="display:flex;align-items:center;cursor:pointer;gap:4px;">
      <input type="radio" v-model="archimateLayer" value="business" /> 业务层
    </label>
    <label style="display:flex;align-items:center;cursor:pointer;gap:4px;">
      <input type="radio" v-model="archimateLayer" value="application" /> 应用层
    </label>
    <label style="display:flex;align-items:center;cursor:pointer;gap:4px;">
      <input type="radio" v-model="archimateLayer" value="technology" /> 技术层
    </label>
  </div>
  <div class="ribbon-group">
    <div class="ribbon-group-label">编辑</div>
    <button class="toolbar-btn" @click="undoArchimate"><i class="fas fa-undo"></i> 撤销</button>
    <button class="toolbar-btn" @click="redoArchimate"><i class="fas fa-redo"></i> 重做</button>
    <button class="toolbar-btn" @click="saveArchimateModel"><i class="fas fa-save"></i> 保存</button>
    <button class="toolbar-btn" @click="clearArchimateCanvas"><i class="fas fa-trash"></i> 清空</button>
  </div>
  <div class="ribbon-group">
    <div class="ribbon-group-label">AI</div>
    <div style="position:relative; display:inline-block;">
      <button class="toolbar-btn" @click="toggleAiMenu('archimate')" :class="{ active: openAiMenu === 'archimate' }">
        <i class="fas fa-robot"></i> AI <i class="fas fa-chevron-down" style="font-size:10px;"></i>
      </button>
      <div v-if="openAiMenu === 'archimate'" class="ai-dropdown">
        <div class="ai-dropdown-title">ArchiMate 架构</div>
        <button class="ai-dropdown-item" @click="runAiAction('archimate', 'review')" :disabled="reviewing">
          <i class="fas fa-magnifying-glass-chart"></i> {{ reviewing ? '评审中...' : 'AI架构评审' }}
        </button>
        <button class="ai-dropdown-item" @click="runAiAction('archimate', 'analyze')" :disabled="analyzing">
          <i class="fas fa-wand-magic-sparkles"></i> {{ analyzing ? '分析中...' : 'AI分析选中元素' }}
        </button>
        <button class="ai-dropdown-item" @click="runAiAction('archimate', 'edit')">
          <i class="fas fa-comment-dots"></i> AI对话式编辑
        </button>
      </div>
    </div>
  </div>
  <div class="ribbon-group">
    <div class="ribbon-group-label">导出</div>
    <button class="toolbar-btn" @click="exportArchimateImage"><i class="fas fa-download"></i> 导出图片</button>
  </div>
</template>
<template v-if="activeTab === 'data'">
  <div class="ribbon-group">
    <div class="ribbon-group-label">建模工具</div>
    <button v-for="tool in erTools" :key="tool.id"
      :class="['toolbar-btn', { active: selectedErTool === tool.id }]"
      @click="selectedErTool = tool.id" :title="tool.name">
      <i :class="tool.icon"></i> {{ tool.name }}
    </button>
  </div>
  <div class="ribbon-group">
    <div class="ribbon-group-label">编辑</div>
    <button class="toolbar-btn" @click="undoEr"><i class="fas fa-undo"></i> 撤销</button>
    <button class="toolbar-btn" @click="redoEr"><i class="fas fa-redo"></i> 重做</button>
    <button class="toolbar-btn" @click="generateErSql"><i class="fas fa-database"></i> 生成SQL</button>
    <button class="toolbar-btn" @click="saveErModel"><i class="fas fa-save"></i> 保存</button>
    <button class="toolbar-btn" @click="clearErCanvas"><i class="fas fa-trash"></i> 清空</button>
  </div>
  <div class="ribbon-group">
    <div class="ribbon-group-label">AI</div>
    <div style="position:relative; display:inline-block;">
      <button class="toolbar-btn" @click="toggleAiMenu('er')" :class="{ active: openAiMenu === 'er' }">
        <i class="fas fa-robot"></i> AI <i class="fas fa-chevron-down" style="font-size:10px;"></i>
      </button>
      <div v-if="openAiMenu === 'er'" class="ai-dropdown">
        <div class="ai-dropdown-title">数据模型</div>
        <button class="ai-dropdown-item" @click="runAiAction('er', 'analyze')" :disabled="analyzing">
          <i class="fas fa-wand-magic-sparkles"></i> {{ analyzing ? '分析中...' : 'AI分析选中表' }}
        </button>
        <button class="ai-dropdown-item" @click="runAiAction('er', 'edit')">
          <i class="fas fa-comment-dots"></i> AI对话式编辑
        </button>
        <button class="ai-dropdown-item" @click="openGenerateDiagram('er')">
          <i class="fas fa-wand-magic-sparkles"></i> 从描述生成图
        </button>
      </div>
    </div>
  </div>
  <div class="ribbon-group">
    <div class="ribbon-group-label">导出</div>
    <button class="toolbar-btn" @click="exportErImage"><i class="fas fa-download"></i> 导出图片</button>
  </div>
</template>
</div>

    <div v-if="activeTab === 'dashboard'" class="dashboard-grid">
      <div class="card">
        <div class="card-icon" style="background: linear-gradient(135deg, #1f5eff 0%, #764ba2 100%);">
          <i class="fas fa-folder-open"></i>
        </div>
        <h3 class="card-title">项目管理</h3>
        <p class="card-desc">创建、管理和组织您的企业架构项目</p>
        <button class="btn btn-primary" @click="activeTab = 'projects'">
          <i class="fas fa-arrow-right"></i> 进入
        </button>
      </div>

      <div class="card">
        <div class="card-icon" style="background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);">
          <i class="fas fa-diagram-project"></i>
        </div>
        <h3 class="card-title">UML建模</h3>
        <p class="card-desc">创建类图、序列图、活动图等UML图表</p>
        <button class="btn btn-primary" @click="activeTab = 'uml'">
          <i class="fas fa-arrow-right"></i> 进入
        </button>
      </div>

      <div class="card">
        <div class="card-icon" style="background: linear-gradient(135deg, #eb3349 0%, #f45c43 100%);">
          <i class="fas fa-cubes"></i>
        </div>
        <h3 class="card-title">ArchiMate建模</h3>
        <p class="card-desc">企业架构可视化与分析</p>
        <button class="btn btn-primary" @click="activeTab = 'archimate'">
          <i class="fas fa-arrow-right"></i> 进入
        </button>
      </div>

      <div class="card">
        <div class="card-icon" style="background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);">
          <i class="fas fa-database"></i>
        </div>
        <h3 class="card-title">数据建模</h3>
        <p class="card-desc">设计ER图和数据库模型</p>
        <button class="btn btn-primary" @click="activeTab = 'data'">
          <i class="fas fa-arrow-right"></i> 进入
        </button>
      </div>

      <div class="card">
        <div class="card-icon" style="background: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%);">
          <i class="fas fa-code"></i>
        </div>
        <h3 class="card-title">代码生成</h3>
        <p class="card-desc">从模型自动生成代码</p>
        <button class="btn btn-primary" @click="activeTab = 'code'">
          <i class="fas fa-arrow-right"></i> 进入
        </button>
      </div>

      <div class="card">
        <div class="card-icon" style="background: linear-gradient(135deg, #fa709a 0%, #fee140 100%);">
          <i class="fas fa-robot"></i>
        </div>
        <h3 class="card-title">AI助手</h3>
        <p class="card-desc">智能分析和建议</p>
        <button class="btn btn-primary" @click="activeTab = 'ai'">
          <i class="fas fa-arrow-right"></i> 进入
        </button>
      </div>
    </div>

    <div v-if="activeTab === 'projects'" class="card">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
        <h3 class="card-title" style="margin: 0;">项目列表</h3>
        <button class="btn btn-primary" @click="showCreateModal = true">
          <i class="fas fa-plus"></i> 新建项目
        </button>
      </div>
      
      <div class="model-list">
        <div v-for="model in models" :key="model.id" class="model-item">
          <div class="model-icon" :style="projectIconStyle(model.name)">{{ projectInitial(model.name) }}</div>
          <div class="model-info">
            <h4>{{ model.name }}</h4>
            <p>{{ model.description || '暂无描述' }}</p>
            <p style="font-size: 11px; margin-top: 4px;">
              <span style="margin-right: 15px;">元素: {{ model.elements_count }}</span>
              <span>关系: {{ model.relationships_count }}</span>
            </p>
          </div>
          <div class="model-actions">
            <button class="btn-edit" @click="openModel(model)">
              <i class="fas fa-eye"></i> 打开
            </button>
            <button class="btn-delete" @click="deleteModel(model.id)">
              <i class="fas fa-trash"></i> 删除
            </button>
          </div>
        </div>
        <div v-if="models.length === 0" style="text-align: center; padding: 40px; color: #999;">
          暂无项目，请创建一个新项目
        </div>
      </div>
    </div>

    <div v-if="activeTab === 'uml'" class="card canvas-container">
      <canvas
        id="canvas"
        width="1150" 
        height="600"
        @click="handleCanvasClick"
        @mousedown="handleMouseDown"
        @dblclick="handleDoubleClick"
        @contextmenu="handleUmlContextMenu"
      ></canvas>
      <div class="canvas-statusbar">
        <div class="status-item"><i class="fas fa-folder"></i> <strong>{{ currentModelName || '未选择项目' }}</strong></div>
        <div class="status-item"><i class="fas fa-box"></i> {{ elements.length }} 元素</div>
        <div class="status-item"><i class="fas fa-link"></i> {{ connections.length }} 关系</div>
        <div class="status-item"><i class="fas fa-mouse-pointer"></i> {{ selectedToolName }}</div>
        <div v-if="onlineUsers.length" class="status-item collab-chip">
          <i class="fas fa-users"></i>
          <span class="collab-avatars">
            <span v-for="(u, i) in onlineUsers" :key="i" class="collab-avatar" :title="u">{{ (u || '?').charAt(0).toUpperCase() }}</span>
          </span>
          在线 {{ onlineUsers.length }}
        </div>
        <div class="status-item status-right"><i class="fas fa-info-circle"></i> 双击编辑 · 右键删除 · 连线工具点两元素</div>
      </div>
    </div>

    <!-- ArchiMate 企业架构建模 -->
    <div v-if="activeTab === 'archimate'" class="card canvas-container">
      <canvas
        ref="archimateCanvas"
        id="archimateCanvas" 
        width="1150" 
        height="600"
        @click="handleArchimateClick"
        @mousedown="handleArchimateMouseDown"
        @dblclick="handleArchimateDoubleClick"
        @contextmenu="handleArchimateContextMenu"
      ></canvas>
      
      <div class="canvas-statusbar">
        <div class="status-item"><i class="fas fa-folder"></i> <strong>{{ currentModelName || '未选择项目' }}</strong></div>
        <div class="status-item"><i class="fas fa-cube"></i> {{ archimateElements.length }} 元素</div>
        <div class="status-item"><i class="fas fa-link"></i> {{ archimateConnections.length }} 关系</div>
        <div class="status-item"><i class="fas fa-mouse-pointer"></i> {{ selectedArchimateToolName }}</div>
        <div class="status-item status-right"><i class="fas fa-info-circle"></i> 双击编辑 · 右键删除 · 连线工具点两元素</div>
      </div>
    </div>

    <!-- 数据建模（ER图） -->
    <div v-if="activeTab === 'data'" class="card canvas-container">
      <canvas
        ref="erCanvas"
        id="erCanvas" 
        width="1150" 
        height="600"
        @click="handleErClick"
        @mousedown="handleErMouseDown"
        @dblclick="handleErDoubleClick"
        @contextmenu="handleErContextMenu"
      ></canvas>
      
      <div class="canvas-statusbar">
        <div class="status-item"><i class="fas fa-folder"></i> <strong>{{ currentModelName || '未选择项目' }}</strong></div>
        <div class="status-item"><i class="fas fa-table"></i> {{ erEntities.length }} 表</div>
        <div class="status-item"><i class="fas fa-link"></i> {{ erRelations.length }} 关系</div>
        <div class="status-item"><i class="fas fa-mouse-pointer"></i> {{ selectedErToolName }}</div>
        <div class="status-item status-right"><i class="fas fa-info-circle"></i> 双击编辑 · 右键删除 · 连线工具点两表</div>
      </div>
    </div>

    <div v-if="activeTab === 'code'" class="card">
      <h3 class="card-title">代码生成</h3>
      <p class="card-desc">从模型自动生成代码</p>
      
      <div style="margin-top: 20px;">
        <div style="display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 20px;">
          <select 
            v-model="codeConfig.source" 
            style="padding: 10px; border-radius: 8px; border: 2px solid #e8ecf0;"
          >
            <option value="uml">UML类图</option>
            <option value="er">ER图</option>
          </select>
          <select 
            v-model="codeConfig.outputType" 
            style="padding: 10px; border-radius: 8px; border: 2px solid #e8ecf0;"
          >
            <option value="entity">实体类</option>
            <option v-if="codeConfig.source === 'uml'" value="controller">Controller</option>
            <option v-if="codeConfig.source === 'uml'" value="service">Service</option>
            <option v-if="codeConfig.source === 'er'" value="sql">SQL脚本</option>
          </select>
          <select 
            v-model="codeConfig.language" 
            style="padding: 10px; border-radius: 8px; border: 2px solid #e8ecf0;"
          >
            <option value="java">Java</option>
            <option value="python">Python</option>
            <option value="typescript">TypeScript</option>
            <option value="csharp">C#</option>
          </select>
          <select 
            v-model="codeConfig.framework" 
            style="padding: 10px; border-radius: 8px; border: 2px solid #e8ecf0;"
          >
            <option value="spring">Spring Boot</option>
            <option value="django">Django</option>
            <option value="nestjs">NestJS</option>
            <option value="none">无框架</option>
          </select>
          <button class="btn btn-primary" @click="generateCode" :disabled="codeGenerating">
            <i class="fas fa-code"></i> {{ codeGenerating ? '生成中...' : '生成代码' }}
          </button>
          <button 
            class="btn btn-outline" 
            @click="copyCode"
            :disabled="!generatedCode || generatedCode.startsWith('//')"
          >
            <i class="fas fa-copy"></i> 复制
          </button>
          <button 
            class="btn btn-outline" 
            @click="downloadCode"
            :disabled="!generatedCode || generatedCode.startsWith('//')"
          >
            <i class="fas fa-download"></i> 下载
          </button>
        </div>
        
        <div class="code-preview">
          <pre>{{ generatedCode }}</pre>
        </div>
      </div>

      <div style="margin-top: 36px; border-top: 1px solid #e8ecf0; padding-top: 24px;">
        <h3 class="card-title"><i class="fas fa-arrow-left-long" style="color: #1f5eff;"></i> 代码反向工程</h3>
        <p class="card-desc">粘贴源代码，AI 反推出 UML 类图或 ER 模型并画到画布上</p>

        <div style="display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 12px;">
          <select
            v-model="reverseConfig.target"
            style="padding: 10px; border-radius: 8px; border: 2px solid #e8ecf0;"
          >
            <option value="uml">UML类图</option>
            <option value="er">ER模型</option>
          </select>
          <select
            v-model="reverseConfig.language"
            style="padding: 10px; border-radius: 8px; border: 2px solid #e8ecf0;"
          >
            <option value="auto">自动识别语言</option>
            <option value="java">Java</option>
            <option value="python">Python</option>
            <option value="typescript">TypeScript</option>
            <option value="csharp">C#</option>
            <option value="go">Go</option>
          </select>
          <button class="btn btn-primary" @click="reverseCode" :disabled="reversing || !reverseConfig.code.trim()">
            <i class="fas fa-arrow-left"></i> {{ reversing ? '反推中...' : '反推模型' }}
          </button>
        </div>

        <textarea
          v-model="reverseConfig.code"
          rows="10"
          placeholder="在此粘贴源代码，例如：一个含用户/订单/商品的 Java 或 Python 类…"
          style="width: 100%; font-family: 'Cascadia Code', Consolas, monospace; font-size: 13px; padding: 12px; border: 1px solid #ddd; border-radius: 8px; resize: vertical; background: #fafbff;"
        ></textarea>

        <div v-if="reverseError" style="margin-top: 10px; color: #d33; background: #fdf0f0; padding: 10px; border-radius: 8px;">
          <i class="fas fa-exclamation-triangle"></i> {{ reverseError }}
        </div>
        <p style="color: #999; font-size: 12px; margin-top: 8px;">
          反推结果会直接画到对应画布（UML类图 / ER模型），之后记得点「保存」落盘。需要先创建或选择一个项目。
        </p>
      </div>

      <div style="margin-top: 36px; border-top: 1px solid #e8ecf0; padding-top: 24px;">
        <h3 class="card-title"><i class="fas fa-file-lines" style="color: #1f5eff;"></i> AI 文档/报表生成</h3>
        <p class="card-desc">用 AI 把当前模型生成设计文档或项目报告，可导出 Markdown / HTML</p>

        <div style="display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 12px;">
          <select v-model="docConfig.docType" style="padding: 10px; border-radius: 8px; border: 2px solid #e8ecf0;">
            <option value="architecture">架构设计文档</option>
            <option value="overview">项目概览报告</option>
            <option value="database">数据库设计文档</option>
          </select>
          <select v-model="docConfig.format" style="padding: 10px; border-radius: 8px; border: 2px solid #e8ecf0;">
            <option value="markdown">Markdown</option>
            <option value="html">HTML</option>
          </select>
          <button class="btn btn-primary" @click="generateDoc" :disabled="docGenerating">
            <i v-if="docGenerating" class="fas fa-spinner fa-spin"></i>
            <i v-else class="fas fa-file-lines"></i> {{ docGenerating ? '生成中...' : '生成文档' }}
          </button>
          <button class="btn btn-outline" @click="copyDoc" :disabled="!generatedDoc">
            <i class="fas fa-copy"></i> 复制
          </button>
          <button class="btn btn-outline" @click="downloadDoc" :disabled="!generatedDoc">
            <i class="fas fa-download"></i> 下载
          </button>
        </div>

        <div v-if="docError" style="margin-top: 10px; color: #d33; background: #fdf0f0; padding: 10px; border-radius: 8px;">
          <i class="fas fa-exclamation-triangle"></i> {{ docError }}
        </div>

        <div v-if="generatedDoc" class="doc-preview">
          <pre>{{ generatedDoc }}</pre>
        </div>
      </div>
    </div>

    <div v-if="activeTab === 'dev'" class="card">
      <h3 class="card-title"><i class="fas fa-tasks" style="color:#1f5eff;"></i> 研发管理</h3>
      <p class="card-desc">管理项目的需求、测试用例、缺陷与任务</p>
      <div style="display:flex; gap:8px; flex-wrap:wrap; margin-bottom:16px;">
        <button v-for="t in devTabs" :key="t.id"
          :class="['toolbar-btn', { active: activeDevTab === t.id }]"
          @click="activeDevTab = t.id; loadDevList()">
          <i :class="t.icon"></i> {{ t.name }}
        </button>
        <div style="flex:1;"></div>
        <button v-if="activeDevTab !== 'defect'" class="btn btn-outline" @click="openDevAi">
          <i class="fas fa-wand-magic-sparkles"></i> AI 生成
        </button>
        <button class="btn btn-primary" @click="openDevModal(null)"><i class="fas fa-plus"></i> 新增</button>
      </div>

      <div v-if="devError" style="color:#d33; background:#fdf0f0; padding:10px; border-radius:8px; margin-bottom:12px;">
        <i class="fas fa-exclamation-triangle"></i> {{ devError }}
      </div>

      <table class="table" v-if="devList.length">
        <thead>
          <tr>
            <th v-for="f in DEV_FIELDS[activeDevTab]" :key="f.key">{{ f.label }}</th>
            <th style="width:100px;">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in devList" :key="item.id">
            <td v-for="f in DEV_FIELDS[activeDevTab]" :key="f.key">{{ item[f.key] || '-' }}</td>
            <td>
              <button class="btn btn-outline" style="padding:4px 8px; font-size:12px; margin-right:4px;" @click="openDevModal(item)">编辑</button>
              <button class="btn-delete" @click="removeDev(item)"><i class="fas fa-trash"></i></button>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-else style="color:#999;">暂无{{ devTabs.find(t => t.id === activeDevTab)?.name }}数据，点「新增」或「AI 生成」创建。</p>
    </div>

    <!-- 后台管理（仅 admin） -->
    <div v-if="activeTab === 'admin'" class="card">
      <h3 class="card-title"><i class="fas fa-shield-halved" style="color:#1f5eff;"></i> 后台管理</h3>
      <p class="card-desc">管理系统所有账号与各账号下的项目</p>

      <div style="display:flex; gap:8px; flex-wrap:wrap; margin-bottom:16px;">
        <button class="btn btn-primary" @click="openAdminUserModal(null)"><i class="fas fa-user-plus"></i> 新增用户</button>
        <button class="btn btn-outline" @click="loadAdminUsers"><i class="fas fa-sync"></i> 刷新</button>
      </div>

      <div v-if="adminError" style="color:#d33; background:#fdf0f0; padding:10px; border-radius:8px; margin-bottom:12px;">
        <i class="fas fa-exclamation-triangle"></i> {{ adminError }}
      </div>

      <table class="table" v-if="adminUsers.length">
        <thead>
          <tr>
            <th>用户名</th>
            <th>邮箱</th>
            <th>角色</th>
            <th>创建时间</th>
            <th>项目数</th>
            <th style="width:220px;">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="u in adminUsers" :key="u.id">
            <td>{{ u.username }}</td>
            <td>{{ u.email || '-' }}</td>
            <td><span :class="['badge', u.role === 'admin' ? 'badge-warning' : 'badge-info']">{{ u.role === 'admin' ? '管理员' : '普通用户' }}</span></td>
            <td>{{ (u.created_at || '').slice(0, 10) }}</td>
            <td>{{ u.project_count }}</td>
            <td>
              <button class="btn btn-outline" style="padding:4px 8px; font-size:12px; margin-right:4px;" @click="viewUserProjects(u)">项目</button>
              <button class="btn btn-outline" style="padding:4px 8px; font-size:12px; margin-right:4px;" @click="openAdminUserModal(u)">编辑</button>
              <button class="btn-delete" @click="removeAdminUser(u)"><i class="fas fa-trash"></i></button>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-else style="color:#999;">暂无用户{{ adminLoading ? '（加载中）' : '' }}</p>
    </div>

    <div v-if="activeTab === 'ai'" class="card" style="padding: 0; height: calc(100vh - 120px);">
      <AIAssistant :project-context="projectContext" :project-id="currentModelId || ''" />
    </div>
  </div>

  <!-- AI 下拉菜单的外层遮罩：点击任意空白关闭 -->
  <div v-if="openAiMenu" class="ai-menu-overlay" @click="openAiMenu = null"></div>

  <!-- 新手教程 -->
  <div v-if="showHelpModal" class="modal-overlay" @click.self="showHelpModal = false">
    <div class="modal-content help-modal">
      <span class="modal-close" @click="showHelpModal = false">&times;</span>
      <h3 style="margin-top:0;"><i class="fas fa-circle-question" style="color:#1f5eff;"></i> 新手教程</h3>
      <p style="color:#666; font-size:13px; margin-bottom:16px;">用 2 分钟了解这个平台能做什么，然后开始建模。</p>

      <div class="help-section">
        <h4><i class="fas fa-user-lock"></i> 一、账号</h4>
        <ul>
          <li>登录 / 注册在首页完成；右上角「退出」退出账号</li>
          <li>每个账号的项目互相隔离，别人看不到你的模型</li>
        </ul>
      </div>

      <div class="help-section">
        <h4><i class="fas fa-compass"></i> 二、三步上手</h4>
        <ol>
          <li>进「项目管理」→ 新建项目，起个名字</li>
          <li>打开项目，顶部导航选一种画布：<b>UML建模 / ArchiMate / 数据建模</b></li>
          <li>点顶部工具栏的图形按钮，再点画布添加元素；拖动调整位置</li>
        </ol>
      </div>

      <div class="help-section">
        <h4><i class="fas fa-palette"></i> 三、三种画布</h4>
        <ul>
          <li><b>UML</b>：类 / 接口 / 关系（继承、组合、关联…）——画系统设计</li>
          <li><b>ArchiMate</b>：业务 / 应用 / 技术三层——画企业架构</li>
          <li><b>数据建模</b>：表 / 字段 / 主外键——画数据库，还能一键生成 SQL</li>
          <li>通用操作：双击元素编辑 · 右键删除 · <b>Ctrl+Z</b> 撤销 / <b>Ctrl+Y</b> 重做 · 记得点「保存」</li>
        </ul>
      </div>

      <div class="help-section">
        <h4><i class="fas fa-robot"></i> 四、AI 功能（画布顶部「AI」按钮）</h4>
        <ul>
          <li><b>AI 校验</b>：检查 UML 模型问题；<b>AI 架构评审</b>：评审 ArchiMate 架构</li>
          <li><b>AI 分析</b>：选中一个元素，让 AI 点评优缺点</li>
          <li><b>AI 对话式编辑</b>：用一句话改模型，比如「给 Order 类加个 status 字段」</li>
          <li>「代码生成」页：模型 → 代码 · 贴代码 → 反推模型 · AI 生成设计文档/报表</li>
        </ul>
      </div>

      <div class="help-section">
        <h4><i class="fas fa-comment-dots"></i> 五、AI 助手</h4>
        <ul>
          <li>右下角「AI助手」页对话问答，回复实时流式输出</li>
          <li><b>记忆库</b>：说「记住：xxx」自动保存，以后 AI 会记住你的项目偏好</li>
        </ul>
      </div>

      <div class="help-section">
        <h4><i class="fas fa-tasks"></i> 六、研发管理</h4>
        <ul>
          <li>管理项目的<b>需求 / 测试用例 / 缺陷 / 任务</b>，支持 AI 一键生成</li>
        </ul>
      </div>

      <div class="help-section">
        <h4><i class="fas fa-lightbulb"></i> 七、小贴士</h4>
        <ul>
          <li>画布底部状态栏显示当前项目 / 元素数 / 当前工具</li>
          <li>顶部功能区可导出图片；工具都带图标和文字提示，悬停可见说明</li>
        </ul>
      </div>

      <div style="margin-top:18px; display:flex; justify-content:space-between; align-items:center; gap:10px;">
        <button class="btn btn-outline" @click="startTour" style="border-color:#1f5eff; color:#1f5eff;">
          <i class="fas fa-compass"></i> 遇到了问题？需要引导？
        </button>
        <button class="btn btn-primary" @click="showHelpModal = false">开始使用</button>
      </div>
    </div>
  </div>

  <div v-if="showValidateModal" class="modal-overlay" @click.self="showValidateModal = false">
    <div class="modal-content" style="width: 660px; max-height: 80vh; overflow-y: auto;">
      <span class="modal-close" @click="showValidateModal = false">&times;</span>
      <h3 style="margin-top: 0;"><i class="fas fa-magnifying-glass-chart"></i> AI 模型校验</h3>

      <template v-if="validating">
        <p style="color:#666;"><i class="fas fa-spinner fa-spin"></i> 正在校验模型，AI 语义分析可能需要几秒钟...</p>
      </template>

      <template v-else-if="validateError">
        <div style="color:#d33; padding: 10px; background:#fdf0f0; border-radius:8px;">
          <i class="fas fa-exclamation-triangle"></i> {{ validateError }}
        </div>
        <p style="color:#999; font-size:12px;">提示：校验需要登录项目所属账号；AI 语义分析需在 AI 设置中配置密钥后启用。</p>
      </template>

      <template v-else-if="validateResult">
        <div style="margin-bottom: 12px;">
          <span :style="{ padding:'3px 10px', borderRadius:'12px', color:'#fff', background: validateResult.valid ? '#52c41a' : '#f5222d' }">
            {{ validateResult.valid ? '✓ 结构通过' : '✗ 存在问题' }}
          </span>
          <span style="color:#666; margin-left:8px;">{{ validateResult.report }}</span>
        </div>

        <div v-if="validateResult.errors && validateResult.errors.length" class="validate-section">
          <h4 style="color:#f5222d; margin-bottom:6px;"><i class="fas fa-times-circle"></i> 错误（{{ validateResult.errors.length }}）</h4>
          <ul class="validate-list">
            <li v-for="(err, i) in validateResult.errors" :key="i" style="color:#f5222d;">
              {{ err.message }}<span v-if="err.element_name" style="color:#999;">（元素：{{ err.element_name }}）</span>
            </li>
          </ul>
        </div>

        <div v-if="validateResult.warnings && validateResult.warnings.length" class="validate-section">
          <h4 style="color:#e6a23c; margin-bottom:6px;"><i class="fas fa-exclamation-triangle"></i> 警告（{{ validateResult.warnings.length }}）</h4>
          <ul class="validate-list">
            <li v-for="(w, i) in validateResult.warnings" :key="i" style="color:#555;">
              <span :style="{ color: w.type === 'semantic' ? '#7d3fc1' : '#e6a23c' }">
                <i v-if="w.type === 'semantic'" class="fas fa-robot"></i> {{ w.message }}
              </span>
              <div v-if="w.suggestion" style="color:#999; font-size:12px; margin-left:16px;">建议：{{ w.suggestion }}</div>
            </li>
          </ul>
        </div>

        <div v-if="validateResult.suggestions && validateResult.suggestions.length" class="validate-section">
          <h4 style="color:#409eff; margin-bottom:6px;"><i class="fas fa-lightbulb"></i> 建议（{{ validateResult.suggestions.length }}）</h4>
          <ul class="validate-list">
            <li v-for="(s, i) in validateResult.suggestions" :key="i" style="color:#555;">{{ s }}</li>
          </ul>
        </div>

        <div v-if="validateResult.ai_analysis && validateResult.ai_analysis.summary" class="validate-section" style="background:#f5f0ff; border-radius:8px; padding:12px; margin-top:16px;">
          <h4 style="color:#7d3fc1; margin:0 0 6px 0;"><i class="fas fa-robot"></i> AI 语义分析</h4>
          <p style="color:#444; margin:0;">{{ validateResult.ai_analysis.summary }}</p>
        </div>
      </template>

      <div style="margin-top:20px; text-align:right;">
        <button class="btn btn-outline" @click="showValidateModal = false">关闭</button>
      </div>
    </div>
  </div>

  <div v-if="showReviewModal" class="modal-overlay" @click.self="showReviewModal = false">
    <div class="modal-content" style="width: 660px; max-height: 80vh; overflow-y: auto;">
      <span class="modal-close" @click="showReviewModal = false">&times;</span>
      <h3 style="margin-top: 0;"><i class="fas fa-magnifying-glass-chart"></i> AI 架构评审（ArchiMate）</h3>

      <template v-if="reviewing">
        <p style="color:#666;"><i class="fas fa-spinner fa-spin"></i> 正在评审模型，AI 语义分析可能需要几秒钟...</p>
      </template>

      <template v-else-if="reviewError">
        <div style="color:#d33; padding: 10px; background:#fdf0f0; border-radius:8px;">
          <i class="fas fa-exclamation-triangle"></i> {{ reviewError }}
        </div>
        <p style="color:#999; font-size:12px;">提示：评审需要登录项目所属账号；AI 语义分析需在 AI 设置中配置密钥后启用。</p>
      </template>

      <template v-else-if="reviewResult">
        <div style="margin-bottom: 12px;">
          <span :style="{ padding:'3px 10px', borderRadius:'12px', color:'#fff', background: reviewResult.valid ? '#52c41a' : '#f5222d' }">
            {{ reviewResult.valid ? '✓ 结构通过' : '✗ 存在问题' }}
          </span>
          <span style="color:#666; margin-left:8px;">{{ reviewResult.report }}</span>
        </div>

        <div v-if="reviewResult.errors && reviewResult.errors.length" class="validate-section">
          <h4 style="color:#f5222d; margin-bottom:6px;"><i class="fas fa-times-circle"></i> 错误（{{ reviewResult.errors.length }}）</h4>
          <ul class="validate-list">
            <li v-for="(err, i) in reviewResult.errors" :key="i" style="color:#f5222d;">
              {{ err.message }}<span v-if="err.element_name" style="color:#999;">（元素：{{ err.element_name }}）</span>
            </li>
          </ul>
        </div>

        <div v-if="reviewResult.warnings && reviewResult.warnings.length" class="validate-section">
          <h4 style="color:#e6a23c; margin-bottom:6px;"><i class="fas fa-exclamation-triangle"></i> 警告（{{ reviewResult.warnings.length }}）</h4>
          <ul class="validate-list">
            <li v-for="(w, i) in reviewResult.warnings" :key="i" style="color:#555;">
              <span :style="{ color: w.type === 'semantic' ? '#7d3fc1' : '#e6a23c' }">
                <i v-if="w.type === 'semantic'" class="fas fa-robot"></i> {{ w.message }}
              </span>
              <div v-if="w.suggestion" style="color:#999; font-size:12px; margin-left:16px;">建议：{{ w.suggestion }}</div>
            </li>
          </ul>
        </div>

        <div v-if="reviewResult.suggestions && reviewResult.suggestions.length" class="validate-section">
          <h4 style="color:#409eff; margin-bottom:6px;"><i class="fas fa-lightbulb"></i> 建议（{{ reviewResult.suggestions.length }}）</h4>
          <ul class="validate-list">
            <li v-for="(s, i) in reviewResult.suggestions" :key="i" style="color:#555;">{{ s }}</li>
          </ul>
        </div>

        <div v-if="reviewResult.ai_analysis && reviewResult.ai_analysis.summary" class="validate-section" style="background:#f5f0ff; border-radius:8px; padding:12px; margin-top:16px;">
          <h4 style="color:#7d3fc1; margin:0 0 6px 0;"><i class="fas fa-robot"></i> AI 语义分析</h4>
          <p style="color:#444; margin:0;">{{ reviewResult.ai_analysis.summary }}</p>
        </div>
      </template>

      <div style="margin-top:20px; text-align:right;">
        <button class="btn btn-outline" @click="showReviewModal = false">关闭</button>
      </div>
    </div>
  </div>

  <div v-if="showAnalyzeModal" class="modal-overlay" @click.self="showAnalyzeModal = false">
    <div class="modal-content" style="width: 620px; max-height: 80vh; overflow-y: auto;">
      <span class="modal-close" @click="showAnalyzeModal = false">&times;</span>
      <h3 style="margin-top: 0;"><i class="fas fa-wand-magic-sparkles"></i> AI 元素分析</h3>

      <template v-if="analyzing">
        <p style="color:#666;"><i class="fas fa-spinner fa-spin"></i> 正在分析元素，AI 语义分析可能需要几秒钟...</p>
      </template>

      <template v-else-if="analyzeError">
        <div style="color:#d33; padding: 10px; background:#fdf0f0; border-radius:8px;">
          <i class="fas fa-exclamation-triangle"></i> {{ analyzeError }}
        </div>
        <p style="color:#999; font-size:12px;">提示：分析需要登录项目所属账号；AI 语义分析需在 AI 设置中配置密钥后启用。</p>
      </template>

      <template v-else-if="analyzeResult">
        <div style="margin-bottom: 12px; padding: 10px 12px; background:#f0f4ff; border-radius:8px;">
          <strong>{{ analyzeResult.name }}</strong>
          <span style="color:#666; margin-left:8px; font-size:12px;">{{ analyzeResult.type }}<template v-if="analyzeResult.layer"> · {{ analyzeResult.layer }}</template></span>
        </div>

        <div v-if="analyzeResult.summary" class="validate-section" style="background:#f5f0ff; border-radius:8px; padding:12px;">
          <h4 style="color:#7d3fc1; margin:0 0 6px 0;"><i class="fas fa-robot"></i> 总体评价</h4>
          <p style="color:#444; margin:0;">{{ analyzeResult.summary }}</p>
        </div>

        <div v-if="analyzeResult.strengths && analyzeResult.strengths.length" class="validate-section">
          <h4 style="color:#52c41a; margin-bottom:6px;"><i class="fas fa-thumbs-up"></i> 优点（{{ analyzeResult.strengths.length }}）</h4>
          <ul class="validate-list">
            <li v-for="(s, i) in analyzeResult.strengths" :key="i" style="color:#555;">{{ s }}</li>
          </ul>
        </div>

        <div v-if="analyzeResult.issues && analyzeResult.issues.length" class="validate-section">
          <h4 style="color:#e6a23c; margin-bottom:6px;"><i class="fas fa-exclamation-triangle"></i> 问题与风险（{{ analyzeResult.issues.length }}）</h4>
          <ul class="validate-list">
            <li v-for="(iss, i) in analyzeResult.issues" :key="i" style="color:#555;">
              <span :style="{ color: iss.severity === 'error' ? '#f5222d' : iss.severity === 'warning' ? '#e6a23c' : '#7d3fc1' }">
                <i class="fas fa-circle-info" style="margin-right:4px;"></i>{{ iss.message }}
              </span>
              <div v-if="iss.suggestion" style="color:#999; font-size:12px; margin-left:16px;">建议：{{ iss.suggestion }}</div>
            </li>
          </ul>
        </div>

        <div v-if="analyzeResult.suggestions && analyzeResult.suggestions.length" class="validate-section">
          <h4 style="color:#409eff; margin-bottom:6px;"><i class="fas fa-lightbulb"></i> 改进建议（{{ analyzeResult.suggestions.length }}）</h4>
          <ul class="validate-list">
            <li v-for="(s, i) in analyzeResult.suggestions" :key="i" style="color:#555;">{{ s }}</li>
          </ul>
        </div>
      </template>

      <div style="margin-top:20px; text-align:right;">
        <button class="btn btn-outline" @click="showAnalyzeModal = false">关闭</button>
      </div>
    </div>
  </div>

  <div v-if="showEditModelModal" class="modal-overlay" @click.self="showEditModelModal = false">
    <div class="modal-content" style="width: 560px;">
      <span class="modal-close" @click="showEditModelModal = false">&times;</span>
      <h3 style="margin-top: 0;"><i class="fas fa-comment-dots"></i> AI 对话式编辑</h3>
      <p style="color:#666; font-size:13px; margin-bottom:12px;">
        当前编辑：<strong>{{ editingModelKind === 'uml' ? 'UML 类图' : editingModelKind === 'archimate' ? 'ArchiMate 架构' : 'ER 数据模型' }}</strong>。
        用自然语言描述你要的修改，例如「给 Order 类加一个 status 字段」「把客户表和订单表改成一对多关系」「给订单流程加一个消息队列节点」。
      </p>
      <textarea
        v-model="editModelInstruction"
        rows="4"
        placeholder="例如：给 Order 类加个 status 字段，并把 User 和 Order 之间的关系改成 Composition"
        style="width:100%; padding:12px; border:1px solid #ddd; border-radius:8px; font-size:14px; resize:vertical; font-family:inherit;"
      ></textarea>
      <div v-if="editModelError" style="margin-top:10px; color:#d33; background:#fdf0f0; padding:10px; border-radius:8px;">
        <i class="fas fa-exclamation-triangle"></i> {{ editModelError }}
      </div>
      <div v-if="editModelSuccess" style="margin-top:10px; color:#2e7d32; background:#e8f5e9; padding:10px; border-radius:8px;">
        <i class="fas fa-check-circle"></i> {{ editModelSuccess }}
      </div>
      <div style="display:flex; justify-content:flex-end; gap:10px; margin-top:16px;">
        <button class="btn btn-outline" @click="showEditModelModal = false">关闭</button>
        <button class="btn btn-primary" @click="submitAiEditModel" :disabled="editModelSubmitting || !editModelInstruction.trim()">
          <i v-if="editModelSubmitting" class="fas fa-spinner fa-spin"></i>
          {{ editModelSubmitting ? '执行中...' : '执行修改' }}
        </button>
      </div>
    </div>
  </div>

  <div v-if="showCreateModal" class="modal-overlay" @click.self="showCreateModal = false">
    <div class="modal-content">
      <span class="modal-close" @click="showCreateModal = false">&times;</span>
      <h3 style="margin-bottom: 20px;">创建新项目</h3>
      <div class="form-group">
        <label>项目名称</label>
        <input v-model="newModel.name" placeholder="请输入项目名称" />
      </div>
      <div class="form-group">
        <label>项目描述</label>
        <textarea v-model="newModel.description" placeholder="请输入项目描述"></textarea>
      </div>
      <div style="display: flex; justify-content: flex-end; gap: 10px;">
        <button class="btn btn-outline" @click="showCreateModal = false">取消</button>
        <button class="btn btn-primary" @click="createModel">创建</button>
      </div>
    </div>
  </div>

  <div v-if="showEditModal" class="modal-overlay" @click.self="showEditModal = false">
    <div class="modal-content">
      <span class="modal-close" @click="showEditModal = false">&times;</span>
      <h3 style="margin-bottom: 20px;">编辑元素</h3>
      <div class="form-group">
        <label>元素名称</label>
        <input v-model="editingElement.name" placeholder="请输入元素名称" />
      </div>
      <div class="form-group">
        <label>属性列表</label>
        <div v-for="(_, index) in editingElement.attributes" :key="index" class="attr-row">
          <input v-model="editingElement.attributes[index]" />
          <button class="btn-delete" style="margin-left: 8px;" @click="removeAttribute(index)">
            <i class="fas fa-times"></i>
          </button>
        </div>
        <button class="btn btn-outline" style="margin-top: 10px;" @click="addAttribute">
          <i class="fas fa-plus"></i> 添加属性
        </button>
      </div>
      <div style="display: flex; justify-content: flex-end; gap: 10px;">
        <button class="btn btn-outline" @click="showEditModal = false">取消</button>
        <button class="btn btn-primary" @click="saveEdit">保存</button>
      </div>
    </div>
  </div>

  <!-- ArchiMate 编辑模态框 -->
  <div v-if="showArchimateEditModal" class="modal-overlay" @click.self="showArchimateEditModal = false">
    <div class="modal-content">
      <span class="modal-close" @click="showArchimateEditModal = false">&times;</span>
      <h3 style="margin-bottom: 20px;">编辑 ArchiMate 元素</h3>
      <div class="form-group">
        <label>元素类型</label>
        <input :value="archimateEditingElement.type" disabled style="background: #f0f0f0;" />
      </div>
      <div class="form-group">
        <label>元素名称</label>
        <input v-model="archimateEditingElement.name" placeholder="请输入元素名称" />
      </div>
      <div class="form-group">
        <label>所属层次</label>
        <select v-model="archimateEditingElement.layer" style="width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px;">
          <option value="business">业务层</option>
          <option value="application">应用层</option>
          <option value="technology">技术层</option>
        </select>
      </div>
      <div style="display: flex; justify-content: flex-end; gap: 10px;">
        <button class="btn btn-outline" @click="showArchimateEditModal = false">取消</button>
        <button class="btn btn-primary" @click="saveArchimateEdit">保存</button>
      </div>
    </div>
  </div>

  <!-- ER图编辑模态框 -->
  <div v-if="showErEditModal" class="modal-overlay" @click.self="showErEditModal = false">
    <div class="modal-content" style="width: 500px; max-height: 80vh; overflow-y: auto;">
      <span class="modal-close" @click="showErEditModal = false">&times;</span>
      <h3 style="margin-bottom: 20px;">编辑数据表</h3>
      <div class="form-group">
        <label>表名</label>
        <input v-model="erEditingEntity.name" placeholder="请输入表名" />
      </div>
      <div class="form-group">
        <label>字段列表</label>
        <div v-for="(field, index) in erEditingEntity.fields" :key="index" class="er-field-row">
          <div style="flex: 1;">
            <input v-model="field.name" placeholder="字段名" style="margin-bottom: 5px;" />
            <select v-model="field.type" style="width: 100%; padding: 6px; border: 1px solid #ddd; border-radius: 4px;">
              <option value="INT">INT</option>
              <option value="BIGINT">BIGINT</option>
              <option value="VARCHAR(255)">VARCHAR(255)</option>
              <option value="VARCHAR(100)">VARCHAR(100)</option>
              <option value="TEXT">TEXT</option>
              <option value="DATETIME">DATETIME</option>
              <option value="DATE">DATE</option>
              <option value="BOOLEAN">BOOLEAN</option>
              <option value="DECIMAL(10,2)">DECIMAL(10,2)</option>
              <option value="JSON">JSON</option>
            </select>
          </div>
          <div style="display: flex; flex-direction: column; gap: 5px; margin-left: 10px;">
            <label style="display: flex; align-items: center; font-size: 12px; cursor: pointer;">
              <input type="checkbox" v-model="field.isPrimary" style="margin-right: 5px;" />
              主键
            </label>
            <label style="display: flex; align-items: center; font-size: 12px; cursor: pointer;">
              <input type="checkbox" v-model="field.isForeign" style="margin-right: 5px;" />
              外键
            </label>
          </div>
          <button class="btn-delete" style="margin-left: 10px; align-self: flex-start;" @click="removeErField(index)" v-if="erEditingEntity.fields.length > 1">
            <i class="fas fa-times"></i>
          </button>
        </div>
        <button class="btn btn-outline" style="margin-top: 10px;" @click="addErField">
          <i class="fas fa-plus"></i> 添加字段
        </button>
      </div>
      <div style="display: flex; justify-content: flex-end; gap: 10px;">
        <button class="btn btn-outline" @click="showErEditModal = false">取消</button>
        <button class="btn btn-primary" @click="saveErEdit">保存</button>
      </div>
    </div>
  </div>

  <!-- 研发管理：新增/编辑表单弹窗 -->
  <div v-if="showDevModal" class="modal-overlay" @click.self="showDevModal = false">
    <div class="modal-content">
      <span class="modal-close" @click="showDevModal = false">&times;</span>
      <h3 style="margin-bottom:16px;">{{ editingDev ? '编辑' : '新增' }}{{ devTabs.find(t => t.id === activeDevTab)?.name }}</h3>
      <div class="form-group" v-for="f in DEV_FIELDS[activeDevTab]" :key="f.key">
        <label>{{ f.label }}</label>
        <input v-model="devForm[f.key]" :placeholder="f.label" />
      </div>
      <div style="display:flex; justify-content:flex-end; gap:10px; margin-top:16px;">
        <button class="btn btn-outline" @click="showDevModal = false">取消</button>
        <button class="btn btn-primary" @click="saveDev">保存</button>
      </div>
    </div>
  </div>

  <!-- 研发管理：AI 生成弹窗（需求用描述文本；测试/任务需选择关联需求） -->
  <div v-if="showDevAiModal" class="modal-overlay" @click.self="showDevAiModal = false">
    <div class="modal-content" style="width: 560px;">
      <span class="modal-close" @click="showDevAiModal = false">&times;</span>
      <h3 style="margin-bottom:12px;"><i class="fas fa-wand-magic-sparkles"></i> AI 生成{{ devTabs.find(t => t.id === activeDevTab)?.name }}</h3>

      <div class="form-group" v-if="activeDevTab === 'testcase'">
        <label>关联需求</label>
        <select v-model="devAiReqId" style="width:100%; padding:8px; border:1px solid #ddd; border-radius:8px; font-size:14px;">
          <option value="">请选择需求</option>
          <option v-for="r in devReqOptions" :key="r.id" :value="r.id">{{ r.name || r.id }}</option>
        </select>
        <p v-if="!devReqOptions.length" style="color:#999; font-size:12px; margin-top:6px;">暂无需求可选，请先到「需求」页创建需求。</p>
      </div>

      <div class="form-group" v-if="activeDevTab === 'task'">
        <label>关联需求（可多选）</label>
        <div style="border:1px solid #ddd; border-radius:8px; padding:10px; max-height:180px; overflow-y:auto;">
          <label v-for="r in devReqOptions" :key="r.id" style="display:flex; align-items:center; gap:8px; padding:4px 0; font-size:14px; cursor:pointer;">
            <input type="checkbox" :value="r.id" v-model="devAiReqIds" /> {{ r.name || r.id }}
          </label>
          <p v-if="!devReqOptions.length" style="color:#999; font-size:12px; margin:0;">暂无需求可选，请先到「需求」页创建需求。</p>
        </div>
      </div>

      <div class="form-group" v-if="activeDevTab === 'requirement' || activeDevTab === 'testcase'">
        <label>{{ activeDevTab === 'requirement' ? '业务描述' : '测试要点 / 需求内容' }}</label>
        <textarea v-model="devAiText" rows="6" placeholder="输入业务描述 / 需求内容，AI 将拆分生成条目…"
          style="width:100%; padding:12px; border:1px solid #ddd; border-radius:8px; font-size:14px; resize:vertical; font-family:inherit;"></textarea>
      </div>
      <p v-if="activeDevTab === 'task'" style="color:#666; font-size:12px; margin-top:4px;">选择要拆分任务的需求，AI 将按需求生成计划任务。</p>

      <div v-if="devError" style="color:#d33; background:#fdf0f0; padding:10px; border-radius:8px; margin-top:4px;">
        <i class="fas fa-exclamation-triangle"></i> {{ devError }}
      </div>

      <div style="display:flex; justify-content:flex-end; gap:10px; margin-top:16px;">
        <button class="btn btn-outline" @click="showDevAiModal = false">取消</button>
        <button class="btn btn-primary" @click="generateDevAi" :disabled="devAiGenerating || !canGenerateDevAi">
          <i v-if="devAiGenerating" class="fas fa-spinner fa-spin"></i> {{ devAiGenerating ? '生成中...' : '生成' }}
        </button>
      </div>
    </div>
  </div>

  <!-- AI 从描述生成图 -->
  <div v-if="showGenDiagramModal" class="modal-overlay" @click.self="showGenDiagramModal = false">
    <div class="modal-content" style="width: 560px;">
      <span class="modal-close" @click="showGenDiagramModal = false">&times;</span>
      <h3 style="margin-bottom:12px;"><i class="fas fa-wand-magic-sparkles" style="color:#1f5eff;"></i> AI 从描述生成{{ genDiagramKind === 'uml' ? 'UML' : 'ER' }}图</h3>

      <div class="form-group" v-if="genDiagramKind === 'uml'">
        <label>图表类型</label>
        <select v-model="genDiagramViewType" style="width:100%; padding:8px; border:1px solid #ddd; border-radius:8px; font-size:14px;">
          <option value="class">类图</option>
          <option value="use_case">用例图</option>
          <option value="activity">活动图</option>
          <option value="sequence">时序图</option>
        </select>
      </div>

      <div class="form-group">
        <label>业务描述</label>
        <textarea v-model="genDiagramText" rows="6"
          placeholder="用自然语言描述你的系统，例如：设计一个图书管理系统，有图书、读者、借阅记录，读者可以借阅和归还图书…"
          style="width:100%; padding:12px; border:1px solid #ddd; border-radius:8px; font-size:14px; resize:vertical; font-family:inherit;"></textarea>
      </div>

      <div v-if="genDiagramError" style="color:#d33; background:#fdf0f0; padding:10px; border-radius:8px; margin-top:4px;">
        <i class="fas fa-exclamation-triangle"></i> {{ genDiagramError }}
      </div>

      <div style="display:flex; justify-content:flex-end; gap:10px; margin-top:16px;">
        <button class="btn btn-outline" @click="showGenDiagramModal = false">取消</button>
        <button class="btn btn-primary" @click="generateDiagram" :disabled="genDiagramLoading || !genDiagramText.trim()">
          <i v-if="genDiagramLoading" class="fas fa-spinner fa-spin"></i> {{ genDiagramLoading ? '生成中...' : '生成' }}
        </button>
      </div>
    </div>
  </div>

  <!-- 后台管理：新增/编辑用户 -->
  <div v-if="showAdminUserModal" class="modal-overlay" @click.self="showAdminUserModal = false">
    <div class="modal-content" style="width: 480px;">
      <span class="modal-close" @click="showAdminUserModal = false">&times;</span>
      <h3 style="margin-bottom:16px;">{{ editingAdminUser ? '编辑用户' : '新增用户' }}</h3>
      <div class="form-group" v-if="!editingAdminUser">
        <label>用户名</label>
        <input v-model="adminUserForm.username" placeholder="请输入用户名" />
      </div>
      <div class="form-group">
        <label>邮箱</label>
        <input v-model="adminUserForm.email" placeholder="name@example.com" />
      </div>
      <div class="form-group">
        <label>{{ editingAdminUser ? '新密码（留空不修改）' : '密码' }}</label>
        <input v-model="adminUserForm.password" type="password" :placeholder="editingAdminUser ? '留空则不修改' : '请输入密码'" />
      </div>
      <div class="form-group">
        <label>角色</label>
        <select v-model="adminUserForm.role" style="width:100%; padding:8px; border:1px solid #ddd; border-radius:8px; font-size:14px;">
          <option value="user">普通用户</option>
          <option value="admin">管理员</option>
        </select>
      </div>
      <div v-if="adminError" style="color:#d33; background:#fdf0f0; padding:10px; border-radius:8px; margin-bottom:8px;">
        <i class="fas fa-exclamation-triangle"></i> {{ adminError }}
      </div>
      <div style="display:flex; justify-content:flex-end; gap:10px; margin-top:16px;">
        <button class="btn btn-outline" @click="showAdminUserModal = false">取消</button>
        <button class="btn btn-primary" @click="saveAdminUser">保存</button>
      </div>
    </div>
  </div>

  <!-- 后台管理：查看用户项目 -->
  <div v-if="showAdminProjectsModal" class="modal-overlay" @click.self="showAdminProjectsModal = false">
    <div class="modal-content" style="width: 640px; max-height: 80vh; overflow-y: auto;">
      <span class="modal-close" @click="showAdminProjectsModal = false">&times;</span>
      <h3 style="margin-bottom:12px;">用户「{{ viewingAdminUser?.username }}」的项目（{{ adminProjects.length }}）</h3>
      <table class="table" v-if="adminProjects.length">
        <thead>
          <tr>
            <th>名称</th>
            <th>描述</th>
            <th>可见性</th>
            <th style="width:80px;">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="p in adminProjects" :key="p.id">
            <td>{{ p.name }}</td>
            <td>{{ p.description || '-' }}</td>
            <td>{{ p.visibility || 'private' }}</td>
            <td><button class="btn-delete" @click="removeAdminProject(p)"><i class="fas fa-trash"></i></button></td>
          </tr>
        </tbody>
      </table>
      <p v-else style="color:#999;">该用户暂无项目。</p>
      <div style="margin-top:16px; text-align:right;">
        <button class="btn btn-outline" @click="showAdminProjectsModal = false">关闭</button>
      </div>
    </div>
  </div>

  <!-- 引导式使用教学（根层，覆盖全站） -->
  <div v-if="showTour">
    <div class="tour-overlay" @click="nextTourStep"></div>
    <div class="tour-highlight" :style="tourHighlightStyle"></div>
    <div class="tour-tooltip">
      <div class="tour-progress">
        <div class="tour-progress-bar" :style="{ width: ((tourStep + 1) / tourSteps.length) * 100 + '%' }"></div>
      </div>
      <h4 style="margin: 12px 0 8px; flex-shrink:0;"><i class="fas fa-compass" style="color:#1f5eff; margin-right:6px;"></i>{{ currentTourStep.title }}</h4>
      <div class="tour-desc">{{ currentTourStep.desc }}</div>
      <div class="tour-footer">
        <span style="font-size:12px; color:#8b98ab;">{{ tourStep + 1 }} / {{ tourSteps.length }}</span>
        <div style="display:flex; gap:8px;">
          <button v-if="tourStep > 0" class="btn btn-outline" @click="prevTourStep">上一步</button>
          <button class="btn btn-outline" @click="skipTour">跳过</button>
          <button v-if="!isLastTourStep" class="btn btn-primary" @click="nextTourStep">下一步</button>
          <button v-else class="btn btn-primary" @click="finishTour">开始探索</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style>
.app-loading {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  font-size: 15px;
  color: var(--muted);
}
.app-loading i {
  color: var(--brand);
}

.container {
  position: relative;
  /* 不能设 z-index：会创建层叠上下文，把内部 AI 下拉(z-index:1000)封在容器(z-index:1)里，
     被根层 .ai-menu-overlay(z-index:900) 盖住 → 菜单点了没反应 */
  max-width: 1240px;
  margin: 0 auto;
  padding: 20px;
}

/* 顶部导航栏 */
.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 14px 20px;
  box-shadow: var(--shadow-sm);
  margin-bottom: 24px;
  flex-wrap: wrap;
}
.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}
.header-logo {
  width: 42px;
  height: 42px;
  border-radius: 12px;
  background: var(--brand-grad);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 20px;
  box-shadow: 0 6px 16px rgba(31, 94, 255, 0.35);
  flex-shrink: 0;
}
.header-text h1 {
  font-size: 20px;
  font-weight: 700;
  color: var(--text);
  line-height: 1.3;
}
.header-text p {
  font-size: 13px;
  color: var(--muted);
}
.header-right {
  display: flex;
  align-items: center;
  gap: 14px;
}
.user-chip {
  display: flex;
  align-items: center;
  gap: 8px;
}
.user-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: var(--brand-grad);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 600;
}
.user-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-2);
}
.btn-logout {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: #fff;
  color: var(--text-2);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}
.btn-logout:hover {
  background: #fef2f2;
  border-color: #fecaca;
  color: #dc2626;
}

.btn-help {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: #fff;
  color: var(--text-2);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}
.btn-help:hover {
  background: #eef4ff;
  border-color: #1f5eff;
  color: #1f5eff;
}

/* 新手教程弹窗 */
.help-modal {
  width: 640px;
  max-height: 82vh;
  overflow-y: auto;
}
.help-section {
  background: #f8fafc;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px 16px;
  margin-bottom: 12px;
}
.help-section h4 {
  font-size: 14px;
  color: var(--text);
  margin: 0 0 6px 0;
  display: flex;
  align-items: center;
  gap: 6px;
}
.help-section h4 i {
  color: #1f5eff;
  width: 16px;
  text-align: center;
}
.help-section ul, .help-section ol {
  margin: 0;
  padding-left: 20px;
  font-size: 13px;
  color: var(--text-2);
  line-height: 1.8;
}

.stats-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 24px;
}

.stat-card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 18px 16px;
  text-align: center;
  box-shadow: var(--shadow-sm);
  transition: transform 0.2s, box-shadow 0.2s;
}

.stat-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-md);
}

.stat-value {
  font-size: 28px;
  font-weight: 700;
  color: var(--brand);
  margin-bottom: 4px;
}

.stat-label {
  font-size: 13px;
  color: var(--muted);
}

.nav-tabs {
  display: flex;
  gap: 8px;
  margin-bottom: 24px;
  flex-wrap: wrap;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 6px;
  box-shadow: var(--shadow-sm);
}

.nav-tab {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 9px 18px;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  background: transparent;
  color: var(--text-2);
  transition: all 0.2s;
}
.nav-tab i {
  font-size: 13px;
  color: var(--muted);
  transition: color 0.2s;
}
.nav-tab:hover i {
  color: var(--brand);
}

.nav-tab:hover {
  background: #eef1f8;
  color: var(--brand);
}

.nav-tab.active {
  background: var(--brand-grad);
  color: #fff;
  box-shadow: 0 4px 12px rgba(31, 94, 255, 0.35);
}
.nav-tab.active i {
  color: #fff;
}

.ribbon {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 12px;
  background: #f7f8fa;
  border: 1px solid #e8ecf0;
  border-radius: 8px;
  margin: 8px 0;
  flex-wrap: wrap;
}
.ribbon-group {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
}
.ribbon-group + .ribbon-group {
  border-left: 1px solid #dfe3ea;
}
.ribbon-group-label {
  font-size: 11px;
  color: #94a3b8;
  margin-right: 2px;
  white-space: nowrap;
}
.ribbon .toolbar-btn {
  padding: 6px 10px;
  white-space: nowrap;
}

.dashboard-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 20px;
}

.card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 24px;
  box-shadow: var(--shadow-sm);
  transition: box-shadow 0.25s;
}

.card:hover {
  box-shadow: var(--shadow-md);
}

.card-icon {
  width: 60px;
  height: 60px;
  border-radius: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 16px;
  font-size: 28px;
}

.card-title {
  font-size: 18px;
  font-weight: 600;
  color: var(--text);
  margin-bottom: 8px;
}

.card-desc {
  font-size: 14px;
  color: var(--text-2);
  margin-bottom: 16px;
}

.btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 10px 20px;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  transition: all 0.2s;
}

.btn-primary {
  background: var(--brand-grad);
  color: white;
  box-shadow: 0 4px 12px rgba(31, 94, 255, 0.3);
}

.btn-primary:hover {
  opacity: 0.92;
  transform: translateY(-1px);
}

.btn-outline {
  background: transparent;
  border: 1.5px solid var(--brand);
  color: var(--brand);
}

.btn-outline:hover {
  background: var(--brand);
  color: white;
}

.model-list {
  margin-top: 20px;
}

.model-item {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 14px 16px;
  background: var(--glass-bg);
  backdrop-filter: blur(var(--glass-blur)) saturate(var(--glass-saturation));
  -webkit-backdrop-filter: blur(var(--glass-blur)) saturate(var(--glass-saturation));
  border: 1px solid var(--glass-border);
  border-radius: 12px;
  margin-bottom: 10px;
  transition: transform 0.3s var(--spring), box-shadow 0.3s var(--smooth);
}
.model-item:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-md), inset 0 1px 1px rgba(255, 255, 255, 0.5);
}
.model-icon {
  width: 46px;
  height: 46px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 19px;
  font-weight: 700;
  flex-shrink: 0;
  box-shadow: inset 0 1px 1px rgba(255, 255, 255, 0.4), 0 2px 8px rgba(0, 0, 0, 0.12);
}
.model-info {
  flex: 1;
}
.model-info h4 {
  margin-bottom: 4px;
  color: #333;
}

.model-info p {
  font-size: 12px;
  color: #999;
}

.model-actions {
  display: flex;
  gap: 10px;
}

.model-actions button {
  padding: 6px 12px;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 12px;
}

.model-actions .btn-edit {
  background: #e3f2fd;
  color: #1976d2;
}

.model-actions .btn-delete {
  background: #ffebee;
  color: #c62828;
}

.canvas-container {
  background: #f8f9fa;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
  box-shadow: var(--shadow-sm);
}

.canvas-container:hover {
  box-shadow: var(--shadow-md);
}

/* 画布底部状态栏（签名元素：专业软件质感） */
.canvas-statusbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 6px 16px;
  padding: 8px 14px;
  background: #fff;
  border-top: 1px solid var(--border);
  font-size: 12px;
  color: var(--text-2);
}
.status-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
}
.status-item i {
  color: var(--muted);
  width: 14px;
  text-align: center;
}
.status-item strong {
  color: var(--text);
  font-weight: 600;
}
.status-right {
  margin-left: auto;
  color: var(--muted);
}
/* 在线协作 */
.collab-chip {
  color: var(--brand);
}
.collab-avatars {
  display: inline-flex;
  gap: 2px;
}
.collab-avatar {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: var(--brand-grad);
  color: #fff;
  font-size: 10px;
  font-weight: 600;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid #fff;
}
.collab-toast {
  position: fixed;
  top: 16px;
  right: 16px;
  z-index: 9999;
  background: rgba(255, 255, 255, 0.95);
  backdrop-filter: blur(10px);
  border: 1px solid var(--glass-border);
  border-radius: 12px;
  box-shadow: var(--shadow-md);
  padding: 10px 16px;
  font-size: 13px;
  color: var(--text);
  display: flex;
  align-items: center;
  gap: 8px;
  animation: modal-in 0.3s ease;
}
.collab-toast i {
  color: var(--brand);
}
.fade-enter-active, .fade-leave-active {
  transition: opacity 0.25s ease;
}
.fade-enter-from, .fade-leave-to {
  opacity: 0;
}

.toolbar-btn {
  padding: 8px 16px;
  border: 1px solid #e8ecf0;
  background: white;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 6px;
  transition: all 0.2s;
}

.toolbar-btn:hover {
  background: #f5f5f5;
}

.toolbar-btn.active {
  background: #1f5eff;
  color: white;
  border-color: #1f5eff;
}

/* AI 功能下拉菜单 */
.ai-menu-overlay {
  position: fixed;
  inset: 0;
  z-index: 900;
}
.ai-dropdown {
  position: absolute;
  top: calc(100% + 6px);
  left: 0;
  min-width: 200px;
  background: #fff;
  border: 1px solid #e8ecf0;
  border-radius: 8px;
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.12);
  padding: 6px;
  z-index: 1000;
}
.ai-dropdown-title {
  font-size: 11px;
  color: #94a3b8;
  padding: 4px 8px 6px;
  border-bottom: 1px solid #f1f5f9;
  margin-bottom: 4px;
}
.ai-dropdown-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px 10px;
  border: none;
  background: transparent;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  color: #334155;
  text-align: left;
}
.ai-dropdown-item:hover:not(:disabled) {
  background: #f1f5f9;
}
.ai-dropdown-item:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.ai-dropdown-item i {
  width: 16px;
  text-align: center;
  color: #d97706; /* AI 强调色（琥珀） */
}

#canvas {
  display: block;
  cursor: crosshair;
}

/* 三画布随容器等比缩放：逻辑坐标恒为 1150×600，物理尺寸由 setupCanvasTransform 按 DPR 换算 */
#canvas, #archimateCanvas, #erCanvas {
  display: block;
  width: 100%;
  height: auto;
  aspect-ratio: 1150 / 600;
}

.table {
  width: 100%;
  border-collapse: collapse;
  margin-top: 20px;
}

.table th, .table td {
  padding: 12px;
  text-align: left;
  border-bottom: 1px solid #e8ecf0;
}

.table th {
  background: #f8f9fa;
  font-weight: 600;
  color: #666;
}

.badge {
  padding: 4px 12px;
  border-radius: 20px;
  font-size: 12px;
  font-weight: 500;
}

.badge-info {
  background: #e3f2fd;
  color: #1565c0;
}

.badge-success {
  background: #e8f5e9;
  color: #2e7d32;
}

.badge-warning {
  background: #fff3e0;
  color: #e65100;
}

.code-preview {
  background: #2d2d2d;
  color: #f8f8f2;
  padding: 20px;
  border-radius: 10px;
  font-family: 'Monaco', 'Consolas', monospace;
  font-size: 13px;
  overflow-x: auto;
  max-height: 300px;
  overflow-y: auto;
}

.doc-preview {
  background: #fbfcfe;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 20px;
  font-size: 14px;
  color: var(--text);
  line-height: 1.65;
  max-height: 420px;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-word;
}

.ai-chat {
  display: flex;
  flex-direction: column;
  height: 400px;
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 15px;
  background: #f8f9fa;
  border-radius: 8px;
  margin-bottom: 15px;
}

.chat-message {
  margin-bottom: 15px;
}

.chat-message.user {
  text-align: right;
}

.chat-message.bot {
  text-align: left;
}

.chat-bubble {
  display: inline-block;
  padding: 12px 18px;
  border-radius: 20px;
  max-width: 70%;
  font-size: 14px;
}

.user .chat-bubble {
  background: linear-gradient(135deg, #1f5eff 0%, #764ba2 100%);
  color: white;
  border-bottom-right-radius: 5px;
}

.bot .chat-bubble {
  background: white;
  color: #333;
  border-bottom-left-radius: 5px;
  box-shadow: 0 2px 10px rgba(0,0,0,0.05);
}

.chat-input {
  display: flex;
  gap: 10px;
}

.chat-input input {
  flex: 1;
  padding: 12px;
  border: 2px solid #e8ecf0;
  border-radius: 25px;
  font-size: 14px;
}

.chat-input input:focus {
  outline: none;
  border-color: #1f5eff;
}

.chat-input button {
  padding: 12px 24px;
  border: none;
  border-radius: 25px;
  background: linear-gradient(135deg, #1f5eff 0%, #764ba2 100%);
  color: white;
  cursor: pointer;
  font-size: 14px;
}

/* === 液态玻璃应用到关键界面元素（浅色适配）=== */
.header, .nav-tabs, .ribbon, .stat-card, .card:not(.canvas-container), .modal-content {
  position: relative;
  background: var(--glass-bg);
  backdrop-filter: blur(var(--glass-blur)) saturate(var(--glass-saturation));
  -webkit-backdrop-filter: blur(var(--glass-blur)) saturate(var(--glass-saturation));
  border-color: var(--glass-border);
  box-shadow: var(--shadow-sm), inset 0 1px 1px rgba(255, 255, 255, 0.5);
}
/* 画布卡保持实底，保证画布内容清晰 */
.canvas-container {
  background: #fff;
  backdrop-filter: none;
  -webkit-backdrop-filter: none;
  border-color: var(--border);
}
/* 功能区不能有 backdrop-filter：会创建层叠上下文，把内部 z-index:1000 的 AI 下拉
   困在功能区之下，被 z-index:900 的全屏遮罩盖住 → AI 菜单点了没反应 */
.ribbon {
  backdrop-filter: none;
  -webkit-backdrop-filter: none;
}
/* 弹窗内容保持近实心可读（0.3 透玻璃叠在暗遮罩上会看不清表单） */
.modal-content {
  background: rgba(255, 255, 255, 0.94);
}
/* 过渡动画 */
.modal-overlay { animation: fade-in 0.2s ease; }
.modal-content { animation: modal-in 0.3s var(--spring); }
.card { animation: fade-up 0.3s var(--smooth); }
.header { animation: fade-up 0.4s var(--smooth); }
.nav-tabs, .ribbon { animation: fade-up 0.35s var(--smooth); }

.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0,0,0,0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-content {
  background: white;
  border-radius: 16px;
  padding: 30px;
  width: 90%;
  max-width: 500px;
  position: relative;
}

.modal-close {
  position: absolute;
  top: 20px;
  right: 20px;
  font-size: 24px;
  cursor: pointer;
  color: #999;
}

.modal-close:hover {
  color: #333;
}

.validate-section {
  margin-top: 14px;
}

.validate-list {
  margin: 0;
  padding-left: 20px;
  line-height: 1.7;
}

.validate-list li {
  margin-bottom: 4px;
}

.form-group {
  margin-bottom: 20px;
}

.form-group label {
  display: block;
  margin-bottom: 8px;
  font-weight: 500;
  color: #333;
}

.form-group input, .form-group textarea {
  width: 100%;
  padding: 12px;
  border: 2px solid #e8ecf0;
  border-radius: 8px;
  font-size: 14px;
  transition: border-color 0.3s;
}

.form-group input:focus, .form-group textarea:focus {
  outline: none;
  border-color: #1f5eff;
}

.form-group textarea {
  resize: vertical;
  min-height: 100px;
}

.attr-row {
  display: flex;
  align-items: center;
  margin-bottom: 8px;
}

.attr-row input {
  flex: 1;
}

.er-field-row {
  display: flex;
  align-items: flex-start;
  margin-bottom: 10px;
  padding: 10px;
  background: #f8f9fa;
  border-radius: 4px;
}

/* === 引导式使用教学（tour）=== */
.tour-overlay {
  position: fixed;
  inset: 0;
  z-index: 9988;
  background: transparent;
  cursor: pointer;
}
.tour-highlight {
  position: fixed;
  z-index: 9990;
  border-radius: 14px;
  border: 2px solid #1f5eff;
  box-shadow: 0 0 0 9999px rgba(15, 23, 42, 0.5);
  pointer-events: none;
  transition: left 0.35s cubic-bezier(0.25, 0.46, 0.45, 0.94),
    top 0.35s cubic-bezier(0.25, 0.46, 0.45, 0.94),
    width 0.35s cubic-bezier(0.25, 0.46, 0.45, 0.94),
    height 0.35s cubic-bezier(0.25, 0.46, 0.45, 0.94);
}
.tour-tooltip {
  position: fixed;
  z-index: 9995;
  bottom: 24px;
  left: 50%;
  transform: translateX(-50%);
  width: 440px;
  max-width: calc(100vw - 24px);
  max-height: calc(100vh - 48px);
  display: flex;
  flex-direction: column;
  background: rgba(255, 255, 255, 0.94);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
  border: 1px solid rgba(255, 255, 255, 0.6);
  border-radius: 16px;
  box-shadow: 0 12px 40px rgba(15, 23, 42, 0.18);
  padding: 14px 20px 16px;
  animation: modal-in 0.3s ease;
}
.tour-desc {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  color: #5b6b82;
  font-size: 14px;
  line-height: 1.7;
  margin: 0;
}
.tour-footer {
  flex-shrink: 0;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px solid #e3e9f2;
}
.tour-progress {
  height: 4px;
  background: #e3e9f2;
  border-radius: 2px;
  overflow: hidden;
  flex-shrink: 0;
}
.tour-progress-bar {
  height: 100%;
  background: linear-gradient(90deg, #1f5eff, #8b5cf6);
  border-radius: 2px;
  transition: width 0.3s cubic-bezier(0.25, 0.46, 0.45, 0.94);
}

</style>
