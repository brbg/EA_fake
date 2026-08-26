// 统一请求封装：自动带会话头、解析 JSON、保留 {ok,status,data} 便于调用方错误处理。
// 借鉴 AI_EA_Web 的 api/request 分层，去掉重复的 fetch + X-Session-Id 样板。

export interface ApiResp<T = any> {
  ok: boolean
  status: number
  data: T | null
}

const sessionHeader = () => ({ 'X-Session-Id': sessionStorage.getItem('sessionId') || '' })

export async function request<T = any>(
  url: string,
  options: { method?: string; body?: unknown } = {}
): Promise<ApiResp<T>> {
  let res: Response
  try {
    res = await fetch(url, {
      method: options.method || 'GET',
      headers: {
        'Content-Type': 'application/json',
        ...sessionHeader()
      },
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined
    })
  } catch (e) {
    return { ok: false, status: 0, data: null }
  }
  let data: T | null = null
  try {
    data = await res.json()
  } catch {
    data = null
  }
  return { ok: res.ok, status: res.status, data }
}

export const get = <T = any>(url: string) => request<T>(url)
export const post = <T = any>(url: string, body?: unknown) => request<T>(url, { method: 'POST', body })
export const put = <T = any>(url: string, body?: unknown) => request<T>(url, { method: 'PUT', body })
export const del = <T = any>(url: string, body?: unknown) => request<T>(url, { method: 'DELETE', body })
