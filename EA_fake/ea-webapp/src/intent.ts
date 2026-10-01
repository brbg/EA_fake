// AI 助手 → 工具动作 的前端意图路由（Phase1 无原生 function-calling，用关键词判定）
export type AgentIntent =
  | { kind: 'architect'; text: string }
  | { kind: 'health'; text: string }
  | { kind: 'edit'; target: 'uml' | 'archimate' | 'er'; text: string }
  | { kind: 'chat'; text: string }

const EDIT_WORDS = ['类', '接口', '实体', '表', '字段', '方法', '服务', '流程', '组件', '关系']

export function detectToolIntent(raw: string): AgentIntent {
  const t = (raw || '').trim()
  // 1) 一键 / 全架构设计
  if (
    /一键|自动完成|生成(一套|整套|个|一)?(企业|整体|完整|项目)?架构|整体架构设计|帮我设计(一个|整套|个|一)?(系统|平台|项目|架构|企业)/.test(t) ||
    /架构.*(平台|系统|项目)/.test(t) && /设计|生成|创建/.test(t)
  ) {
    return { kind: 'architect', text: t }
  }
  // 2) 健康度/诊断（当前项目）
  if (/健康度|体检|诊断|评估(当前)?项目|检查.*模型|评分/.test(t)) {
    return { kind: 'health', text: t }
  }
  // 3) 改模型（当前项目画布）
  if (/^(帮我)?(添加|加|新增|删除|去掉|增加|改成|重命名|修改).{0,8}一个?/.test(t) && EDIT_WORDS.some((w) => t.includes(w))) {
    const target: 'uml' | 'archimate' | 'er' = /表|实体|字段/.test(t) ? 'er' : /服务|流程|组件/.test(t) ? 'archimate' : 'uml'
    return { kind: 'edit', target, text: t }
  }
  return { kind: 'chat', text: t }
}
