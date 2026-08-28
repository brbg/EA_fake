// 模型（项目）CRUD API
import { get, post, put, del } from '../utils/request'

export const modelApi = {
  list: () => get('/api/models'),
  get: (id: string) => get(`/api/models/${id}`),
  create: (body: { name: string; description?: string }) => post('/api/models', body),
  save: (id: string, body: Record<string, unknown>) => put(`/api/models/${id}`, body),
  remove: (id: string) => del(`/api/models/${id}`),
  // 版本管理
  versions: (id: string) => get(`/api/models/${id}/versions`),
  saveVersion: (id: string, comment: string) => post(`/api/models/${id}/versions/save`, { comment }),
  restoreVersion: (id: string, index: number) => post(`/api/models/${id}/versions/${index}`),
  // 项目健康度（model_id 即 project_id）
  health: (id: string) => get(`/api/projects/${id}/health`),
}

export default modelApi
