// AI服务API调用模块
// 提供与大模型对话的统一接口

const API_BASE_URL = '/api/v1'

// 获取会话ID
const getSessionId = () => {
  return sessionStorage.getItem('sessionId') || ''
}

// 设置会话ID
const setSessionId = (sessionId: string) => {
  sessionStorage.setItem('sessionId', sessionId)
}

// 获取AI配置
export const getAIConfig = async () => {
  try {
    const response = await fetch(`${API_BASE_URL}/ai/config`)
    return await response.json()
  } catch (error) {
    console.error('获取AI配置失败:', error)
    return { config: { enabled: false, error: '获取配置失败' } }
  }
}

// 更新AI配置
export const updateAIConfig = async (config: {
  provider?: string
  api_key?: string
  base_url?: string
  model?: string
  reasoning_model?: string
  max_tokens?: number
  temperature?: number
  stream?: boolean
}) => {
  try {
    const response = await fetch(`${API_BASE_URL}/ai/config`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        'X-Session-Id': getSessionId()
      },
      body: JSON.stringify(config)
    })
    return await response.json()
  } catch (error) {
    console.error('更新AI配置失败:', error)
    return { error: '更新配置失败' }
  }
}

// 获取支持的AI提供商列表
export const getAIProviders = async () => {
  try {
    const response = await fetch(`${API_BASE_URL}/ai/providers`)
    return await response.json()
  } catch (error) {
    console.error('获取AI提供商列表失败:', error)
    return { providers: [] }
  }
}

// 调用大模型对话（非流式）
export const chatWithAI = async (messages: Array<{ role: string; content: string }>, sessionId?: string) => {
  try {
    const response = await fetch(`${API_BASE_URL}/ai/llm/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Session-Id': getSessionId()
      },
      body: JSON.stringify({
        messages,
        session_id: sessionId
      })
    })
    
    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.error || '对话失败')
    }
    
    return await response.json()
  } catch (error) {
    console.error('AI对话失败:', error)
    throw error
  }
}

// 流式调用大模型对话
export const chatWithAIStream = async (
  messages: Array<{ role: string; content: string }>,
  onMessage: (content: string) => void,
  onError: (error: string) => void,
  sessionId?: string,
  useReasoning = false,
  onReasoning?: (text: string) => void
) => {
  try {
    const response = await fetch(`${API_BASE_URL}/ai/llm/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Session-Id': getSessionId()
      },
      body: JSON.stringify({
        messages,
        session_id: sessionId,
        use_reasoning: useReasoning
      })
    })
    
    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.error || '对话失败')
    }
    
    const reader = response.body?.getReader()
    const decoder = new TextDecoder()
    
    if (!reader) {
      throw new Error('无法读取响应流')
    }
    
    while (true) {
      const { done, value } = await reader.read()
      
      if (done) {
        break
      }
      
      const chunk = decoder.decode(value)
      const lines = chunk.split('\n')
      
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.substring(6))
            
            if (data.error) {
              onError(data.error)
              return
            }
            
            if (data.choices && data.choices[0].delta) {
              const delta = data.choices[0].delta
              if (delta.content) {
                onMessage(delta.content)
              } else if (delta.reasoning_content && onReasoning) {
                onReasoning(delta.reasoning_content)
              }
            } else if (data.content) {
              onMessage(data.content)
            }
            
            if (data.done) {
              return
            }
          } catch (e) {
            // 忽略解析错误，继续处理下一行
          }
        }
      }
    }
  } catch (error) {
    console.error('AI流式对话失败:', error)
    onError(error instanceof Error ? error.message : '对话失败')
  }
}

// 传统AI对话（使用mock响应）
export const mockChat = async (message: string) => {
  return new Promise((resolve) => {
    setTimeout(() => {
      resolve({
        message: '对话成功',
        response: {
          role: 'assistant',
          content: `您的问题是: "${message}"\n\nAI分析结果:\n\n1. 模型复杂度评估\n2. 架构优化建议\n3. 最佳实践推荐\n\n如需详细分析，请上传或创建一个模型。`
        }
      })
    }, 1500)
  })
}

export default {
  getAIConfig,
  updateAIConfig,
  getAIProviders,
  chatWithAI,
  chatWithAIStream,
  mockChat,
  getSessionId,
  setSessionId
}
