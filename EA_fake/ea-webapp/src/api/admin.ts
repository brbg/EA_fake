// 后台管理 API（管理员）
import { get, post, put, del } from '../utils/request'

export const adminApi = {
  users: () => get('/api/admin/users'),
  createUser: (body: { username: string; email: string; password: string; role: string }) =>
    post('/api/admin/users', body),
  updateUser: (id: string, body: Record<string, unknown>) => put(`/api/admin/users/${id}`, body),
  deleteUser: (id: string) => del(`/api/admin/users/${id}`),
  userProjects: (id: string) => get(`/api/admin/users/${id}/projects`),
  deleteProject: (projectId: string) => del(`/api/admin/projects/${projectId}`),
}

export default adminApi
