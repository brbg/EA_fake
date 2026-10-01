// AI 智能体（一键企业架构设计 Agent）服务：调 /architect/stream SSE，逐步回调事件
export interface AgentStepView {
  key: string
  title: string
  status: 'pending' | 'running' | 'ok' | 'error' | 'skipped'
  detail?: any
}
export interface AgentDoneResult {
  project_id: string
  project_name: string
  generated: any
  health: any
  optimization: any
  action_log: Array<{ step: string; title: string; status: string; ok: boolean; detail?: any }>
  chat_summary: string
}
export interface AgentEvent {
  type: string
  step?: string
  status?: string
  title?: string
  detail?: any
  project_id?: string
  project_name?: string
  /** 工具结果里携带的「当前绑定项目」信息（智能体新建/绑定项目时透传） */
  project?: { project_id: string; project_name: string } | null
  error?: string
  result?: AgentDoneResult
}

const AUTH = () => ({
  'Content-Type': 'application/json',
  'X-Session-Id': sessionStorage.getItem('sessionId') || ''
})

export async function runAgentStream(
  body: { text: string; apply_optimization?: boolean },
  onEvent: (e: AgentEvent) => void
): Promise<AgentDoneResult | null> {
  return streamAgentFetch('/api/v1/ai/agent/architect/stream',
    { apply_optimization: body.apply_optimization !== false, text: body.text }, onEvent)
}

// 智能体工具调用循环（Phase2）：LLM 自主决定调用哪些工具操作当前项目
export async function runAgentChat(
  projectId: string,
  message: string,
  memories: string[],
  onEvent: (e: AgentEvent) => void
): Promise<void> {
  // 历史对话由后端按项目保存/注入（上限 512K），前端只传本轮消息
  await streamAgentFetch('/api/v1/ai/agent/run', { project_id: projectId, message, memories }, onEvent)
}

// 取某项目的历史对话（点击项目时恢复）
export async function fetchAgentHistory(projectId: string): Promise<Array<{ role: string; content: string; ts?: string }>> {
  if (!projectId) return []
  try {
    const r = await fetch(`/api/v1/ai/agent/history?project_id=${encodeURIComponent(projectId)}`, { headers: AUTH() })
    if (!r.ok) return []
    const d = await r.json()
    return Array.isArray(d?.messages) ? d.messages : []
  } catch {
    return []
  }
}

// 清空某项目的历史对话
export async function clearAgentHistory(projectId: string): Promise<void> {
  if (!projectId) return
  try {
    await fetch(`/api/v1/ai/agent/history?project_id=${encodeURIComponent(projectId)}`, { method: 'DELETE', headers: AUTH() })
  } catch { /* 忽略 */ }
}

async function streamAgentFetch(url: string, body: unknown, onEvent: (e: AgentEvent) => void): Promise<AgentDoneResult | null> {
  const resp = await fetch(url, { method: 'POST', headers: AUTH(), body: JSON.stringify(body) })
  if (!resp.ok) {
    const d = await resp.json().catch(() => ({}))
    throw new Error(d?.error || 'Agent 执行失败')
  }
  const reader = resp.body?.getReader()
  const decoder = new TextDecoder()
  if (!reader) throw new Error('无法读取响应流')
  let done: AgentDoneResult | null = null
  let buf = ''
  while (true) {
    const { done: d, value } = await reader.read()
    if (d) break
    buf += decoder.decode(value, { stream: true })
    let idx
    while ((idx = buf.indexOf('\n')) >= 0) {
      const line = buf.slice(0, idx).trim()
      buf = buf.slice(idx + 1)
      if (!line.startsWith('data: ')) continue
      const raw = line.slice(6).trim()
      if (raw === '[DONE]') continue
      try {
        const ev = JSON.parse(raw) as AgentEvent
        onEvent(ev)
        if (ev.type === 'done' && ev.result) done = ev.result
      } catch { /* 忽略坏行 */ }
    }
  }
  return done
}
