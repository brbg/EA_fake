"""UML AI 生成服务（结构化 JSON 生成/布局/关键词回退）。

按「拆巨石」计划从 app.py 抽出，供 app.py 的 UML AI 路由与 generate-diagram 使用。
"""
import uuid
import json
from constants import ELEMENT_TYPES, RELATIONSHIP_TYPES
from core import AIService, ai_service_config, _ai_parse_json_response
from prompts import uml_system_prompt, VALIDATE_SYSTEM_PROMPT, ARCHIMATE_GENERATE_SYSTEM_PROMPT

#: 画布认识的 UML 元素类型（闭合白名单）
_UML_CANVAS_TYPES = frozenset(ELEMENT_TYPES['uml'])


def _normalize_uml_type(t, default='Class', report=None):
    """把LLM返回的元素类型归一化成画布认识的UML类型。

    闭合白名单：认不出的类型回落到 `default` 并记一条 report，而不是
    `capitalize()` 直接放行——放行会让「LLM 编出来的类型」原样进模型，
    到渲染/校验那一步才以更难查的形式暴露。
    """
    key = str(t).strip().lower()
    aliases = {
        'class': 'Class', 'interface': 'Interface', 'enum': 'Enum', 'enumeration': 'Enum',
        'usecase': 'UseCase', 'use_case': 'UseCase',
        'actor': 'Actor', 'activity': 'Activity', 'action': 'Activity',
        'start': 'Activity', 'end': 'Activity', 'decision': 'Activity',
        'state': 'State', 'sequence': 'Sequence', 'component': 'Component',
        'package': 'Package', 'node': 'Node', 'artifact': 'Artifact',
    }
    result = aliases.get(key, str(t).strip().capitalize())
    if result in _UML_CANVAS_TYPES:
        return result
    if report is not None:
        report.append(f'未知元素类型「{t}」，已按 {default} 处理')
    return default


def _default_rel_type(view_type):
    """各视图类型的关系默认类型。"""
    return 'Flow' if view_type in ('activity', 'sequence') else 'Association'


def _ai_generate_uml(prompt, view_type):
    """调用LLM生成UML结构化数据（元素+关系）。AI未启用/失败返回None，由调用方回退关键词解析。"""
    if not ai_service_config.enabled:
        return None

    system_prompt = uml_system_prompt(view_type)
    messages = [
        {'role': 'system', 'content': system_prompt},
        {'role': 'user', 'content': prompt}
    ]
    result = AIService.chat_completion(messages, max_tokens=4096, temperature=0.3)
    if not isinstance(result, dict) or 'error' in result:
        return None
    try:
        content = result['choices'][0]['message']['content']
    except (KeyError, IndexError, TypeError):
        return None
    data = _ai_parse_json_response(content)
    if not isinstance(data, dict) or not isinstance(data.get('elements'), list):
        return None
    relationships = data.get('relationships')
    if not isinstance(relationships, list):
        relationships = []
    return data['elements'], relationships


def _est_text_w(s, bold=False):
    """估算文本像素宽（中文按 12px、其余按 6.6px；粗体略放大）。"""
    w = 0.0
    for ch in str(s):
        w += 12.0 if ord(ch) > 127 else 6.6
    return w * (1.06 if bold else 1.0)


def _est_uml_size(elem_type, item):
    """按元素内容估算画布尺寸（与前端 drawElement 的自适应规则一致），用于防重叠布局。"""
    fixed = {'Actor': (60, 80), 'UseCase': (100, 60), 'Activity': (100, 50)}
    if elem_type in fixed:
        return fixed[elem_type]
    name = str(item.get('name') or '')
    attrs = item.get('attributes') if isinstance(item.get('attributes'), list) else []
    methods = item.get('methods') if isinstance(item.get('methods'), list) else []
    maxw = _est_text_w(name, True)
    for a in attrs:
        maxw = max(maxw, _est_text_w(a))
    for m in methods:
        maxw = max(maxw, _est_text_w(m))
    w = max(120, int(maxw) + 18)
    line_h = 14
    attr_h = max(1, len(attrs)) * line_h
    meth_h = len(methods) * line_h
    h = 25 + 10 + attr_h + ((7 + meth_h) if methods else 0) + 8
    return w, h


def _layout_ai_elements(elements_raw, relationships_raw, view_type, report=None):
    """把LLM返回的元素/关系（按名字引用）布局成画布元素（分配uuid/坐标/宽高）。

    `report` 传入 list 时收集「被改写/被丢弃」的说明，供上层展示与记录。
    """
    name_to_uuid = {}
    name_by_uuid = {}
    elements = []
    # 流式布局：按内容估算尺寸后逐行排布，避免元素重叠（画布逻辑宽 1150）
    LX, LY, GAP_X, GAP_Y, CANVAS_W = 60, 60, 50, 50, 1150
    cur_x, cur_y, row_h = LX, LY, 0
    for item in elements_raw:
        if not isinstance(item, dict) or not item.get('name'):
            continue
        name = str(item['name']).strip()
        if not name or name in name_to_uuid:
            continue

        raw_type = str(item.get('type') or 'Class').strip()
        elem_type = _normalize_uml_type(raw_type, report=report)
        w, h = _est_uml_size(elem_type, item)
        # 超出行宽则换行（新行 y 下移本行最高元素的高度）
        if cur_x + w > CANVAS_W - 40:
            cur_x, cur_y, row_h = LX, cur_y + row_h + GAP_Y, 0
        elem = {
            'uuid': str(uuid.uuid4()),
            'type': elem_type,
            'name': name,
            'description': item.get('description', '') or '',
            'x': cur_x,
            'y': cur_y,
            'width': w,
            'height': h,
        }
        cur_x += w + GAP_X
        row_h = max(row_h, h)
        # 活动图起止/判定节点画成圆形
        if raw_type.lower() in ('start', 'end', 'decision'):
            elem['shape'] = 'circle'
        # 类图带属性/方法
        if elem_type == 'Class':
            attrs = item.get('attributes')
            methods = item.get('methods')
            if isinstance(attrs, list):
                elem['attributes'] = [str(a) for a in attrs]
            if isinstance(methods, list):
                elem['methods'] = [str(m) for m in methods]

        name_to_uuid[name] = elem['uuid']
        name_by_uuid[elem['uuid']] = name
        elements.append(elem)

    relationships = []
    for rel in relationships_raw:
        if not isinstance(rel, dict):
            continue
        src_name = str(rel.get('source') or '').strip()
        tgt_name = str(rel.get('target') or '').strip()
        src = name_to_uuid.get(src_name)
        tgt = name_to_uuid.get(tgt_name)
        if not src or not tgt or src == tgt:
            if report is not None:
                report.append(f'关系 {src_name or "?"} → {tgt_name or "?"} 端点无法解析或自环，已丢弃')
            continue
        rel_type = str(rel.get('type') or _default_rel_type(view_type)).strip()
        if rel_type not in RELATIONSHIP_TYPES:
            if report is not None:
                report.append(f'未知关系类型「{rel_type}」，已按 {_default_rel_type(view_type)} 处理')
            rel_type = _default_rel_type(view_type)
        relationships.append({
            'uuid': str(uuid.uuid4()),
            'source': src,
            'target': tgt,
            'source_name': name_by_uuid[src],
            'target_name': name_by_uuid[tgt],
            'type': rel_type,
            'description': rel.get('description', '') or ''
        })

    return elements, relationships


def generate_uml_from_prompt(prompt, view_type):
    """根据提示生成UML元素（优先LLM，失败/未启用时回退到关键词解析）"""
    ai_result = _ai_generate_uml(prompt, view_type)
    if ai_result is not None:
        return _layout_ai_elements(ai_result[0], ai_result[1], view_type)

    elements = []
    relationships = []

    # 根据视图类型生成不同的元素
    if view_type == 'class':
        # 模拟从业务描述中提取类
        classes = extract_classes_from_text(prompt)
        x, y = 100, 100
        
        for i, cls in enumerate(classes):
            elements.append({
                'uuid': str(uuid.uuid4()),
                'type': 'Class',
                'name': cls['name'],
                'description': cls.get('description', ''),
                'x': x + (i % 3) * 200,
                'y': y + (i // 3) * 150,
                'width': 120,
                'height': 80,
                'attributes': cls.get('attributes', []),
                'methods': cls.get('methods', [])
            })
        
        # 添加关系
        for i in range(len(elements) - 1):
            relationships.append({
                'uuid': str(uuid.uuid4()),
                'source': elements[i]['uuid'],
                'target': elements[i+1]['uuid'],
                'source_name': elements[i]['name'],
                'target_name': elements[i+1]['name'],
                'type': 'Association',
                'description': ''
            })
    
    elif view_type == 'use_case':
        # 生成用例图元素
        use_cases = extract_use_cases_from_text(prompt)
        x, y = 100, 100
        
        # 添加角色
        elements.append({
            'uuid': str(uuid.uuid4()),
            'type': 'Actor',
            'name': '用户',
            'description': '系统使用者',
            'x': x,
            'y': y + 100,
            'width': 60,
            'height': 80
        })
        
        for i, uc in enumerate(use_cases):
            elements.append({
                'uuid': str(uuid.uuid4()),
                'type': 'UseCase',
                'name': uc['name'],
                'description': uc.get('description', ''),
                'x': x + 150,
                'y': y + i * 120,
                'width': 100,
                'height': 60
            })
            # 添加关联
            relationships.append({
                'uuid': str(uuid.uuid4()),
                'source': elements[0]['uuid'],
                'target': elements[i+1]['uuid'],
                'source_name': '用户',
                'target_name': uc['name'],
                'type': 'Association',
                'description': ''
            })
    
    elif view_type == 'activity':
        # 生成活动图
        activities = extract_activities_from_text(prompt)
        x, y = 100, 100
        
        # 开始节点
        elements.append({
            'uuid': str(uuid.uuid4()),
            'type': 'Activity',
            'name': '开始',
            'description': '',
            'x': x,
            'y': y,
            'width': 40,
            'height': 40,
            'shape': 'circle'
        })
        
        for i, activity in enumerate(activities):
            elements.append({
                'uuid': str(uuid.uuid4()),
                'type': 'Activity',
                'name': activity['name'],
                'description': activity.get('description', ''),
                'x': x + 150 + (i // 2) * 150,
                'y': y + (i % 2) * 100,
                'width': 100,
                'height': 50,
                'shape': 'rounded'
            })
        
        # 结束节点
        elements.append({
            'uuid': str(uuid.uuid4()),
            'type': 'Activity',
            'name': '结束',
            'description': '',
            'x': x + 300,
            'y': y + 50,
            'width': 40,
            'height': 40,
            'shape': 'circle'
        })
        
        # 添加流程连接
        for i in range(len(elements) - 1):
            relationships.append({
                'uuid': str(uuid.uuid4()),
                'source': elements[i]['uuid'],
                'target': elements[i+1]['uuid'],
                'source_name': elements[i]['name'],
                'target_name': elements[i+1]['name'],
                'type': 'Flow',
                'description': ''
            })
    
    elif view_type == 'sequence':
        # 生成分时序图
        participants = extract_participants_from_text(prompt)
        x, y = 100, 100
        
        # 添加参与者
        for i, participant in enumerate(participants):
            elements.append({
                'uuid': str(uuid.uuid4()),
                'type': 'Actor' if i == 0 else 'ApplicationComponent',
                'name': participant,
                'description': '',
                'x': x + i * 150,
                'y': y,
                'width': 80,
                'height': 40
            })
        
        # 添加消息
        for i in range(len(participants) - 1):
            relationships.append({
                'uuid': str(uuid.uuid4()),
                'source': elements[i]['uuid'],
                'target': elements[i+1]['uuid'],
                'source_name': participants[i],
                'target_name': participants[i+1],
                'type': 'Flow',
                'description': f'消息{i+1}'
            })
    
    else:
        # 默认生成一些示例元素
        x, y = 100, 100
        for i in range(3):
            elements.append({
                'uuid': str(uuid.uuid4()),
                'type': 'ApplicationComponent',
                'name': f'组件{i+1}',
                'description': '',
                'x': x + i * 200,
                'y': y,
                'width': 100,
                'height': 60
            })
    
    return elements, relationships

def extract_classes_from_text(text):
    """从文本中提取类信息（模拟AI解析）"""
    keywords = ['用户', '订单', '商品', '服务', '系统', '模块', '数据', '接口']
    classes = []
    
    for keyword in keywords:
        if keyword in text:
            classes.append({
                'name': keyword,
                'description': f'{keyword}实体',
                'attributes': ['id', 'name', 'created_at'],
                'methods': ['create()', 'update()', 'delete()']
            })
            if len(classes) >= 5:
                break
    
    if not classes:
        classes = [
            {'name': 'User', 'description': '用户实体', 'attributes': ['id', 'name', 'email'], 'methods': ['login()', 'logout()']},
            {'name': 'Order', 'description': '订单实体', 'attributes': ['id', 'userId', 'amount'], 'methods': ['create()', 'cancel()']},
            {'name': 'Product', 'description': '商品实体', 'attributes': ['id', 'name', 'price'], 'methods': ['getInfo()', 'updateStock()']}
        ]
    
    return classes

def extract_use_cases_from_text(text):
    """从文本中提取用例"""
    use_cases = []
    
    if '登录' in text or '注册' in text:
        use_cases.append({'name': '用户登录', 'description': '用户通过账号密码登录系统'})
    if '查询' in text or '搜索' in text:
        use_cases.append({'name': '查询数据', 'description': '用户查询相关信息'})
    if '创建' in text or '新增' in text:
        use_cases.append({'name': '创建记录', 'description': '用户创建新的业务记录'})
    if '管理' in text:
        use_cases.append({'name': '管理配置', 'description': '用户管理系统配置'})
    
    if not use_cases:
        use_cases = [
            {'name': '用户登录', 'description': '用户登录系统'},
            {'name': '浏览数据', 'description': '用户浏览系统数据'},
            {'name': '提交表单', 'description': '用户提交业务表单'}
        ]
    
    return use_cases

def extract_activities_from_text(text):
    """从文本中提取活动"""
    activities = []
    
    if '开始' in text or '启动' in text:
        activities.append({'name': '开始流程', 'description': '启动业务流程'})
    if '验证' in text or '检查' in text:
        activities.append({'name': '验证数据', 'description': '验证输入数据的有效性'})
    if '处理' in text or '计算' in text:
        activities.append({'name': '处理业务', 'description': '执行业务逻辑处理'})
    if '保存' in text or '存储' in text:
        activities.append({'name': '保存数据', 'description': '将数据保存到数据库'})
    if '结束' in text or '完成' in text:
        activities.append({'name': '完成流程', 'description': '结束业务流程'})
    
    if not activities:
        activities = [
            {'name': '接收请求', 'description': '接收用户请求'},
            {'name': '验证权限', 'description': '验证用户权限'},
            {'name': '执行业务', 'description': '执行核心业务逻辑'},
            {'name': '返回结果', 'description': '返回处理结果'}
        ]
    
    return activities

def extract_participants_from_text(text):
    """从文本中提取参与者"""
    participants = []
    
    if '用户' in text:
        participants.append('用户')
    if '系统' in text or '服务' in text:
        participants.append('系统服务')
    if '数据库' in text:
        participants.append('数据库')
    if 'API' in text:
        participants.append('外部API')
    
    if not participants:
        participants = ['用户', '前端', '后端', '数据库']
    
    return participants

def _ai_validate_semantics(elements, relationships):
    """调用LLM做语义级模型评审。AI未启用/失败返回None。"""
    if not ai_service_config.enabled:
        return None

    system_prompt = VALIDATE_SYSTEM_PROMPT
    desc_lines = []
    for e in elements:
        desc_lines.append(f"- {e.get('type')} {e.get('name')}: {e.get('description', '')}")
    # 关系里的源/目标用名称描述（兼容 id/uuid 与 source/startElement 两种字段名）
    name_map = {(_elem_id(e) or ''): e.get('name') for e in elements}
    for r in relationships:
        s = name_map.get(_rel_source(r) or '') or _rel_source(r)
        t = name_map.get(_rel_target(r) or '') or _rel_target(r)
        desc_lines.append(f"- 关系: {s} --({r.get('type')})--> {t}")
    user_prompt = '\n'.join(desc_lines) if desc_lines else '模型为空'

    messages = [
        {'role': 'system', 'content': system_prompt},
        {'role': 'user', 'content': user_prompt}
    ]
    result = AIService.chat_completion(messages, max_tokens=2000, temperature=0.3, use_reasoning=True)
    if not isinstance(result, dict) or 'error' in result:
        return None
    try:
        content = result['choices'][0]['message']['content']
    except (KeyError, IndexError, TypeError):
        return None
    data = _ai_parse_json_response(content)
    if not isinstance(data, dict):
        return None
    issues = data.get('issues')
    if not isinstance(issues, list):
        issues = []
    data['issues'] = issues
    data['summary'] = data.get('summary', '')
    return data


def _elem_id(elem):
    """元素主键：兼容前端(id)与后端(uuid)两种字段名。"""
    return elem.get('uuid') or elem.get('id')


def _rel_source(rel):
    """关系源元素：兼容 source / startElement。"""
    return rel.get('source') or rel.get('startElement')


def _rel_target(rel):
    """关系目标元素：兼容 target / endElement。"""
    return rel.get('target') or rel.get('endElement')


def validate_uml_model(model, view=None, use_ai=True):
    """校验UML模型（元素 id/uuid 均可，关系兼容 source/startElement、target/endElement）。

    `use_ai=False` 时跳过语义级 AI 评审，只做确定性结构规则——质量打分器与
    离线测试必须走这条路，否则一次打分就会静默发 LLM 请求、结果不可复现。
    """
    errors = []
    warnings = []
    suggestions = []
    valid_count = 0
    invalid_count = 0

    elements_to_check = view['elements'] if view else model.elements
    relationships_to_check = view['relationships'] if view else model.relationships

    # 检查元素命名
    for elem in elements_to_check:
        name = (elem.get('name') or '').strip()
        if not name or name in ['Unnamed', '未命名']:
            errors.append({
                'type': 'naming',
                'severity': 'error',
                'message': '元素未命名',
                'element_id': _elem_id(elem),
                'element_name': name or '未知'
            })
            invalid_count += 1
        elif len(name) > 50:
            warnings.append({
                'type': 'naming',
                'severity': 'warning',
                'message': f"元素名称过长: {name}",
                'element_id': _elem_id(elem)
            })
        else:
            valid_count += 1

    # 检查关系合法性（源/目标必须指向真实存在的元素）
    elem_uuids = {_elem_id(e) for e in elements_to_check}

    for rel in relationships_to_check:
        r_src = _rel_source(rel)
        r_tgt = _rel_target(rel)
        if r_src is None or r_src not in elem_uuids:
            errors.append({
                'type': 'relationship',
                'severity': 'error',
                'message': '关系源元素不存在',
                'relationship_id': rel.get('uuid') or rel.get('id', ''),
                'source': r_src
            })
            invalid_count += 1
        if r_tgt is None or r_tgt not in elem_uuids:
            errors.append({
                'type': 'relationship',
                'severity': 'error',
                'message': '关系目标元素不存在',
                'relationship_id': rel.get('uuid') or rel.get('id', ''),
                'target': r_tgt
            })
            invalid_count += 1
        if r_src is not None and r_src == r_tgt:
            warnings.append({
                'type': 'relationship',
                'severity': 'warning',
                'message': f"自引用关系: {rel.get('source_name', '') or rel.get('name', '')}",
                'relationship_id': rel.get('uuid') or rel.get('id', '')
            })

    # 检查UML语法规范
    for elem in elements_to_check:
        etype = (elem.get('type') or '').lower()
        if etype in ('class', 'interface'):
            # 检查类的属性和方法
            attrs = elem.get('attributes', [])
            methods = elem.get('methods', [])

            for attr in attrs:
                if not isinstance(attr, str) or len(attr) > 100:
                    warnings.append({
                        'type': 'attribute',
                        'severity': 'warning',
                        'message': f"属性格式不正确: {attr}",
                        'element_id': _elem_id(elem)
                    })

            for method in methods:
                if not isinstance(method, str) or len(method) > 100:
                    warnings.append({
                        'type': 'method',
                        'severity': 'warning',
                        'message': f"方法格式不正确: {method}",
                        'element_id': _elem_id(elem)
                    })

    # 生成修复建议
    if errors:
        suggestions.append("请修复上述错误后重新校验")
    if invalid_count > 0:
        suggestions.append(f"共有 {invalid_count} 个问题需要修复")

    # 语义级AI评审（叠加在结构规则之上，AI未启用时跳过）
    ai_analysis = _ai_validate_semantics(elements_to_check, relationships_to_check) if use_ai else None
    if ai_analysis:
        for issue in ai_analysis.get('issues', []):
            if not isinstance(issue, dict) or not issue.get('message'):
                continue
            warnings.append({
                'type': 'semantic',
                'severity': str(issue.get('severity', 'warning')).lower(),
                'message': issue['message'],
                'suggestion': issue.get('suggestion', '')
            })
            if issue.get('suggestion'):
                suggestions.append(issue['suggestion'])
        if ai_analysis.get('summary'):
            suggestions.append(ai_analysis['summary'])

    return {
        'valid': len(errors) == 0,
        'valid_count': valid_count,
        'invalid_count': invalid_count,
        'errors': errors,
        'warnings': warnings,
        'suggestions': suggestions,
        'report': f"校验完成: {valid_count} 个有效元素, {invalid_count} 个问题",
        'ai_analysis': ai_analysis or {'summary': ''}
    }

def apply_layout(view, algorithm='tree'):
    """应用布局算法"""
    elements = view.get('elements', [])
    
    if algorithm == 'tree':
        # 树形布局
        x, y = 100, 100
        row_height = 120
        col_width = 180
        
        for i, elem in enumerate(elements):
            col = i % 4
            row = i // 4
            elem['x'] = x + col * col_width
            elem['y'] = y + row * row_height
    
    elif algorithm == 'flow':
        # 流式布局
        x, y = 100, 100
        spacing = 30
        
        for i, elem in enumerate(elements):
            elem['x'] = x
            elem['y'] = y + i * (elem.get('height', 60) + spacing)
    
    elif algorithm == 'grid':
        # 网格布局
        x, y = 100, 100
        cols = 3
        spacing_x = 200
        spacing_y = 150
        
        for i, elem in enumerate(elements):
            col = i % cols
            row = i // cols
            elem['x'] = x + col * spacing_x
            elem['y'] = y + row * spacing_y
    
    elif algorithm == 'circle':
        # 环形布局
        center_x, center_y = 400, 300
        radius = 200
        count = len(elements)
        
        for i, elem in enumerate(elements):
            angle = (i / count) * 2 * 3.14159
            elem['x'] = center_x + radius * math.cos(angle) - (elem.get('width', 100) / 2)
            elem['y'] = center_y + radius * math.sin(angle) - (elem.get('height', 60) / 2)
    
    return {'elements': elements}

def generate_explanation(model, view_id, element_id, question):
    """生成UML解释"""
    view = None
    if view_id:
        view = next((v for v in model.views if v['uuid'] == view_id), None)
    
    element = None
    if element_id:
        element = next((e for e in model.elements if e['uuid'] == element_id), None)
        if not element and view:
            element = next((e for e in view.get('elements', []) if e['uuid'] == element_id), None)
    
    result = {
        'question': question,
        'explanation': '',
        'details': []
    }
    
    if element:
        # 解释单个元素
        result['explanation'] = f"元素「{element['name']}」是一个{element['type']}类型的UML元素。"
        
        if element.get('description'):
            result['explanation'] += f"描述：{element['description']}"
        
        if element.get('attributes'):
            result['details'].append({
                'title': '属性',
                'content': ', '.join(element['attributes'])
            })
        
        if element.get('methods'):
            result['details'].append({
                'title': '方法',
                'content': ', '.join(element['methods'])
            })
        
        # 查找相关关系
        related_rels = []
        for rel in model.relationships:
            if rel['source'] == element['uuid']:
                target_elem = next((e for e in model.elements if e['uuid'] == rel['target']), None)
                if target_elem:
                    related_rels.append(f"通过{rel['type']}关系连接到「{target_elem['name']}」")
            elif rel['target'] == element['uuid']:
                source_elem = next((e for e in model.elements if e['uuid'] == rel['source']), None)
                if source_elem:
                    related_rels.append(f"「{source_elem['name']}」通过{rel['type']}关系连接到本元素")
        
        if related_rels:
            result['details'].append({
                'title': '关联关系',
                'content': '; '.join(related_rels)
            })
    
    elif view:
        # 解释整个视图
        elem_count = len(view.get('elements', []))
        rel_count = len(view.get('relationships', []))
        
        result['explanation'] = f"这是一个{UML_VIEW_TYPES.get(view['type'], view['type'])}视图，包含{elem_count}个元素和{rel_count}条关系。"
        
        if view.get('elements'):
            elem_names = [e['name'] for e in view['elements'][:5]]
            if len(view['elements']) > 5:
                elem_names.append(f"...等{len(view['elements'])}个元素")
            result['details'].append({
                'title': '包含元素',
                'content': ', '.join(elem_names)
            })
    
    else:
        # 解释整个模型
        result['explanation'] = f"本模型包含{len(model.elements)}个元素和{len(model.relationships)}条关系，共有{len(model.views)}个视图。"
    
    if question:
        # 根据问题生成针对性回答
        if '什么' in question or '是什么' in question:
            result['explanation'] = f"根据您的问题「{question}」，{result['explanation']}"
        elif '如何' in question or '怎样' in question:
            result['explanation'] = f"关于「{question}」，{result['explanation']}。建议您查看相关元素的详细属性和关系。"
        elif '为什么' in question:
            result['explanation'] = f"针对「{question}」，{result['explanation']}。具体原因需要结合业务上下文分析。"
    
    return result



# ============ ArchiMate 生成（AI 智能体用：LLM 优先 + 规则回退） ============
ARCH_LAYERS = ('business', 'application', 'technology')

def generate_archimate_from_prompt(prompt):
    """业务描述 → ArchiMate 原始数据 {elements:[{type,name,layer}], relationships:[{source,target,type}]}。
    返回 (elements_raw, relationships_raw)；LLM 未启用/失败回退 _mock_archimate。"""
    ai = _ai_generate_archimate(prompt)
    if ai is not None:
        return ai
    return _mock_archimate(prompt)


def _ai_generate_archimate(prompt):
    if not ai_service_config.enabled:
        return None
    messages = [
        {'role': 'system', 'content': ARCHIMATE_GENERATE_SYSTEM_PROMPT},
        {'role': 'user', 'content': prompt}
    ]
    result = AIService.chat_completion(messages, max_tokens=4096, temperature=0.3)
    if not isinstance(result, dict) or 'error' in result:
        return None
    try:
        content = result['choices'][0]['message']['content']
    except (KeyError, IndexError, TypeError):
        return None
    data = _ai_parse_json_response(content)
    if not isinstance(data, dict) or not isinstance(data.get('elements'), list):
        return None
    rels = data.get('relationships')
    if not isinstance(rels, list):
        rels = []
    return data['elements'], rels


def _mock_archimate(prompt):
    """AI 不可用时的 ArchiMate 兜底：根据业务文本粗分层（尽力，提示用户可重生成）。"""
    text = (prompt or '')
    words = []
    import re
    seg = re.split(r'[，。；、,.?!\n\s]+', text)
    for s in seg:
        s = s.strip()
        if not s or len(s) < 2:
            continue
        words.append(s)
    core = words[0][:14] if words else '核心业务'
    theme = words[1][:14] if len(words) > 1 else '支撑业务'
    elements = [
        {'type': 'process', 'name': f'{core}主流程', 'layer': 'business', 'description': ''},
        {'type': 'service', 'name': f'{core}服务', 'layer': 'business', 'description': ''},
        {'type': 'process', 'name': f'{theme}协同', 'layer': 'business', 'description': ''},
        {'type': 'component', 'name': f'{core}应用', 'layer': 'application', 'description': ''},
        {'type': 'component', 'name': '集成网关', 'layer': 'application', 'description': ''},
        {'type': 'node', 'name': '业务数据库', 'layer': 'technology', 'description': ''},
        {'type': 'node', 'name': '消息中间件', 'layer': 'technology', 'description': ''},
    ]
    rels = [
        {'source': f'{core}主流程', 'target': f'{core}服务', 'type': 'serving'},
        {'source': f'{core}应用', 'target': f'{core}服务', 'type': 'realization'},
        {'source': '集成网关', 'target': f'{theme}协同', 'type': 'realization'},
        {'source': f'{core}主流程', 'target': f'{theme}协同', 'type': 'flow'},
        {'source': '业务数据库', 'target': f'{core}应用', 'type': 'serving'},
        {'source': '消息中间件', 'target': '集成网关', 'type': 'serving'},
    ]
    return elements, rels
