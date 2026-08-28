// 协作 API（加入 / 退出 / 取消 / 查看协作者）
import { get, post, del } from '../utils/request'

export const collabApi = {
  // 按账户 id 列出其拥有的项目（用于加入协作）
  listUserProjects: (userId: string) => get(`/api/v1/users/${userId}/projects`),
  // 加入某项目为 editor 协作者
  join: (projectId: string) => post(`/api/v1/project/${projectId}/join`),
  // 按 owner 账户 id 加入其当前打开的项目（直接进当前项目）
  joinCurrent: (ownerUserId: string) => post('/api/v1/project/join-current', { owner_user_id: ownerUserId }),
  // 列出项目协作者（owner 或成员可查）
  collaborators: (projectId: string) => get(`/api/v1/project/${projectId}/collaborators`),
  // owner 取消指定协作者
  revoke: (projectId: string, userId: string) =>
    del(`/api/v1/project/${projectId}/collaborators/${userId}`),
  // 协作者主动退出
  leave: (projectId: string) => post(`/api/v1/project/${projectId}/leave`),
  // 协作变更申请（类 GitHub PR：协作者提交 → owner 审批）
  proposals: (projectId: string) => get(`/api/v1/project/${projectId}/proposals`),
  submitProposal: (projectId: string, body: { title: string; data: Record<string, unknown> }) =>
    post(`/api/v1/project/${projectId}/proposals`, body),
  approveProposal: (projectId: string, proposalId: string) =>
    post(`/api/v1/project/${projectId}/proposals/${proposalId}/approve`),
  rejectProposal: (projectId: string, proposalId: string) =>
    post(`/api/v1/project/${projectId}/proposals/${proposalId}/reject`),
  // 项目知识库（AI 每次调用自动记录关键结论）
  knowledge: (projectId: string) => get(`/api/v1/project/${projectId}/knowledge`),
  addKnowledge: (projectId: string, body: { summary: string; source?: string }) =>
    post(`/api/v1/project/${projectId}/knowledge`, body),
  deleteKnowledge: (projectId: string, entryId: string) =>
    del(`/api/v1/project/${projectId}/knowledge/${entryId}`),
}

export default collabApi
