"""元素类型、关系类型、颜色映射等常量定义。"""

# 元素类型定义
ELEMENT_TYPES = {
    'business': ['BusinessActor', 'BusinessRole', 'BusinessProcess', 'BusinessFunction',
                 'BusinessInteraction', 'BusinessEvent', 'BusinessService', 'BusinessInterface',
                 'BusinessObject', 'Contract', 'Product', 'Representation', 'Meaning'],
    'application': ['ApplicationComponent', 'ApplicationFunction', 'ApplicationInteraction',
                    'ApplicationProcess', 'ApplicationService', 'ApplicationInterface',
                    'ApplicationEvent', 'DataObject'],
    'technology': ['Node', 'Device', 'SystemSoftware', 'TechnologyService', 'TechnologyInterface',
                   'TechnologyProcess', 'TechnologyFunction', 'TechnologyInteraction',
                   'TechnologyEvent', 'Artifact', 'DataStore', 'Network'],
    # Enum 必须在内：edit_model_system_prompt('uml') 把它列为合法类型，
    # 漏掉会让下面的闭合白名单把合法的 Enum 降级成 Class
    'uml': ['Class', 'Interface', 'Enum', 'UseCase', 'Actor', 'Package', 'Component',
            'Node', 'Artifact', 'Activity', 'State', 'Sequence', 'Communication']
}

# 关系类型定义
RELATIONSHIP_TYPES = ['Assignment', 'Association', 'Aggregation', 'Composition',
                      'Realization', 'Serving', 'Access', 'Flow', 'Influence', 'Triggering',
                      'Generalization', 'Dependency']

# 元素颜色映射
ELEMENT_COLORS = {
    'BusinessActor': '#ffffb5',
    'BusinessRole': '#ffffb5',
    'BusinessProcess': '#ffffb5',
    'BusinessFunction': '#ffffb5',
    'BusinessInteraction': '#ffffb5',
    'BusinessEvent': '#ffffb5',
    'BusinessService': '#ffffb5',
    'BusinessInterface': '#ffffb5',
    'BusinessObject': '#ffffb5',
    'Contract': '#ffffb5',
    'Product': '#ffffb5',
    'Representation': '#ffffb5',
    'Meaning': '#ffffb5',
    'ApplicationComponent': '#b5ffff',
    'ApplicationFunction': '#b5ffff',
    'ApplicationInteraction': '#b5ffff',
    'ApplicationProcess': '#b5ffff',
    'ApplicationService': '#b5ffff',
    'ApplicationInterface': '#b5ffff',
    'ApplicationEvent': '#b5ffff',
    'DataObject': '#b5ffff',
    'Node': '#c9e7b7',
    'Device': '#c9e7b7',
    'SystemSoftware': '#c9e7b7',
    'TechnologyService': '#c9e7b7',
    'TechnologyInterface': '#c9e7b7',
    'TechnologyProcess': '#c9e7b7',
    'TechnologyFunction': '#c9e7b7',
    'TechnologyInteraction': '#c9e7b7',
    'TechnologyEvent': '#c9e7b7',
    'Artifact': '#c9e7b7',
    'DataStore': '#c9e7b7',
    'Network': '#c9e7b7',
    'Class': '#ffd5b4',
    'Interface': '#e5bfff',
    'UseCase': '#c4ffc4',
    'Actor': '#ffffaa',
    'Package': '#d4d4ff',
    'Component': '#ffd4ff',
    'Activity': '#ffa5a5',
    'State': '#a5ffd4'
}


def get_default_color(elem_type):
    return ELEMENT_COLORS.get(elem_type, '#d0d0d0')


# ---------------------------------------------------------------- ArchiMate
# 单一事实来源：此前这三处各写一份、会各自漂移——
#   ① backend/app.py（校验用）② backend/prompts.py（提示词里的枚举串）③ 前端 archimateTools
# 用**有序元组**而不是 set：提示词里要把它们拼成 `a/b/c` 给模型看，顺序必须是稳定的，
# 不能靠 set 的迭代顺序（每次进程启动都可能不同）。
# 成员判断用 `in` 即可，元组一样work（元素 ≤10 个，顺序查找的开销可忽略）。
#
# 元素类型按层次聚类，便于阅读（不是强制约束——类型与层次是两个独立字段）：
#   业务层：actor / process / service
#   应用层：component
#   技术层：node / device / system_software / communication_network / technology_service
#   跨层：artifact
# 技术层这 5 个是 2026-10 补的：此前技术层只有 node/artifact，"部署拓扑"画不出来
# （服务器、数据库、中间件、网关都只能挤成 node，视觉上无法区分）。
ARCHIMATE_ELEMENT_TYPES = ('actor', 'process', 'service', 'component',
                           'node', 'device', 'system_software', 'communication_network',
                           'technology_service', 'artifact')
# assignment 是 ArchiMate 规范里表达「部署/分配」的关系（如应用组件分配到节点上），
# 加它是为了「部署视图」不再用 serving 凑合（语义上 serving 是「提供服务」）。
ARCHIMATE_REL_TYPES = ('association', 'realization', 'serving', 'assignment',
                       'composition', 'aggregation', 'access', 'flow', 'triggering')
ARCHIMATE_LAYERS = ('business', 'application', 'technology')

# 三层背景带的 y 范围（逻辑坐标；画布逻辑高 600，正好三等分）。
# 后端布局器的 layer_y 必须落在对应带内，否则元素会画到别的层的带上——
# 而且此前 layer_y[technology]=560 + 元素高 70 = 630 已超出 600 被裁掉 30px。
ARCHIMATE_LAYER_BANDS = {'business': (0, 200), 'application': (200, 400), 'technology': (400, 600)}

# 提示词里直接插值用的枚举串（从上面派生，杜绝「改了集合忘了改提示词」）
ARCHIMATE_ELEMENT_ENUM = '/'.join(ARCHIMATE_ELEMENT_TYPES)
ARCHIMATE_REL_ENUM = '/'.join(ARCHIMATE_REL_TYPES)
ARCHIMATE_LAYER_ENUM = '/'.join(ARCHIMATE_LAYERS)

# 三层配色（后端布局器与前端 getLayerColor 需保持一致）
ARCH_HEAD = {'business': '#3498db', 'application': '#2ecc71', 'technology': '#e67e22'}
ARCH_BODY = {'business': '#ecf0f1', 'application': '#e8f8f5', 'technology': '#fef5e7'}
