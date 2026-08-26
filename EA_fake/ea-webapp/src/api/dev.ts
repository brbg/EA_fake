// 研发管理 API（需求/测试用例/缺陷/任务）
import { get, post, put, del } from '../utils/request'
import { projectUrl } from './ai'

export type DevKind = 'requirement' | 'testcase' | 'defect' | 'task'
export const DEV_LIST_KEY: Record<DevKind, string> = {
  requirement: 'requirements',
  testcase: 'test_cases',
  defect: 'defects',
  task: 'tasks',
}

export const devApi = {
  crud: (kind: DevKind, projectId: string, body?: Record<string, unknown>) => {
    const url = projectUrl(projectId, `/${kind}`)
    if (!body) return get(url)
    if (body.id) return put(url, body)
    return post(url, body)
  },
  remove: (kind: DevKind, projectId: string, id: string) =>
    del(projectUrl(projectId, `/${kind}`), { id }),
  aiGenerate: (kind: 'requirement' | 'testcase' | 'task', projectId: string, body: Record<string, unknown>) =>
    post(projectUrl(projectId, `/${kind}/ai/generate`), body),
  aiPlan: (projectId: string, body: { req_ids: unknown[] }) =>
    post(projectUrl(projectId, '/task/ai/plan'), body),
  list: (kind: DevKind, projectId: string) => get(projectUrl(projectId, `/${kind}`)),
}

export default devApi
