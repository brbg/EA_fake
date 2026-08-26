// 模型（项目）CRUD API
import { get, post, put, del } from '../utils/request'

export const modelApi = {
  list: () => get('/api/models'),
  get: (id: string) => get(`/api/models/${id}`),
  create: (body: { name: string; description?: string }) => post('/api/models', body),
  save: (id: string, body: Record<string, unknown>) => put(`/api/models/${id}`, body),
  remove: (id: string) => del(`/api/models/${id}`),
}

export default modelApi
