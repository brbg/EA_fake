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
