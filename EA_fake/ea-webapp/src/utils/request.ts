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

export interface BlobResp {
  ok: boolean
  status: number
  blob: Blob | null
  /** 从 Content-Disposition 解析出的文件名（服务端没给则用 fallback） */
  filename: string
  error: string
}

// 解析 Content-Disposition 里的文件名：优先 RFC 5987 的 filename*=UTF-8''（中文名），
// 退回普通 filename="..."，都没有就用调用方给的兜底名。
function parseFilename(disposition: string, fallback: string): string {
  if (!disposition) return fallback
  const star = /filename\*=UTF-8''([^;]+)/i.exec(disposition)
  if (star) {
    try {
      return decodeURIComponent(star[1])
    } catch {
      try { return decodeURI(star[1]) } catch { /* 落到普通 filename */ }
    }
  }
  const plain = /filename="?([^";]+)"?/i.exec(disposition)
  return plain ? plain[1] : fallback
}

/** 下载二进制（如 zip）。与 request() 同样自动带会话头，但走 blob 而非 json。 */
export async function postBlob(url: string, body: unknown, fallbackName = 'download.bin'): Promise<BlobResp> {
  let res: Response
  try {
    res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...sessionHeader() },
      body: JSON.stringify(body)
    })
  } catch (e) {
    return { ok: false, status: 0, blob: null, filename: fallbackName, error: '网络异常，下载失败' }
  }

  const ctype = res.headers.get('Content-Type') || ''
  // 服务端出错时走的是 jsonify，必须按 JSON 解析才能把中文原因带回给用户
  if (!res.ok || ctype.includes('application/json')) {
    let msg = `下载失败（${res.status}）`
    try {
      const d = await res.json()
      if (d?.error) msg = d.error
    } catch { /* 保持默认文案 */ }
    return { ok: false, status: res.status, blob: null, filename: fallbackName, error: msg }
  }

  const blob = await res.blob()
  return {
    ok: true,
    status: res.status,
    blob,
    filename: parseFilename(res.headers.get('Content-Disposition') || '', fallbackName),
    error: ''
  }
}

export const get = <T = any>(url: string) => request<T>(url)
export const post = <T = any>(url: string, body?: unknown) => request<T>(url, { method: 'POST', body })
export const put = <T = any>(url: string, body?: unknown) => request<T>(url, { method: 'PUT', body })
export const del = <T = any>(url: string, body?: unknown) => request<T>(url, { method: 'DELETE', body })
