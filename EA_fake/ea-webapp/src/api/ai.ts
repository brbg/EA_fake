// AI API（校验/评审/分析/对话编辑/生成图/文档/记忆/代码生成/反向工程）
import { get, post, del, postBlob } from '../utils/request'

export const projectUrl = (projectId: string, path: string) =>
  `/api/v1/project/${projectId}${path}`

export const aiApi = {
  validateUml: (projectId: string, body: { view_id?: string | null }) =>
    post(projectUrl(projectId, '/ai/validate-uml'), body),
  reviewArchimate: (projectId: string) =>
    post(projectUrl(projectId, '/ai/review-archimate'), {}),
  analyzeElement: (projectId: string, body: Record<string, unknown>) =>
    post(projectUrl(projectId, '/ai/analyze-element'), body),
  editModel: (projectId: string, body: Record<string, unknown>) =>
    post(projectUrl(projectId, '/ai/edit-model'), body),
  generateDiagram: (projectId: string, body: { text: string; kind: string; view_type?: string }) =>
    post(projectUrl(projectId, '/ai/generate-diagram'), body),
  document: (projectId: string, body: { doc_type: string; format: string }) =>
    post(projectUrl(projectId, '/ai/document'), body),
  memoryList: (projectId: string) => get(projectUrl(projectId, '/ai/memory')),
  memoryAdd: (projectId: string, body: { content: string }) =>
    post(projectUrl(projectId, '/ai/memory'), body),
  memoryDelete: (projectId: string, memId: string) =>
    del(projectUrl(projectId, `/ai/memory/${memId}`)),
}

export const codeApi = {
  generate: (body: Record<string, unknown>) => post('/api/v1/ai/code/generate', body),
  // 若依 RuoYi-Vue3 整套模块：一次产出 domain/mapper/xml/service/controller/前端/SQL 多文件
  generateRuoYi: (body: Record<string, unknown>) => post('/api/v1/ai/code/ruoyi/generate', body),
  generateRuoYiZip: (body: Record<string, unknown>) =>
    postBlob('/api/v1/ai/code/ruoyi/download', body, 'ruoyi-module.zip'),
  // 分析 UML 图，推荐最接近的设计模式
  recommendPattern: (body: { elements: unknown[]; connections: unknown[] }) =>
    post('/api/v1/ai/pattern/recommend', body),
  reverse: (body: { code: string; language: string; target: string }) =>
    post('/api/v1/ai/code/reverse', body),
}

export default aiApi
