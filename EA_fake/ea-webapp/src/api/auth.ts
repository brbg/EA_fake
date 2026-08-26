// 鉴权 API
import { post, get } from '../utils/request'

export const authApi = {
  register: (body: { username: string; email: string; password: string }) =>
    post('/api/auth/register', body),
  login: (body: { username: string; password: string }) =>
    post('/api/auth/login', body),
  logout: () => post('/api/auth/logout'),
  validate: () => get('/api/auth/validate'),
}

export default authApi
