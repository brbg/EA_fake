// 协作 API（加入 / 退出 / 取消 / 查看协作者）
import { get, post, del } from '../utils/request'

export const collabApi = {
  // 按账户 id 列出其拥有的项目（用于加入协作）
  listUserProjects: (userId: string) => get(`/api/v1/users/${userId}/projects`),
  // 加入某项目为 editor 协作者
  join: (projectId: string) => post(`/api/v1/project/${projectId}/join`),
  // 列出项目协作者（owner 或成员可查）
  collaborators: (projectId: string) => get(`/api/v1/project/${projectId}/collaborators`),
  // owner 取消指定协作者
  revoke: (projectId: string, userId: string) =>
    del(`/api/v1/project/${projectId}/collaborators/${userId}`),
  // 协作者主动退出
  leave: (projectId: string) => post(`/api/v1/project/${projectId}/leave`),
}

export default collabApi
