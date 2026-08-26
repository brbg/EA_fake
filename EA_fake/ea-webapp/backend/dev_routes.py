"""研发管理 API（Blueprint）：需求/测试用例/缺陷/任务 CRUD + AI 生成。

按「拆巨石」计划从 app.py 抽出，共享状态从 core.py、实体类从 models.py 导入。
"""
import uuid
import datetime
from flask import Blueprint, request, jsonify
from models import Requirement, TestCase, Defect, Task
from core import (
    _require_user_id, _model_owned_by, load_model_from_cache,
    _load_dev_entries, _save_dev_entries,
)

dev_bp = Blueprint('dev', __name__)


def ai_generate_requirements(project_id, requirement_text):
    """AI生成需求"""
    requirements = []
    
    # 分析需求文本
    lines = requirement_text.split('\n')
    for i, line in enumerate(lines):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        
        # 识别需求类型
        req_type = 'functional'
        if any(keyword in line.lower() for keyword in ['性能', '安全', '可靠', '扩展', '兼容']):
            req_type = 'non_functional'
        elif '用户故事' in line or '作为' in line:
            req_type = 'user_story'
        elif any(keyword in line.lower() for keyword in ['技术', '架构', '接口', '数据库']):
            req_type = 'technical'
        
        # 确定优先级
        priority = 'medium'
        if any(keyword in line.lower() for keyword in ['紧急', '关键', '必须', '核心']):
            priority = 'critical'
        elif any(keyword in line.lower() for keyword in ['重要', '优先', '主要']):
            priority = 'high'
        elif any(keyword in line.lower() for keyword in ['次要', '可选', '未来']):
            priority = 'low'
        
        req = Requirement(project_id, line[:50], line, req_type)
        req.priority = priority
        requirements.append(req)
    
    return requirements

def ai_generate_test_cases(project_id, req_id, requirement_text):
    """AI生成测试用例"""
    test_cases = []
    
    # 基础测试用例
    base_case = TestCase(project_id, '正常流程测试', '验证正常业务流程', 'normal')
    base_case.req_id = req_id
    base_case.add_step(1, '执行正常业务流程', '流程正常执行')
    base_case.add_step(2, '验证结果', '结果符合预期')
    test_cases.append(base_case)
    
    # 边界测试用例
    boundary_case = TestCase(project_id, '边界值测试', '验证边界条件', 'complex')
    boundary_case.req_id = req_id
    boundary_case.add_step(1, '输入边界值', '系统正常处理')
    boundary_case.add_step(2, '验证边界值+1', '系统正常处理')
    boundary_case.add_step(3, '验证边界值-1', '系统正常处理')
    test_cases.append(boundary_case)
    
    # 异常测试用例
    exception_case = TestCase(project_id, '异常场景测试', '验证异常处理', 'complex')
    exception_case.req_id = req_id
    exception_case.add_step(1, '输入异常数据', '系统给出正确提示')
    exception_case.add_step(2, '验证错误处理', '系统正确处理异常')
    test_cases.append(exception_case)
    
    return test_cases

def ai_plan_tasks(project_id, requirements):
    """AI规划任务"""
    tasks = []
    
    for req in requirements:
        # 为每个需求创建开发任务
        dev_task = Task(project_id, f'开发：{req.name}', f'实现需求：{req.description}', 'development')
        dev_task.req_id = req.id
        dev_task.priority = req.priority
        dev_task.work_hours = 8
        dev_task.status = 'pending'
        
        # 创建测试任务
        test_task = Task(project_id, f'测试：{req.name}', f'测试需求：{req.description}', 'testing')
        test_task.req_id = req.id
        test_task.priority = req.priority
        test_task.work_hours = 4
        test_task.status = 'pending'
        
        # 添加依赖关系：测试任务依赖开发任务
        test_task.add_dependency(dev_task.id, 'finish_to_start')
        
        tasks.extend([dev_task, test_task])
    
    return tasks
@dev_bp.route('/api/v1/project/<project_id>/requirement/ai/generate', methods=['POST'])
def ai_generate_requirements_api(project_id):
    """AI生成需求"""
    user_id = _require_user_id()
    if user_id is None:
        return jsonify({'error': '未登录'}), 401

    model = load_model_from_cache(project_id)
    if not _model_owned_by(model, user_id):
        return jsonify({'error': '项目不存在'}), 404

    data = request.json
    requirement_text = data.get('requirement_text', '')

    requirements = ai_generate_requirements(project_id, requirement_text)

    # 保存需求（持久化）
    entries = _load_dev_entries('req', project_id)
    for req in requirements:
        req.user_id = user_id
        entries.append(req.to_dict())
    _save_dev_entries('req', project_id, entries)

    return jsonify({
        'message': 'AI需求生成成功',
        'requirements': [r.to_dict() for r in requirements],
        'count': len(requirements)
    })

@dev_bp.route('/api/v1/project/<project_id>/requirement', methods=['GET', 'POST', 'PUT', 'DELETE'])
def manage_requirements(project_id):
    """需求管理"""
    user_id = _require_user_id()
    if user_id is None:
        return jsonify({'error': '未登录'}), 401

    model = load_model_from_cache(project_id)
    if not _model_owned_by(model, user_id):
        return jsonify({'error': '项目不存在'}), 404

    if request.method == 'GET':
        # 获取需求列表
        entries = _load_dev_entries('req', project_id)
        return jsonify({'requirements': entries})

    elif request.method == 'POST':
        # 创建需求
        data = request.json
        req = Requirement(project_id, data.get('name', ''), data.get('description', ''), data.get('type', 'functional'))
        req.user_id = user_id
        req.assignee_id = data.get('assignee_id', '')
        req.priority = data.get('priority', 'medium')
        req.status = data.get('status', 'draft')

        entries = _load_dev_entries('req', project_id)
        entry = req.to_dict()
        entries.append(entry)
        _save_dev_entries('req', project_id, entries)

        return jsonify({
            'message': '需求创建成功',
            'requirement': entry
        })

    elif request.method == 'PUT':
        # 更新需求
        data = request.json
        req_id = data.get('id')

        entries = _load_dev_entries('req', project_id)
        entry = next((e for e in entries if e.get('id') == req_id), None)
        if entry is None:
            return jsonify({'error': '需求不存在'}), 404

        if 'name' in data:
            entry['name'] = data['name']
        if 'description' in data:
            entry['description'] = data['description']
        if 'type' in data:
            entry['type'] = data['type']
        if 'priority' in data:
            entry['priority'] = data['priority']
        if 'status' in data:
            entry['status'] = data['status']
        if 'assignee_id' in data:
            entry['assignee_id'] = data['assignee_id']

        entry['updated_at'] = datetime.datetime.now().isoformat()
        _save_dev_entries('req', project_id, entries)

        return jsonify({
            'message': '需求更新成功',
            'requirement': entry
        })

    elif request.method == 'DELETE':
        # 删除需求
        req_id = (request.json or {}).get('id') or request.args.get('id')

        entries = _load_dev_entries('req', project_id)
        entry = next((e for e in entries if e.get('id') == req_id), None)
        if entry is None:
            return jsonify({'error': '需求不存在'}), 404

        entries = [e for e in entries if e.get('id') != req_id]
        _save_dev_entries('req', project_id, entries)

        return jsonify({'message': '需求删除成功'})

@dev_bp.route('/api/v1/project/<project_id>/requirement/list', methods=['GET'])
def get_requirements_list(project_id):
    """获取需求列表"""
    user_id = _require_user_id()
    if user_id is None:
        return jsonify({'error': '未登录'}), 401

    model = load_model_from_cache(project_id)
    if not _model_owned_by(model, user_id):
        return jsonify({'error': '项目不存在'}), 404

    # 获取筛选参数
    status = request.args.get('status')
    priority = request.args.get('priority')
    assignee_id = request.args.get('assignee_id')

    requirements = _load_dev_entries('req', project_id)

    # 应用筛选
    if status:
        requirements = [e for e in requirements if e.get('status') == status]
    if priority:
        requirements = [e for e in requirements if e.get('priority') == priority]
    if assignee_id:
        requirements = [e for e in requirements if e.get('assignee_id') == assignee_id]

    return jsonify({
        'requirements': requirements,
        'total': len(requirements)
    })

@dev_bp.route('/api/v1/project/<project_id>/testcase/ai/generate', methods=['POST'])
def ai_generate_test_cases_api(project_id):
    """AI生成测试用例"""
    user_id = _require_user_id()
    if user_id is None:
        return jsonify({'error': '未登录'}), 401

    model = load_model_from_cache(project_id)
    if not _model_owned_by(model, user_id):
        return jsonify({'error': '项目不存在'}), 404

    data = request.json
    req_id = data.get('req_id')
    requirement_text = data.get('requirement_text', '')

    test_cases = ai_generate_test_cases(project_id, req_id, requirement_text)

    # 保存测试用例（持久化）
    entries = _load_dev_entries('tc', project_id)
    for case in test_cases:
        case.assignee_id = user_id
        entries.append(case.to_dict())
    _save_dev_entries('tc', project_id, entries)

    return jsonify({
        'message': 'AI测试用例生成成功',
        'test_cases': [c.to_dict() for c in test_cases],
        'count': len(test_cases)
    })

@dev_bp.route('/api/v1/project/<project_id>/testcase', methods=['GET', 'POST', 'PUT', 'DELETE'])
def manage_test_cases(project_id):
    """测试用例管理"""
    user_id = _require_user_id()
    if user_id is None:
        return jsonify({'error': '未登录'}), 401

    model = load_model_from_cache(project_id)
    if not _model_owned_by(model, user_id):
        return jsonify({'error': '项目不存在'}), 404

    if request.method == 'GET':
        # 获取测试用例列表
        entries = _load_dev_entries('tc', project_id)
        return jsonify({'test_cases': entries})

    elif request.method == 'POST':
        # 创建测试用例
        data = request.json
        case = TestCase(project_id, data.get('name', ''), data.get('description', ''), data.get('level', 'normal'))
        case.req_id = data.get('req_id')
        case.use_case_id = data.get('use_case_id')
        case.assignee_id = data.get('assignee_id', '')

        entries = _load_dev_entries('tc', project_id)
        entry = case.to_dict()
        entries.append(entry)
        _save_dev_entries('tc', project_id, entries)

        return jsonify({
            'message': '测试用例创建成功',
            'test_case': entry
        })

    elif request.method == 'PUT':
        # 更新测试用例
        data = request.json
        case_id = data.get('id')

        entries = _load_dev_entries('tc', project_id)
        entry = next((e for e in entries if e.get('id') == case_id), None)
        if entry is None:
            return jsonify({'error': '测试用例不存在'}), 404

        if 'name' in data:
            entry['name'] = data['name']
        if 'description' in data:
            entry['description'] = data['description']
        if 'status' in data:
            entry['status'] = data['status']
        if 'level' in data:
            entry['level'] = data['level']
        if 'req_id' in data:
            entry['req_id'] = data['req_id']
        if 'assignee_id' in data:
            entry['assignee_id'] = data['assignee_id']

        entry['updated_at'] = datetime.datetime.now().isoformat()
        _save_dev_entries('tc', project_id, entries)

        return jsonify({
            'message': '测试用例更新成功',
            'test_case': entry
        })

    elif request.method == 'DELETE':
        # 删除测试用例
        case_id = (request.json or {}).get('id') or request.args.get('id')

        entries = _load_dev_entries('tc', project_id)
        entry = next((e for e in entries if e.get('id') == case_id), None)
        if entry is None:
            return jsonify({'error': '测试用例不存在'}), 404

        entries = [e for e in entries if e.get('id') != case_id]
        _save_dev_entries('tc', project_id, entries)

        return jsonify({'message': '测试用例删除成功'})

@dev_bp.route('/api/v1/project/<project_id>/testcase/list', methods=['GET'])
def get_test_cases_list(project_id):
    """获取测试用例列表"""
    user_id = _require_user_id()
    if user_id is None:
        return jsonify({'error': '未登录'}), 401

    model = load_model_from_cache(project_id)
    if not _model_owned_by(model, user_id):
        return jsonify({'error': '项目不存在'}), 404

    # 获取筛选参数
    req_id = request.args.get('req_id')
    level = request.args.get('level')
    status = request.args.get('status')

    test_cases = _load_dev_entries('tc', project_id)

    # 应用筛选
    if req_id:
        test_cases = [c for c in test_cases if c.get('req_id') == req_id]
    if level:
        test_cases = [c for c in test_cases if c.get('level') == level]
    if status:
        test_cases = [c for c in test_cases if c.get('status') == status]

    return jsonify({
        'test_cases': test_cases,
        'total': len(test_cases)
    })

@dev_bp.route('/api/v1/project/<project_id>/defect', methods=['GET', 'POST', 'PUT', 'DELETE'])
def manage_defects(project_id):
    """缺陷管理"""
    user_id = _require_user_id()
    if user_id is None:
        return jsonify({'error': '未登录'}), 401

    model = load_model_from_cache(project_id)
    if not _model_owned_by(model, user_id):
        return jsonify({'error': '项目不存在'}), 404

    if request.method == 'GET':
        # 获取缺陷列表
        entries = _load_dev_entries('def', project_id)
        return jsonify({'defects': entries})

    elif request.method == 'POST':
        # 创建缺陷
        data = request.json
        defect = Defect(project_id, data.get('name', ''), data.get('description', ''), data.get('level', 'medium'))
        defect.case_id = data.get('case_id')
        defect.req_id = data.get('req_id')
        defect.element_id = data.get('element_id')
        defect.assignee_id = data.get('assignee_id', '')
        defect.reproduce_step = data.get('reproduce_step', '')
        defect.actual_result = data.get('actual_result', '')
        defect.expected_result = data.get('expected_result', '')

        entries = _load_dev_entries('def', project_id)
        entry = defect.to_dict()
        entries.append(entry)
        _save_dev_entries('def', project_id, entries)

        return jsonify({
            'message': '缺陷创建成功',
            'defect': entry
        })

    elif request.method == 'PUT':
        # 更新缺陷
        data = request.json
        defect_id = data.get('id')

        entries = _load_dev_entries('def', project_id)
        entry = next((e for e in entries if e.get('id') == defect_id), None)
        if entry is None:
            return jsonify({'error': '缺陷不存在'}), 404

        if 'name' in data:
            entry['name'] = data['name']
        if 'description' in data:
            entry['description'] = data['description']
        if 'status' in data:
            entry['status'] = data['status']
        if 'level' in data:
            entry['level'] = data['level']
        if 'assignee_id' in data:
            entry['assignee_id'] = data['assignee_id']

        entry['updated_at'] = datetime.datetime.now().isoformat()
        _save_dev_entries('def', project_id, entries)

        return jsonify({
            'message': '缺陷更新成功',
            'defect': entry
        })

    elif request.method == 'DELETE':
        # 删除缺陷
        defect_id = (request.json or {}).get('id') or request.args.get('id')

        entries = _load_dev_entries('def', project_id)
        entry = next((e for e in entries if e.get('id') == defect_id), None)
        if entry is None:
            return jsonify({'error': '缺陷不存在'}), 404

        entries = [e for e in entries if e.get('id') != defect_id]
        _save_dev_entries('def', project_id, entries)

        return jsonify({'message': '缺陷删除成功'})

@dev_bp.route('/api/v1/project/<project_id>/task/ai/plan', methods=['POST'])
def ai_plan_tasks_api(project_id):
    """AI任务规划"""
    user_id = _require_user_id()
    if user_id is None:
        return jsonify({'error': '未登录'}), 401

    model = load_model_from_cache(project_id)
    if not _model_owned_by(model, user_id):
        return jsonify({'error': '项目不存在'}), 404

    data = request.json
    req_ids = data.get('req_ids', [])

    # 从持久化读取需求（重建 Requirement 对象供 ai_plan_tasks 使用）
    req_entries = {r.get('id'): r for r in _load_dev_entries('req', project_id)}
    requirements = []
    for rid in req_ids:
        d = req_entries.get(rid)
        if d is None:
            continue
        req = Requirement(d.get('project_id', project_id), d.get('name', ''), d.get('description', ''), d.get('type', 'functional'))
        req.id = d.get('id')
        req.priority = d.get('priority', 'medium')
        requirements.append(req)

    # 规划任务
    tasks = ai_plan_tasks(project_id, requirements)

    # 保存任务（持久化）
    entries = _load_dev_entries('task', project_id)
    for task in tasks:
        task.assignee_id = user_id
        entries.append(task.to_dict())
    _save_dev_entries('task', project_id, entries)

    return jsonify({
        'message': 'AI任务规划成功',
        'tasks': [t.to_dict() for t in tasks],
        'count': len(tasks)
    })

@dev_bp.route('/api/v1/project/<project_id>/task', methods=['GET', 'POST', 'PUT', 'DELETE'])
def manage_tasks(project_id):
    """任务管理"""
    user_id = _require_user_id()
    if user_id is None:
        return jsonify({'error': '未登录'}), 401

    model = load_model_from_cache(project_id)
    if not _model_owned_by(model, user_id):
        return jsonify({'error': '项目不存在'}), 404

    if request.method == 'GET':
        # 获取任务列表
        entries = _load_dev_entries('task', project_id)
        return jsonify({'tasks': entries})

    elif request.method == 'POST':
        # 创建任务
        data = request.json
        task = Task(project_id, data.get('name', ''), data.get('description', ''), data.get('type', 'development'))
        task.req_id = data.get('req_id')
        task.element_id = data.get('element_id')
        task.assignee_id = data.get('assignee_id', '')
        task.priority = data.get('priority', 'medium')
        task.status = data.get('status', 'pending')
        task.work_hours = int(data.get('work_hours') or 0)
        task.plan_start_time = data.get('plan_start_time')
        task.plan_end_time = data.get('plan_end_time')

        entries = _load_dev_entries('task', project_id)
        entry = task.to_dict()
        entries.append(entry)
        _save_dev_entries('task', project_id, entries)

        return jsonify({
            'message': '任务创建成功',
            'task': entry
        })

    elif request.method == 'PUT':
        # 更新任务
        data = request.json
        task_id = data.get('id')

        entries = _load_dev_entries('task', project_id)
        entry = next((e for e in entries if e.get('id') == task_id), None)
        if entry is None:
            return jsonify({'error': '任务不存在'}), 404

        if 'name' in data:
            entry['name'] = data['name']
        if 'description' in data:
            entry['description'] = data['description']
        if 'status' in data:
            entry['status'] = data['status']
        if 'progress' in data:
            entry['progress'] = data['progress']
        if 'assignee_id' in data:
            entry['assignee_id'] = data['assignee_id']
        if 'type' in data:
            entry['type'] = data['type']
        if 'priority' in data:
            entry['priority'] = data['priority']
        if 'work_hours' in data:
            entry['work_hours'] = int(data['work_hours'] or 0)

        entry['updated_at'] = datetime.datetime.now().isoformat()
        _save_dev_entries('task', project_id, entries)

        return jsonify({
            'message': '任务更新成功',
            'task': entry
        })

    elif request.method == 'DELETE':
        # 删除任务
        task_id = (request.json or {}).get('id') or request.args.get('id')

        entries = _load_dev_entries('task', project_id)
        entry = next((e for e in entries if e.get('id') == task_id), None)
        if entry is None:
            return jsonify({'error': '任务不存在'}), 404

        entries = [e for e in entries if e.get('id') != task_id]
        _save_dev_entries('task', project_id, entries)

        return jsonify({'message': '任务删除成功'})

@dev_bp.route('/api/v1/project/<project_id>/task/list', methods=['GET'])
def get_tasks_list(project_id):
    """获取任务列表"""
    user_id = _require_user_id()
    if user_id is None:
        return jsonify({'error': '未登录'}), 401

    model = load_model_from_cache(project_id)
    if not _model_owned_by(model, user_id):
        return jsonify({'error': '项目不存在'}), 404

    # 获取筛选参数
    status = request.args.get('status')
    assignee_id = request.args.get('assignee_id')
    priority = request.args.get('priority')

    tasks = _load_dev_entries('task', project_id)

    # 应用筛选
    if status:
        tasks = [t for t in tasks if t.get('status') == status]
    if assignee_id:
        tasks = [t for t in tasks if t.get('assignee_id') == assignee_id]
    if priority:
        tasks = [t for t in tasks if t.get('priority') == priority]

    return jsonify({
        'tasks': tasks,
        'total': len(tasks)
    })
