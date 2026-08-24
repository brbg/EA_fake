export interface ProjectContext {
  currentModelId: string
  currentModelName: string
  activeTab?: string
  umlElements: Array<{
    id: string | number
    type: string
    name: string
    attributes: string[]
    x?: number
    y?: number
    width?: number
    height?: number
  }>
  umlRelationships: Array<{
    id: string | number
    sourceId: string | number
    targetId: string | number
    type: string
  }>
  archimateElements: Array<{
    id: string | number
    type: string
    name: string
    layer: string
    x?: number
    y?: number
    width?: number
    height?: number
  }>
  archimateRelationships: Array<{
    id: string | number
    sourceId: string | number
    targetId: string | number
    type: string
  }>
  erEntities: Array<{
    id: string | number
    name: string
    attributes: Array<{
      id: string | number
      name: string
      type: string
      isPrimaryKey: boolean
      isForeignKey: boolean
    }>
    x?: number
    y?: number
    width?: number
    height?: number
  }>
  erRelationships: Array<{
    id: string | number
    sourceId: string | number
    targetId: string | number
    type: string
  }>
}

export const buildProjectContext = (context: ProjectContext): string => {
  const parts: string[] = []
  
  if (context.currentModelName) {
    parts.push(`当前项目：${context.currentModelName}`)
  }
  
  const umlCount = context.umlElements.length
  const archimateCount = context.archimateElements.length
  const erCount = context.erEntities.length
  
  if (umlCount > 0) {
    parts.push(`\n--- UML类图 (${umlCount}个元素) ---`)
    
    const classNames: string[] = []
    const interfaceNames: string[] = []
    
    context.umlElements.forEach(elem => {
      if (elem.type === 'class') {
        classNames.push(elem.name)
      } else if (elem.type === 'interface') {
        interfaceNames.push(elem.name)
      }
    })
    
    if (classNames.length > 0) {
      parts.push(`类: ${classNames.join(', ')}`)
    }
    if (interfaceNames.length > 0) {
      parts.push(`接口: ${interfaceNames.join(', ')}`)
    }
    
    context.umlElements.forEach(elem => {
      const attrs = elem.attributes.length > 0 
        ? `\n  属性: ${elem.attributes.join(', ')}`
        : ''
      parts.push(`${elem.type === 'class' ? '类' : '接口'} ${elem.name}${attrs}`)
    })
    
    if (context.umlRelationships.length > 0) {
      parts.push('\n关系:')
      context.umlRelationships.forEach(conn => {
        const startName = findElementName(context.umlElements, conn.sourceId)
        const endName = findElementName(context.umlElements, conn.targetId)
        const relType = mapRelationType(conn.type)
        parts.push(`  ${startName} ${relType} ${endName}`)
      })
    }
  }
  
  if (archimateCount > 0) {
    parts.push(`\n--- ArchiMate模型 (${archimateCount}个元素) ---`)
    
    const layers = ['business', 'application', 'technology']
    layers.forEach(layer => {
      const layerElements = context.archimateElements.filter(e => e.layer === layer)
      if (layerElements.length > 0) {
        parts.push(`${mapLayer(layer)}层:`)
        layerElements.forEach(elem => {
          parts.push(`  ${mapArchimateType(elem.type)}: ${elem.name}`)
        })
      }
    })
  }
  
  if (erCount > 0) {
    parts.push(`\n--- ER数据模型 (${erCount}个实体) ---`)
    
    context.erEntities.forEach(entity => {
      const fields = entity.attributes.length > 0
        ? `\n  字段: ${entity.attributes.map(f => {
            const pkMark = f.isPrimaryKey ? ' (PK)' : ''
            const fkMark = f.isForeignKey ? ' (FK)' : ''
            return `${f.name}: ${f.type}${pkMark}${fkMark}`
          }).join(', ')}`
        : ''
      parts.push(`实体 ${entity.name}${fields}`)
    })
    
    if (context.erRelationships.length > 0) {
      parts.push('\n关系:')
      context.erRelationships.forEach(rel => {
        const sourceName = findEntityName(context.erEntities, rel.sourceId)
        const targetName = findEntityName(context.erEntities, rel.targetId)
        parts.push(`  ${sourceName} -${rel.type}- ${targetName}`)
      })
    }
  }
  
  if (umlCount === 0 && archimateCount === 0 && erCount === 0) {
    parts.push('\n--- 当前项目为空 ---')
    parts.push('用户尚未创建任何模型元素。')
  }
  
  return parts.join('\n')
}

const findElementName = (elements: Array<{ id: string | number; name: string }>, id: string | number): string => {
  const elem = elements.find(e => e.id === id)
  return elem ? elem.name : `[${id}]`
}

const findEntityName = (entities: Array<{ id: string | number; name: string }>, id: string | number): string => {
  const entity = entities.find(e => e.id === id)
  return entity ? entity.name : `[${id}]`
}

const mapRelationType = (type: string): string => {
  const mappings: Record<string, string> = {
    'association': '关联',
    'inheritance': '继承',
    'composition': '组合',
    'realization': '实现',
    'dependency': '依赖',
    'aggregation': '聚合'
  }
  return mappings[type] || type
}

const mapLayer = (layer: string): string => {
  const mappings: Record<string, string> = {
    'business': '业务',
    'application': '应用',
    'technology': '技术'
  }
  return mappings[layer] || layer
}

const mapArchimateType = (type: string): string => {
  const mappings: Record<string, string> = {
    'actor': '角色',
    'process': '流程',
    'service': '服务',
    'component': '组件',
    'node': '节点',
    'artifact': '制品',
    'businessActor': '业务角色',
    'businessProcess': '业务流程',
    'businessService': '业务服务',
    'applicationComponent': '应用组件',
    'applicationService': '应用服务',
    'technologyComponent': '技术组件',
    'technologyService': '技术服务',
    'systemSoftware': '系统软件',
    'device': '设备'
  }
  return mappings[type] || type
}

export const SYSTEM_PROMPT_TEMPLATE = `你是一个专业的企业架构（Enterprise Architect）AI助手，擅长分析UML类图、ArchiMate架构模型和ER数据模型。

## 当前项目上下文
{PROJECT_CONTEXT}

## 你的职责
1. **模型分析**: 根据项目上下文分析模型结构、关系和设计模式
2. **架构建议**: 提供架构优化建议、最佳实践和改进方案
3. **代码生成**: 根据模型生成相应的代码（Java、Python、TypeScript等）
4. **问题解答**: 回答关于模型设计、UML规范、ArchiMate标准等问题

## 回答要求
- 优先基于项目上下文进行回答
- 如果问题与当前项目无关，可以忽略上下文
- 保持专业、简洁、准确
- 使用Markdown格式输出

用户问题：`

export const buildMessagesWithContext = (
  userMessage: string,
  projectContext: ProjectContext
): Array<{ role: string; content: string }> => {
  const contextText = buildProjectContext(projectContext)
  const systemPrompt = SYSTEM_PROMPT_TEMPLATE.replace('{PROJECT_CONTEXT}', contextText)
  
  return [
    { role: 'system', content: systemPrompt },
    { role: 'user', content: userMessage }
  ]
}
