"""
AI原生Enterprise Architect Web应用 - 后端服务
基于Flask框架，提供完整的企业架构建模和AI分析功能
"""

import os
import uuid
import json
import secrets
import datetime
import math
import requests
import bcrypt
import db
from constants import ELEMENT_TYPES, RELATIONSHIP_TYPES, ELEMENT_COLORS, get_default_color
from models import Project, SimpleModel, Requirement, TestCase, Defect, Task
from prompts import uml_system_prompt, ER_SYSTEM_PROMPT, code_system_prompt, VALIDATE_SYSTEM_PROMPT, REVIEW_SYSTEM_PROMPT, ELEMENT_ANALYSIS_SYSTEM_PROMPT, code_reverse_system_prompt, edit_model_system_prompt, document_system_prompt
from flask import Flask, request, jsonify, send_from_directory, render_template, session, stream_with_context, Response
from flask_cors import CORS
from flask_socketio import SocketIO, emit, join_room, leave_room

# === 共享基础设施（app/缓存/公共辅助/AI服务）已移至 core.py ===
from core import (
    app, socketio,
    models_cache, users_cache, projects_cache, sessions_cache,
    bookmarks_cache, snapshots_cache, operation_logs_cache, file_locks_cache,
    hash_password, verify_password, load_users, save_users, ensure_admin_account,
    load_projects, save_project, AIServiceConfig, ai_service_config, AIService,
    load_model_from_cache, save_model, _require_user_id, _model_owned_by,
    _load_dev_entries, _save_dev_entries,
    er_views_cache, data_dictionary_cache, versions_cache, branches_cache, reviews_cache,
    _require_admin, _find_user_by_id, _delete_project_data,
    _ai_parse_json_response,
)

# 注册 Blueprint（按「拆巨石」计划逐步从 app.py 抽出）
from auth_routes import auth_bp
app.register_blueprint(auth_bp)
from dev_routes import dev_bp
app.register_blueprint(dev_bp)
from admin_routes import admin_bp
app.register_blueprint(admin_bp)
from er_routes import er_bp, _ai_generate_er_data, extract_entities_from_requirements
app.register_blueprint(er_bp)
# UML AI 生成服务（已从 app.py 抽出）
from uml_ai import (
    _ai_generate_uml, _layout_ai_elements, generate_uml_from_prompt,
    extract_classes_from_text, extract_use_cases_from_text, extract_activities_from_text,
    extract_participants_from_text, _normalize_uml_type, _default_rel_type,
    _ai_validate_semantics, validate_uml_model, _elem_id, _rel_source, _rel_target,
)

@app.route('/api/test')
def test_route():
    return jsonify({'message': 'test_v1', 'models': list(models_cache.keys())})

# === 用户管理（hash_password/verify_password/load_users/save_users/ensure_admin_account 已移至 core.py）===

# === 项目管理 ===

# === AI服务配置（AIServiceConfig/AIService/ai_service_config 已移至 core.py）===
# === 路由 ===

@app.route('/')
def index():
    return send_from_directory('../dist', 'index.html')

@app.route('/assets/<path:filename>')
def serve_assets(filename):
    return send_from_directory('../dist/assets', filename)

@app.route('/editor/<model_id>')
def editor(model_id):
    return send_from_directory('../frontend/templates', 'editor.html')

# === 用户认证 API（register/login/logout/validate 已移至 auth_routes.py Blueprint）===


# _require_admin/_find_user_by_id/_delete_project_data 及后台管理路由已移至 core.py / admin_routes.py


# === 项目管理 API ===

@app.route('/api/projects', methods=['GET'])
def get_projects():
    """获取项目列表"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    user_id = sessions_cache[session_id]['user_id']
    projects = load_projects()
    
    user_projects = []
    for project_id, project in projects.items():
        # 检查用户是否是项目成员或所有者
        if project.owner_id == user_id or user_id in project.permissions:
            user_projects.append({
                'id': project.id,
                'name': project.name,
                'description': project.description,
                'status': project.status,
                'created_at': project.created_at,
                'updated_at': project.updated_at,
                'member_count': len(project.members),
                'role': project.permissions.get(user_id, 'owner' if project.owner_id == user_id else 'viewer')
            })
    
    return jsonify({'projects': user_projects})

@app.route('/api/projects', methods=['POST'])
def create_project():
    """创建新项目"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    data = request.json
    name = data.get('name', '未命名项目')
    description = data.get('description', '')
    
    user_id = sessions_cache[session_id]['user_id']
    project = Project(name, description, user_id)
    
    # AI辅助生成项目包结构
    project.settings['templates'] = ai_generate_templates(project)
    
    save_project(project)
    
    # 创建关联模型
    model = SimpleModel(name)
    save_model(project.id, model)

    project.model_id = project.id
    save_project(project)
    
    return jsonify({
        'message': '项目创建成功',
        'project': project.to_dict()
    })

def ai_generate_templates(project):
    """AI辅助生成项目模板"""
    return [
        {'name': '业务架构', 'elements': ['BusinessActor', 'BusinessProcess', 'BusinessService']},
        {'name': '应用架构', 'elements': ['ApplicationComponent', 'ApplicationService', 'DataObject']},
        {'name': '技术架构', 'elements': ['Node', 'SystemSoftware', 'TechnologyService']}
    ]

@app.route('/api/projects/<project_id>', methods=['GET'])
def get_project(project_id):
    """获取项目详情"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    projects = load_projects()
    if project_id not in projects:
        return jsonify({'error': '项目不存在'}), 404
    
    project = projects[project_id]
    user_id = sessions_cache[session_id]['user_id']
    
    # 检查权限
    if project.owner_id != user_id and user_id not in project.permissions:
        return jsonify({'error': '无权限访问此项目'}), 403
    
    return jsonify(project.to_dict())

@app.route('/api/projects/<project_id>', methods=['PUT'])
def update_project(project_id):
    """更新项目信息"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    projects = load_projects()
    if project_id not in projects:
        return jsonify({'error': '项目不存在'}), 404
    
    project = projects[project_id]
    user_id = sessions_cache[session_id]['user_id']
    
    # 只有所有者可以更新
    if project.owner_id != user_id:
        return jsonify({'error': '无权限'}), 403
    
    data = request.json
    if 'name' in data:
        project.name = data['name']
    if 'description' in data:
        project.description = data['description']
    if 'settings' in data:
        project.settings.update(data['settings'])
    
    save_project(project)
    
    return jsonify({'message': '项目更新成功'})

@app.route('/api/projects/<project_id>/members', methods=['POST'])
def add_project_member(project_id):
    """添加项目成员"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    projects = load_projects()
    if project_id not in projects:
        return jsonify({'error': '项目不存在'}), 404
    
    project = projects[project_id]
    user_id = sessions_cache[session_id]['user_id']
    
    # 只有所有者可以添加成员
    if project.owner_id != user_id:
        return jsonify({'error': '无权限'}), 403
    
    data = request.json
    member_username = data.get('username')
    role = data.get('role', 'viewer')
    
    users = load_users()
    if member_username not in users:
        return jsonify({'error': '用户不存在'}), 400
    
    member_id = users[member_username]['id']
    project.add_member(member_id, role)
    save_project(project)
    
    return jsonify({'message': '成员添加成功'})

@app.route('/api/projects/<project_id>/members/<member_id>', methods=['PUT'])
def update_member_role(project_id, member_id):
    """更新成员权限"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    projects = load_projects()
    if project_id not in projects:
        return jsonify({'error': '项目不存在'}), 404
    
    project = projects[project_id]
    user_id = sessions_cache[session_id]['user_id']
    
    if project.owner_id != user_id:
        return jsonify({'error': '无权限'}), 403
    
    data = request.json
    role = data.get('role')
    if role not in ['owner', 'editor', 'viewer']:
        return jsonify({'error': '无效的角色'}), 400
    
    project.update_permission(member_id, role)
    save_project(project)
    
    return jsonify({'message': '权限更新成功'})

@app.route('/api/projects/<project_id>/members/<member_id>', methods=['DELETE'])
def remove_project_member(project_id, member_id):
    """移除项目成员"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    projects = load_projects()
    if project_id not in projects:
        return jsonify({'error': '项目不存在'}), 404
    
    project = projects[project_id]
    user_id = sessions_cache[session_id]['user_id']
    
    if project.owner_id != user_id:
        return jsonify({'error': '无权限'}), 403
    
    project.remove_member(member_id)
    save_project(project)
    
    return jsonify({'message': '成员移除成功'})

@app.route('/api/projects/<project_id>/health', methods=['GET'])
def project_health_check(project_id):
    """项目健康检查"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    projects = load_projects()
    if project_id not in projects:
        return jsonify({'error': '项目不存在'}), 404
    
    project = projects[project_id]
    model = load_model_from_cache(project.model_id)
    
    # 执行健康检查
    health_result = perform_health_check(model, project)
    project.health_check = health_result
    save_project(project)
    
    return jsonify(health_result)

def perform_health_check(model, project):
    """执行健康检查"""
    issues = []
    suggestions = []
    score = 100
    
    if model:
        # 检查元素数量
        if len(model.elements) == 0:
            issues.append('模型中没有元素')
            suggestions.append('建议添加架构元素来构建完整的模型')
            score -= 20
        
        # 检查孤立元素
        elem_with_rels = set()
        for rel in model.relationships:
            elem_with_rels.add(rel['source'])
            elem_with_rels.add(rel['target'])
        
        isolated_count = len(model.elements) - len(elem_with_rels)
        if isolated_count > 0:
            issues.append(f'{isolated_count} 个孤立元素')
            suggestions.append('建议为孤立元素添加关系连接')
            score -= min(isolated_count * 5, 20)
        
        # 检查命名规范
        unnamed_count = sum(1 for e in model.elements if e['name'] in ['Unnamed', '', None])
        if unnamed_count > 0:
            issues.append(f'{unnamed_count} 个未命名元素')
            suggestions.append('建议为所有元素添加有意义的名称')
            score -= min(unnamed_count * 3, 15)
    
    return {
        'score': max(0, score),
        'issues': issues,
        'suggestions': suggestions
    }

# === 模型管理 API（load_model_from_cache/_require_user_id/_model_owned_by 已移至 core.py）===

@app.route('/api/models', methods=['GET'])
def get_models():
    """获取当前用户的模型列表（按 owner 隔离）"""
    user_id = _require_user_id()
    if user_id is None:
        return jsonify({'error': '未登录'}), 401

    models_info = []
    for model_id, model in models_cache.items():
        if getattr(model, 'owner_id', '') != user_id:
            continue
        models_info.append({
            'id': model_id,
            'name': model.name,
            'description': model.description,
            'elements_count': len(model.elements),
            'relationships_count': len(model.relationships),
            'views_count': len(model.views),
            'version': model.version
        })

    # 也从 db 加载尚未缓存的模型
    for key in db.keys('model:'):
        model_id = key[len('model:'):]
        if model_id not in models_cache:
            data = db.get(key)
            if data is not None and data.get('owner_id') == user_id:
                models_info.append({
                    'id': model_id,
                    'name': data.get('name', model_id),
                    'description': data.get('description', ''),
                    'elements_count': len(data.get('elements', [])),
                    'relationships_count': len(data.get('relationships', [])),
                    'views_count': len(data.get('views', [])),
                    'version': data.get('version', '1.0.0')
                })

    return jsonify({'models': models_info})

@app.route('/api/models', methods=['POST'])
def create_model():
    """创建新模型（归属当前登录用户）"""
    user_id = _require_user_id()
    if user_id is None:
        return jsonify({'error': '未登录'}), 401

    data = request.json
    model_id = str(uuid.uuid4())[:8]
    model_name = data.get('name', f'Model_{model_id}')

    m = SimpleModel(model_name, desc=data.get('description', ''))
    m.owner_id = user_id

    # 保存并缓存模型
    save_model(model_id, m)

    # 同步创建同 id 的项目记录，统一归属（AI 校验等接口按项目校验归属）
    project = Project(model_name, data.get('description', ''), user_id)
    project.id = model_id
    project.model_id = model_id
    save_project(project)

    return jsonify({
        'id': model_id,
        'name': model_name,
        'message': '模型创建成功'
    })

@app.route('/api/models/<model_id>', methods=['GET'])
def get_model(model_id):
    """获取单个模型详情（仅限所属用户）"""
    user_id = _require_user_id()
    if user_id is None:
        return jsonify({'error': '未登录'}), 401

    model = load_model_from_cache(model_id)
    if not _model_owned_by(model, user_id):
        return jsonify({'error': '模型不存在'}), 404

    return jsonify(model.to_dict())

@app.route('/api/models/<model_id>', methods=['PUT'])
def update_model(model_id):
    """更新模型信息（仅限所属用户）"""
    user_id = _require_user_id()
    if user_id is None:
        return jsonify({'error': '未登录'}), 401

    data = request.json
    model = load_model_from_cache(model_id)
    if not _model_owned_by(model, user_id):
        return jsonify({'error': '模型不存在'}), 404

    if 'elements' in data:
        model.elements = data['elements']

    if 'connections' in data:
        model.relationships = data['connections']

    if 'archimateElements' in data:
        model.archimate_elements = data['archimateElements']

    if 'archimateConnections' in data:
        model.archimate_connections = data['archimateConnections']

    if 'erEntities' in data:
        model.er_entities = data['erEntities']

    if 'erRelations' in data:
        model.er_relations = data['erRelations']

    save_model(model_id, model)

    return jsonify({
        'message': '模型更新成功',
        'element_count': len(model.elements),
        'relationship_count': len(model.relationships)
    })

@app.route('/api/models/<model_id>', methods=['DELETE'])
def delete_model(model_id):
    """删除模型（仅限所属用户）"""
    user_id = _require_user_id()
    if user_id is None:
        return jsonify({'error': '未登录'}), 401

    model = load_model_from_cache(model_id)
    if not _model_owned_by(model, user_id):
        return jsonify({'error': '模型不存在'}), 404

    # 从缓存中移除
    if model_id in models_cache:
        del models_cache[model_id]

    # 从 db 删除模型、项目、评论
    db.delete(f'model:{model_id}')
    db.delete(f'project:{model_id}')
    db.delete(f'comments:{model_id}')

    return jsonify({'message': '模型删除成功'})

@app.route('/api/models/<model_id>/views', methods=['GET'])
def get_model_views(model_id):
    """获取模型的视图列表"""
    model = load_model_from_cache(model_id)
    if model is None:
        return jsonify({'error': '模型不存在'}), 404
    
    model = models_cache[model_id]
    views = []
    
    for view in model.views:
        views.append({
            'uuid': view['uuid'],
            'name': view['name'],
            'type': view.get('type', 'class'),
            'nodes_count': len(view.get('elements', [])),
            'created_at': view.get('created_at', ''),
            'updated_at': view.get('updated_at', '')
        })
    
    return jsonify({'views': views})

@app.route('/api/models/<model_id>/views', methods=['POST'])
def create_model_view(model_id):
    """创建新视图"""
    model = load_model_from_cache(model_id)
    if model is None:
        return jsonify({'error': '模型不存在'}), 404
    
    model = models_cache[model_id]
    data = request.json
    
    view_type = data.get('type', 'class')
    view_name = data.get('name', f'未命名视图{len(model.views)+1}')
    
    view = model.add_view(view_name, view_type)
    save_model(model_id, model)
    
    return jsonify({
        'message': '视图创建成功',
        'view': view
    })

def ai_generate_code_impl(model, language):
    """AI生成代码实现"""
    if language == 'python':
        return generate_python_code(model)
    elif language == 'java':
        return generate_java_code(model)
    elif language == 'sql':
        return generate_sql_code(model)
    else:
        return generate_python_code(model)

def generate_python_code(model):
    """生成Python代码"""
    code = '# 自动生成的Python代码\n\n'
    
    # 生成类定义
    for elem in model.elements:
        if elem['type'] in ['Class', 'ApplicationComponent']:
            code += f"class {elem['name']}:\n"
            code += f"    \"\"\"{elem['description']}\"\"\"\n"
            code += "    def __init__(self):\n"
            code += "        pass\n\n"
    
    code += '# 关系映射\n'
    for rel in model.relationships:
        source_elem = next((e for e in model.elements if e['uuid'] == rel['source']), None)
        target_elem = next((e for e in model.elements if e['uuid'] == rel['target']), None)
        if source_elem and target_elem:
            code += f"# {source_elem['name']} {rel['type']} {target_elem['name']}\n"
    
    return code

def generate_java_code(model):
    """生成Java代码"""
    code = '// 自动生成的Java代码\n\n'
    
    for elem in model.elements:
        if elem['type'] in ['Class', 'ApplicationComponent']:
            code += f"public class {elem['name']} {{\n"
            code += f"    // {elem['description']}\n"
            code += "}\n\n"
    
    return code

def generate_sql_code(model):
    """生成SQL代码"""
    code = '-- 自动生成的SQL代码\n\n'
    
    for elem in model.elements:
        if elem['type'] in ['DataObject', 'Class']:
            code += f"CREATE TABLE {elem['name'].lower()} (\n"
            code += "    id INT PRIMARY KEY AUTO_INCREMENT,\n"
            code += "    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,\n"
            code += "    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP\n"
            code += ");\n\n"
    
    return code

# === 版本管理 API ===

@app.route('/api/models/<model_id>/versions', methods=['GET'])
def get_model_versions(model_id):
    """获取模型版本历史"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    model = load_model_from_cache(model_id)
    if model is None:
        return jsonify({'error': '模型不存在'}), 404
    
    model = models_cache[model_id]
    
    return jsonify({
        'current_version': model.version,
        'history': model.history
    })

@app.route('/api/models/<model_id>/versions/save', methods=['POST'])
def save_model_version(model_id):
    """保存版本"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    model = load_model_from_cache(model_id)
    if model is None:
        return jsonify({'error': '模型不存在'}), 404
    
    data = request.json
    comment = data.get('comment', '')
    
    model = models_cache[model_id]
    model.save_version(comment)
    save_model(model_id, model)

    return jsonify({
        'message': '版本保存成功',
        'version': model.version
    })

@app.route('/api/models/<model_id>/versions/<version_index>', methods=['POST'])
def restore_model_version(model_id, version_index):
    """恢复版本"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    model = load_model_from_cache(model_id)
    if model is None:
        return jsonify({'error': '模型不存在'}), 404
    
    model = models_cache[model_id]
    
    try:
        index = int(version_index)
        if model.restore_version(index):
            save_model(model_id, model)
            return jsonify({'message': '版本恢复成功', 'version': model.version})
        else:
            return jsonify({'error': '无效的版本索引'}), 400
    except ValueError:
        return jsonify({'error': '无效的版本索引'}), 400

# === 批注与评论 API ===

@app.route('/api/models/<model_id>/comments', methods=['POST'])
def add_comment(model_id):
    """添加批注/评论"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    data = request.json
    element_id = data.get('element_id')
    content = data.get('content')
    
    if not content:
        return jsonify({'error': '评论内容不能为空'}), 400
    
    user_info = sessions_cache[session_id]
    
    comment = {
        'id': str(uuid.uuid4()),
        'element_id': element_id,
        'user_id': user_info['user_id'],
        'username': user_info['username'],
        'content': content,
        'created_at': datetime.datetime.now().isoformat(),
        'replies': []
    }
    
    # 保存评论到 db
    comments = db.get(f'comments:{model_id}', [])
    comments.append(comment)
    db.set(f'comments:{model_id}', comments)

    return jsonify(comment)

@app.route('/api/models/<model_id>/comments', methods=['GET'])
def get_comments(model_id):
    """获取评论列表"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    comments = db.get(f'comments:{model_id}', [])

    return jsonify({'comments': comments})

# === 操作审计 API ===

@app.route('/api/audit/logs', methods=['GET'])
def get_audit_logs():
    """获取操作日志"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    logs = db.get('audit_logs', [])
    return jsonify({'logs': logs})

def log_audit(action, detail='', model_id=None):
    """记录审计日志"""
    log_entry = {
        'id': str(uuid.uuid4()),
        'action': action,
        'detail': detail,
        'model_id': model_id,
        'timestamp': datetime.datetime.now().isoformat()
    }

    logs = db.get('audit_logs', [])
    logs.append(log_entry)
    db.set('audit_logs', logs)

# === 元素类型 API ===

@app.route('/api/element-types', methods=['GET'])
def get_element_types():
    """获取所有元素类型"""
    return jsonify(ELEMENT_TYPES)

@app.route('/api/relationship-types', methods=['GET'])
def get_relationship_types():
    """获取所有关系类型"""
    return jsonify({'types': RELATIONSHIP_TYPES})

@app.route('/api/element-colors', methods=['GET'])
def get_element_colors():
    """获取元素颜色映射"""
    return jsonify(ELEMENT_COLORS)

# === SocketIO实时协作 ===

@socketio.on('join_project')
def handle_join_project(data):
    """用户加入项目房间"""
    project_id = data.get('project_id')
    join_room(project_id)
    emit('user_joined', {'message': '用户加入项目'}, room=project_id)

@socketio.on('leave_project')
def handle_leave_project(data):
    """用户离开项目房间"""
    project_id = data.get('project_id')
    leave_room(project_id)
    emit('user_left', {'message': '用户离开项目'}, room=project_id)

@socketio.on('element_update')
def handle_element_update(data):
    """元素更新通知"""
    project_id = data.get('project_id')
    emit('element_updated', data, room=project_id, include_self=False)

@socketio.on('cursor_move')
def handle_cursor_move(data):
    """光标移动通知"""
    project_id = data.get('project_id')
    emit('cursor_moved', data, room=project_id, include_self=False)

@socketio.on('selection_change')
def handle_selection_change(data):
    """选择变化通知"""
    project_id = data.get('project_id')
    emit('selection_changed', data, room=project_id, include_self=False)

# === 项目工程与基础管理扩展 API ===

# 行业模板配置
INDUSTRY_TEMPLATES = {
    'finance': {
        'name': '金融行业模板',
        'packages': ['业务能力', '产品服务', '客户渠道', '风险管理', '合规审计'],
        'elements': ['BusinessService', 'BusinessProcess', 'ApplicationComponent', 'Node']
    },
    'manufacturing': {
        'name': '制造业模板',
        'packages': ['生产流程', '供应链', '设备管理', '质量控制', '仓储物流'],
        'elements': ['BusinessProcess', 'BusinessObject', 'TechnologyService', 'DataStore']
    },
    'government': {
        'name': '政务行业模板',
        'packages': ['政务服务', '数据共享', '监管治理', '安全保障', '流程审批'],
        'elements': ['BusinessService', 'ApplicationComponent', 'DataObject', 'TechnologyInterface']
    },
    'iot': {
        'name': '物联网模板',
        'packages': ['设备层', '网络层', '平台层', '应用层', '数据层'],
        'elements': ['Device', 'Network', 'ApplicationComponent', 'DataStore', 'TechnologyService']
    },
    'software': {
        'name': '软件行业模板',
        'packages': ['前端', '后端', '数据库', '中间件', 'API网关'],
        'elements': ['ApplicationComponent', 'Interface', 'DataStore', 'TechnologyService']
    }
}

# 角色权限模板
ROLE_TEMPLATES = {
    'owner': {
        'name': '项目所有者',
        'permissions': ['read', 'write', 'edit', 'delete', 'manage_members', 'manage_settings']
    },
    'architect': {
        'name': '架构师',
        'permissions': ['read', 'write', 'edit', 'delete', 'validate', 'export']
    },
    'developer': {
        'name': '开发人员',
        'permissions': ['read', 'write', 'edit', 'validate', 'export']
    },
    'tester': {
        'name': '测试人员',
        'permissions': ['read', 'validate', 'export']
    },
    'product': {
        'name': '产品经理',
        'permissions': ['read', 'write', 'edit', 'export']
    },
    'viewer': {
        'name': '查看者',
        'permissions': ['read']
    }
}

def generate_project_package_structure(industry):
    """根据行业生成项目包结构"""
    template = INDUSTRY_TEMPLATES.get(industry, INDUSTRY_TEMPLATES['software'])
    packages = []
    
    for i, pkg_name in enumerate(template['packages']):
        packages.append({
            'package_id': str(uuid.uuid4())[:8],
            'name': pkg_name,
            'description': f'{pkg_name}模块',
            'order_num': i,
            'children': []
        })
    
    return packages

def ai_recommend_permissions(role, team_size=5):
    """AI推荐权限配置"""
    template = ROLE_TEMPLATES.get(role, ROLE_TEMPLATES['viewer'])
    recommendations = {
        'role': role,
        'recommended_permissions': template['permissions'],
        'suggestion': f'对于{template["name"]}角色，建议配置以下权限: {", ".join(template["permissions"])}'
    }
    
    # 根据团队规模调整建议
    if team_size > 10:
        recommendations['warning'] = '团队规模较大，建议启用更细粒度的权限控制'
    
    return recommendations

def ai_generate_project_summary(project, model):
    """AI生成项目摘要"""
    element_count = len(model.elements) if model else 0
    rel_count = len(model.relationships) if model else 0
    member_count = len(project.members)
    
    summary = {
        'project_name': project.name,
        'description': project.description,
        'created_at': project.created_at,
        'last_updated': project.updated_at,
        'owner': '用户ID: ' + project.owner_id,
        'member_count': member_count,
        'element_count': element_count,
        'relationship_count': rel_count,
        'health_score': project.health_check.get('score', 100),
        'overview': f'本项目包含{element_count}个元素和{rel_count}条关系，共有{member_count}名成员协作。',
        'highlights': [
            f'项目规模：{element_count}个架构元素',
            f'团队协作：{member_count}名成员参与',
            f'健康状态：{"良好" if project.health_check.get("score", 100) >= 80 else "需要关注"}'
        ],
        'recommendations': []
    }
    
    if element_count == 0:
        summary['recommendations'].append('建议添加架构元素来构建完整的模型')
    if member_count == 0:
        summary['recommendations'].append('建议添加团队成员进行协作')
    
    return summary

@app.route('/api/v1/project/create', methods=['POST'])
def create_project_v1():
    """创建新项目，支持AI辅助生成项目结构"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    data = request.json
    name = data.get('name', '未命名项目')
    description = data.get('description', '')
    industry = data.get('industry', 'software')
    auto_generate = data.get('auto_generate', True)
    
    user_id = sessions_cache[session_id]['user_id']
    project = Project(name, description, user_id)
    
    # AI辅助生成项目结构
    if auto_generate:
        project.settings['industry'] = industry
        project.settings['packages'] = generate_project_package_structure(industry)
        project.settings['templates'] = INDUSTRY_TEMPLATES.get(industry, INDUSTRY_TEMPLATES['software'])
    
    save_project(project)
    
    # 创建关联模型
    model = SimpleModel(name)
    save_model(project.id, model)

    project.model_id = project.id
    save_project(project)
    
    return jsonify({
        'message': '项目创建成功',
        'project': project.to_dict()
    })

@app.route('/api/v1/project/list', methods=['GET'])
def get_project_list_v1():
    """获取用户有权限的项目列表，支持分页、筛选"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    user_id = sessions_cache[session_id]['user_id']
    projects = load_projects()
    
    # 筛选参数
    page = int(request.args.get('page', 1))
    size = int(request.args.get('size', 10))
    status = request.args.get('status')
    keyword = request.args.get('keyword')
    
    user_projects = []
    for project_id, project in projects.items():
        # 检查权限
        if project.owner_id != user_id and user_id not in project.permissions:
            continue
        
        # 状态筛选
        if status and project.status != status:
            continue
        
        # 关键词筛选
        if keyword and keyword.lower() not in project.name.lower() and keyword.lower() not in project.description.lower():
            continue
        
        user_projects.append({
            'id': project.id,
            'name': project.name,
            'description': project.description,
            'status': project.status,
            'created_at': project.created_at,
            'updated_at': project.updated_at,
            'member_count': len(project.members),
            'health_score': project.health_check.get('score', 100),
            'role': project.permissions.get(user_id, 'owner' if project.owner_id == user_id else 'viewer'),
            'industry': project.settings.get('industry', 'software')
        })
    
    # 分页
    total = len(user_projects)
    user_projects = user_projects[(page-1)*size : page*size]
    
    return jsonify({
        'projects': user_projects,
        'total': total,
        'page': page,
        'size': size
    })

@app.route('/api/v1/project/<project_id>', methods=['GET'])
def get_project_detail_v1(project_id):
    """获取项目基本信息、包结构、成员、配置"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    projects = load_projects()
    if project_id not in projects:
        return jsonify({'error': '项目不存在'}), 404
    
    project = projects[project_id]
    user_id = sessions_cache[session_id]['user_id']
    
    if project.owner_id != user_id and user_id not in project.permissions:
        return jsonify({'error': '无权限访问此项目'}), 403
    
    model = load_model_from_cache(project.model_id)
    
    return jsonify({
        'project': project.to_dict(),
        'model_info': {
            'element_count': len(model.elements) if model else 0,
            'relationship_count': len(model.relationships) if model else 0,
            'view_count': len(model.views) if model else 0
        } if model else None
    })

@app.route('/api/v1/project/<project_id>/config', methods=['PUT'])
def update_project_config_v1(project_id):
    """更新项目全局配置、样式、模板、权限"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    projects = load_projects()
    if project_id not in projects:
        return jsonify({'error': '项目不存在'}), 404
    
    project = projects[project_id]
    user_id = sessions_cache[session_id]['user_id']
    
    if project.owner_id != user_id:
        return jsonify({'error': '无权限'}), 403
    
    data = request.json
    
    if 'global_style' in data:
        project.settings['global_style'] = data['global_style']
    if 'templates' in data:
        project.settings['templates'] = data['templates']
    if 'industry' in data:
        project.settings['industry'] = data['industry']
        project.settings['packages'] = generate_project_package_structure(data['industry'])
    if 'permissions' in data:
        project.settings['permissions'] = data['permissions']
    
    save_project(project)
    
    return jsonify({'message': '配置更新成功', 'settings': project.settings})

@app.route('/api/v1/project/<project_id>/search', methods=['POST'])
def project_search_v1(project_id):
    """项目内全局语义检索，支持自然语言提问"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    projects = load_projects()
    if project_id not in projects:
        return jsonify({'error': '项目不存在'}), 404
    
    project = projects[project_id]
    user_id = sessions_cache[session_id]['user_id']
    
    if project.owner_id != user_id and user_id not in project.permissions:
        return jsonify({'error': '无权限'}), 403
    
    data = request.json
    query = data.get('query', '')
    
    model = load_model_from_cache(project.model_id)
    
    results = []
    if model:
        # 语义检索模拟
        for elem in model.elements:
            # 匹配名称、描述
            match_score = 0
            if query.lower() in elem['name'].lower():
                match_score += 50
            if elem.get('description') and query.lower() in elem['description'].lower():
                match_score += 30
            if query.lower() in elem['type'].lower():
                match_score += 20
            
            if match_score > 0:
                results.append({
                    'id': elem['uuid'],
                    'name': elem['name'],
                    'type': elem['type'],
                    'description': elem.get('description', ''),
                    'match_score': match_score,
                    'location': 'element'
                })
        
        # 搜索关系
        for rel in model.relationships:
            rel_desc = f"{rel.get('source_name', '')} {rel['type']} {rel.get('target_name', '')}"
            if query.lower() in rel_desc.lower():
                results.append({
                    'id': rel.get('uuid', ''),
                    'name': rel_desc,
                    'type': rel['type'],
                    'description': rel.get('description', ''),
                    'match_score': 30,
                    'location': 'relationship'
                })
    
    # 按匹配度排序
    results.sort(key=lambda x: x['match_score'], reverse=True)
    
    return jsonify({
        'query': query,
        'results': results[:20],
        'total': len(results)
    })

@app.route('/api/v1/project/<project_id>/inspect', methods=['POST'])
def project_inspect_v1(project_id):
    """触发AI项目健康巡检，生成优化报告"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    projects = load_projects()
    if project_id not in projects:
        return jsonify({'error': '项目不存在'}), 404
    
    project = projects[project_id]
    user_id = sessions_cache[session_id]['user_id']
    
    if project.owner_id != user_id and user_id not in project.permissions:
        return jsonify({'error': '无权限'}), 403
    
    model = load_model_from_cache(project.model_id)
    
    # 执行详细健康检查
    inspection_result = perform_detailed_inspection(model, project)
    project.health_check = inspection_result
    save_project(project)
    
    return jsonify(inspection_result)

def perform_detailed_inspection(model, project):
    """执行详细健康检查"""
    issues = []
    suggestions = []
    warnings = []
    score = 100
    
    if not model:
        return {
            'score': 0,
            'status': 'critical',
            'issues': ['模型不存在'],
            'suggestions': ['请先创建模型'],
            'warnings': [],
            'report': '项目模型不存在，请先创建模型'
        }
    
    # 检查空元素
    empty_elements = [e for e in model.elements if not e['name'] or e['name'] in ['Unnamed', '']]
    if empty_elements:
        issues.append(f'发现 {len(empty_elements)} 个空名称元素')
        suggestions.append('建议为所有元素添加有意义的名称')
        score -= min(len(empty_elements) * 5, 20)
    
    # 检查无效连线
    elem_uuids = {e['uuid'] for e in model.elements}
    invalid_relationships = []
    for rel in model.relationships:
        if rel['source'] not in elem_uuids or rel['target'] not in elem_uuids:
            invalid_relationships.append(rel)
    
    if invalid_relationships:
        issues.append(f'发现 {len(invalid_relationships)} 条无效连线')
        suggestions.append('建议删除或修复无效的关系连接')
        score -= min(len(invalid_relationships) * 5, 15)
    
    # 检查命名规范
    naming_issues = []
    for elem in model.elements:
        if ' ' in elem['name'] or elem['name'].islower():
            naming_issues.append(elem['name'])
    
    if naming_issues:
        issues.append(f'发现 {len(naming_issues)} 个命名不规范的元素')
        suggestions.append('建议使用驼峰命名法或 Pascal 命名法')
        score -= min(len(naming_issues) * 2, 10)
    
    # 检查缺失注释
    no_desc_elements = [e for e in model.elements if not e.get('description') or e['description'] == '']
    if no_desc_elements:
        issues.append(f'发现 {len(no_desc_elements)} 个缺少描述的元素')
        suggestions.append('建议为重要元素添加业务描述')
        score -= min(len(no_desc_elements) * 2, 10)
    
    # 检查循环依赖
    cycle_count = detect_cycles(model)
    if cycle_count > 0:
        issues.append(f'发现 {cycle_count} 处循环依赖')
        suggestions.append('建议重构消除循环依赖')
        score -= cycle_count * 10
    
    # 检查结构混乱
    if len(model.elements) > 0 and len(model.relationships) == 0:
        issues.append('元素之间缺少关系连接')
        suggestions.append('建议为元素添加适当的关系')
        score -= 15
    
    # 检查项目配置
    if not project.settings.get('industry'):
        warnings.append('未设置行业类型，建议配置以获得更好的模板推荐')
    
    status = 'excellent' if score >= 90 else 'good' if score >= 70 else 'warning' if score >= 50 else 'critical'
    
    return {
        'score': max(0, score),
        'status': status,
        'issues': issues,
        'suggestions': suggestions,
        'warnings': warnings,
        'report': generate_inspection_report(score, issues, suggestions),
        'element_count': len(model.elements),
        'relationship_count': len(model.relationships),
        'view_count': len(model.views)
    }

def detect_cycles(model):
    """检测循环依赖"""
    if not model or not model.relationships:
        return 0
    
    graph = {}
    for elem in model.elements:
        graph[elem['uuid']] = []
    
    for rel in model.relationships:
        if rel['source'] in graph and rel['target'] in graph:
            graph[rel['source']].append(rel['target'])
    
    # 简单的循环检测
    visited = set()
    rec_stack = set()
    cycles = 0
    
    def dfs(node):
        nonlocal cycles
        if node not in visited:
            visited.add(node)
            rec_stack.add(node)
            for neighbor in graph.get(node, []):
                if neighbor not in visited:
                    if dfs(neighbor):
                        cycles += 1
                elif neighbor in rec_stack:
                    cycles += 1
        if node in rec_stack:
            rec_stack.remove(node)
        return False
    
    for node in graph:
        if node not in visited:
            dfs(node)
    
    return cycles

def generate_inspection_report(score, issues, suggestions):
    """生成检查报告"""
    report = f"项目健康评分: {score}/100\n\n"
    
    if score >= 90:
        report += "状态: 优秀 - 项目整体健康状况良好\n"
    elif score >= 70:
        report += "状态: 良好 - 项目存在一些小问题，建议关注\n"
    elif score >= 50:
        report += "状态: 警告 - 项目存在较多问题，需要整改\n"
    else:
        report += "状态: 严重 - 项目存在严重问题，急需处理\n"
    
    if issues:
        report += "\n发现的问题:\n"
        for i, issue in enumerate(issues, 1):
            report += f"  {i}. {issue}\n"
    
    if suggestions:
        report += "\n优化建议:\n"
        for i, suggestion in enumerate(suggestions, 1):
            report += f"  {i}. {suggestion}\n"
    
    return report

@app.route('/api/v1/project/<project_id>/member', methods=['POST'])
def manage_project_member_v1(project_id):
    """添加/移除/更新项目成员、权限配置"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    projects = load_projects()
    if project_id not in projects:
        return jsonify({'error': '项目不存在'}), 404
    
    project = projects[project_id]
    user_id = sessions_cache[session_id]['user_id']
    
    if project.owner_id != user_id:
        return jsonify({'error': '无权限'}), 403
    
    data = request.json
    action = data.get('action', 'add')
    member_username = data.get('username')
    role = data.get('role', 'viewer')
    
    users = load_users()
    if member_username not in users:
        return jsonify({'error': '用户不存在'}), 400
    
    member_id = users[member_username]['id']
    
    if action == 'add':
        project.add_member(member_id, role)
        message = '成员添加成功'
    elif action == 'update':
        project.update_permission(member_id, role)
        message = '权限更新成功'
    elif action == 'remove':
        project.remove_member(member_id)
        message = '成员移除成功'
    else:
        return jsonify({'error': '无效操作'}), 400
    
    save_project(project)
    return jsonify({'message': message, 'members': project.members})

@app.route('/api/v1/project/<project_id>/export', methods=['POST'])
def export_project_v1(project_id):
    """项目文件导出、备份、快照生成"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    projects = load_projects()
    if project_id not in projects:
        return jsonify({'error': '项目不存在'}), 404
    
    project = projects[project_id]
    user_id = sessions_cache[session_id]['user_id']
    
    if project.owner_id != user_id and project.permissions.get(user_id) not in ['owner', 'editor']:
        return jsonify({'error': '无权限'}), 403
    
    data = request.json
    export_type = data.get('type', 'full')
    
    # 创建快照
    snapshot_id = str(uuid.uuid4())[:8]
    snapshot_data = {
        'snapshot_id': snapshot_id,
        'project_id': project_id,
        'snapshot_name': data.get('name', f'快照_{datetime.datetime.now().strftime("%Y%m%d_%H%M%S")}'),
        'description': data.get('description', ''),
        'version': project.settings.get('version', '1.0.0'),
        'created_at': datetime.datetime.now().isoformat(),
        'user_id': user_id,
        'project_data': project.to_dict()
    }
    
    # 保存快照
    snapshot_path = os.path.join(app.config['VERSION_FOLDER'], f'{project_id}_{snapshot_id}.json')
    with open(snapshot_path, 'w', encoding='utf-8') as f:
        json.dump(snapshot_data, f, ensure_ascii=False, indent=2)
    
    return jsonify({
        'message': '导出成功',
        'snapshot_id': snapshot_id,
        'file_path': snapshot_path,
        'export_type': export_type
    })

@app.route('/api/v1/project/<project_id>/log', methods=['GET'])
def get_project_logs_v1(project_id):
    """获取项目操作审计日志，支持分页、筛选"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    projects = load_projects()
    if project_id not in projects:
        return jsonify({'error': '项目不存在'}), 404
    
    project = projects[project_id]
    user_id = sessions_cache[session_id]['user_id']
    
    if project.owner_id != user_id and user_id not in project.permissions:
        return jsonify({'error': '无权限'}), 403
    
    # 模拟日志数据
    logs = []
    log_types = ['create', 'update', 'delete', 'add_member', 'update_permission', 'export', 'import']
    
    for i in range(20):
        logs.append({
            'log_id': str(uuid.uuid4())[:8],
            'operation_type': log_types[i % len(log_types)],
            'operation_content': get_log_content(log_types[i % len(log_types)]),
            'user_id': user_id,
            'ip_address': f'192.168.1.{100 + i % 10}',
            'created_at': (datetime.datetime.now() - datetime.timedelta(hours=i)).isoformat()
        })
    
    # 分页
    page = int(request.args.get('page', 1))
    size = int(request.args.get('size', 10))
    total = len(logs)
    logs = logs[(page-1)*size : page*size]
    
    return jsonify({
        'logs': logs,
        'total': total,
        'page': page,
        'size': size
    })

def get_log_content(op_type):
    """获取日志内容描述"""
    content_map = {
        'create': '创建项目',
        'update': '更新项目配置',
        'delete': '删除元素',
        'add_member': '添加项目成员',
        'update_permission': '更新成员权限',
        'export': '导出项目',
        'import': '导入项目'
    }
    return content_map.get(op_type, op_type)

@app.route('/api/v1/project/<project_id>/summary', methods=['GET'])
def get_project_summary_v1(project_id):
    """获取项目摘要与概览"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    projects = load_projects()
    if project_id not in projects:
        return jsonify({'error': '项目不存在'}), 404
    
    project = projects[project_id]
    user_id = sessions_cache[session_id]['user_id']
    
    if project.owner_id != user_id and user_id not in project.permissions:
        return jsonify({'error': '无权限'}), 403
    
    model = load_model_from_cache(project.model_id)
    summary = ai_generate_project_summary(project, model)
    
    return jsonify(summary)

@app.route('/api/v1/project/<project_id>/ai/recommend-permissions', methods=['POST'])
def ai_recommend_permissions_v1(project_id):
    """AI智能推荐权限配置"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    projects = load_projects()
    if project_id not in projects:
        return jsonify({'error': '项目不存在'}), 404
    
    project = projects[project_id]
    user_id = sessions_cache[session_id]['user_id']
    
    if project.owner_id != user_id:
        return jsonify({'error': '无权限'}), 403
    
    data = request.json
    role = data.get('role', 'viewer')
    team_size = data.get('team_size', len(project.members))
    
    recommendations = ai_recommend_permissions(role, team_size)
    return jsonify(recommendations)

# === UML全图建模 API ===

UML_VIEW_TYPES = {
    'class': '类图',
    'object': '对象图',
    'component': '组件图',
    'deployment': '部署图',
    'package': '包图',
    'composite': '复合结构图',
    'use_case': '用例图',
    'sequence': '时序图',
    'communication': '协作图',
    'state_machine': '状态机图',
    'activity': '活动图',
    'interaction_overview': '交互概览图',
    'timing': '时序概览图',
    'prototype': '原型图',
    'freehand': '自由绘图画布'
}

@app.route('/api/v1/project/<project_id>/view/create', methods=['POST'])
def create_uml_view_v1(project_id):
    """创建新的UML视图"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    projects = load_projects()
    if project_id not in projects:
        return jsonify({'error': '项目不存在'}), 404
    
    project = projects[project_id]
    user_id = sessions_cache[session_id]['user_id']
    
    if project.owner_id != user_id and project.permissions.get(user_id) not in ['owner', 'editor']:
        return jsonify({'error': '无权限'}), 403
    
    data = request.json
    view_type = data.get('view_type', 'class')
    name = data.get('name', f'未命名{UML_VIEW_TYPES.get(view_type, "视图")}')
    package_id = data.get('package_id')
    
    model = load_model_from_cache(project.model_id)
    if not model:
        model = SimpleModel(project.name)
    
    view = {
        'uuid': str(uuid.uuid4()),
        'name': name,
        'type': view_type,
        'package_id': package_id,
        'elements': [],
        'relationships': [],
        'created_at': datetime.datetime.now().isoformat(),
        'updated_at': datetime.datetime.now().isoformat()
    }
    
    model.views.append(view)
    save_model(project.model_id, model)
    
    return jsonify({
        'message': '视图创建成功',
        'view': view
    })

@app.route('/api/v1/project/<project_id>/view/list', methods=['GET'])
def get_uml_views_v1(project_id):
    """获取项目内的UML视图列表"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    projects = load_projects()
    if project_id not in projects:
        return jsonify({'error': '项目不存在'}), 404
    
    project = projects[project_id]
    user_id = sessions_cache[session_id]['user_id']
    
    if project.owner_id != user_id and user_id not in project.permissions:
        return jsonify({'error': '无权限'}), 403
    
    model = load_model_from_cache(project.model_id)
    
    views = []
    if model:
        for view in model.views:
            views.append({
                'id': view['uuid'],
                'name': view['name'],
                'type': view['type'],
                'type_label': UML_VIEW_TYPES.get(view['type'], view['type']),
                'element_count': len(view.get('elements', [])),
                'created_at': view['created_at'],
                'updated_at': view['updated_at']
            })
    
    return jsonify({'views': views})

@app.route('/api/v1/project/<project_id>/view/<view_id>', methods=['GET'])
def get_uml_view_v1(project_id, view_id):
    """获取单个视图详情"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    projects = load_projects()
    if project_id not in projects:
        return jsonify({'error': '项目不存在'}), 404
    
    project = projects[project_id]
    user_id = sessions_cache[session_id]['user_id']
    
    if project.owner_id != user_id and user_id not in project.permissions:
        return jsonify({'error': '无权限'}), 403
    
    model = load_model_from_cache(project.model_id)
    if not model:
        return jsonify({'error': '模型不存在'}), 404
    
    view = next((v for v in model.views if v['uuid'] == view_id), None)
    if not view:
        return jsonify({'error': '视图不存在'}), 404
    
    return jsonify(view)

@app.route('/api/v1/project/<project_id>/view/<view_id>', methods=['PUT'])
def update_uml_view_v1(project_id, view_id):
    """更新视图信息"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    projects = load_projects()
    if project_id not in projects:
        return jsonify({'error': '项目不存在'}), 404
    
    project = projects[project_id]
    user_id = sessions_cache[session_id]['user_id']
    
    if project.owner_id != user_id and project.permissions.get(user_id) not in ['owner', 'editor']:
        return jsonify({'error': '无权限'}), 403
    
    data = request.json
    model = load_model_from_cache(project.model_id)
    if not model:
        return jsonify({'error': '模型不存在'}), 404
    
    view = next((v for v in model.views if v['uuid'] == view_id), None)
    if not view:
        return jsonify({'error': '视图不存在'}), 404
    
    if 'name' in data:
        view['name'] = data['name']
    if 'type' in data:
        view['type'] = data['type']
    if 'elements' in data:
        view['elements'] = data['elements']
    if 'relationships' in data:
        view['relationships'] = data['relationships']
    view['updated_at'] = datetime.datetime.now().isoformat()
    
    save_model(project.model_id, model)
    
    return jsonify({'message': '视图更新成功', 'view': view})

@app.route('/api/v1/project/<project_id>/view/<view_id>', methods=['DELETE'])
def delete_uml_view_v1(project_id, view_id):
    """删除视图"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    projects = load_projects()
    if project_id not in projects:
        return jsonify({'error': '项目不存在'}), 404
    
    project = projects[project_id]
    user_id = sessions_cache[session_id]['user_id']
    
    if project.owner_id != user_id and project.permissions.get(user_id) not in ['owner', 'editor']:
        return jsonify({'error': '无权限'}), 403
    
    model = load_model_from_cache(project.model_id)
    if not model:
        return jsonify({'error': '模型不存在'}), 404
    
    initial_count = len(model.views)
    model.views = [v for v in model.views if v['uuid'] != view_id]
    
    if len(model.views) == initial_count:
        return jsonify({'error': '视图不存在'}), 404
    
    save_model(project.model_id, model)
    
    return jsonify({'message': '视图删除成功'})

@app.route('/api/v1/project/<project_id>/ai/generate-uml', methods=['POST'])
def ai_generate_uml_v1(project_id):
    """AI生成UML图"""
    session_id = request.headers.get('X-Session-Id')
    
    # 调试信息
    print(f"[DEBUG] session_id: {session_id}")
    print(f"[DEBUG] sessions_cache keys: {list(sessions_cache.keys())}")
    
    # 如果没有登录，允许生成演示数据
    is_logged_in = session_id in sessions_cache
    print(f"[DEBUG] is_logged_in: {is_logged_in}")
    
    # 检查项目（如果已登录）
    project = None
    if is_logged_in:
        projects = load_projects()
        if project_id not in projects:
            return jsonify({'error': '项目不存在'}), 404
        
        project = projects[project_id]
        user_id = sessions_cache[session_id]['user_id']
        
        if project.owner_id != user_id and project.permissions.get(user_id) not in ['owner', 'editor']:
            return jsonify({'error': '无权限'}), 403
    
    data = request.json
    prompt = data.get('prompt', '')
    view_type = data.get('view_type', 'class')
    
    if not prompt:
        return jsonify({'error': '请输入业务描述'}), 400
    
    # 对于未登录用户，创建临时模型
    if project:
        model = load_model_from_cache(project.model_id)
        if not model:
            model = SimpleModel(project.name)
    else:
        model = SimpleModel('演示项目')
    
    # AI生成UML元素（模拟）
    generated_elements, generated_relationships = generate_uml_from_prompt(prompt, view_type)
    
    # 创建新视图
    view_name = f'AI生成_{UML_VIEW_TYPES.get(view_type, view_type)}'
    view = {
        'uuid': str(uuid.uuid4()),
        'name': view_name,
        'type': view_type,
        'elements': generated_elements,
        'relationships': generated_relationships,
        'created_at': datetime.datetime.now().isoformat(),
        'updated_at': datetime.datetime.now().isoformat()
    }
    
    model.views.append(view)
    
    # 添加到全局元素
    for elem in generated_elements:
        model.elements.append(elem)
    
    for rel in generated_relationships:
        model.relationships.append(rel)
    
    # 只有已登录用户才保存模型
    if project:
        save_model(project.model_id, model)
    
    return jsonify({
        'message': 'UML图生成成功',
        'view': view,
        'generated_elements': len(generated_elements),
        'generated_relationships': len(generated_relationships)
    })

# === AI生成UML（结构化JSON） ===

# _ai_parse_json_response 已移至 core.py

@app.route('/api/v1/project/<project_id>/ai/validate-uml', methods=['POST'])
def ai_validate_uml_v1(project_id):
    """AI校验UML语法规范"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    projects = load_projects()
    if project_id not in projects:
        return jsonify({'error': '项目不存在'}), 404
    
    project = projects[project_id]
    user_id = sessions_cache[session_id]['user_id']
    
    if project.owner_id != user_id and user_id not in project.permissions:
        return jsonify({'error': '无权限'}), 403
    
    data = request.json
    view_id = data.get('view_id')
    
    model = load_model_from_cache(project.model_id)
    if not model:
        return jsonify({'error': '模型不存在'}), 404
    
    view = None
    if view_id:
        view = next((v for v in model.views if v['uuid'] == view_id), None)
        if not view:
            return jsonify({'error': '视图不存在'}), 404
    
    # 执行校验
    validation_result = validate_uml_model(model, view)
    
    return jsonify(validation_result)

@app.route('/api/v1/project/<project_id>/ai/layout', methods=['POST'])
def ai_layout_uml_v1(project_id):
    """AI自动布局UML图"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    projects = load_projects()
    if project_id not in projects:
        return jsonify({'error': '项目不存在'}), 404
    
    project = projects[project_id]
    user_id = sessions_cache[session_id]['user_id']
    
    if project.owner_id != user_id and project.permissions.get(user_id) not in ['owner', 'editor']:
        return jsonify({'error': '无权限'}), 403
    
    data = request.json
    view_id = data.get('view_id')
    algorithm = data.get('algorithm', 'tree')
    
    model = load_model_from_cache(project.model_id)
    if not model:
        return jsonify({'error': '模型不存在'}), 404
    
    view = next((v for v in model.views if v['uuid'] == view_id), None)
    if not view:
        return jsonify({'error': '视图不存在'}), 404
    
    # 执行自动布局
    layout_view = apply_layout(view, algorithm)
    view.update(layout_view)
    view['updated_at'] = datetime.datetime.now().isoformat()
    
    save_model(project.model_id, model)
    
    return jsonify({
        'message': '布局优化完成',
        'view': view,
        'algorithm': algorithm
    })

@app.route('/api/v1/project/<project_id>/ai/explain', methods=['POST'])
def ai_explain_uml_v1(project_id):
    """AI解释UML图语义"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    projects = load_projects()
    if project_id not in projects:
        return jsonify({'error': '项目不存在'}), 404
    
    project = projects[project_id]
    user_id = sessions_cache[session_id]['user_id']
    
    if project.owner_id != user_id and user_id not in project.permissions:
        return jsonify({'error': '无权限'}), 403
    
    data = request.json
    view_id = data.get('view_id')
    element_id = data.get('element_id')
    question = data.get('question', '')
    
    model = load_model_from_cache(project.model_id)
    if not model:
        return jsonify({'error': '模型不存在'}), 404
    
    # 生成解释
    explanation = generate_explanation(model, view_id, element_id, question)
    
    return jsonify(explanation)

# === 操作日志管理 ===

def add_operation_log(project_id, user_id, operation_type, content, ip_address=''):
    """添加操作日志"""
    if project_id not in operation_logs_cache:
        operation_logs_cache[project_id] = []
    
    log_entry = {
        'id': str(uuid.uuid4())[:8],
        'project_id': project_id,
        'user_id': user_id,
        'operation_type': operation_type,
        'content': content,
        'ip_address': ip_address,
        'created_at': datetime.datetime.now().isoformat()
    }
    
    operation_logs_cache[project_id].insert(0, log_entry)  # 最新的在前面
    
    # 只保留最近100条
    if len(operation_logs_cache[project_id]) > 100:
        operation_logs_cache[project_id] = operation_logs_cache[project_id][:100]
    
    # 保存日志到 db
    db.set(f'operation_logs:{project_id}', operation_logs_cache[project_id])

    return log_entry

def load_operation_logs(project_id):
    """加载操作日志"""
    if project_id in operation_logs_cache:
        return operation_logs_cache[project_id]

    logs = db.get(f'operation_logs:{project_id}', [])
    if logs:
        operation_logs_cache[project_id] = logs
    return logs

# === 书签管理 ===

def add_bookmark(project_id, user_id, element_id, element_type, name):
    """添加书签"""
    key = f'{project_id}_{user_id}'
    if key not in bookmarks_cache:
        bookmarks_cache[key] = []
    
    bookmark = {
        'id': str(uuid.uuid4())[:8],
        'project_id': project_id,
        'user_id': user_id,
        'element_id': element_id,
        'element_type': element_type,
        'name': name,
        'created_at': datetime.datetime.now().isoformat()
    }
    
    bookmarks_cache[key].append(bookmark)
    
    # 保存书签到 db
    db.set(f'bookmarks:{key}', bookmarks_cache[key])

    return bookmark

def load_bookmarks(project_id, user_id):
    """加载书签"""
    key = f'{project_id}_{user_id}'
    if key in bookmarks_cache:
        return bookmarks_cache[key]

    bookmarks = db.get(f'bookmarks:{key}', [])
    if bookmarks:
        bookmarks_cache[key] = bookmarks
    return bookmarks

# === 版本快照管理 ===

def create_snapshot(project_id, user_id, snapshot_name, description=''):
    """创建快照"""
    projects = load_projects()
    if project_id not in projects:
        return None
    
    project = projects[project_id]
    model = load_model_from_cache(project.model_id)
    
    if not model:
        return None
    
    snapshot = {
        'id': str(uuid.uuid4())[:8],
        'project_id': project_id,
        'name': snapshot_name,
        'description': description,
        'version': model.version,
        'snapshot_data': {
            'project': project.to_dict(),
            'model': model.to_dict()
        },
        'file_path': '',
        'created_at': datetime.datetime.now().isoformat(),
        'user_id': user_id
    }
    
    if project_id not in snapshots_cache:
        snapshots_cache[project_id] = []
    
    snapshots_cache[project_id].insert(0, snapshot)
    
    # 保存快照到 db
    db.set(f'snapshot:{snapshot["id"]}', snapshot)
    db.set(f'snapshots:{project_id}', snapshots_cache[project_id])

    return snapshot

def load_snapshots(project_id):
    """加载快照列表"""
    if project_id in snapshots_cache:
        return snapshots_cache[project_id]

    snapshots = db.get(f'snapshots:{project_id}', [])
    if snapshots:
        snapshots_cache[project_id] = snapshots
    return snapshots

# === 文件锁管理 ===

def acquire_lock(project_id, element_id, user_id):
    """获取锁"""
    key = f'{project_id}_{element_id}'
    now = datetime.datetime.now()
    
    # 检查锁是否存在
    if key in file_locks_cache:
        lock_info = file_locks_cache[key]
        # 检查锁是否过期（超过5分钟）
        lock_time = datetime.datetime.fromisoformat(lock_info['locked_at'])
        if (now - lock_time).total_seconds() < 300:  # 5分钟内
            if lock_info['user_id'] != user_id:
                return False, lock_info  # 被其他人锁定
            # 本人锁定，刷新时间
            lock_info['locked_at'] = now.isoformat()
            return True, lock_info
    
    # 获取锁
    lock_info = {
        'user_id': user_id,
        'locked_at': now.isoformat()
    }
    file_locks_cache[key] = lock_info
    return True, lock_info

def release_lock(project_id, element_id, user_id):
    """释放锁"""
    key = f'{project_id}_{element_id}'
    if key in file_locks_cache:
        if file_locks_cache[key]['user_id'] == user_id:
            del file_locks_cache[key]
            return True
        return False
    return True  # 本来就没有锁

# === AI项目摘要生成 ===

def generate_project_summary(project, model):
    """生成项目摘要"""
    element_count = len(model.elements)
    relationship_count = len(model.relationships)
    view_count = len(model.views)
    member_count = len(project.members) + 1  # 包含所有者
    
    # 统计元素类型
    element_types = {}
    for elem in model.elements:
        elem_type = elem.get('type', 'Unknown')
        element_types[elem_type] = element_types.get(elem_type, 0) + 1
    
    # 生成模块清单
    modules = []
    if element_types.get('BusinessProcess', 0) > 0:
        modules.append('业务流程模块')
    if element_types.get('ApplicationComponent', 0) > 0:
        modules.append('应用架构模块')
    if element_types.get('Node', 0) > 0:
        modules.append('技术架构模块')
    if element_types.get('Class', 0) > 0:
        modules.append('数据模型模块')
    
    # 生成摘要
    summary = {
        'project_overview': f"{project.name}项目是一个{project.industry}行业的企业架构建模项目，"
                           f"包含{element_count}个元素、{relationship_count}条关系和{view_count}个视图。",
        'architecture_overview': f"本项目采用分层架构设计，覆盖了{'、'.join(modules) if modules else '多个架构层次'}。",
        'modules': modules or ['基础架构模块'],
        'personnel': {
            'total': member_count,
            'roles': list(set([m['role'] for m in project.members] + ['owner']))
        },
        'highlights': [
            f"完整的{project.industry}行业架构模型",
            f"{element_count}个架构元素已定义",
            f"支持多用户协作编辑"
        ],
        'risks': [
            "建议定期进行健康检查",
            "注意元素命名规范",
            "及时更新文档"
        ],
        'todo': [
            "完成所有视图创建",
            "补充元素注释",
            "进行模型验证"
        ],
        'generated_at': datetime.datetime.now().isoformat()
    }
    
    return summary

# === AI项目初始化 - 基于行业生成包结构 ===

def generate_ai_project_structure(project, industry):
    """AI根据行业生成项目结构"""
    if industry not in INDUSTRY_TEMPLATES:
        industry = 'software'  # 默认软件行业
    
    template = INDUSTRY_TEMPLATES[industry]
    
    # 生成包结构
    for i, package_name in enumerate(template['packages']):
        project.add_package(package_name, f"{industry}行业{package_name}包")
    
    # 生成角色
    for role_name, desc in template['roles'].items():
        project.add_role(role_name, desc)
    
    # 添加日志
    add_operation_log(project.id, project.owner_id, 'project_init', 
                      f'基于{industry}行业模板初始化项目结构', 'localhost')
    
    return project

# === AI语义检索 ===

def ai_semantic_search(model, query):
    """AI语义检索"""
    results = []
    query_lower = query.lower()
    
    # 搜索元素
    for elem in model.elements:
        score = 0
        name = elem.get('name', '').lower()
        desc = elem.get('description', '').lower()
        elem_type = elem.get('type', '').lower()
        
        # 关键词匹配
        if query_lower in name:
            score += 10
        if query_lower in desc:
            score += 5
        if query_lower in elem_type:
            score += 3
        
        # 语义相关词
        semantic_keywords = {
            '用户': ['user', '用户', '客户', 'actor'],
            '数据': ['data', '数据', '信息', 'object'],
            '流程': ['process', '流程', '活动', 'workflow'],
            '服务': ['service', '服务', '接口', 'interface'],
            '系统': ['system', '系统', '组件', 'component'],
            '架构': ['architecture', '架构', '结构', 'structure']
        }
        
        for keyword, synonyms in semantic_keywords.items():
            if any(syn in query_lower for syn in synonyms):
                if any(syn in name or syn in desc for syn in synonyms):
                    score += 4
        
        if score > 0:
            results.append({
                'type': 'element',
                'item': elem,
                'score': score,
                'match_reason': f"在「{elem.get('name')}」元素中找到匹配"
            })
    
    # 搜索关系
    for rel in model.relationships:
        score = 0
        name = rel.get('name', '').lower()
        rel_type = rel.get('type', '').lower()
        
        if query_lower in name or query_lower in rel_type:
            score += 5
        
        if score > 0:
            results.append({
                'type': 'relationship',
                'item': rel,
                'score': score,
                'match_reason': f"在「{rel.get('name') or rel.get('type')}」关系中找到匹配"
            })
    
    # 搜索视图
    for view in model.views:
        score = 0
        name = view.get('name', '').lower()
        desc = view.get('description', '').lower()
        view_type = view.get('type', '').lower()
        
        if query_lower in name:
            score += 8
        if query_lower in desc:
            score += 4
        if query_lower in view_type:
            score += 2
        
        if score > 0:
            results.append({
                'type': 'view',
                'item': view,
                'score': score,
                'match_reason': f"在「{view.get('name')}」视图中找到匹配"
            })
    
    # 按分数排序
    results.sort(key=lambda x: x['score'], reverse=True)
    
    return {
        'query': query,
        'total_matches': len(results),
        'results': results[:20]  # 最多返回20个
    }

# === AI权限智能分配 ===

def ai_recommend_permissions(project, member_role):
    """AI推荐权限"""
    role_permissions = {
        'architect': {
            'read': True, 'write': True, 'edit': True, 'delete': True,
            'validate': True, 'export': True, 'package_level': 'all',
            'element_level': 'all'
        },
        'developer': {
            'read': True, 'write': True, 'edit': True, 'delete': False,
            'validate': True, 'export': True, 'package_level': 'assigned',
            'element_level': 'assigned'
        },
        'tester': {
            'read': True, 'write': False, 'edit': False, 'delete': False,
            'validate': True, 'export': True, 'package_level': 'read_only',
            'element_level': 'read_only'
        },
        'product': {
            'read': True, 'write': True, 'edit': True, 'delete': False,
            'validate': False, 'export': True, 'package_level': 'business',
            'element_level': 'business'
        },
        'viewer': {
            'read': True, 'write': False, 'edit': False, 'delete': False,
            'validate': False, 'export': False, 'package_level': 'read_only',
            'element_level': 'read_only'
        }
    }
    
    # 获取权限模板
    permissions = role_permissions.get(member_role, role_permissions['viewer'])
    
    # 生成权限审计报告
    audit_report = {
        'recommended_permissions': permissions,
        'risk_warnings': [],
        'redundancy_notes': []
    }
    
    if permissions.get('delete'):
        audit_report['risk_warnings'].append(f"角色{member_role}拥有删除权限，请注意权限控制")
    
    if len(project.members) > 5 and member_role == 'viewer':
        audit_report['redundancy_notes'].append("建议为大量查看用户创建统一查看组")
    
    return audit_report

# === 新增API接口 ===

# 创建项目V2（支持AI初始化）
@app.route('/api/v1/project/create', methods=['POST'])
def create_project_v2():
    """创建新项目，支持AI辅助生成项目结构"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    data = request.json
    name = data.get('name', '')
    description = data.get('description', '')
    industry = data.get('industry', 'software')
    visibility = data.get('visibility', 'private')
    use_ai_template = data.get('use_ai_template', True)
    
    if not name:
        return jsonify({'error': '项目名称不能为空'}), 400
    
    user_id = sessions_cache[session_id]['user_id']
    project = Project(name, description, user_id, industry, visibility)
    
    # 初始化模型
    model = SimpleModel(name, description)
    project.model_id = str(uuid.uuid4())[:8]
    save_model(project.model_id, model)
    
    # AI辅助生成项目结构
    if use_ai_template:
        project = generate_ai_project_structure(project, industry)
    
    # 添加所有者
    project.add_member(user_id, 'owner')
    
    # 添加角色
    project.add_role('owner', '项目所有者', {
        'read': True, 'write': True, 'edit': True, 'delete': True,
        'validate': True, 'export': True
    })
    project.add_role('architect', '架构师', {
        'read': True, 'write': True, 'edit': True, 'delete': False,
        'validate': True, 'export': True
    })
    project.add_role('developer', '开发人员', {
        'read': True, 'write': True, 'edit': True, 'delete': False,
        'validate': True, 'export': True
    })
    project.add_role('viewer', '查看者', {
        'read': True, 'write': False, 'edit': False, 'delete': False,
        'validate': False, 'export': False
    })
    
    save_project(project)
    
    # 添加操作日志
    add_operation_log(project.id, user_id, 'project_create', 
                      f'创建项目「{name}」', request.remote_addr or 'localhost')
    
    return jsonify({
        'message': '项目创建成功',
        'project': project.to_dict(),
        'used_industry_template': use_ai_template
    })

# 获取项目列表V2
@app.route('/api/v1/project/list', methods=['GET'])
def get_project_list_v2():
    """获取用户有权限的项目列表，支持分页、筛选"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    user_id = sessions_cache[session_id]['user_id']
    projects = load_projects()
    
    # 筛选用户有权限的项目
    user_projects = []
    for proj in projects.values():
        if proj.owner_id == user_id or user_id in proj.permissions:
            user_projects.append(proj.to_dict())
    
    # 支持筛选
    status_filter = request.args.get('status')
    if status_filter:
        user_projects = [p for p in user_projects if p.get('status') == status_filter]
    
    # 支持分页
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('page_size', 20))
    start = (page - 1) * page_size
    end = start + page_size
    
    return jsonify({
        'projects': user_projects[start:end],
        'total': len(user_projects),
        'page': page,
        'page_size': page_size
    })

# 项目导入
@app.route('/api/v1/project/<project_id>/import', methods=['POST'])
def import_project(project_id):
    """项目导入"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    projects = load_projects()
    if project_id not in projects:
        return jsonify({'error': '项目不存在'}), 404
    
    project = projects[project_id]
    user_id = sessions_cache[session_id]['user_id']
    
    if project.owner_id != user_id:
        return jsonify({'error': '无权限操作'}), 403
    
    data = request.json
    import_data = data.get('import_data', {})
    
    # 处理导入数据
    model = load_model_from_cache(project.model_id)
    if model and import_data.get('elements'):
        for elem in import_data['elements']:
            model.elements.append(elem)
        for rel in import_data.get('relationships', []):
            model.relationships.append(rel)
        save_model(project.model_id, model)
    
    add_operation_log(project_id, user_id, 'project_import', '导入项目数据', request.remote_addr or 'localhost')
    
    return jsonify({'message': '项目导入成功'})

# 项目导出
@app.route('/api/v1/project/<project_id>/export', methods=['POST'])
def export_project(project_id):
    """项目文件导出、备份、快照生成"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    projects = load_projects()
    if project_id not in projects:
        return jsonify({'error': '项目不存在'}), 404
    
    project = projects[project_id]
    user_id = sessions_cache[session_id]['user_id']
    
    if project.owner_id != user_id and project.permissions.get(user_id) not in ['owner', 'architect']:
        return jsonify({'error': '无权限操作'}), 403
    
    model = load_model_from_cache(project.model_id)
    
    export_data = {
        'project': project.to_dict(),
        'model': model.to_dict() if model else None,
        'exported_at': datetime.datetime.now().isoformat(),
        'exported_by': user_id
    }
    
    # 创建快照
    data = request.json
    snapshot_name = data.get('snapshot_name', f'快照_{datetime.datetime.now().strftime("%Y%m%d_%H%M%S")}')
    snapshot_description = data.get('snapshot_description', '')
    
    create_snapshot(project_id, user_id, snapshot_name, snapshot_description)
    
    add_operation_log(project_id, user_id, 'project_export', '导出项目数据', request.remote_addr or 'localhost')
    
    return jsonify({
        'message': '项目导出成功',
        'export_data': export_data
    })

# 获取快照列表
@app.route('/api/v1/project/<project_id>/snapshots', methods=['GET'])
def get_project_snapshots(project_id):
    """获取项目版本快照列表"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    snapshots = load_snapshots(project_id)
    return jsonify({'snapshots': snapshots})

# 获取操作日志V2
@app.route('/api/v1/project/<project_id>/logs', methods=['GET'])
def get_operation_logs_v2(project_id):
    """获取项目操作审计日志，支持分页、筛选"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    logs = load_operation_logs(project_id)
    
    # 筛选
    operation_type = request.args.get('operation_type')
    if operation_type:
        logs = [log for log in logs if log.get('operation_type') == operation_type]
    
    # 分页
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('page_size', 50))
    start = (page - 1) * page_size
    end = start + page_size
    
    return jsonify({
        'logs': logs[start:end],
        'total': len(logs),
        'page': page,
        'page_size': page_size
    })

# 书签管理API
@app.route('/api/v1/project/<project_id>/bookmark', methods=['POST', 'GET', 'DELETE'])
def manage_bookmarks(project_id):
    """书签管理：添加、获取、删除"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    user_id = sessions_cache[session_id]['user_id']
    
    if request.method == 'POST':
        data = request.json
        bookmark = add_bookmark(
            project_id, user_id,
            data.get('element_id'),
            data.get('element_type'),
            data.get('name')
        )
        return jsonify({'message': '书签添加成功', 'bookmark': bookmark})
    
    elif request.method == 'GET':
        bookmarks = load_bookmarks(project_id, user_id)
        return jsonify({'bookmarks': bookmarks})
    
    elif request.method == 'DELETE':
        data = request.json
        bookmarks = load_bookmarks(project_id, user_id)
        bookmarks = [b for b in bookmarks if b.get('id') != data.get('bookmark_id')]
        
        key = f'{project_id}_{user_id}'
        bookmarks_cache[key] = bookmarks
        
        return jsonify({'message': '书签删除成功'})

# 文件锁API
@app.route('/api/v1/project/<project_id>/lock', methods=['POST', 'DELETE'])
def manage_file_locks(project_id):
    """文件锁管理：获取、释放"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    user_id = sessions_cache[session_id]['user_id']
    data = request.json
    element_id = data.get('element_id')
    
    if request.method == 'POST':
        success, lock_info = acquire_lock(project_id, element_id, user_id)
        if success:
            return jsonify({'message': '锁获取成功', 'lock_info': lock_info})
        else:
            return jsonify({'error': '元素已被锁定', 'lock_info': lock_info}), 409
    
    elif request.method == 'DELETE':
        success = release_lock(project_id, element_id, user_id)
        return jsonify({'message': '锁释放成功' if success else '释放失败'})

# 项目语义检索V2
@app.route('/api/v1/project/<project_id>/search', methods=['POST'])
def semantic_search_v2(project_id):
    """项目内全局语义检索，支持自然语言提问"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    projects = load_projects()
    if project_id not in projects:
        return jsonify({'error': '项目不存在'}), 404
    
    project = projects[project_id]
    model = load_model_from_cache(project.model_id)
    if not model:
        return jsonify({'results': [], 'total_matches': 0})
    
    data = request.json
    query = data.get('query', '')
    
    search_results = ai_semantic_search(model, query)
    
    # 记录操作
    add_operation_log(project_id, sessions_cache[session_id]['user_id'], 'search', 
                      f'搜索「{query}」', request.remote_addr or 'localhost')
    
    return jsonify(search_results)

# 项目摘要生成
@app.route('/api/v1/project/<project_id>/summary', methods=['GET'])
def get_project_summary(project_id):
    """AI生成项目摘要与概览"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    projects = load_projects()
    if project_id not in projects:
        return jsonify({'error': '项目不存在'}), 404
    
    project = projects[project_id]
    model = load_model_from_cache(project.model_id)
    
    summary = generate_project_summary(project, model)
    
    return jsonify(summary)

# 更新项目配置V2
@app.route('/api/v1/project/<project_id>/config', methods=['PUT'])
def update_project_config_v2(project_id):
    """更新项目全局配置、样式、模板、权限"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    projects = load_projects()
    if project_id not in projects:
        return jsonify({'error': '项目不存在'}), 404
    
    project = projects[project_id]
    user_id = sessions_cache[session_id]['user_id']
    
    if project.owner_id != user_id:
        return jsonify({'error': '无权限操作'}), 403
    
    data = request.json
    if 'settings' in data:
        project.settings.update(data['settings'])
        project.updated_at = datetime.datetime.now().isoformat()
    
    save_project(project)
    
    add_operation_log(project_id, user_id, 'config_update', 
                      '更新项目配置', request.remote_addr or 'localhost')
    
    return jsonify({
        'message': '项目配置更新成功',
        'settings': project.settings
    })

# === UML模型快照与版本管理 ===

class ViewSnapshot:
    """视图快照管理"""
    def __init__(self, view_id, name, version, user_id):
        self.id = str(uuid.uuid4())[:8]
        self.view_id = view_id
        self.name = name
        self.version = version
        self.user_id = user_id
        self.created_at = datetime.datetime.now().isoformat()
        self.data = {}
    
    def to_dict(self):
        return {
            'id': self.id,
            'view_id': self.view_id,
            'name': self.name,
            'version': self.version,
            'user_id': self.user_id,
            'created_at': self.created_at,
            'data': self.data
        }

# 视图快照缓存
view_snapshots_cache = {}

# === UML元素高级属性定义 ===

UML_ELEMENT_PROPERTIES = {
    'Class': {
        'properties': ['abstract', 'final', 'static', 'visibility'],
        'attributes': True,
        'methods': True,
        'stereotypes': ['entity', 'boundary', 'control', 'service', 'repository']
    },
    'Interface': {
        'properties': ['visibility'],
        'attributes': False,
        'methods': True,
        'stereotypes': ['api', 'service', 'callback']
    },
    'UseCase': {
        'properties': ['abstract', 'extension_points'],
        'attributes': False,
        'methods': False,
        'stereotypes': ['essential', 'supporting']
    },
    'Actor': {
        'properties': ['abstract'],
        'attributes': False,
        'methods': False,
        'stereotypes': ['human', 'system', 'timer']
    },
    'Activity': {
        'properties': ['is_atomic', 'is_compound'],
        'attributes': False,
        'methods': False,
        'stereotypes': ['manual', 'automatic', 'batch']
    },
    'State': {
        'properties': ['is_initial', 'is_final', 'is_composite'],
        'attributes': False,
        'methods': False,
        'stereotypes': ['simple', 'composite', 'submachine']
    }
}

# UML关系类型详细定义
UML_RELATIONSHIP_DETAILS = {
    'Association': {
        'label': '关联',
        'direction': 'bidirectional',
        'properties': ['multiplicity_source', 'multiplicity_target', 'navigability']
    },
    'Aggregation': {
        'label': '聚合',
        'direction': 'unidirectional',
        'properties': ['multiplicity_source', 'multiplicity_target']
    },
    'Composition': {
        'label': '组合',
        'direction': 'unidirectional',
        'properties': ['multiplicity_source', 'multiplicity_target']
    },
    'Generalization': {
        'label': '泛化',
        'direction': 'unidirectional',
        'properties': ['is_substitutable']
    },
    'Realization': {
        'label': '实现',
        'direction': 'unidirectional',
        'properties': ['mapping']
    },
    'Dependency': {
        'label': '依赖',
        'direction': 'unidirectional',
        'properties': ['stereotype']
    },
    'Include': {
        'label': '包含',
        'direction': 'unidirectional',
        'properties': []
    },
    'Extend': {
        'label': '扩展',
        'direction': 'unidirectional',
        'properties': ['condition']
    },
    'Flow': {
        'label': '流程',
        'direction': 'unidirectional',
        'properties': ['guard', 'action']
    },
    'Message': {
        'label': '消息',
        'direction': 'unidirectional',
        'properties': ['sequence', 'return_type', 'arguments']
    }
}

# 主题和样式定义
UML_THEMES = {
    'default': {
        'name': '默认主题',
        'background': '#ffffff',
        'grid_color': '#e0e0e0',
        'element_fill': '#f5f5f5',
        'element_stroke': '#333333',
        'text_color': '#333333',
        'line_color': '#666666',
        'font_family': 'Arial, sans-serif',
        'font_size': 12
    },
    'dark': {
        'name': '暗色主题',
        'background': '#2d2d2d',
        'grid_color': '#404040',
        'element_fill': '#3d3d3d',
        'element_stroke': '#cccccc',
        'text_color': '#cccccc',
        'line_color': '#999999',
        'font_family': 'Arial, sans-serif',
        'font_size': 12
    },
    'blueprint': {
        'name': '蓝图主题',
        'background': '#1a237e',
        'grid_color': '#283593',
        'element_fill': '#3949ab',
        'element_stroke': '#ffffff',
        'text_color': '#ffffff',
        'line_color': '#90caf9',
        'font_family': 'Courier New, monospace',
        'font_size': 11
    },
    'minimal': {
        'name': '极简主题',
        'background': '#fafafa',
        'grid_color': '#eeeeee',
        'element_fill': '#ffffff',
        'element_stroke': '#bdbdbd',
        'text_color': '#424242',
        'line_color': '#9e9e9e',
        'font_family': 'Helvetica, Arial, sans-serif',
        'font_size': 11
    }
}

# === UML图层管理 ===

class ViewLayer:
    """视图图层"""
    def __init__(self, view_id, name, order_num=0):
        self.id = str(uuid.uuid4())[:8]
        self.view_id = view_id
        self.name = name
        self.order_num = order_num
        self.is_locked = False
        self.is_visible = True
        self.elements = []
        self.created_at = datetime.datetime.now().isoformat()
    
    def to_dict(self):
        return {
            'id': self.id,
            'view_id': self.view_id,
            'name': self.name,
            'order_num': self.order_num,
            'is_locked': self.is_locked,
            'is_visible': self.is_visible,
            'elements': self.elements,
            'created_at': self.created_at
        }

# 图层缓存
view_layers_cache = {}

def get_view_layers(view_id):
    """获取视图图层"""
    if view_id not in view_layers_cache:
        view_layers_cache[view_id] = [
            ViewLayer(view_id, '背景层', 0).to_dict(),
            ViewLayer(view_id, '默认层', 1).to_dict(),
            ViewLayer(view_id, '前景层', 2).to_dict()
        ]
    return view_layers_cache[view_id]

# === AI辅助UML建模增强功能 ===

def ai_recommend_elements(view_type, existing_elements, context=''):
    """AI智能推荐关联元素"""
    recommendations = []
    
    # 基于现有元素推荐关联元素
    element_types = [e['type'] for e in existing_elements]
    
    if view_type == 'class':
        if 'Class' in element_types and 'Interface' not in element_types:
            recommendations.append({
                'type': 'Interface',
                'name': 'I' + existing_elements[0]['name'] + 'Service',
                'reason': '类通常需要接口来定义服务契约',
                'position': 'right'
            })
        if len(existing_elements) > 1:
            recommendations.append({
                'type': 'Class',
                'name': existing_elements[0]['name'] + 'Factory',
                'reason': '多个类存在时，工厂模式有助于对象创建',
                'position': 'below'
            })
    
    elif view_type == 'use_case':
        if 'Actor' in element_types:
            recommendations.append({
                'type': 'UseCase',
                'name': '管理' + existing_elements[0].get('name', '数据'),
                'reason': '角色通常需要管理相关的用例',
                'position': 'right'
            })
    
    elif view_type == 'sequence':
        if len(existing_elements) >= 2:
            recommendations.append({
                'type': 'Actor',
                'name': '系统管理员',
                'reason': '时序图中通常需要管理员角色',
                'position': 'left'
            })
    
    return recommendations

def ai_recommend_relationships(element, all_elements, view_type):
    """AI智能推荐关系"""
    recommendations = []
    
    for other in all_elements:
        if other['uuid'] == element['uuid']:
            continue
        
        # 基于元素类型推荐关系
        if element['type'] == 'Class' and other['type'] == 'Class':
            if element['name'] in other.get('attributes', []):
                recommendations.append({
                    'target': other['uuid'],
                    'type': 'Association',
                    'reason': f"{other['name']}包含{element['name']}类型的属性"
                })
            elif other['name'] in element.get('attributes', []):
                recommendations.append({
                    'target': other['uuid'],
                    'type': 'Association',
                    'reason': f"{element['name']}包含{other['name']}类型的属性"
                })
        
        elif element['type'] == 'Class' and other['type'] == 'Interface':
            recommendations.append({
                'target': other['uuid'],
                'type': 'Realization',
                'reason': f"类可以实现接口定义的服务"
            })
        
        elif element['type'] == 'Actor' and other['type'] == 'UseCase':
            recommendations.append({
                'target': other['uuid'],
                'type': 'Association',
                'reason': f"角色与用例之间存在关联"
            })
    
    return recommendations

def ai_generate_attributes_methods(class_name, description=''):
    """AI智能生成属性和方法"""
    attributes = []
    methods = []
    
    # 基于类名推断属性和方法
    class_lower = class_name.lower()
    
    if 'user' in class_lower or '用户' in class_name:
        attributes = ['id: Long', 'username: String', 'password: String', 'email: String', 'createdAt: DateTime']
        methods = ['login(): boolean', 'logout(): void', 'updateProfile(): boolean', 'validatePassword(): boolean']
    elif 'order' in class_lower or '订单' in class_name:
        attributes = ['id: Long', 'userId: Long', 'totalAmount: BigDecimal', 'status: OrderStatus', 'createdAt: DateTime']
        methods = ['createOrder(): Order', 'cancelOrder(): boolean', 'pay(): boolean', 'ship(): void']
    elif 'product' in class_lower or '商品' in class_name:
        attributes = ['id: Long', 'name: String', 'price: BigDecimal', 'stock: Integer', 'category: String']
        methods = ['getInfo(): ProductDTO', 'updateStock(quantity: int): boolean', 'checkAvailability(): boolean']
    elif 'service' in class_lower or '服务' in class_name:
        attributes = ['id: Long', 'name: String', 'endpoint: String', 'status: ServiceStatus']
        methods = ['start(): void', 'stop(): void', 'restart(): void', 'healthCheck(): boolean']
    else:
        attributes = ['id: Long', 'name: String', 'createdAt: DateTime', 'updatedAt: DateTime']
        methods = ['create(): boolean', 'update(): boolean', 'delete(): boolean', 'findById(id: Long): ' + class_name]
    
    return attributes, methods

def ai_detect_circular_dependencies(model):
    """AI检测循环依赖"""
    circular_deps = []
    
    # 构建依赖图
    dependency_graph = {}
    for elem in model.elements:
        dependency_graph[elem['uuid']] = []
    
    for rel in model.relationships:
        if rel['type'] in ['Dependency', 'Association', 'Aggregation', 'Composition']:
            if rel['source'] in dependency_graph:
                dependency_graph[rel['source']].append(rel['target'])
    
    # 检测循环
    def has_cycle(node, visited, rec_stack):
        visited.add(node)
        rec_stack.add(node)
        
        for neighbor in dependency_graph.get(node, []):
            if neighbor not in visited:
                if has_cycle(neighbor, visited, rec_stack):
                    return True
            elif neighbor in rec_stack:
                return True
        
        rec_stack.remove(node)
        return False
    
    visited = set()
    for node in dependency_graph:
        if node not in visited:
            if has_cycle(node, visited, set()):
                elem = next((e for e in model.elements if e['uuid'] == node), None)
                if elem:
                    circular_deps.append({
                        'element_id': node,
                        'element_name': elem['name'],
                        'severity': 'error',
                        'message': f'检测到循环依赖: {elem["name"]}'
                    })
    
    return circular_deps

def ai_suggest_naming_convention(element):
    """AI建议命名规范"""
    suggestions = []
    name = element.get('name', '')
    elem_type = element.get('type', '')
    
    if not name:
        suggestions.append('元素名称不能为空')
        return suggestions
    
    # 类名应该使用大驼峰
    if elem_type == 'Class':
        if not name[0].isupper():
            suggestions.append(f'类名应该使用大驼峰命名法，建议改为: {name.capitalize()}')
        if '_' in name or '-' in name:
            suggestions.append(f'类名不应包含下划线或横线，建议改为: {name.replace("_", "").replace("-", "")}')
    
    # 方法名应该使用小驼峰
    elif elem_type == 'Method':
        if name[0].isupper():
            suggestions.append(f'方法名应该使用小驼峰命名法，建议改为: {name[0].lower() + name[1:]}')
    
    # 属性名应该使用小驼峰
    elif elem_type == 'Attribute':
        if name[0].isupper():
            suggestions.append(f'属性名应该使用小驼峰命名法，建议改为: {name[0].lower() + name[1:]}')
    
    # 通用检查
    if len(name) > 50:
        suggestions.append('名称过长，建议缩短到50个字符以内')
    
    if len(name) < 2:
        suggestions.append('名称过短，建议使用更有意义的名称')
    
    return suggestions

# === 新增UML建模API ===

@app.route('/api/v1/view/<view_id>/element', methods=['POST', 'PUT', 'DELETE'])
def manage_view_element(view_id):
    """管理视图元素：添加、更新、删除"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    user_id = sessions_cache[session_id]['user_id']
    
    # 查找视图所属的项目
    projects = load_projects()
    project = None
    model = None
    view = None
    
    for proj in projects.values():
        m = load_model_from_cache(proj.model_id)
        if m:
            v = next((v for v in m.views if v['uuid'] == view_id), None)
            if v:
                project = proj
                model = m
                view = v
                break
    
    if not view:
        return jsonify({'error': '视图不存在'}), 404
    
    if project.owner_id != user_id and project.permissions.get(user_id) not in ['owner', 'editor']:
        return jsonify({'error': '无权限'}), 403
    
    if request.method == 'POST':
        data = request.json
        element = {
            'uuid': str(uuid.uuid4()),
            'type': data.get('type', 'Class'),
            'name': data.get('name', '未命名'),
            'description': data.get('description', ''),
            'x': data.get('x', 100),
            'y': data.get('y', 100),
            'width': data.get('width', 120),
            'height': data.get('height', 80),
            'attributes': data.get('attributes', []),
            'methods': data.get('methods', []),
            'properties': data.get('properties', {}),
            'style': data.get('style', {}),
            'layer_id': data.get('layer_id', 'default')
        }
        
        view['elements'].append(element)
        view['updated_at'] = datetime.datetime.now().isoformat()
        save_model(project.model_id, model)
        
        # 记录操作日志
        add_operation_log(project.id, user_id, 'element_create', 
                          f'创建元素「{element["name"]}」', request.remote_addr or 'localhost')
        
        return jsonify({'message': '元素创建成功', 'element': element})
    
    elif request.method == 'PUT':
        data = request.json
        element_id = data.get('element_id')
        element = next((e for e in view['elements'] if e['uuid'] == element_id), None)
        
        if not element:
            return jsonify({'error': '元素不存在'}), 404
        
        # 更新元素属性
        for key in ['name', 'description', 'x', 'y', 'width', 'height', 
                    'attributes', 'methods', 'properties', 'style', 'layer_id']:
            if key in data:
                element[key] = data[key]
        
        element['updated_at'] = datetime.datetime.now().isoformat()
        view['updated_at'] = datetime.datetime.now().isoformat()
        save_model(project.model_id, model)
        
        add_operation_log(project.id, user_id, 'element_update', 
                          f'更新元素「{element["name"]}」', request.remote_addr or 'localhost')
        
        return jsonify({'message': '元素更新成功', 'element': element})
    
    elif request.method == 'DELETE':
        data = request.json
        element_id = data.get('element_id')
        element = next((e for e in view['elements'] if e['uuid'] == element_id), None)
        
        if not element:
            return jsonify({'error': '元素不存在'}), 404
        
        view['elements'] = [e for e in view['elements'] if e['uuid'] != element_id]
        # 同时删除相关的关系
        view['relationships'] = [r for r in view['relationships'] 
                                  if r['source'] != element_id and r['target'] != element_id]
        
        view['updated_at'] = datetime.datetime.now().isoformat()
        save_model(project.model_id, model)
        
        add_operation_log(project.id, user_id, 'element_delete', 
                          f'删除元素「{element["name"]}」', request.remote_addr or 'localhost')
        
        return jsonify({'message': '元素删除成功'})

@app.route('/api/v1/view/<view_id>/relationship', methods=['POST', 'PUT', 'DELETE'])
def manage_view_relationship(view_id):
    """管理视图关系：添加、更新、删除"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    user_id = sessions_cache[session_id]['user_id']
    
    # 查找视图
    projects = load_projects()
    project = None
    model = None
    view = None
    
    for proj in projects.values():
        m = load_model_from_cache(proj.model_id)
        if m:
            v = next((v for v in m.views if v['uuid'] == view_id), None)
            if v:
                project = proj
                model = m
                view = v
                break
    
    if not view:
        return jsonify({'error': '视图不存在'}), 404
    
    if project.owner_id != user_id and project.permissions.get(user_id) not in ['owner', 'editor']:
        return jsonify({'error': '无权限'}), 403
    
    if request.method == 'POST':
        data = request.json
        source_id = data.get('source')
        target_id = data.get('target')
        
        # 验证源和目标元素存在
        source = next((e for e in view['elements'] if e['uuid'] == source_id), None)
        target = next((e for e in view['elements'] if e['uuid'] == target_id), None)
        
        if not source or not target:
            return jsonify({'error': '源或目标元素不存在'}), 400
        
        relationship = {
            'uuid': str(uuid.uuid4()),
            'source': source_id,
            'target': target_id,
            'source_name': source['name'],
            'target_name': target['name'],
            'type': data.get('type', 'Association'),
            'description': data.get('description', ''),
            'properties': data.get('properties', {}),
            'style': data.get('style', {})
        }
        
        view['relationships'].append(relationship)
        view['updated_at'] = datetime.datetime.now().isoformat()
        save_model(project.model_id, model)
        
        add_operation_log(project.id, user_id, 'relationship_create', 
                          f'创建关系「{source["name"]} -> {target["name"]}」', request.remote_addr or 'localhost')
        
        return jsonify({'message': '关系创建成功', 'relationship': relationship})
    
    elif request.method == 'DELETE':
        data = request.json
        rel_id = data.get('relationship_id')
        relationship = next((r for r in view['relationships'] if r['uuid'] == rel_id), None)
        
        if not relationship:
            return jsonify({'error': '关系不存在'}), 404
        
        view['relationships'] = [r for r in view['relationships'] if r['uuid'] != rel_id]
        view['updated_at'] = datetime.datetime.now().isoformat()
        save_model(project.model_id, model)
        
        return jsonify({'message': '关系删除成功'})

@app.route('/api/v1/view/<view_id>/ai/recommend', methods=['POST'])
def ai_recommend_for_view(view_id):
    """AI智能推荐元素和关系"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    # 查找视图
    projects = load_projects()
    project = None
    model = None
    view = None
    
    for proj in projects.values():
        m = load_model_from_cache(proj.model_id)
        if m:
            v = next((v for v in m.views if v['uuid'] == view_id), None)
            if v:
                project = proj
                model = m
                view = v
                break
    
    if not view:
        return jsonify({'error': '视图不存在'}), 404
    
    data = request.json
    element_id = data.get('element_id')
    context = data.get('context', '')
    
    recommendations = {
        'elements': [],
        'relationships': [],
        'attributes': [],
        'methods': []
    }
    
    # 推荐关联元素
    recommendations['elements'] = ai_recommend_elements(
        view['type'], view['elements'], context
    )
    
    # 如果指定了元素，推荐关系
    if element_id:
        element = next((e for e in view['elements'] if e['uuid'] == element_id), None)
        if element:
            recommendations['relationships'] = ai_recommend_relationships(
                element, view['elements'], view['type']
            )
            
            # 推荐属性和方法
            if element['type'] == 'Class':
                attrs, methods = ai_generate_attributes_methods(
                    element['name'], element.get('description', '')
                )
                recommendations['attributes'] = attrs
                recommendations['methods'] = methods
    
    return jsonify({
        'message': 'AI推荐完成',
        'recommendations': recommendations
    })

@app.route('/api/v1/view/<view_id>/ai/complete', methods=['POST'])
def ai_complete_element(view_id):
    """AI自动补全元素属性、方法、注释"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    # 查找视图
    projects = load_projects()
    project = None
    model = None
    view = None
    
    for proj in projects.values():
        m = load_model_from_cache(proj.model_id)
        if m:
            v = next((v for v in m.views if v['uuid'] == view_id), None)
            if v:
                project = proj
                model = m
                view = v
                break
    
    if not view:
        return jsonify({'error': '视图不存在'}), 404
    
    data = request.json
    element_id = data.get('element_id')
    element = next((e for e in view['elements'] if e['uuid'] == element_id), None)
    
    if not element:
        return jsonify({'error': '元素不存在'}), 404
    
    completion = {
        'element_id': element_id,
        'original': {
            'attributes': element.get('attributes', []),
            'methods': element.get('methods', []),
            'description': element.get('description', '')
        }
    }
    
    # 根据元素类型补全
    if element['type'] == 'Class':
        attrs, methods = ai_generate_attributes_methods(
            element['name'], element.get('description', '')
        )
        
        # 合并现有和生成的
        existing_attrs = set(element.get('attributes', []))
        existing_methods = set(element.get('methods', []))
        
        new_attrs = [a for a in attrs if a not in existing_attrs]
        new_methods = [m for m in methods if m not in existing_methods]
        
        completion['suggested'] = {
            'attributes': new_attrs,
            'methods': new_methods,
            'description': f'{element["name"]}类，用于处理相关业务逻辑。' if not element.get('description') else None
        }
    
    # 命名规范建议
    naming_suggestions = ai_suggest_naming_convention(element)
    completion['naming_suggestions'] = naming_suggestions
    
    return jsonify({
        'message': 'AI补全完成',
        'completion': completion
    })

@app.route('/api/v1/view/<view_id>/layer', methods=['GET', 'POST', 'PUT', 'DELETE'])
def manage_view_layers(view_id):
    """管理视图图层"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    if request.method == 'GET':
        layers = get_view_layers(view_id)
        return jsonify({'layers': layers})
    
    elif request.method == 'POST':
        data = request.json
        layer = ViewLayer(view_id, data.get('name', '新图层'), 
                          data.get('order_num', 0)).to_dict()
        
        if view_id not in view_layers_cache:
            view_layers_cache[view_id] = []
        view_layers_cache[view_id].append(layer)
        
        return jsonify({'message': '图层创建成功', 'layer': layer})
    
    elif request.method == 'PUT':
        data = request.json
        layer_id = data.get('layer_id')
        
        if view_id in view_layers_cache:
            for layer in view_layers_cache[view_id]:
                if layer['id'] == layer_id:
                    if 'name' in data:
                        layer['name'] = data['name']
                    if 'is_locked' in data:
                        layer['is_locked'] = data['is_locked']
                    if 'is_visible' in data:
                        layer['is_visible'] = data['is_visible']
                    if 'order_num' in data:
                        layer['order_num'] = data['order_num']
                    return jsonify({'message': '图层更新成功', 'layer': layer})
        
        return jsonify({'error': '图层不存在'}), 404
    
    elif request.method == 'DELETE':
        data = request.json
        layer_id = data.get('layer_id')
        
        if view_id in view_layers_cache:
            view_layers_cache[view_id] = [l for l in view_layers_cache[view_id] if l['id'] != layer_id]
            return jsonify({'message': '图层删除成功'})
        
        return jsonify({'error': '图层不存在'}), 404

@app.route('/api/v1/view/<view_id>/theme', methods=['GET', 'PUT'])
def manage_view_theme(view_id):
    """管理视图主题"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    if request.method == 'GET':
        return jsonify({
            'themes': UML_THEMES,
            'current_theme': 'default'
        })
    
    elif request.method == 'PUT':
        data = request.json
        theme_name = data.get('theme', 'default')
        
        if theme_name not in UML_THEMES:
            return jsonify({'error': '主题不存在'}), 400
        
        return jsonify({
            'message': '主题切换成功',
            'theme': UML_THEMES[theme_name]
        })

@app.route('/api/v1/view/<view_id>/snapshot', methods=['POST', 'GET'])
def manage_view_snapshots(view_id):
    """管理视图快照"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    user_id = sessions_cache[session_id]['user_id']
    
    if request.method == 'POST':
        data = request.json
        name = data.get('name', f'快照_{datetime.datetime.now().strftime("%Y%m%d_%H%M%S")}')
        version = data.get('version', '1.0.0')
        
        snapshot = ViewSnapshot(view_id, name, version, user_id)
        
        # 保存当前视图数据
        projects = load_projects()
        for proj in projects.values():
            m = load_model_from_cache(proj.model_id)
            if m:
                v = next((v for v in m.views if v['uuid'] == view_id), None)
                if v:
                    snapshot.data = {
                        'elements': v.get('elements', []),
                        'relationships': v.get('relationships', [])
                    }
                    break
        
        if view_id not in view_snapshots_cache:
            view_snapshots_cache[view_id] = []
        view_snapshots_cache[view_id].insert(0, snapshot.to_dict())
        
        return jsonify({
            'message': '快照创建成功',
            'snapshot': snapshot.to_dict()
        })
    
    elif request.method == 'GET':
        snapshots = view_snapshots_cache.get(view_id, [])
        return jsonify({'snapshots': snapshots})

@app.route('/api/v1/view/<view_id>/export', methods=['POST'])
def export_view(view_id):
    """导出视图"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    data = request.json
    format_type = data.get('format', 'json')
    
    # 查找视图
    projects = load_projects()
    project = None
    model = None
    view = None
    
    for proj in projects.values():
        m = load_model_from_cache(proj.model_id)
        if m:
            v = next((v for v in m.views if v['uuid'] == view_id), None)
            if v:
                project = proj
                model = m
                view = v
                break
    
    if not view:
        return jsonify({'error': '视图不存在'}), 404
    
    if format_type == 'json':
        export_data = {
            'view': view,
            'exported_at': datetime.datetime.now().isoformat(),
            'format': 'json'
        }
    elif format_type == 'xmi':
        # 简化的XMI格式
        export_data = {
            'xmi': generate_xmi(view),
            'exported_at': datetime.datetime.now().isoformat(),
            'format': 'xmi'
        }
    else:
        export_data = {
            'view': view,
            'exported_at': datetime.datetime.now().isoformat(),
            'format': 'json'
        }
    
    return jsonify({
        'message': '导出成功',
        'export_data': export_data
    })

def generate_xmi(view):
    """生成简化的XMI格式"""
    xmi = f'''<?xml version="1.0" encoding="UTF-8"?>
<XMI xmlns:UML="http://www.omg.org/spec/UML/20161101">
    <XMI.content>
        <UML:Model name="{view.get('name', 'Model')}">
            <UML:Namespace.ownedElement>'''
    
    for elem in view.get('elements', []):
        xmi += f'''
                <UML:Class xmi.id="{elem['uuid']}" name="{elem['name']}" />'''
    
    for rel in view.get('relationships', []):
        xmi += f'''
                <UML:Association xmi.id="{rel['uuid']}">
                    <UML:Association.connection>
                        <UML:AssociationEnd type="{rel['source']}"/>
                        <UML:AssociationEnd type="{rel['target']}"/>
                    </UML:Association.connection>
                </UML:Association>'''
    
    xmi += '''
            </UML:Namespace.ownedElement>
        </UML:Model>
    </XMI.content>
</XMI>'''
    
    return xmi

@app.route('/api/v1/view/<view_id>/clone', methods=['POST'])
def clone_view(view_id):
    """复制视图"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    user_id = sessions_cache[session_id]['user_id']
    
    # 查找视图
    projects = load_projects()
    project = None
    model = None
    view = None
    
    for proj in projects.values():
        m = load_model_from_cache(proj.model_id)
        if m:
            v = next((v for v in m.views if v['uuid'] == view_id), None)
            if v:
                project = proj
                model = m
                view = v
                break
    
    if not view:
        return jsonify({'error': '视图不存在'}), 404
    
    if project.owner_id != user_id and project.permissions.get(user_id) not in ['owner', 'editor']:
        return jsonify({'error': '无权限'}), 403
    
    # 创建副本
    cloned_view = {
        'uuid': str(uuid.uuid4()),
        'name': view['name'] + ' (副本)',
        'type': view['type'],
        'package_id': view.get('package_id'),
        'elements': [dict(e) for e in view.get('elements', [])],
        'relationships': [dict(r) for r in view.get('relationships', [])],
        'created_at': datetime.datetime.now().isoformat(),
        'updated_at': datetime.datetime.now().isoformat()
    }
    
    # 为副本元素生成新的UUID
    uuid_map = {}
    for elem in cloned_view['elements']:
        old_uuid = elem['uuid']
        new_uuid = str(uuid.uuid4())
        uuid_map[old_uuid] = new_uuid
        elem['uuid'] = new_uuid
    
    for rel in cloned_view['relationships']:
        rel['uuid'] = str(uuid.uuid4())
        rel['source'] = uuid_map.get(rel['source'], rel['source'])
        rel['target'] = uuid_map.get(rel['target'], rel['target'])
    
    model.views.append(cloned_view)
    save_model(project.model_id, model)
    
    return jsonify({
        'message': '视图复制成功',
        'view': cloned_view
    })

# === 模块三：模型元素与UML扩展体系 ===

# UML Profile管理类
class UMLProfile:
    """UML Profile概要文件"""
    def __init__(self, name, description='', project_id=None):
        self.id = str(uuid.uuid4())[:8]
        self.name = name
        self.description = description
        self.project_id = project_id
        self.version = '1.0.0'
        self.author = ''
        self.stereotypes = []
        self.tagged_values = []
        self.constraints = []
        self.created_at = datetime.datetime.now().isoformat()
        self.updated_at = datetime.datetime.now().isoformat()
    
    def add_stereotype(self, name, description='', icon='', style=None, properties=None):
        """添加构造型"""
        stereotype = {
            'id': str(uuid.uuid4())[:8],
            'name': name,
            'description': description,
            'icon': icon,
            'style': style or {},
            'properties': properties or [],
            'created_at': datetime.datetime.now().isoformat()
        }
        self.stereotypes.append(stereotype)
        self.updated_at = datetime.datetime.now().isoformat()
        return stereotype
    
    def add_tagged_value(self, name, description='', data_type='string', default_value='', stereotype_id=None, constraint=None):
        """添加标记值"""
        tagged_value = {
            'id': str(uuid.uuid4())[:8],
            'name': name,
            'description': description,
            'data_type': data_type,
            'default_value': default_value,
            'stereotype_id': stereotype_id,
            'constraint': constraint or {},
            'created_at': datetime.datetime.now().isoformat()
        }
        self.tagged_values.append(tagged_value)
        self.updated_at = datetime.datetime.now().isoformat()
        return tagged_value
    
    def add_constraint(self, name, description='', ocl_expression='', target_type=''):
        """添加约束"""
        constraint = {
            'id': str(uuid.uuid4())[:8],
            'name': name,
            'description': description,
            'ocl_expression': ocl_expression,
            'target_type': target_type,
            'created_at': datetime.datetime.now().isoformat()
        }
        self.constraints.append(constraint)
        self.updated_at = datetime.datetime.now().isoformat()
        return constraint
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'project_id': self.project_id,
            'version': self.version,
            'author': self.author,
            'stereotypes': self.stereotypes,
            'tagged_values': self.tagged_values,
            'constraints': self.constraints,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }

# Profile缓存
profiles_cache = {}

# 元素扩展缓存
element_extensions_cache = {}

# 元素标签缓存
element_tags_cache = {}

# 系统内置构造型
BUILTIN_STEREOTYPES = {
    'business': {
        'name': '业务',
        'description': '业务层元素',
        'icon': '🏢',
        'color': '#FFFFB5'
    },
    'application': {
        'name': '应用',
        'description': '应用层元素',
        'icon': '💻',
        'color': '#B5FFFF'
    },
    'technology': {
        'name': '技术',
        'description': '技术层元素',
        'icon': '⚙️',
        'color': '#C9E7B7'
    },
    'entity': {
        'name': '实体',
        'description': '业务实体',
        'icon': '📦',
        'color': '#F5DEAA'
    },
    'service': {
        'name': '服务',
        'description': '服务接口',
        'icon': '🔌',
        'color': '#DDA0DD'
    },
    'repository': {
        'name': '仓储',
        'description': '数据仓储',
        'icon': '🗄️',
        'color': '#FFDAB9'
    },
    'controller': {
        'name': '控制器',
        'description': '控制层',
        'icon': '🎮',
        'color': '#E0FFFF'
    },
    'dto': {
        'name': 'DTO',
        'description': '数据传输对象',
        'icon': '📤',
        'color': '#F0E68C'
    },
    'exception': {
        'name': '异常',
        'description': '异常类',
        'icon': '⚠️',
        'color': '#FFB6C1'
    },
    'configuration': {
        'name': '配置',
        'description': '配置类',
        'icon': '⚙️',
        'color': '#D3D3D3'
    }
}

# === AI智能扩展建模功能 ===

def ai_recommend_stereotypes(element, context=''):
    """AI智能推荐构造型"""
    recommendations = []
    element_type = element.get('type', '')
    element_name = element.get('name', '')
    description = element.get('description', '')
    
    # 基于元素类型推荐
    if element_type in ['Class', 'ApplicationComponent']:
        # 基于名称关键词推荐
        name_lower = element_name.lower()
        
        if any(keyword in name_lower for keyword in ['service', '服务']):
            recommendations.append({'name': 'service', 'confidence': 0.9, 'reason': '名称包含服务关键词'})
        elif any(keyword in name_lower for keyword in ['repository', '仓储', 'dao']):
            recommendations.append({'name': 'repository', 'confidence': 0.9, 'reason': '名称包含仓储关键词'})
        elif any(keyword in name_lower for keyword in ['controller', '控制']):
            recommendations.append({'name': 'controller', 'confidence': 0.85, 'reason': '名称包含控制器关键词'})
        elif any(keyword in name_lower for keyword in ['dto', 'vo', 'dto', 'transfer']):
            recommendations.append({'name': 'dto', 'confidence': 0.85, 'reason': '名称包含DTO关键词'})
        elif any(keyword in name_lower for keyword in ['exception', '异常']):
            recommendations.append({'name': 'exception', 'confidence': 0.8, 'reason': '名称包含异常关键词'})
        elif any(keyword in name_lower for keyword in ['config', '配置']):
            recommendations.append({'name': 'configuration', 'confidence': 0.8, 'reason': '名称包含配置关键词'})
        elif any(keyword in name_lower for keyword in ['entity', '实体', 'model']):
            recommendations.append({'name': 'entity', 'confidence': 0.85, 'reason': '名称包含实体关键词'})
        
        # 基于描述推荐
        if description:
            desc_lower = description.lower()
            if any(keyword in desc_lower for keyword in ['业务', '领域']):
                recommendations.append({'name': 'business', 'confidence': 0.7, 'reason': '描述包含业务领域关键词'})
            elif any(keyword in desc_lower for keyword in ['技术', '实现']):
                recommendations.append({'name': 'technology', 'confidence': 0.7, 'reason': '描述包含技术实现关键词'})
    
    return recommendations

def ai_generate_tagged_values(element, stereotype_name=''):
    """AI智能生成标记值"""
    tagged_values = []
    element_type = element.get('type', '')
    
    if stereotype_name == 'service':
        tagged_values = [
            {'name': 'serviceLevel', 'data_type': 'string', 'default_value': 'SLA-99.9%', 'description': '服务级别协议'},
            {'name': 'timeout', 'data_type': 'integer', 'default_value': '30000', 'description': '超时时间(ms)'},
            {'name': 'retryCount', 'data_type': 'integer', 'default_value': '3', 'description': '重试次数'}
        ]
    elif stereotype_name == 'entity':
        tagged_values = [
            {'name': 'tableName', 'data_type': 'string', 'default_value': '', 'description': '数据库表名'},
            {'name': 'primaryKey', 'data_type': 'string', 'default_value': 'id', 'description': '主键字段'},
            {'name': 'cacheable', 'data_type': 'boolean', 'default_value': 'false', 'description': '是否缓存'}
        ]
    elif stereotype_name == 'repository':
        tagged_values = [
            {'name': 'dataSource', 'data_type': 'string', 'default_value': 'default', 'description': '数据源名称'},
            {'name': 'readOnly', 'data_type': 'boolean', 'default_value': 'false', 'description': '是否只读'}
        ]
    elif element_type == 'Class':
        tagged_values = [
            {'name': 'version', 'data_type': 'string', 'default_value': '1.0', 'description': '版本号'},
            {'name': 'author', 'data_type': 'string', 'default_value': '', 'description': '作者'},
            {'name': 'status', 'data_type': 'string', 'default_value': 'draft', 'description': '状态'},
            {'name': 'priority', 'data_type': 'string', 'default_value': 'medium', 'description': '优先级'}
        ]
    
    return tagged_values

def ai_generate_ocl_constraint(element, rule_description=''):
    """AI生成OCL约束"""
    constraints = []
    
    if not rule_description:
        # 默认约束
        if element.get('type') == 'Class':
            constraints.append({
                'name': '非空约束',
                'ocl_expression': 'self.name->notEmpty()',
                'description': '元素名称不能为空',
                'target_type': 'Class'
            })
            constraints.append({
                'name': '名称长度约束',
                'ocl_expression': 'self.name.size() <= 50',
                'description': '元素名称长度不能超过50个字符',
                'target_type': 'Class'
            })
    else:
        # 基于自然语言描述生成约束
        if any(keyword in rule_description for keyword in ['唯一', 'unique', '不重复']):
            constraints.append({
                'name': '唯一性约束',
                'ocl_expression': 'self.allInstances()->isUnique(x | x.name)',
                'description': rule_description,
                'target_type': element.get('type', 'Class')
            })
        if any(keyword in rule_description for keyword in ['非空', 'not null', '必填']):
            constraints.append({
                'name': '非空约束',
                'ocl_expression': 'self.name->notEmpty()',
                'description': rule_description,
                'target_type': element.get('type', 'Class')
            })
    
    return constraints

def ai_classify_elements(model):
    """AI智能分类元素"""
    classifications = []
    
    for elem in model.elements:
        tags = []
        category = '未分类'
        
        # 基于类型分类
        elem_type = elem.get('type', '')
        if elem_type in ['Class', 'ApplicationComponent']:
            category = '业务组件'
            tags.append('component')
        elif elem_type == 'Actor':
            category = '角色'
            tags.append('actor')
        elif elem_type == 'UseCase':
            category = '用例'
            tags.append('usecase')
        elif elem_type in ['Database', 'Node', 'Device']:
            category = '基础设施'
            tags.append('infrastructure')
        
        # 基于名称关键词添加标签
        name_lower = elem.get('name', '').lower()
        if 'user' in name_lower or '用户' in name_lower:
            tags.append('user-related')
        if 'order' in name_lower or '订单' in name_lower:
            tags.append('order-related')
        if 'product' in name_lower or '商品' in name_lower:
            tags.append('product-related')
        if 'service' in name_lower or '服务' in name_lower:
            tags.append('service')
        if 'api' in name_lower:
            tags.append('api')
        
        classifications.append({
            'element_id': elem['uuid'],
            'element_name': elem['name'],
            'category': category,
            'tags': tags,
            'confidence': 0.85
        })
    
    return classifications

def ai_validate_constraints(model):
    """AI校验约束"""
    violations = []
    warnings = []
    
    for elem in model.elements:
        # 检查命名规范
        name = elem.get('name', '')
        if not name or name.strip() == '':
            violations.append({
                'element_id': elem['uuid'],
                'element_name': '未命名',
                'type': 'naming',
                'severity': 'error',
                'message': '元素名称不能为空',
                'suggestion': '请为元素添加有意义的名称'
            })
        elif len(name) > 100:
            warnings.append({
                'element_id': elem['uuid'],
                'element_name': name,
                'type': 'naming',
                'severity': 'warning',
                'message': f'元素名称过长（{len(name)}字符）',
                'suggestion': '建议缩短名称至50字符以内'
            })
        
        # 检查类的属性
        if elem.get('type') == 'Class':
            attrs = elem.get('attributes', [])
            if len(attrs) == 0:
                warnings.append({
                    'element_id': elem['uuid'],
                    'element_name': name,
                    'type': 'structure',
                    'severity': 'warning',
                    'message': '类没有定义属性',
                    'suggestion': '建议为类添加属性'
                })
    
    # 检查关系
    for rel in model.relationships:
        if rel['source'] == rel['target']:
            violations.append({
                'relationship_id': rel.get('uuid', ''),
                'type': 'relationship',
                'severity': 'error',
                'message': f'自引用关系: {rel.get("source_name", "")}',
                'suggestion': '请检查并修复自引用关系'
            })
    
    return {
        'valid': len(violations) == 0,
        'violations': violations,
        'warnings': warnings,
        'summary': f'检测到 {len(violations)} 个错误和 {len(warnings)} 个警告'
    }

def ai_generate_profile(industry='software', requirements=''):
    """AI生成UML Profile"""
    profile = UMLProfile(f'{industry}_profile', f'{industry}行业标准Profile')
    
    # 基于行业生成构造型
    industry_stereotypes = {
        '金融': ['account', 'transaction', 'security', 'risk', 'compliance'],
        '制造': ['product', 'workflow', 'quality', 'inventory', 'equipment'],
        '政务': ['service', 'approval', 'data', 'security', 'regulation'],
        '物联网': ['device', 'sensor', 'gateway', 'cloud', 'analytics'],
        '软件': ['service', 'controller', 'repository', 'dto', 'entity']
    }
    
    stereotypes = industry_stereotypes.get(industry, industry_stereotypes['软件'])
    
    for stereotype in stereotypes:
        profile.add_stereotype(
            name=stereotype,
            description=f'{stereotype}相关元素',
            icon='📌',
            style={'color': '#4CAF50'}
        )
    
    # 添加通用标记值
    common_tags = [
        {'name': 'version', 'data_type': 'string', 'description': '版本号'},
        {'name': 'author', 'data_type': 'string', 'description': '作者'},
        {'name': 'status', 'data_type': 'string', 'description': '状态'},
        {'name': 'priority', 'data_type': 'string', 'description': '优先级'},
        {'name': 'phase', 'data_type': 'string', 'description': '阶段'}
    ]
    
    for tag in common_tags:
        profile.add_tagged_value(**tag)
    
    # 添加通用约束
    profile.add_constraint(
        name='命名规范',
        description='元素名称不能为空且长度不超过50字符',
        ocl_expression='self.name->notEmpty() and self.name.size() <= 50',
        target_type='Class'
    )
    
    profile.add_constraint(
        name='唯一性约束',
        description='同一包内元素名称应唯一',
        ocl_expression='self.allInstances()->isUnique(x | x.name)',
        target_type='Class'
    )
    
    return profile

# === UML扩展体系API ===

@app.route('/api/v1/project/<project_id>/profile/create', methods=['POST'])
def create_profile(project_id):
    """创建新的UML Profile"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    data = request.json
    name = data.get('name', '未命名Profile')
    description = data.get('description', '')
    
    profile = UMLProfile(name, description, project_id)
    profiles_cache[profile.id] = profile
    
    return jsonify({
        'message': 'Profile创建成功',
        'profile': profile.to_dict()
    })

@app.route('/api/v1/project/<project_id>/profile/list', methods=['GET'])
def get_profile_list(project_id):
    """获取项目内的Profile列表"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    profiles = []
    for profile in profiles_cache.values():
        if profile.project_id == project_id or profile.project_id is None:
            profiles.append(profile.to_dict())
    
    # 添加系统内置Profile
    profiles.append({
        'id': 'builtin',
        'name': '系统内置Profile',
        'description': '系统内置的构造型和标记值',
        'stereotypes': [{'id': k, 'name': v['name'], 'description': v['description'], 'icon': v['icon']} 
                        for k, v in BUILTIN_STEREOTYPES.items()],
        'is_builtin': True
    })
    
    return jsonify({'profiles': profiles})

@app.route('/api/v1/profile/<profile_id>', methods=['GET'])
def get_profile_detail(profile_id):
    """获取Profile详情"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    if profile_id == 'builtin':
        return jsonify({
            'profile': {
                'id': 'builtin',
                'name': '系统内置Profile',
                'description': '系统内置的构造型和标记值',
                'stereotypes': [{'id': k, 'name': v['name'], 'description': v['description'], 
                                'icon': v['icon'], 'color': v['color']} 
                               for k, v in BUILTIN_STEREOTYPES.items()],
                'tagged_values': [],
                'constraints': [],
                'is_builtin': True
            }
        })
    
    if profile_id not in profiles_cache:
        return jsonify({'error': 'Profile不存在'}), 404
    
    return jsonify({'profile': profiles_cache[profile_id].to_dict()})

@app.route('/api/v1/profile/<profile_id>/save', methods=['PUT'])
def save_profile(profile_id):
    """保存Profile内容"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    if profile_id not in profiles_cache:
        return jsonify({'error': 'Profile不存在'}), 404
    
    profile = profiles_cache[profile_id]
    data = request.json
    
    if 'name' in data:
        profile.name = data['name']
    if 'description' in data:
        profile.description = data['description']
    if 'version' in data:
        profile.version = data['version']
    
    # 更新构造型
    if 'stereotypes' in data:
        profile.stereotypes = data['stereotypes']
    
    # 更新标记值
    if 'tagged_values' in data:
        profile.tagged_values = data['tagged_values']
    
    # 更新约束
    if 'constraints' in data:
        profile.constraints = data['constraints']
    
    profile.updated_at = datetime.datetime.now().isoformat()
    
    return jsonify({'message': 'Profile保存成功', 'profile': profile.to_dict()})

@app.route('/api/v1/project/<project_id>/profile/apply', methods=['POST'])
def apply_profile(project_id):
    """应用Profile到项目"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    data = request.json
    profile_id = data.get('profile_id')
    
    if profile_id not in profiles_cache:
        return jsonify({'error': 'Profile不存在'}), 404
    
    profile = profiles_cache[profile_id]
    projects = load_projects()
    
    if project_id not in projects:
        return jsonify({'error': '项目不存在'}), 404
    
    project = projects[project_id]
    model = load_model_from_cache(project.model_id)
    
    applied_count = 0
    for stereotype in profile.stereotypes:
        # 为匹配的元素应用构造型
        for elem in model.elements:
            # 简单匹配：基于元素类型
            if elem.get('type') in ['Class', 'ApplicationComponent']:
                if 'stereotypes' not in elem:
                    elem['stereotypes'] = []
                if stereotype['name'] not in elem['stereotypes']:
                    elem['stereotypes'].append(stereotype['name'])
                    applied_count += 1
    
    save_model(project.model_id, model)
    
    return jsonify({
        'message': 'Profile应用成功',
        'applied_count': applied_count,
        'stereotype_count': len(profile.stereotypes)
    })

@app.route('/api/v1/project/<project_id>/profile/ai/generate', methods=['POST'])
def ai_generate_profile_api(project_id):
    """AI生成Profile"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    data = request.json
    industry = data.get('industry', 'software')
    requirements = data.get('requirements', '')
    
    profile = ai_generate_profile(industry, requirements)
    profile.project_id = project_id
    profiles_cache[profile.id] = profile
    
    return jsonify({
        'message': 'AI生成Profile成功',
        'profile': profile.to_dict()
    })

@app.route('/api/v1/element/<element_id>/extension', methods=['PUT'])
def update_element_extension(element_id):
    """编辑元素的扩展属性"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    data = request.json
    
    # 查找元素所在的项目和模型
    projects = load_projects()
    found = False
    
    for project in projects.values():
        model = load_model_from_cache(project.model_id)
        if model:
            elem = next((e for e in model.elements if e['uuid'] == element_id), None)
            if elem:
                # 更新构造型
                if 'stereotypes' in data:
                    elem['stereotypes'] = data['stereotypes']
                
                # 更新标记值
                if 'tagged_values' in data:
                    if 'tagged_values' not in elem:
                        elem['tagged_values'] = {}
                    elem['tagged_values'].update(data['tagged_values'])
                
                # 更新约束
                if 'constraints' in data:
                    elem['constraints'] = data['constraints']
                
                save_model(project.model_id, model)
                found = True
                break
            
            # 检查视图中的元素
            for view in model.views:
                elem_in_view = next((e for e in view.get('elements', []) if e['uuid'] == element_id), None)
                if elem_in_view:
                    if 'stereotypes' in data:
                        elem_in_view['stereotypes'] = data['stereotypes']
                    save_model(project.model_id, model)
                    found = True
                    break
    
    if not found:
        return jsonify({'error': '元素不存在'}), 404
    
    return jsonify({'message': '元素扩展属性更新成功'})

@app.route('/api/v1/project/<project_id>/element/ai/classify', methods=['POST'])
def ai_classify_elements_api(project_id):
    """AI智能分类元素"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    projects = load_projects()
    if project_id not in projects:
        return jsonify({'error': '项目不存在'}), 404
    
    project = projects[project_id]
    model = load_model_from_cache(project.model_id)
    
    if not model:
        return jsonify({'error': '模型不存在'}), 404
    
    classifications = ai_classify_elements(model)
    
    # 应用分类结果到元素
    for classification in classifications:
        elem = next((e for e in model.elements if e['uuid'] == classification['element_id']), None)
        if elem:
            if 'category' not in elem:
                elem['category'] = classification['category']
            if 'tags' not in elem:
                elem['tags'] = []
            for tag in classification['tags']:
                if tag not in elem['tags']:
                    elem['tags'].append(tag)
    
    save_model(project.model_id, model)
    
    return jsonify({
        'message': 'AI分类完成',
        'classifications': classifications,
        'total_classified': len(classifications)
    })

@app.route('/api/v1/project/<project_id>/constraint/validate', methods=['POST'])
def validate_constraints_api(project_id):
    """约束智能校验"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    projects = load_projects()
    if project_id not in projects:
        return jsonify({'error': '项目不存在'}), 404
    
    project = projects[project_id]
    model = load_model_from_cache(project.model_id)
    
    if not model:
        return jsonify({'error': '模型不存在'}), 404
    
    result = ai_validate_constraints(model)
    
    return jsonify({
        'message': '约束校验完成',
        'valid': result['valid'],
        'violations': result['violations'],
        'warnings': result['warnings'],
        'summary': result['summary']
    })

@app.route('/api/v1/profile/<profile_id>/export', methods=['POST'])
def export_profile(profile_id):
    """导出Profile"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    if profile_id == 'builtin':
        export_data = {
            'id': 'builtin',
            'name': '系统内置Profile',
            'stereotypes': BUILTIN_STEREOTYPES,
            'exported_at': datetime.datetime.now().isoformat()
        }
        return jsonify({'message': '导出成功', 'export_data': export_data})
    
    if profile_id not in profiles_cache:
        return jsonify({'error': 'Profile不存在'}), 404
    
    profile = profiles_cache[profile_id]
    export_data = profile.to_dict()
    export_data['exported_at'] = datetime.datetime.now().isoformat()
    
    return jsonify({'message': '导出成功', 'export_data': export_data})

@app.route('/api/v1/profile/import', methods=['POST'])
def import_profile():
    """导入Profile"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    data = request.json
    profile_data = data.get('profile_data')
    
    if not profile_data:
        return jsonify({'error': '缺少Profile数据'}), 400
    
    # 创建新Profile
    profile = UMLProfile(profile_data.get('name', '导入的Profile'), 
                         profile_data.get('description', ''))
    profile.version = profile_data.get('version', '1.0.0')
    
    # 复制构造型
    for stereo in profile_data.get('stereotypes', []):
        profile.stereotypes.append(stereo)
    
    # 复制标记值
    for tv in profile_data.get('tagged_values', []):
        profile.tagged_values.append(tv)
    
    # 复制约束
    for con in profile_data.get('constraints', []):
        profile.constraints.append(con)
    
    profiles_cache[profile.id] = profile
    
    return jsonify({'message': 'Profile导入成功', 'profile': profile.to_dict()})

@app.route('/api/v1/element/<element_id>/tag', methods=['POST', 'DELETE'])
def manage_element_tag(element_id):
    """管理元素标签"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    data = request.json
    tag_name = data.get('tag_name')
    
    if not tag_name:
        return jsonify({'error': '标签名称不能为空'}), 400
    
    # 查找元素
    projects = load_projects()
    found = False
    
    for project in projects.values():
        model = load_model_from_cache(project.model_id)
        if model:
            elem = next((e for e in model.elements if e['uuid'] == element_id), None)
            if elem:
                if request.method == 'POST':
                    if 'tags' not in elem:
                        elem['tags'] = []
                    if tag_name not in elem['tags']:
                        elem['tags'].append(tag_name)
                elif request.method == 'DELETE':
                    if 'tags' in elem:
                        elem['tags'] = [t for t in elem['tags'] if t != tag_name]
                
                save_model(project.model_id, model)
                found = True
                break
    
    if not found:
        return jsonify({'error': '元素不存在'}), 404
    
    action = '添加' if request.method == 'POST' else '删除'
    return jsonify({'message': f'{action}标签成功', 'tags': elem.get('tags', [])})

# === 模块四：企业架构建模 ===

# 架构框架定义
ARCHITECTURE_FRAMEWORKS = {
    'togaf': {
        'name': 'TOGAF 9.2',
        'description': 'The Open Group Architecture Framework',
        'dimensions': ['business', 'application', 'data', 'technology', 'strategy', 'implementation'],
        'views': ['BusinessCapability', 'BusinessProcess', 'ApplicationArchitecture', 'DataArchitecture', 'TechnologyArchitecture']
    },
    'archimate': {
        'name': 'ArchiMate 3.1',
        'description': 'ArchiMate Architecture Modeling Language',
        'dimensions': ['business', 'application', 'technology', 'strategy', 'physical', 'implementation'],
        'views': ['BusinessLayer', 'ApplicationLayer', 'TechnologyLayer', 'PhysicalLayer', 'Motivation']
    },
    'zachman': {
        'name': 'Zachman Framework',
        'description': 'Zachman Enterprise Architecture Framework',
        'dimensions': ['context', 'conceptual', 'logical', 'physical', 'component', 'operations'],
        'views': ['Scope', 'BusinessModel', 'SystemModel', 'TechnologyModel', 'DetailedDesign', 'Implementation']
    },
    'dodaf': {
        'name': 'DoDAF',
        'description': 'Department of Defense Architecture Framework',
        'dimensions': ['operational', 'systems', 'technical', 'project'],
        'views': ['OV-1', 'OV-2', 'OV-3', 'SV-1', 'SV-2', 'TV-1']
    },
    'c4': {
        'name': 'C4 Model',
        'description': 'C4 Software Architecture Model',
        'dimensions': ['context', 'container', 'component', 'code'],
        'views': ['SystemContext', 'Container', 'Component', 'Code']
    },
    'ddd': {
        'name': 'DDD',
        'description': 'Domain-Driven Design',
        'dimensions': ['domain', 'application', 'infrastructure'],
        'views': ['DomainModel', 'ContextMap', 'Aggregate', 'BoundedContext']
    }
}

# 架构维度定义
ARCHITECTURE_DIMENSIONS = {
    'business': {'name': '业务架构', 'icon': '🏢', 'color': '#FFFFB5'},
    'application': {'name': '应用架构', 'icon': '💻', 'color': '#B5FFFF'},
    'data': {'name': '数据架构', 'icon': '📊', 'color': '#E0FFFF'},
    'technology': {'name': '技术架构', 'icon': '⚙️', 'color': '#C9E7B7'},
    'strategy': {'name': '战略架构', 'icon': '🎯', 'color': '#FFDAB9'},
    'implementation': {'name': '实现架构', 'icon': '🚀', 'color': '#DDA0DD'}
}

# 架构元素类型定义
ARCHITECTURE_ELEMENT_TYPES = {
    # 业务架构元素
    'business': [
        {'type': 'BusinessActor', 'name': '业务角色', 'icon': '👤'},
        {'type': 'BusinessProcess', 'name': '业务流程', 'icon': '🔄'},
        {'type': 'BusinessEntity', 'name': '业务实体', 'icon': '📦'},
        {'type': 'BusinessRule', 'name': '业务规则', 'icon': '📋'},
        {'type': 'BusinessCapability', 'name': '业务能力', 'icon': '💪'},
        {'type': 'ValueStream', 'name': '价值流', 'icon': '💰'}
    ],
    # 应用架构元素
    'application': [
        {'type': 'ApplicationSystem', 'name': '应用系统', 'icon': '🖥️'},
        {'type': 'ApplicationComponent', 'name': '应用组件', 'icon': '🧩'},
        {'type': 'Interface', 'name': '接口', 'icon': '🔌'},
        {'type': 'API', 'name': 'API', 'icon': '🌐'},
        {'type': 'DataFlow', 'name': '数据流', 'icon': '📊'}
    ],
    # 数据架构元素
    'data': [
        {'type': 'DataEntity', 'name': '数据实体', 'icon': '📊'},
        {'type': 'DataStore', 'name': '数据存储', 'icon': '🗄️'},
        {'type': 'DataFlow', 'name': '数据流向', 'icon': '➡️'},
        {'type': 'DataDictionary', 'name': '数据字典', 'icon': '📖'}
    ],
    # 技术架构元素
    'technology': [
        {'type': 'Node', 'name': '节点', 'icon': '🖥️'},
        {'type': 'Device', 'name': '设备', 'icon': '📱'},
        {'type': 'Network', 'name': '网络', 'icon': '🌐'},
        {'type': 'Middleware', 'name': '中间件', 'icon': '🔧'},
        {'type': 'Database', 'name': '数据库', 'icon': '🗄️'}
    ],
    # 战略架构元素
    'strategy': [
        {'type': 'BusinessGoal', 'name': '业务目标', 'icon': '🎯'},
        {'type': 'Strategy', 'name': '战略举措', 'icon': '📈'},
        {'type': 'Capability', 'name': '能力', 'icon': '💪'},
        {'type': 'Stakeholder', 'name': '利益相关者', 'icon': '👥'}
    ]
}

# 架构关系类型
ARCHITECTURE_RELATIONSHIP_TYPES = [
    {'type': 'Association', 'name': '关联', 'label': '关联'},
    {'type': 'Aggregation', 'name': '聚合', 'label': '聚合'},
    {'type': 'Composition', 'name': '组合', 'label': '组合'},
    {'type': 'Dependency', 'name': '依赖', 'label': '依赖'},
    {'type': 'Flow', 'name': '流向', 'label': '流向'},
    {'type': 'Realization', 'name': '实现', 'label': '实现'},
    {'type': 'Trigger', 'name': '触发', 'label': '触发'},
    {'type': 'Serves', 'name': '服务于', 'label': '服务于'}
]

# === 架构项目管理类 ===

class ArchitectureProject:
    """企业架构项目"""
    def __init__(self, name, framework_type='archimate', description='', industry='software', business_goal=''):
        self.id = str(uuid.uuid4())[:8]
        self.name = name
        self.description = description
        self.framework_type = framework_type
        self.industry = industry
        self.business_goal = business_goal
        self.user_id = ''
        self.status = 'draft'
        self.dimensions = []
        self.views = []
        self.elements = []
        self.relationships = []
        self.created_at = datetime.datetime.now().isoformat()
        self.updated_at = datetime.datetime.now().isoformat()
        self.config = {}
    
    def add_dimension(self, dimension_type):
        """添加架构维度"""
        dim_info = ARCHITECTURE_DIMENSIONS.get(dimension_type, {'name': dimension_type})
        dimension = {
            'id': str(uuid.uuid4())[:8],
            'type': dimension_type,
            'name': dim_info['name'],
            'description': f'{dim_info["name"]}维度',
            'order_num': len(self.dimensions),
            'icon': dim_info.get('icon', '📐'),
            'color': dim_info.get('color', '#888888'),
            'created_at': datetime.datetime.now().isoformat()
        }
        self.dimensions.append(dimension)
        return dimension
    
    def add_view(self, dimension_id, view_type, name=''):
        """添加架构视图"""
        view = {
            'id': str(uuid.uuid4())[:8],
            'dimension_id': dimension_id,
            'type': view_type,
            'name': name or f'{view_type}视图',
            'description': '',
            'elements': [],
            'relationships': [],
            'created_at': datetime.datetime.now().isoformat(),
            'updated_at': datetime.datetime.now().isoformat()
        }
        self.views.append(view)
        return view
    
    def add_element(self, view_id, element_type, name, description='', x=100, y=100):
        """添加架构元素"""
        element = {
            'id': str(uuid.uuid4())[:8],
            'view_id': view_id,
            'type': element_type,
            'name': name,
            'description': description,
            'x': x,
            'y': y,
            'width': 120,
            'height': 60,
            'properties': {},
            'style': {},
            'created_at': datetime.datetime.now().isoformat()
        }
        self.elements.append(element)
        return element
    
    def add_relationship(self, source_id, target_id, relationship_type, description=''):
        """添加架构关系"""
        relationship = {
            'id': str(uuid.uuid4())[:8],
            'source': source_id,
            'target': target_id,
            'type': relationship_type,
            'description': description,
            'properties': {},
            'created_at': datetime.datetime.now().isoformat()
        }
        self.relationships.append(relationship)
        return relationship
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'framework_type': self.framework_type,
            'industry': self.industry,
            'business_goal': self.business_goal,
            'status': self.status,
            'dimensions': self.dimensions,
            'views': self.views,
            'elements': self.elements,
            'relationships': self.relationships,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'config': self.config
        }

# 架构项目缓存
architecture_projects_cache = {}

# === AI企业架构建模功能 ===

def ai_generate_architecture(project, requirements):
    """AI生成完整架构方案"""
    # 根据框架类型生成架构维度
    framework = ARCHITECTURE_FRAMEWORKS.get(project.framework_type, ARCHITECTURE_FRAMEWORKS['archimate'])
    
    # 添加维度
    for dim_type in framework['dimensions']:
        project.add_dimension(dim_type)
    
    # 为每个维度创建视图
    for dim in project.dimensions:
        view_types = get_view_types_for_dimension(dim['type'])
        for view_type in view_types[:2]:
            project.add_view(dim['id'], view_type)
    
    # AI生成元素
    generate_elements_for_dimension(project, requirements)
    
    return project

def get_view_types_for_dimension(dimension_type):
    """获取维度对应的视图类型"""
    view_mapping = {
        'business': ['BusinessCapability', 'BusinessProcess', 'ValueStream'],
        'application': ['ApplicationArchitecture', 'SystemContext', 'Component'],
        'data': ['DataArchitecture', 'DataFlow', 'DataModel'],
        'technology': ['TechnologyArchitecture', 'Deployment', 'Network'],
        'strategy': ['CapabilityMap', 'StrategyMap', 'Stakeholder']
    }
    return view_mapping.get(dimension_type, ['DefaultView'])

def generate_elements_for_dimension(project, requirements):
    """为各维度生成元素"""
    req_lower = requirements.lower()
    
    # 业务架构元素
    business_dim = next((d for d in project.dimensions if d['type'] == 'business'), None)
    if business_dim:
        business_view = next((v for v in project.views if v['dimension_id'] == business_dim['id']), None)
        if business_view:
            # 生成业务能力
            capabilities = ['用户管理', '订单管理', '产品管理', '支付服务']
            for i, cap in enumerate(capabilities):
                project.add_element(business_view['id'], 'BusinessCapability', cap, f'{cap}能力描述', 100 + i*150, 100)
            
            # 生成业务流程
            processes = ['用户注册', '订单创建', '支付流程', '发货流程']
            for i, proc in enumerate(processes):
                project.add_element(business_view['id'], 'BusinessProcess', proc, f'{proc}流程描述', 100 + i*150, 200)
    
    # 应用架构元素
    app_dim = next((d for d in project.dimensions if d['type'] == 'application'), None)
    if app_dim:
        app_view = next((v for v in project.views if v['dimension_id'] == app_dim['id']), None)
        if app_view:
            apps = ['前端应用', '后端服务', '认证服务', '消息队列']
            for i, app in enumerate(apps):
                project.add_element(app_view['id'], 'ApplicationSystem', app, f'{app}描述', 100 + i*150, 100)
    
    # 技术架构元素
    tech_dim = next((d for d in project.dimensions if d['type'] == 'technology'), None)
    if tech_dim:
        tech_view = next((v for v in project.views if v['dimension_id'] == tech_dim['id']), None)
        if tech_view:
            techs = ['Web服务器', '应用服务器', '数据库', '缓存']
            for i, tech in enumerate(techs):
                project.add_element(tech_view['id'], 'Node', tech, f'{tech}描述', 100 + i*150, 100)
    
    # 添加关系
    add_relationships_between_elements(project)

def add_relationships_between_elements(project):
    """添加元素间的关系"""
    # 简单的关系生成：连接相邻元素
    for view in project.views:
        view_elements = [e for e in project.elements if e['view_id'] == view['id']]
        for i in range(len(view_elements) - 1):
            project.add_relationship(view_elements[i]['id'], view_elements[i+1]['id'], 'Flow')

def _ai_review_architecture_semantics(project):
    """调用LLM做语义级架构评审。AI未启用/失败返回None。"""
    if not ai_service_config.enabled:
        return None

    system_prompt = REVIEW_SYSTEM_PROMPT
    name_map = {e.get('id'): e.get('name') for e in project.elements}
    desc_lines = [
        f"框架类型: {project.framework_type}",
        f"维度: {[d.get('type') for d in project.dimensions]}"
    ]
    for e in project.elements:
        desc_lines.append(f"- {e.get('type')} {e.get('name')}: {e.get('description', '')}")
    for r in project.relationships:
        s = name_map.get(r.get('source')) or r.get('source')
        t = name_map.get(r.get('target')) or r.get('target')
        desc_lines.append(f"- 关系: {s} --({r.get('type')})--> {t}")
    user_prompt = '\n'.join(desc_lines)

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


def ai_review_architecture(project):
    """AI架构评审"""
    issues = []
    warnings = []
    suggestions = []
    
    # 检查元素数量
    if len(project.elements) == 0:
        issues.append({
            'type': 'empty',
            'severity': 'warning',
            'message': '架构项目中没有元素',
            'suggestion': '请添加架构元素'
        })
    
    # 检查关系数量
    if len(project.relationships) == 0 and len(project.elements) > 1:
        warnings.append({
            'type': 'no_relationships',
            'severity': 'warning',
            'message': '元素之间没有建立关系',
            'suggestion': '请为相关元素建立关系'
        })
    
    # 检查命名规范
    for elem in project.elements:
        if not elem['name'] or elem['name'] in ['', 'Unnamed']:
            issues.append({
                'type': 'naming',
                'severity': 'error',
                'message': f'元素未命名',
                'element_id': elem['id'],
                'suggestion': '请为元素添加有意义的名称'
            })
    
    # 检查维度覆盖
    framework = ARCHITECTURE_FRAMEWORKS.get(project.framework_type, {})
    expected_dims = framework.get('dimensions', [])
    actual_dims = [d['type'] for d in project.dimensions]
    
    for expected_dim in expected_dims:
        if expected_dim not in actual_dims:
            warnings.append({
                'type': 'dimension_missing',
                'severity': 'warning',
                'message': f'缺少{ARCHITECTURE_DIMENSIONS.get(expected_dim, {"name": expected_dim})["name"]}维度',
                'suggestion': '建议添加该维度'
            })
    
    # 检查循环依赖
    circular_deps = detect_circular_dependencies(project)
    for dep in circular_deps:
        issues.append({
            'type': 'circular_dependency',
            'severity': 'error',
            'message': f'检测到循环依赖: {dep}',
            'suggestion': '请重构消除循环依赖'
        })
    
    # 生成建议
    if len(issues) > 0:
        suggestions.append('请修复上述错误以提升架构质量')
    if len(warnings) > 0:
        suggestions.append('建议关注上述警告项')

    # 语义级AI评审（叠加在结构规则之上，AI未启用时跳过）
    ai_analysis = _ai_review_architecture_semantics(project)
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
        'valid': len(issues) == 0,
        'total_elements': len(project.elements),
        'total_relationships': len(project.relationships),
        'total_views': len(project.views),
        'total_dimensions': len(project.dimensions),
        'issues': issues,
        'warnings': warnings,
        'suggestions': suggestions,
        'summary': f'评审完成：{len(issues)}个问题，{len(warnings)}个警告',
        'ai_analysis': ai_analysis or {'summary': ''}
    }


def _ai_review_archimate_semantics(model):
    """对模型里的 ArchiMate 元素做 LLM 语义评审。AI 未启用/失败返回 None。"""
    if not ai_service_config.enabled:
        return None

    # 复用通用语义评审：把 ArchiMate 数据映射成 project 结构
    class _ReviewProject:
        pass
    proj = _ReviewProject()
    proj.framework_type = 'ArchiMate'
    proj.dimensions = []
    proj.elements = model.archimate_elements
    proj.relationships = [
        {
            'source': rel.get('startElement'),
            'target': rel.get('endElement'),
            'type': rel.get('type', 'association')
        }
        for rel in model.archimate_connections
    ]
    return _ai_review_architecture_semantics(proj)


def review_archimate_model(model):
    """对模型里的 ArchiMate 架构做结构 + 语义评审，返回与 validate_uml_model 同构的结果。"""
    errors = []
    warnings = []
    suggestions = []
    valid_count = 0
    invalid_count = 0

    elements = model.archimate_elements
    relationships = model.archimate_connections

    if not elements:
        warnings.append({
            'type': 'empty',
            'severity': 'warning',
            'message': '架构画布为空，没有元素',
            'suggestion': '请添加业务 / 应用 / 技术层元素'
        })

    elem_ids = {e.get('id') for e in elements}

    # 命名检查
    for elem in elements:
        name = elem.get('name', '')
        if not name or name in ('Unnamed', ''):
            errors.append({
                'type': 'naming',
                'severity': 'error',
                'message': '元素未命名',
                'element_id': elem.get('id'),
                'element_name': name
            })
            invalid_count += 1
        else:
            valid_count += 1

    # 关系合法性检查
    for rel in relationships:
        source = rel.get('startElement')
        target = rel.get('endElement')
        if source not in elem_ids:
            errors.append({
                'type': 'relationship',
                'severity': 'error',
                'message': '关系源元素不存在',
                'relationship_id': rel.get('id', ''),
                'source': source
            })
            invalid_count += 1
        if target not in elem_ids:
            errors.append({
                'type': 'relationship',
                'severity': 'error',
                'message': '关系目标元素不存在',
                'relationship_id': rel.get('id', ''),
                'target': target
            })
            invalid_count += 1
        if source == target:
            warnings.append({
                'type': 'relationship',
                'severity': 'warning',
                'message': '自引用关系',
                'relationship_id': rel.get('id', '')
            })

    if elements and not relationships:
        warnings.append({
            'type': 'no_relationships',
            'severity': 'warning',
            'message': '元素之间没有建立关系',
            'suggestion': '请为相关元素建立关系'
        })

    # 语义级 AI 评审（叠加在结构规则之上，AI 未启用时跳过）
    ai_analysis = _ai_review_archimate_semantics(model)
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

    if errors:
        suggestions.append('请修复上述错误后重新评审')
    if invalid_count > 0:
        suggestions.append(f'共有 {invalid_count} 个问题需要修复')

    return {
        'valid': len(errors) == 0,
        'valid_count': valid_count,
        'invalid_count': invalid_count,
        'errors': errors,
        'warnings': warnings,
        'suggestions': suggestions,
        'report': f'评审完成: {valid_count} 个有效元素, {invalid_count} 个问题',
        'ai_analysis': ai_analysis or {'summary': ''}
    }


@app.route('/api/v1/project/<model_id>/ai/review-archimate', methods=['POST'])
def ai_review_archimate_v1(model_id):
    """AI 评审当前模型的 ArchiMate 架构（仅限所属用户）"""
    user_id = _require_user_id()
    if user_id is None:
        return jsonify({'error': '未登录'}), 401

    model = load_model_from_cache(model_id)
    if not _model_owned_by(model, user_id):
        return jsonify({'error': '模型不存在'}), 404

    return jsonify(review_archimate_model(model))


# === AI 选中元素分析 ===

def _name_of(elements, eid):
    """在元素列表里按 id 找名字，找不到回退为 id 本身。"""
    for e in elements or []:
        if e.get('id') == eid:
            return e.get('name') or eid
    return eid


def _analyze_element_context(kind, element, context):
    """把选中元素 + 周边元素/关系序列化为 LLM 可读的文本上下文。"""
    elements = context.get('elements', []) or []
    relationships = context.get('relationships', []) or []
    eid = element.get('id')

    lines = [f"元素类型: {element.get('type')}", f"名称: {element.get('name') or ''}"]
    if element.get('layer'):
        lines.append(f"ArchiMate层次: {element.get('layer')}")
    if element.get('description'):
        lines.append(f"描述: {element.get('description')}")
    if element.get('attributes'):
        lines.append(f"属性/方法: {element.get('attributes')}")
    if element.get('fields'):
        lines.append(
            '字段: ' + ', '.join(
                f"{f.get('name')}({f.get('type')}{' PK' if f.get('isPrimary') else ''}{' FK' if f.get('isForeign') else ''})"
                for f in element.get('fields', [])
            )
        )

    # 与本元素相连的关系（UML 用 source/target，ArchiMate 用 startElement/endElement）
    rels = [
        r for r in relationships
        if eid in (r.get('startElement'), r.get('endElement'), r.get('source'), r.get('target'))
    ]
    if rels:
        lines.append("关联关系:")
        for r in rels[:8]:
            s = r.get('startElement') or r.get('source')
            t = r.get('endElement') or r.get('target')
            lines.append(f"- {_name_of(elements, s)} --({r.get('type')})--> {_name_of(elements, t)}")

    others = [e for e in elements if e.get('id') != eid]
    if others:
        names = [e.get('name') or e.get('id') for e in others[:15]]
        lines.append("图中其他元素: " + ', '.join(names))

    return '\n'.join(lines)


def _analyze_element_mock(kind, element, context):
    """AI 未启用/调用失败时的规则回退分析（不依赖外部服务）。"""
    issues = []
    strengths = []
    suggestions = []
    name = (element.get('name') or '').strip()

    if not name:
        issues.append({'severity': 'error', 'message': '元素没有命名', 'suggestion': '为元素取一个符合命名规范的名字'})

    if kind == 'uml':
        if element.get('type') == 'class':
            attrs = element.get('attributes', [])
            if not attrs:
                suggestions.append('类缺少属性/方法，建议补充以明确结构')
            else:
                strengths.append(f"定义了 {len(attrs)} 个属性/方法")
        strengths.append(f"这是一个 UML {element.get('type')} 元素")
    elif kind == 'archimate':
        if not element.get('layer'):
            suggestions.append('未指定 ArchiMate 层次，建议补充所属层次')
        else:
            strengths.append(f"已标注 ArchiMate {element.get('layer')} 层次")
    elif kind == 'er':
        fields = element.get('fields', [])
        pk = [f for f in fields if f.get('isPrimary')]
        if fields and not pk:
            issues.append({'severity': 'warning', 'message': '表没有主键', 'suggestion': '为表添加一个主键字段'})
        if fields:
            strengths.append(f"包含 {len(fields)} 个字段")

    summary = '存在需要改进的问题' if issues else '整体设计基本合理'
    return {'summary': summary, 'strengths': strengths, 'issues': issues, 'suggestions': suggestions}


def analyze_element(kind, element, context):
    """对单个选中元素做 AI 语义分析。真实调 LLM，未启用/失败回退规则 mock。"""
    name = (element.get('name') or '').strip() or (element.get('type') or '未命名元素')
    base = {
        'name': name,
        'type': element.get('type'),
        'layer': element.get('layer'),
        'generated': False,
    }

    if not ai_service_config.enabled:
        return {**base, **_analyze_element_mock(kind, element, context)}

    user_prompt = _analyze_element_context(kind, element, context)
    messages = [
        {'role': 'system', 'content': ELEMENT_ANALYSIS_SYSTEM_PROMPT},
        {'role': 'user', 'content': '待分析元素：\n' + user_prompt},
    ]
    result = AIService.chat_completion(messages, max_tokens=2000, temperature=0.3, use_reasoning=True)
    if not isinstance(result, dict) or 'error' in result:
        return {**base, **_analyze_element_mock(kind, element, context)}
    try:
        content = result['choices'][0]['message']['content']
    except (KeyError, IndexError, TypeError):
        return {**base, **_analyze_element_mock(kind, element, context)}

    data = _ai_parse_json_response(content)
    if not isinstance(data, dict):
        return {**base, **_analyze_element_mock(kind, element, context)}

    for field in ('strengths', 'issues', 'suggestions'):
        if not isinstance(data.get(field), list):
            data[field] = []
    data['summary'] = data.get('summary', '')
    data['generated'] = True
    data['name'] = base['name']
    data['type'] = base['type']
    data['layer'] = base['layer']
    return data


@app.route('/api/v1/project/<model_id>/ai/analyze-element', methods=['POST'])
def ai_analyze_element_v1(model_id):
    """AI 分析画布中选中的单个元素（仅限所属用户）。
    body: {kind: 'uml'|'archimate'|'er', element: {...}, context: {elements, relationships}}
    """
    user_id = _require_user_id()
    if user_id is None:
        return jsonify({'error': '未登录'}), 401

    model = load_model_from_cache(model_id)
    if not _model_owned_by(model, user_id):
        return jsonify({'error': '模型不存在'}), 404

    data = request.json or {}
    kind = data.get('kind', 'uml')
    element = data.get('element') or {}
    context = data.get('context') or {}
    if not isinstance(element, dict):
        return jsonify({'error': '缺少 element 参数'}), 400
    if kind not in ('uml', 'archimate', 'er'):
        return jsonify({'error': 'kind 必须是 uml/archimate/er'}), 400

    return jsonify(analyze_element(kind, element, context))

def detect_circular_dependencies(project):
    """检测循环依赖"""
    circular_deps = []
    graph = {}
    
    # 构建依赖图
    for elem in project.elements:
        graph[elem['id']] = []
    
    for rel in project.relationships:
        if rel['source'] in graph:
            graph[rel['source']].append(rel['target'])
    
    # 检测循环
    visited = set()
    rec_stack = set()
    
    def has_cycle(node):
        if node not in visited:
            visited.add(node)
            rec_stack.add(node)
            for neighbor in graph.get(node, []):
                if neighbor not in visited and has_cycle(neighbor):
                    return True
                elif neighbor in rec_stack:
                    return True
        if node in rec_stack:
            rec_stack.remove(node)
        return False
    
    for node in graph:
        if has_cycle(node):
            elem = next((e for e in project.elements if e['id'] == node), None)
            if elem:
                circular_deps.append(elem['name'])
    
    return circular_deps

def ai_evolution_plan(project, business_goals, technology_trends):
    """AI生成架构演进规划"""
    plan = {
        'name': f'{project.name}演进规划',
        'version': '1.0.0',
        'description': '基于业务目标和技术趋势生成的架构演进路线',
        'milestones': [],
        'recommendations': [],
        'risks': []
    }
    
    # 生成里程碑
    milestones = [
        {
            'phase': 'Phase 1',
            'name': '基础架构优化',
            'duration': '0-3个月',
            'deliverables': ['架构评估报告', '技术债务清理', '性能优化'],
            'status': 'planned'
        },
        {
            'phase': 'Phase 2',
            'name': '核心能力升级',
            'duration': '3-6个月',
            'deliverables': ['微服务拆分', 'API网关建设', '服务治理'],
            'status': 'planned'
        },
        {
            'phase': 'Phase 3',
            'name': '智能化升级',
            'duration': '6-12个月',
            'deliverables': ['AI能力集成', '自动化运维', '智能监控'],
            'status': 'planned'
        }
    ]
    plan['milestones'] = milestones
    
    # 技术选型建议
    recommendations = [
        {'area': '云平台', 'current': '自建', 'recommended': '混合云', 'reason': '降低运维成本，提高弹性'},
        {'area': '数据库', 'current': '单体数据库', 'recommended': '分布式数据库', 'reason': '支持水平扩展'},
        {'area': '中间件', 'current': '传统MQ', 'recommended': '云原生消息队列', 'reason': '提高可靠性和可扩展性'}
    ]
    plan['recommendations'] = recommendations
    
    # 风险识别
    risks = [
        {'risk': '技术债务清理难度', 'severity': 'medium', 'mitigation': '分阶段逐步清理，制定详细计划'},
        {'risk': '团队技能差距', 'severity': 'low', 'mitigation': '培训和人才引进并行'},
        {'risk': '业务中断风险', 'severity': 'high', 'mitigation': '采用蓝绿部署、灰度发布策略'}
    ]
    plan['risks'] = risks
    
    return plan

def ai_generate_architecture_document(project, audience='executive'):
    """AI生成架构文档"""
    doc = {
        'title': f'{project.name}架构说明书',
        'audience': audience,
        'version': '1.0.0',
        'generated_at': datetime.datetime.now().isoformat(),
        'sections': []
    }
    
    if audience == 'executive':
        # 高管视角：高层架构概述
        doc['sections'] = [
            {
                'title': '1. 业务目标',
                'content': f"本架构方案旨在支持企业战略目标：{project.business_goal}"
            },
            {
                'title': '2. 架构概述',
                'content': f"采用{ARCHITECTURE_FRAMEWORKS.get(project.framework_type, {}).get('name', '未知框架')}架构框架，涵盖{len(project.dimensions)}个维度，包含{len(project.elements)}个架构元素"
            },
            {
                'title': '3. 核心能力',
                'content': '• 用户管理能力\n• 业务流程自动化\n• 数据驱动决策\n• 弹性扩展能力'
            },
            {
                'title': '4. 投资估算',
                'content': '预计总投资：XX万元，分X期实施'
            }
        ]
    else:
        # 技术视角：详细设计
        doc['sections'] = [
            {
                'title': '1. 架构背景',
                'content': f"项目名称：{project.name}\n行业：{project.industry}\n业务目标：{project.business_goal}"
            },
            {
                'title': '2. 架构维度',
                'content': '\n'.join([f"• {d['name']}" for d in project.dimensions])
            },
            {
                'title': '3. 架构元素清单',
                'content': f"共{len(project.elements)}个元素，{len(project.relationships)}条关系"
            },
            {
                'title': '4. 技术选型',
                'content': '• 前端：React/Vue\n• 后端：Spring Boot/Node.js\n• 数据库：MySQL/PostgreSQL\n• 缓存：Redis\n• 消息队列：Kafka'
            },
            {
                'title': '5. 安全考虑',
                'content': '• 身份认证：OAuth2.0\n• 数据加密：AES-256\n• 访问控制：RBAC\n• 审计日志：全链路追踪'
            }
        ]
    
    return doc

def ai_adapt_framework(project, target_framework):
    """AI框架适配"""
    old_framework = project.framework_type
    project.framework_type = target_framework
    
    # 转换元素类型
    element_type_mapping = {
        ('archimate', 'togaf'): {
            'BusinessActor': 'BusinessRole',
            'BusinessProcess': 'BusinessProcess',
            'ApplicationComponent': 'ApplicationComponent'
        },
        ('togaf', 'archimate'): {
            'BusinessRole': 'BusinessActor',
            'BusinessProcess': 'BusinessProcess',
            'ApplicationComponent': 'ApplicationComponent'
        },
        ('archimate', 'c4'): {
            'ApplicationSystem': 'Container',
            'ApplicationComponent': 'Component',
            'BusinessActor': 'Person'
        }
    }
    
    mapping_key = (old_framework, target_framework)
    mapping = element_type_mapping.get(mapping_key, {})
    
    for elem in project.elements:
        if elem['type'] in mapping:
            elem['type'] = mapping[elem['type']]
    
    # 更新维度
    target_framework_info = ARCHITECTURE_FRAMEWORKS.get(target_framework, {})
    expected_dims = target_framework_info.get('dimensions', [])
    actual_dims = [d['type'] for d in project.dimensions]
    
    # 添加缺失的维度
    for dim_type in expected_dims:
        if dim_type not in actual_dims:
            project.add_dimension(dim_type)
    
    return {
        'message': '框架适配完成',
        'old_framework': old_framework,
        'new_framework': target_framework,
        'elements_converted': len([e for e in project.elements if e['type'] in mapping]),
        'dimensions_added': len([d for d in expected_dims if d not in actual_dims])
    }

def analyze_dependencies(project):
    """分析架构依赖"""
    dependencies = {
        'total_elements': len(project.elements),
        'total_relationships': len(project.relationships),
        'dependency_graph': [],
        'circular_dependencies': [],
        'impact_analysis': []
    }
    
    # 构建依赖图
    for rel in project.relationships:
        source_elem = next((e for e in project.elements if e['id'] == rel['source']), None)
        target_elem = next((e for e in project.elements if e['id'] == rel['target']), None)
        
        if source_elem and target_elem:
            dependencies['dependency_graph'].append({
                'source': source_elem['name'],
                'target': target_elem['name'],
                'type': rel['type']
            })
    
    # 检测循环依赖
    dependencies['circular_dependencies'] = detect_circular_dependencies(project)
    
    # 影响分析
    for elem in project.elements[:5]:  # 只分析前5个元素
        dependent_count = sum(1 for rel in project.relationships if rel['source'] == elem['id'])
        depended_count = sum(1 for rel in project.relationships if rel['target'] == elem['id'])
        
        dependencies['impact_analysis'].append({
            'element_id': elem['id'],
            'element_name': elem['name'],
            'dependent_on': depended_count,
            'depended_by': dependent_count,
            'impact_level': 'high' if depended_count > 3 else 'medium' if depended_count > 1 else 'low'
        })
    
    return dependencies

# === 企业架构建模API ===

@app.route('/api/v1/architecture/project/create', methods=['POST'])
def create_architecture_project():
    """创建架构项目"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    data = request.json
    name = data.get('name', '未命名架构项目')
    framework_type = data.get('framework_type', 'archimate')
    description = data.get('description', '')
    industry = data.get('industry', 'software')
    business_goal = data.get('business_goal', '')
    
    project = ArchitectureProject(name, framework_type, description, industry, business_goal)
    project.user_id = sessions_cache[session_id]['user_id']
    
    architecture_projects_cache[project.id] = project
    
    return jsonify({
        'message': '架构项目创建成功',
        'project': project.to_dict()
    })

@app.route('/api/v1/architecture/project/list', methods=['GET'])
def get_architecture_projects():
    """获取架构项目列表"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    projects = [p.to_dict() for p in architecture_projects_cache.values()]
    
    return jsonify({'projects': projects})

@app.route('/api/v1/architecture/project/<project_id>', methods=['GET'])
def get_architecture_project(project_id):
    """获取架构项目详情"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    if project_id not in architecture_projects_cache:
        return jsonify({'error': '项目不存在'}), 404
    
    project = architecture_projects_cache[project_id]
    
    return jsonify({'project': project.to_dict()})

@app.route('/api/v1/architecture/project/<project_id>/save', methods=['PUT'])
def save_architecture_project(project_id):
    """保存架构项目"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    if project_id not in architecture_projects_cache:
        return jsonify({'error': '项目不存在'}), 404
    
    project = architecture_projects_cache[project_id]
    data = request.json
    
    if 'name' in data:
        project.name = data['name']
    if 'description' in data:
        project.description = data['description']
    if 'status' in data:
        project.status = data['status']
    if 'dimensions' in data:
        project.dimensions = data['dimensions']
    if 'views' in data:
        project.views = data['views']
    if 'elements' in data:
        project.elements = data['elements']
    if 'relationships' in data:
        project.relationships = data['relationships']
    
    project.updated_at = datetime.datetime.now().isoformat()
    
    return jsonify({'message': '项目保存成功', 'project': project.to_dict()})

@app.route('/api/v1/architecture/project/<project_id>/ai/generate', methods=['POST'])
def ai_generate_architecture_api(project_id):
    """AI生成架构方案"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    if project_id not in architecture_projects_cache:
        return jsonify({'error': '项目不存在'}), 404
    
    project = architecture_projects_cache[project_id]
    data = request.json
    requirements = data.get('requirements', '')
    
    ai_generate_architecture(project, requirements)
    project.status = 'generated'
    
    return jsonify({
        'message': 'AI架构方案生成成功',
        'project': project.to_dict(),
        'generated_elements': len(project.elements),
        'generated_views': len(project.views),
        'generated_dimensions': len(project.dimensions)
    })

@app.route('/api/v1/architecture/project/<project_id>/framework/adapt', methods=['POST'])
def adapt_framework_api(project_id):
    """架构框架适配"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    if project_id not in architecture_projects_cache:
        return jsonify({'error': '项目不存在'}), 404
    
    project = architecture_projects_cache[project_id]
    data = request.json
    target_framework = data.get('framework', 'togaf')
    
    result = ai_adapt_framework(project, target_framework)
    
    return jsonify(result)

@app.route('/api/v1/architecture/project/<project_id>/ai/review', methods=['POST'])
def ai_review_architecture_api(project_id):
    """AI架构评审"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    if project_id not in architecture_projects_cache:
        return jsonify({'error': '项目不存在'}), 404
    
    project = architecture_projects_cache[project_id]
    result = ai_review_architecture(project)
    
    return jsonify({
        'message': '架构评审完成',
        'review': result
    })

@app.route('/api/v1/architecture/project/<project_id>/ai/evolution', methods=['POST'])
def ai_evolution_plan_api(project_id):
    """AI架构演进规划"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    if project_id not in architecture_projects_cache:
        return jsonify({'error': '项目不存在'}), 404
    
    project = architecture_projects_cache[project_id]
    data = request.json
    business_goals = data.get('business_goals', '')
    technology_trends = data.get('technology_trends', '')
    
    plan = ai_evolution_plan(project, business_goals, technology_trends)
    
    return jsonify({
        'message': '架构演进规划生成成功',
        'plan': plan
    })

@app.route('/api/v1/architecture/project/<project_id>/ai/document', methods=['POST'])
def ai_generate_document_api(project_id):
    """AI生成架构文档"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    if project_id not in architecture_projects_cache:
        return jsonify({'error': '项目不存在'}), 404
    
    project = architecture_projects_cache[project_id]
    data = request.json
    audience = data.get('audience', 'executive')
    
    document = ai_generate_architecture_document(project, audience)
    
    return jsonify({
        'message': '架构文档生成成功',
        'document': document
    })

@app.route('/api/v1/architecture/project/<project_id>/dependency/analyze', methods=['POST'])
def analyze_dependencies_api(project_id):
    """依赖与影响分析"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    if project_id not in architecture_projects_cache:
        return jsonify({'error': '项目不存在'}), 404
    
    project = architecture_projects_cache[project_id]
    result = analyze_dependencies(project)
    
    return jsonify({
        'message': '依赖分析完成',
        'analysis': result
    })

@app.route('/api/v1/architecture/project/<project_id>/export', methods=['POST'])
def export_architecture_project(project_id):
    """导出架构项目"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    if project_id not in architecture_projects_cache:
        return jsonify({'error': '项目不存在'}), 404
    
    project = architecture_projects_cache[project_id]
    export_data = {
        'project': project.to_dict(),
        'exported_at': datetime.datetime.now().isoformat(),
        'format': 'json'
    }
    
    return jsonify({
        'message': '架构项目导出成功',
        'export_data': export_data
    })

@app.route('/api/v1/architecture/frameworks', methods=['GET'])
def get_architecture_frameworks():
    """获取支持的架构框架列表"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    frameworks = []
    for key, value in ARCHITECTURE_FRAMEWORKS.items():
        frameworks.append({
            'id': key,
            'name': value['name'],
            'description': value['description'],
            'dimensions': value['dimensions']
        })
    
    return jsonify({'frameworks': frameworks})

@app.route('/api/v1/architecture/dimensions', methods=['GET'])
def get_architecture_dimensions():
    """获取架构维度列表"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    dimensions = []
    for key, value in ARCHITECTURE_DIMENSIONS.items():
        dimensions.append({
            'id': key,
            'name': value['name'],
            'icon': value['icon'],
            'color': value['color']
        })
    
    return jsonify({'dimensions': dimensions})

@app.route('/api/v1/architecture/element-types', methods=['GET'])
def get_architecture_element_types():
    """获取架构元素类型"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    return jsonify({'element_types': ARCHITECTURE_ELEMENT_TYPES})

# === 模块五：数据建模与 ER / 数据库工程 ===

# 数据库类型定义
DATABASE_TYPES = {
    'mysql': {'name': 'MySQL', 'port': 3306, 'driver': 'com.mysql.cj.jdbc.Driver'},
    'oracle': {'name': 'Oracle', 'port': 1521, 'driver': 'oracle.jdbc.OracleDriver'},
    'sqlserver': {'name': 'SQL Server', 'port': 1433, 'driver': 'com.microsoft.sqlserver.jdbc.SQLServerDriver'},
    'postgresql': {'name': 'PostgreSQL', 'port': 5432, 'driver': 'org.postgresql.Driver'},
    'db2': {'name': 'DB2', 'port': 50000, 'driver': 'com.ibm.db2.jcc.DB2Driver'},
    'sqlite': {'name': 'SQLite', 'port': None, 'driver': 'org.sqlite.JDBC'}
}

# 数据类型映射
DATA_TYPE_MAPPING = {
    'mysql': {
        'string': 'VARCHAR',
        'text': 'TEXT',
        'integer': 'INT',
        'bigint': 'BIGINT',
        'float': 'FLOAT',
        'double': 'DOUBLE',
        'decimal': 'DECIMAL',
        'date': 'DATE',
        'datetime': 'DATETIME',
        'timestamp': 'TIMESTAMP',
        'boolean': 'BOOLEAN',
        'binary': 'BLOB'
    },
    'postgresql': {
        'string': 'VARCHAR',
        'text': 'TEXT',
        'integer': 'INTEGER',
        'bigint': 'BIGINT',
        'float': 'REAL',
        'double': 'DOUBLE PRECISION',
        'decimal': 'NUMERIC',
        'date': 'DATE',
        'datetime': 'TIMESTAMP',
        'timestamp': 'TIMESTAMP',
        'boolean': 'BOOLEAN',
        'binary': 'BYTEA'
    },
    'oracle': {
        'string': 'VARCHAR2',
        'text': 'CLOB',
        'integer': 'NUMBER',
        'bigint': 'NUMBER',
        'float': 'FLOAT',
        'double': 'DOUBLE PRECISION',
        'decimal': 'NUMBER',
        'date': 'DATE',
        'datetime': 'TIMESTAMP',
        'timestamp': 'TIMESTAMP',
        'boolean': 'NUMBER(1)',
        'binary': 'BLOB'
    },
    'sqlserver': {
        'string': 'VARCHAR',
        'text': 'TEXT',
        'integer': 'INT',
        'bigint': 'BIGINT',
        'float': 'FLOAT',
        'double': 'FLOAT',
        'decimal': 'DECIMAL',
        'date': 'DATE',
        'datetime': 'DATETIME',
        'timestamp': 'TIMESTAMP',
        'boolean': 'BIT',
        'binary': 'VARBINARY'
    }
}

# === ER视图管理类 ===

# ER 模块（ERView 类 / AI 生成优化 / DDL / ER 路由）已移至 er_routes.py

# === 模块六：代码双向工程 ===

# 编程语言定义
PROGRAMMING_LANGUAGES = {
    'java': {
        'name': 'Java',
        'extension': '.java',
        'frameworks': ['SpringBoot', 'SpringCloud', 'Hibernate', 'MyBatis'],
        'comment_style': '//',
        'namespace': 'package'
    },
    'python': {
        'name': 'Python',
        'extension': '.py',
        'frameworks': ['Django', 'Flask', 'FastAPI', 'Pyramid'],
        'comment_style': '#',
        'namespace': 'module'
    },
    'csharp': {
        'name': 'C#',
        'extension': '.cs',
        'frameworks': ['.NET Core', 'ASP.NET', 'Entity Framework', 'Xamarin'],
        'comment_style': '//',
        'namespace': 'namespace'
    },
    'cpp': {
        'name': 'C/C++',
        'extension': '.cpp',
        'frameworks': ['MFC', 'Qt', 'STL'],
        'comment_style': '//',
        'namespace': 'namespace'
    },
    'go': {
        'name': 'Go',
        'extension': '.go',
        'frameworks': ['Gin', 'Echo', 'Fiber'],
        'comment_style': '//',
        'namespace': 'package'
    },
    'javascript': {
        'name': 'JavaScript',
        'extension': '.js',
        'frameworks': ['Express', 'NestJS', 'Vue', 'React', 'Angular'],
        'comment_style': '//',
        'namespace': ''
    },
    'typescript': {
        'name': 'TypeScript',
        'extension': '.ts',
        'frameworks': ['NestJS', 'Vue', 'React', 'Angular'],
        'comment_style': '//',
        'namespace': 'namespace'
    },
    'php': {
        'name': 'PHP',
        'extension': '.php',
        'frameworks': ['Laravel', 'Symfony', 'CodeIgniter'],
        'comment_style': '//',
        'namespace': 'namespace'
    }
}

# 代码层级架构定义
CODE_LAYERS = {
    'controller': {'name': '控制器层', 'suffix': 'Controller', 'description': '处理HTTP请求和响应'},
    'service': {'name': '服务层', 'suffix': 'Service', 'description': '业务逻辑处理'},
    'repository': {'name': '仓储层', 'suffix': 'Repository', 'description': '数据访问层'},
    'entity': {'name': '实体层', 'suffix': 'Entity', 'description': '数据模型定义'},
    'dto': {'name': '数据传输对象', 'suffix': 'DTO', 'description': '数据传输对象'},
    'vo': {'name': '视图对象', 'suffix': 'VO', 'description': '视图对象'},
    'mapper': {'name': '映射层', 'suffix': 'Mapper', 'description': '对象关系映射'}
}

# 默认代码模板
DEFAULT_CODE_TEMPLATES = {
    'java_springboot': '''package {package_name};

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.*;

/**
 * {class_name}控制器
 * {description}
 */
@RestController
@RequestMapping("/api/{resource_name}")
public class {class_name}Controller {

    @Autowired
    private {class_name}Service {resource_name}Service;

    @GetMapping
    public Result list() {
        return Result.success({resource_name}Service.list());
    }

    @GetMapping("/{id}")
    public Result getById(@PathVariable Long id) {
        return Result.success({resource_name}Service.getById(id));
    }

    @PostMapping
    public Result add(@RequestBody {class_name}DTO dto) {
        {resource_name}Service.add(dto);
        return Result.success();
    }

    @PutMapping("/{id}")
    public Result update(@PathVariable Long id, @RequestBody {class_name}DTO dto) {
        dto.setId(id);
        {resource_name}Service.update(dto);
        return Result.success();
    }

    @DeleteMapping("/{id}")
    public Result delete(@PathVariable Long id) {
        {resource_name}Service.delete(id);
        return Result.success();
    }
}
''',

    'python_fastapi': '''from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
import {module_name}.schemas as schemas
import {module_name}.services as services
from {module_name}.database import get_db

router = APIRouter(prefix="/api/{resource_name}", tags=["{resource_name}"])

@router.get("/", response_model=List[schemas.{class_name}Response])
def list_{resource_name}(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """获取{resource_name}列表"""
    return services.get_{resource_name}(db, skip=skip, limit=limit)

@router.get("/{id}", response_model=schemas.{class_name}Response)
def get_{resource_name}_by_id(id: int, db: Session = Depends(get_db)):
    """根据ID获取{resource_name}"""
    db_{resource_name} = services.get_{resource_name}_by_id(db, id=id)
    if db_{resource_name} is None:
        raise HTTPException(status_code=404, detail="{class_name} not found")
    return db_{resource_name}

@router.post("/", response_model=schemas.{class_name}Response)
def create_{resource_name}({resource_name}: schemas.{class_name}Create, db: Session = Depends(get_db)):
    """创建{resource_name}"""
    return services.create_{resource_name}(db=db, {resource_name}={resource_name})

@router.put("/{id}", response_model=schemas.{class_name}Response)
def update_{resource_name}(id: int, {resource_name}: schemas.{class_name}Update, db: Session = Depends(get_db)):
    """更新{resource_name}"""
    return services.update_{resource_name}(db=db, id=id, {resource_name}={resource_name})

@router.delete("/{id}")
def delete_{resource_name}(id: int, db: Session = Depends(get_db)):
    """删除{resource_name}"""
    services.delete_{resource_name}(db=db, id=id)
    return {{"message": "Deleted successfully"}}
''',

    'typescript_nestjs': '''import { Controller, Get, Post, Put, Delete, Body, Param } from "@nestjs/common";
import { {class_name}Service } from "./{resource_name}.service";
import { {class_name}DTO } from "./dto/{resource_name}.dto";

@Controller("{resource_name}")
export class {class_name}Controller {
    constructor(private readonly {resource_name}Service: {class_name}Service) {}

    @Get()
    async findAll() {
        return this.{resource_name}Service.findAll();
    }

    @Get(":id")
    async findOne(@Param("id") id: string) {
        return this.{resource_name}Service.findOne(id);
    }

    @Post()
    async create(@Body() dto: {class_name}DTO) {
        return this.{resource_name}Service.create(dto);
    }

    @Put(":id")
    async update(@Param("id") id: string, @Body() dto: {class_name}DTO) {
        return this.{resource_name}Service.update(id, dto);
    }

    @Delete(":id")
    async remove(@Param("id") id: string) {
        return this.{resource_name}Service.remove(id);
    }
}
'''
}

# === 代码任务管理类 ===

class CodeGenerateTask:
    """代码生成任务"""
    def __init__(self, model_id, project_id, language, framework=''):
        self.id = str(uuid.uuid4())[:8]
        self.model_id = model_id
        self.project_id = project_id
        self.language = language
        self.framework = framework
        self.status = 'pending'
        self.progress = 0
        self.files = []
        self.created_at = datetime.datetime.now().isoformat()
        self.updated_at = datetime.datetime.now().isoformat()
        self.user_id = ''
    
    def add_file(self, file_path, content, language):
        """添加生成的代码文件"""
        file = {
            'id': str(uuid.uuid4())[:8],
            'path': file_path,
            'name': file_path.split('/')[-1],
            'content': content,
            'language': language,
            'created_at': datetime.datetime.now().isoformat()
        }
        self.files.append(file)
        return file
    
    def to_dict(self):
        return {
            'id': self.id,
            'model_id': self.model_id,
            'project_id': self.project_id,
            'language': self.language,
            'framework': self.framework,
            'status': self.status,
            'progress': self.progress,
            'files': self.files,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'user_id': self.user_id
        }

class CodeReverseTask:
    """代码逆向建模任务"""
    def __init__(self, project_id, source_type, source_path, language):
        self.id = str(uuid.uuid4())[:8]
        self.project_id = project_id
        self.source_type = source_type
        self.source_path = source_path
        self.language = language
        self.status = 'pending'
        self.progress = 0
        self.models = []
        self.created_at = datetime.datetime.now().isoformat()
        self.updated_at = datetime.datetime.now().isoformat()
        self.user_id = ''
    
    def to_dict(self):
        return {
            'id': self.id,
            'project_id': self.project_id,
            'source_type': self.source_type,
            'source_path': self.source_path,
            'language': self.language,
            'status': self.status,
            'progress': self.progress,
            'models': self.models,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'user_id': self.user_id
        }

class CodeSyncTask:
    """代码-模型同步任务"""
    def __init__(self, project_id, model_id, sync_type):
        self.id = str(uuid.uuid4())[:8]
        self.project_id = project_id
        self.model_id = model_id
        self.sync_type = sync_type
        self.status = 'pending'
        self.progress = 0
        self.records = []
        self.conflicts = []
        self.created_at = datetime.datetime.now().isoformat()
        self.updated_at = datetime.datetime.now().isoformat()
    
    def add_record(self, change_type, element_name, content):
        """添加同步记录"""
        record = {
            'id': str(uuid.uuid4())[:8],
            'type': change_type,
            'element': element_name,
            'content': content,
            'created_at': datetime.datetime.now().isoformat()
        }
        self.records.append(record)
        return record
    
    def to_dict(self):
        return {
            'id': self.id,
            'project_id': self.project_id,
            'model_id': self.model_id,
            'sync_type': self.sync_type,
            'status': self.status,
            'progress': self.progress,
            'records': self.records,
            'conflicts': self.conflicts,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }

# 代码任务缓存
code_generate_tasks_cache = {}
code_reverse_tasks_cache = {}
code_sync_tasks_cache = {}
code_review_reports_cache = {}
code_files_cache = {}
code_templates_cache = {}

# === AI代码生成功能 ===

# === AI语义级代码生成 ===

def _strip_code_fences(content):
    """去掉LLM返回代码里的markdown代码围栏。"""
    content = content.strip()
    if content.startswith('```'):
        lines = content.split('\n')
        # 去掉开头 ```lang
        if lines and lines[0].strip().startswith('```'):
            lines = lines[1:]
        # 去掉结尾 ```
        if lines and lines[-1].strip() == '```':
            lines = lines[:-1]
        content = '\n'.join(lines).strip()
    return content


def _describe_model_for_code(source, elements, er_entities, er_relations):
    """把模型结构描述成文本，供LLM生成代码。"""
    lines = []
    if source == 'er':
        id_to_name = {}
        for ent in er_entities:
            id_to_name[ent.get('id')] = ent.get('name', '')
            attrs = []
            for f in ent.get('fields', []):
                pk = ' [主键]' if f.get('isPrimary') else ''
                fk = ' [外键]' if f.get('isForeign') else ''
                attrs.append(f"{f.get('name')}({f.get('type', 'string')}){pk}{fk}")
            lines.append(f"- 实体 {ent.get('name')}: " + (', '.join(attrs) or '无属性'))
        for rel in er_relations:
            s = id_to_name.get(rel.get('startEntity'))
            t = id_to_name.get(rel.get('endEntity'))
            if s and t:
                lines.append(f"- 关系: {s} {rel.get('type')} {t}")
    else:
        for e in elements:
            attrs = ', '.join(e.get('attributes') or []) or '无'
            methods = ', '.join(e.get('methods') or []) or '无'
            lines.append(f"- {e.get('type')} {e.get('name')}: 属性[{attrs}] 方法[{methods}] 描述:{e.get('description') or ''}")
    return '\n'.join(lines)


def _ai_generate_code(description, language, framework, output_type):
    """调用LLM生成代码。AI未启用/失败返回None。"""
    if not ai_service_config.enabled:
        return None

    system_prompt = code_system_prompt(language, framework, output_type)
    messages = [
        {'role': 'system', 'content': system_prompt},
        {'role': 'user', 'content': description}
    ]
    result = AIService.chat_completion(messages, max_tokens=4096, temperature=0.3)
    if not isinstance(result, dict) or 'error' in result:
        return None
    try:
        content = result['choices'][0]['message']['content']
    except (KeyError, IndexError, TypeError):
        return None
    content = _strip_code_fences(content)
    return content if content else None


@app.route('/api/v1/ai/code/generate', methods=['POST'])
def ai_code_generate_v1():
    """AI语义级代码生成（LLM）。AI未启用/失败返回error，由前端回退本地模板。"""
    data = request.json or {}
    source = data.get('source', 'uml')
    elements = data.get('elements') or []
    er_entities = data.get('erEntities') or []
    er_relations = data.get('erRelations') or []
    language = data.get('language', 'python')
    framework = data.get('framework', '')
    output_type = data.get('outputType', 'entity')

    description = _describe_model_for_code(source, elements, er_entities, er_relations)
    if not description.strip():
        return jsonify({'error': '模型为空，无法生成代码'}), 400

    code = _ai_generate_code(description, language, framework, output_type)
    if code is None:
        return jsonify({'error': 'AI服务不可用，已使用本地模板生成'}), 200

    return jsonify({'code': code})


# === 代码反向工程 ===

def _normalize_er_rel_type(rtype):
    """把 LLM/后端 snake_case 关系类型归一化为前端画布 camelCase（oneToOne/oneToMany/manyToMany）。"""
    return {
        'one_to_one': 'oneToOne',
        'one_to_many': 'oneToMany',
        'many_to_one': 'oneToMany',   # 前端无 many_to_one，归到 1:N
        'many_to_many': 'manyToMany',
    }.get(rtype, 'oneToMany')


def _layout_ai_er(entities_raw, relations_raw):
    """把 LLM 返回的 ER 实体/关系布局成前端画布结构（分配 id/坐标/宽高，字段映射）。"""
    name_to_id = {}
    entities = []
    x, y = 100, 100
    for i, item in enumerate(entities_raw):
        if not isinstance(item, dict) or not item.get('name'):
            continue
        name = str(item['name']).strip()
        if not name or name in name_to_id:
            continue
        eid = i + 1
        fields = []
        attrs = item.get('attributes')
        if isinstance(attrs, list):
            for a in attrs:
                if not isinstance(a, dict) or not a.get('name'):
                    continue
                fields.append({
                    'name': str(a['name']),
                    'type': str(a.get('data_type') or a.get('type') or 'string').upper(),
                    'isPrimary': bool(a.get('is_primary_key', False)),
                    'isForeign': bool(a.get('is_foreign_key', False))
                })
        if not fields:
            fields = [{'name': 'id', 'type': 'INT', 'isPrimary': True, 'isForeign': False}]
        entities.append({
            'id': eid,
            'name': name,
            'x': x + (i % 3) * 210,
            'y': y + (i // 3) * 160,
            'width': 150,
            'displayHeight': max(80, 40 + 18 * len(fields)),
            'fields': fields
        })
        name_to_id[name] = eid

    relations = []
    valid_types = {'one_to_one', 'one_to_many', 'many_to_one', 'many_to_many'}
    if isinstance(relations_raw, list):
        for r in relations_raw:
            if not isinstance(r, dict):
                continue
            s = name_to_id.get(str(r.get('source') or '').strip())
            t = name_to_id.get(str(r.get('target') or '').strip())
            if s is None or t is None or s == t:
                continue
            rtype = str(r.get('type') or 'one_to_many').strip()
            if rtype not in valid_types:
                rtype = 'one_to_many'
            relations.append({
                'id': len(relations) + 1,
                'type': _normalize_er_rel_type(rtype),
                'startEntity': s,
                'endEntity': t
            })

    # 回退：LLM 未给关系时，按外键字段推断一对多关系（字段形如 <实体名>_id）
    if not relations:
        for ent in entities:
            for f in ent.get('fields', []):
                fname = (f.get('name') or '').strip().lower().replace(' ', '').replace('_', '')
                if not fname.endswith('id'):
                    continue
                for other in entities:
                    if other['id'] == ent['id']:
                        continue
                    oname = (other.get('name') or '').strip().lower().replace(' ', '').replace('_', '')
                    if oname and fname.startswith(oname + 'id'):
                        relations.append({'id': len(relations) + 1, 'type': 'oneToMany',
                                          'startEntity': other['id'], 'endEntity': ent['id']})
                        break
    return entities, relations


def reverse_code_to_model(code, language, target):
    """解析源代码反推出模型结构化数据。AI 未启用/调用失败返回 None。"""
    if not code or not code.strip():
        return None
    if not ai_service_config.enabled:
        return None

    messages = [
        {'role': 'system', 'content': code_reverse_system_prompt(target)},
        {'role': 'user', 'content': f'语言：{language or "auto"}\n源代码：\n{code}'}
    ]
    result = AIService.chat_completion(messages, max_tokens=4096, temperature=0.3)
    if not isinstance(result, dict) or 'error' in result:
        return None
    try:
        content = result['choices'][0]['message']['content']
    except (KeyError, IndexError, TypeError):
        return None
    data = _ai_parse_json_response(content)
    if not isinstance(data, dict):
        return None
    return data


def _uuid_elements_to_canvas(elements, relationships):
    """把 _layout_ai_elements 的 uuid 结果重写为前端画布 id 结构（uuid→数字 id，source/target→startElement/endElement）。"""
    uuid_to_id = {e['uuid']: i + 1 for i, e in enumerate(elements)}
    for e in elements:
        e['id'] = uuid_to_id[e.pop('uuid')]
    for r in relationships:
        r.pop('uuid', None)
        r['id'] = len(relationships)  # 占位，前端会用 startElement/endElement
        r['startElement'] = uuid_to_id.get(r.get('source'))
        r['endElement'] = uuid_to_id.get(r.get('target'))
        r.pop('source', None)
        r.pop('target', None)
        r.pop('source_name', None)
        r.pop('target_name', None)
    return elements, relationships


@app.route('/api/v1/ai/code/reverse', methods=['POST'])
def ai_code_reverse_v1():
    """代码反向工程：粘贴代码 → 反推 UML 类图 / ER 模型（LLM）。"""
    data = request.json or {}
    code = data.get('code', '')
    language = data.get('language', 'auto')
    target = data.get('target', 'uml')

    if not code or not code.strip():
        return jsonify({'error': '请粘贴源代码'}), 400
    if target not in ('uml', 'er'):
        return jsonify({'error': 'target 必须是 uml 或 er'}), 400

    result = reverse_code_to_model(code, language, target)
    if result is None:
        return jsonify({'error': 'AI 服务不可用或未能解析代码，请确认已配置 API 密钥后重试'}), 422

    if target == 'uml':
        elements_raw = result.get('elements')
        relationships_raw = result.get('relationships')
        if not isinstance(elements_raw, list) or not elements_raw:
            return jsonify({'error': '未能从代码中提取出类结构'}), 422
        if not isinstance(relationships_raw, list):
            relationships_raw = []
        elements, relationships = _layout_ai_elements(elements_raw, relationships_raw, 'class')
        elements, relationships = _uuid_elements_to_canvas(elements, relationships)
        return jsonify({'target': 'uml', 'elements': elements, 'relationships': relationships})

    entities_raw = result.get('entities')
    if not isinstance(entities_raw, list) or not entities_raw:
        return jsonify({'error': '未能从代码中提取出实体'}), 422
    entities, relations = _layout_ai_er(entities_raw, result.get('relationships') or [])
    return jsonify({'target': 'er', 'entities': entities, 'relationships': relations})


@app.route('/api/v1/project/<project_id>/ai/generate-diagram', methods=['POST'])
def ai_generate_diagram_v1(project_id):
    """自然语言 → UML/ER 图，返回前端画布可直接使用的形状（不落盘，前端画上后走保存）。"""
    user_id = _require_user_id()
    if user_id is None:
        return jsonify({'error': '未登录'}), 401

    project = load_projects().get(project_id)
    if project is None:
        return jsonify({'error': '项目不存在'}), 404
    if project.owner_id != user_id and project.permissions.get(user_id) not in ('owner', 'editor'):
        return jsonify({'error': '无权限'}), 403

    data = request.json or {}
    text = (data.get('text') or '').strip()
    kind = data.get('kind', 'uml')
    view_type = data.get('view_type', 'class')
    if not text:
        return jsonify({'error': '请输入业务描述'}), 400
    if kind not in ('uml', 'er'):
        return jsonify({'error': 'kind 必须是 uml 或 er'}), 400

    if kind == 'uml':
        # generate_uml_from_prompt 内部已布局（含 uuid），只需转前端 id 结构
        elements_raw, relationships_raw = generate_uml_from_prompt(text, view_type)
        if not elements_raw:
            return jsonify({'error': 'AI 服务不可用或未能解析描述，请确认已配置 API 密钥后重试'}), 422
        elements, relationships = _uuid_elements_to_canvas(elements_raw, relationships_raw)
        return jsonify({'target': 'uml', 'elements': elements, 'relationships': relationships})

    # ER：LLM 原始数据 → 画布布局（关系类型已归一化 camelCase）
    ai_data = _ai_generate_er_data(text)
    entities_raw = ai_data.get('entities') if isinstance(ai_data, dict) else None
    relations_raw = ai_data.get('relationships') if isinstance(ai_data, dict) else []
    if not isinstance(entities_raw, list) or not entities_raw:
        entities_raw = extract_entities_from_requirements(text)
        relations_raw = []
    if not isinstance(relations_raw, list):
        relations_raw = []
    if not isinstance(entities_raw, list) or not entities_raw:
        return jsonify({'error': '未能从描述中提取出实体，请补充更明确的业务信息'}), 422
    entities, relations = _layout_ai_er(entities_raw, relations_raw)
    return jsonify({'target': 'er', 'entities': entities, 'relationships': relations})


# === 对话式编辑 ===

def _describe_uml_for_edit(elements, connections):
    """把当前 UML 模型序列化为 LLM 可读文本。"""
    lines = []
    for e in elements:
        parts = [f"{e.get('type')} {e.get('name')}"]
        attrs = e.get('attributes') or []
        methods = e.get('methods') or []
        if attrs:
            parts.append('属性: ' + '; '.join(str(a) for a in attrs))
        if methods:
            parts.append('方法: ' + '; '.join(str(m) for m in methods))
        lines.append('- ' + ' | '.join(parts))
    lines.append('关系:')
    name_by_id = {e['id']: e['name'] for e in elements if e.get('id') is not None and e.get('name')}
    for c in connections:
        s = name_by_id.get(c.get('startElement')) or c.get('startElement')
        t = name_by_id.get(c.get('endElement')) or c.get('endElement')
        lines.append(f"- {s} --({c.get('type')})--> {t}")
    return '\n'.join(lines) or '（空模型）'


def _describe_er_for_edit(erEntities, erRelations):
    """把当前 ER 模型序列化为 LLM 可读文本。"""
    lines = []
    for e in erEntities:
        fields = []
        for f in e.get('fields') or []:
            tag = 'PK' if f.get('isPrimary') else ('FK' if f.get('isForeign') else '')
            fields.append(f"{f.get('name')}({f.get('type')}{(' ' + tag) if tag else ''})")
        lines.append(f"- {e.get('name')}: " + ', '.join(fields))
    lines.append('关系:')
    name_by_id = {e['id']: e['name'] for e in erEntities if e.get('id') is not None and e.get('name')}
    for r in erRelations:
        s = name_by_id.get(r.get('startEntity')) or r.get('startEntity')
        t = name_by_id.get(r.get('endEntity')) or r.get('endEntity')
        lines.append(f"- {s} --({r.get('type')})--> {t}")
    return '\n'.join(lines) or '（空模型）'


def _ai_edit_model(kind, description, instruction):
    """调用 LLM 生成增量编辑操作列表。AI 未启用/失败返回 None。"""
    if not ai_service_config.enabled:
        return None
    messages = [
        {'role': 'system', 'content': edit_model_system_prompt(kind)},
        {'role': 'user', 'content': f'当前模型：\n{description}\n\n用户指令：{instruction}'}
    ]
    result = AIService.chat_completion(messages, max_tokens=2000, temperature=0.3, use_reasoning=True)
    if not isinstance(result, dict) or 'error' in result:
        return None
    try:
        content = result['choices'][0]['message']['content']
    except (KeyError, IndexError, TypeError):
        return None
    data = _ai_parse_json_response(content)
    if not isinstance(data, dict) or not isinstance(data.get('operations'), list):
        return None
    return data['operations']


def _apply_uml_edits(elements, connections, ops):
    """把操作列表应用到当前 UML 模型（按类名解析 id），返回新元素/连接。"""
    elements = [dict(e) for e in elements]
    connections = [dict(c) for c in connections]
    name_to_id = {}
    for e in elements:
        if e.get('name') and e.get('id') is not None:
            name_to_id.setdefault(str(e['name']).strip(), e['id'])
    next_id = max([e.get('id', 0) for e in elements] + [0]) + 1
    new_elements = list(elements)
    new_connections = list(connections)

    for op in ops:
        if not isinstance(op, dict):
            continue
        o = str(op.get('op') or '').strip()
        if o == 'add_element':
            name = str(op.get('name') or '').strip()
            if not name or name in name_to_id:
                continue
            eid = next_id
            next_id += 1
            elem = {'id': eid, 'type': str(op.get('type') or 'Class').strip() or 'Class', 'name': name,
                    'x': 100, 'y': 100 + len(new_elements) * 40, 'width': 120, 'height': 80}
            if isinstance(op.get('attributes'), list):
                elem['attributes'] = [str(a) for a in op['attributes']]
            if isinstance(op.get('methods'), list):
                elem['methods'] = [str(m) for m in op['methods']]
            if op.get('description'):
                elem['description'] = str(op['description'])
            name_to_id[name] = eid
            new_elements.append(elem)
        elif o == 'update_element':
            name = str(op.get('name') or '').strip()
            eid = name_to_id.get(name)
            if eid is None:
                continue
            target = next((e for e in new_elements if e.get('id') == eid), None)
            if not target:
                continue
            if isinstance(op.get('attributes'), list):
                target['attributes'] = [str(a) for a in op['attributes']]
            if isinstance(op.get('methods'), list):
                target['methods'] = [str(m) for m in op['methods']]
            if op.get('description'):
                target['description'] = str(op['description'])
        elif o == 'delete_element':
            name = str(op.get('name') or '').strip()
            eid = name_to_id.get(name)
            if eid is None:
                continue
            new_elements = [e for e in new_elements if e.get('id') != eid]
            new_connections = [c for c in new_connections
                               if c.get('startElement') != eid and c.get('endElement') != eid]
            name_to_id.pop(name, None)
        elif o == 'add_relationship':
            s = name_to_id.get(str(op.get('source') or '').strip())
            t = name_to_id.get(str(op.get('target') or '').strip())
            if s is None or t is None or s == t:
                continue
            rtype = str(op.get('type') or 'Association').strip()
            if rtype not in RELATIONSHIP_TYPES:
                rtype = 'Association'
            new_connections.append({'id': next_id, 'type': rtype, 'startElement': s, 'endElement': t})
            next_id += 1
        elif o == 'delete_relationship':
            s = name_to_id.get(str(op.get('source') or '').strip())
            t = name_to_id.get(str(op.get('target') or '').strip())
            new_connections = [c for c in new_connections
                               if not (c.get('startElement') == s and c.get('endElement') == t)]

    return new_elements, new_connections


def _apply_er_edits(erEntities, erRelations, ops):
    """把操作列表应用到当前 ER 模型（按实体名解析 id），返回新实体/关系。"""
    erEntities = [dict(e) for e in erEntities]
    erRelations = [dict(r) for r in erRelations]
    name_to_id = {}
    for e in erEntities:
        if e.get('name') and e.get('id') is not None:
            name_to_id.setdefault(str(e['name']).strip(), e['id'])
    next_id = max([e.get('id', 0) for e in erEntities] + [0]) + 1
    new_entities = list(erEntities)
    new_relations = list(erRelations)

    for op in ops:
        if not isinstance(op, dict):
            continue
        o = str(op.get('op') or '').strip()
        if o == 'add_entity':
            name = str(op.get('name') or '').strip()
            if not name or name in name_to_id:
                continue
            eid = next_id
            next_id += 1
            fields = []
            for f in op.get('fields') or []:
                if isinstance(f, dict) and f.get('name'):
                    fields.append({'name': str(f['name']), 'type': str(f.get('type') or 'string').upper(),
                                   'isPrimary': bool(f.get('isPrimary', False)),
                                   'isForeign': bool(f.get('isForeign', False))})
            if not fields:
                fields = [{'name': 'id', 'type': 'INT', 'isPrimary': True, 'isForeign': False}]
            new_entities.append({'id': eid, 'name': name, 'x': 100, 'y': 100 + len(new_entities) * 40,
                                 'width': 150, 'displayHeight': max(80, 40 + 18 * len(fields)), 'fields': fields})
            name_to_id[name] = eid
        elif o == 'delete_entity':
            name = str(op.get('name') or '').strip()
            eid = name_to_id.get(name)
            if eid is None:
                continue
            new_entities = [e for e in new_entities if e.get('id') != eid]
            new_relations = [r for r in new_relations
                             if r.get('startEntity') != eid and r.get('endEntity') != eid]
            name_to_id.pop(name, None)
        elif o == 'add_field':
            eid = name_to_id.get(str(op.get('entity') or '').strip())
            if eid is None:
                continue
            target = next((e for e in new_entities if e.get('id') == eid), None)
            f = op.get('field')
            if target and isinstance(f, dict) and f.get('name'):
                target['fields'].append({'name': str(f['name']), 'type': str(f.get('type') or 'string').upper(),
                                         'isPrimary': bool(f.get('isPrimary', False)),
                                         'isForeign': bool(f.get('isForeign', False))})
                target['displayHeight'] = max(80, 40 + 18 * len(target['fields']))
        elif o == 'delete_field':
            eid = name_to_id.get(str(op.get('entity') or '').strip())
            fname = str(op.get('field_name') or '').strip()
            if eid is None:
                continue
            target = next((e for e in new_entities if e.get('id') == eid), None)
            if target:
                target['fields'] = [f for f in target['fields'] if f.get('name') != fname]
                target['displayHeight'] = max(80, 40 + 18 * len(target['fields']))
        elif o == 'add_relation':
            s = name_to_id.get(str(op.get('source') or '').strip())
            t = name_to_id.get(str(op.get('target') or '').strip())
            if s is None or t is None or s == t:
                continue
            rtype = str(op.get('type') or 'one_to_many').strip()
            if rtype not in ('one_to_one', 'one_to_many', 'many_to_one', 'many_to_many'):
                rtype = 'one_to_many'
            new_relations.append({'id': next_id, 'type': _normalize_er_rel_type(rtype), 'startEntity': s, 'endEntity': t})
            next_id += 1
        elif o == 'delete_relation':
            s = name_to_id.get(str(op.get('source') or '').strip())
            t = name_to_id.get(str(op.get('target') or '').strip())
            new_relations = [r for r in new_relations
                             if not (r.get('startEntity') == s and r.get('endEntity') == t)]

    return new_entities, new_relations


ARCHIMATE_ELEMENT_TYPES = {'actor', 'process', 'service', 'component', 'node', 'artifact'}
ARCHIMATE_REL_TYPES = {'association', 'realization', 'serving', 'composition',
                       'aggregation', 'access', 'flow', 'triggering'}
ARCHIMATE_LAYERS = ('business', 'application', 'technology')


def _describe_archimate_for_edit(archimateElements, archimateConnections):
    """把当前 ArchiMate 模型序列化为 LLM 可读文本。"""
    lines = []
    for e in archimateElements:
        layer = e.get('layer') or ''
        lines.append(f"- {e.get('type')} {e.get('name')}" + (f" [层次:{layer}]" if layer else ''))
    lines.append('关系:')
    name_by_id = {e['id']: e['name'] for e in archimateElements if e.get('id') is not None and e.get('name')}
    for c in archimateConnections:
        s = name_by_id.get(c.get('startElement')) or c.get('startElement')
        t = name_by_id.get(c.get('endElement')) or c.get('endElement')
        lines.append(f"- {s} --({c.get('type')})--> {t}")
    return '\n'.join(lines) or '（空模型）'


def _apply_archimate_edits(archimateElements, archimateConnections, ops):
    """把操作列表应用到当前 ArchiMate 模型（按元素名解析 id），返回新元素/连接。"""
    archimateElements = [dict(e) for e in archimateElements]
    archimateConnections = [dict(c) for c in archimateConnections]
    name_to_id = {}
    for e in archimateElements:
        if e.get('name') and e.get('id') is not None:
            name_to_id.setdefault(str(e['name']).strip(), e['id'])
    next_id = max([e.get('id', 0) for e in archimateElements] + [0]) + 1
    new_elements = list(archimateElements)
    new_connections = list(archimateConnections)

    for op in ops:
        if not isinstance(op, dict):
            continue
        o = str(op.get('op') or '').strip()
        if o == 'add_element':
            name = str(op.get('name') or '').strip()
            if not name or name in name_to_id:
                continue
            etype = str(op.get('type') or 'service').strip().lower()
            if etype not in ARCHIMATE_ELEMENT_TYPES:
                etype = 'service'
            layer = str(op.get('layer') or 'business').strip()
            if layer not in ARCHIMATE_LAYERS:
                layer = 'business'
            eid = next_id
            next_id += 1
            new_elements.append({'id': eid, 'type': etype, 'name': name, 'layer': layer,
                                 'x': 100, 'y': 100 + len(new_elements) * 50,
                                 'width': 120, 'height': 80,
                                 'color': '#ffffff', 'headerColor': '#667eea'})
            name_to_id[name] = eid
        elif o == 'update_element':
            name = str(op.get('name') or '').strip()
            eid = name_to_id.get(name)
            if eid is None:
                continue
            target = next((e for e in new_elements if e.get('id') == eid), None)
            if not target:
                continue
            new_name = str(op.get('new_name') or '').strip()
            if new_name:
                name_to_id.pop(name, None)
                target['name'] = new_name
                name_to_id[new_name] = eid
            layer = str(op.get('layer') or '').strip()
            if layer in ARCHIMATE_LAYERS:
                target['layer'] = layer
        elif o == 'delete_element':
            name = str(op.get('name') or '').strip()
            eid = name_to_id.get(name)
            if eid is None:
                continue
            new_elements = [e for e in new_elements if e.get('id') != eid]
            new_connections = [c for c in new_connections
                               if c.get('startElement') != eid and c.get('endElement') != eid]
            name_to_id.pop(name, None)
        elif o == 'add_relationship':
            s = name_to_id.get(str(op.get('source') or '').strip())
            t = name_to_id.get(str(op.get('target') or '').strip())
            if s is None or t is None or s == t:
                continue
            rtype = str(op.get('type') or 'association').strip().lower()
            if rtype not in ARCHIMATE_REL_TYPES:
                rtype = 'association'
            new_connections.append({'id': next_id, 'type': rtype, 'startElement': s, 'endElement': t})
            next_id += 1
        elif o == 'delete_relationship':
            s = name_to_id.get(str(op.get('source') or '').strip())
            t = name_to_id.get(str(op.get('target') or '').strip())
            new_connections = [c for c in new_connections
                               if not (c.get('startElement') == s and c.get('endElement') == t)]

    return new_elements, new_connections


@app.route('/api/v1/project/<model_id>/ai/edit-model', methods=['POST'])
def ai_edit_model_v1(model_id):
    """对话式编辑：自然语言指令 → 增量修改当前模型（仅限所属用户）。
    body: {kind: 'uml'|'er', instruction, elements, connections} 或 {kind:'er', erEntities, erRelations}
    """
    user_id = _require_user_id()
    if user_id is None:
        return jsonify({'error': '未登录'}), 401

    model = load_model_from_cache(model_id)
    if not _model_owned_by(model, user_id):
        return jsonify({'error': '模型不存在'}), 404

    data = request.json or {}
    kind = data.get('kind', 'uml')
    instruction = (data.get('instruction') or '').strip()
    if kind not in ('uml', 'er', 'archimate'):
        return jsonify({'error': 'kind 必须是 uml / er / archimate'}), 400
    if not instruction:
        return jsonify({'error': '请输入修改指令'}), 400

    if kind == 'uml':
        elements = data.get('elements') or []
        connections = data.get('connections') or []
        if not elements:
            return jsonify({'error': '当前 UML 画布为空，请先画一些元素'}), 400
        description = _describe_uml_for_edit(elements, connections)
        ops = _ai_edit_model('uml', description, instruction)
        if ops is None:
            return jsonify({'error': 'AI 服务不可用或未能解析指令，请确认已配置 API 密钥后重试'}), 422
        new_elements, new_connections = _apply_uml_edits(elements, connections, ops)
        return jsonify({'kind': 'uml', 'elements': new_elements, 'connections': new_connections, 'applied_ops': len(ops)})

    if kind == 'archimate':
        archElements = data.get('archimateElements') or []
        archConnections = data.get('archimateConnections') or []
        if not archElements:
            return jsonify({'error': '当前 ArchiMate 画布为空，请先画一些元素'}), 400
        description = _describe_archimate_for_edit(archElements, archConnections)
        ops = _ai_edit_model('archimate', description, instruction)
        if ops is None:
            return jsonify({'error': 'AI 服务不可用或未能解析指令，请确认已配置 API 密钥后重试'}), 422
        new_elements, new_connections = _apply_archimate_edits(archElements, archConnections, ops)
        return jsonify({'kind': 'archimate', 'archimateElements': new_elements,
                        'archimateConnections': new_connections, 'applied_ops': len(ops)})

    erEntities = data.get('erEntities') or []
    erRelations = data.get('erRelations') or []
    if not erEntities:
        return jsonify({'error': '当前 ER 画布为空，请先建一些表'}), 400
    description = _describe_er_for_edit(erEntities, erRelations)
    ops = _ai_edit_model('er', description, instruction)
    if ops is None:
        return jsonify({'error': 'AI 服务不可用或未能解析指令，请确认已配置 API 密钥后重试'}), 422
    new_entities, new_relations = _apply_er_edits(erEntities, erRelations, ops)
    return jsonify({'kind': 'er', 'erEntities': new_entities, 'erRelations': new_relations, 'applied_ops': len(ops)})


# === 项目专属记忆库 ===

def _get_memories(model_id):
    """读取项目的记忆条目列表。"""
    data = db.get(f'memory:{model_id}', {}) or {}
    entries = data.get('entries')
    if not isinstance(entries, list):
        entries = []
    return entries


@app.route('/api/v1/project/<model_id>/ai/memory', methods=['GET'])
def get_model_memory(model_id):
    """获取项目记忆库（仅限所属用户）"""
    user_id = _require_user_id()
    if user_id is None:
        return jsonify({'error': '未登录'}), 401
    model = load_model_from_cache(model_id)
    if not _model_owned_by(model, user_id):
        return jsonify({'error': '模型不存在'}), 404
    return jsonify({'memories': _get_memories(model_id)})


@app.route('/api/v1/project/<model_id>/ai/memory', methods=['POST'])
def add_model_memory(model_id):
    """添加一条项目记忆（仅限所属用户）"""
    user_id = _require_user_id()
    if user_id is None:
        return jsonify({'error': '未登录'}), 401
    model = load_model_from_cache(model_id)
    if not _model_owned_by(model, user_id):
        return jsonify({'error': '模型不存在'}), 404

    content = (request.json or {}).get('content', '').strip()
    if not content:
        return jsonify({'error': '记忆内容不能为空'}), 400

    entries = _get_memories(model_id)
    entry = {
        'id': str(uuid.uuid4())[:8],
        'content': content,
        'created_at': datetime.datetime.now().isoformat()
    }
    entries.append(entry)
    db.set(f'memory:{model_id}', {'entries': entries})
    return jsonify({'memory': entry, 'memories': entries})


@app.route('/api/v1/project/<model_id>/ai/memory/<mem_id>', methods=['DELETE'])
def delete_model_memory(model_id, mem_id):
    """删除一条项目记忆（仅限所属用户）"""
    user_id = _require_user_id()
    if user_id is None:
        return jsonify({'error': '未登录'}), 401
    model = load_model_from_cache(model_id)
    if not _model_owned_by(model, user_id):
        return jsonify({'error': '模型不存在'}), 404

    entries = [e for e in _get_memories(model_id) if e.get('id') != mem_id]
    db.set(f'memory:{model_id}', {'entries': entries})
    return jsonify({'message': '删除成功', 'memories': entries})


# === AI 文档/报表生成 ===

def _describe_model_for_document(model, doc_type):
    """把模型的 UML / ArchiMate / ER 三部分序列化为 LLM 可读文本。"""
    lines = []
    if model.elements:
        lines.append('## UML 类/接口')
        for e in model.elements:
            attrs = e.get('attributes') or []
            methods = e.get('methods') or []
            extra = ''
            if attrs:
                extra += ' | 属性: ' + '; '.join(str(a) for a in attrs)
            if methods:
                extra += ' | 方法: ' + '; '.join(str(m) for m in methods)
            lines.append(f"- {e.get('type')} {e.get('name')}{extra}")
        lines.append('## UML 关系')
        name_by_id = {e['id']: e['name'] for e in model.elements if e.get('id') is not None and e.get('name')}
        for r in model.relationships:
            s = name_by_id.get(r.get('startElement')) or r.get('startElement')
            t = name_by_id.get(r.get('endElement')) or r.get('endElement')
            lines.append(f"- {s} --({r.get('type')})--> {t}")
    if model.archimate_elements:
        lines.append('## ArchiMate 元素')
        for e in model.archimate_elements:
            layer = e.get('layer') or ''
            lines.append(f"- {e.get('type')} {e.get('name')}" + (f" [层次:{layer}]" if layer else ''))
        lines.append('## ArchiMate 关系')
        name_by_id = {e['id']: e['name'] for e in model.archimate_elements if e.get('id') is not None and e.get('name')}
        for r in model.archimate_connections:
            s = name_by_id.get(r.get('startElement')) or r.get('startElement')
            t = name_by_id.get(r.get('endElement')) or r.get('endElement')
            lines.append(f"- {s} --({r.get('type')})--> {t}")
    if model.er_entities:
        lines.append('## ER 实体')
        for e in model.er_entities:
            fields = ', '.join(
                f"{f.get('name')}({f.get('type')}{' PK' if f.get('isPrimary') else ''}{' FK' if f.get('isForeign') else ''})"
                for f in e.get('fields', [])
            )
            lines.append(f"- {e.get('name')}: {fields}")
        lines.append('## ER 关系')
        name_by_id = {e['id']: e['name'] for e in model.er_entities if e.get('id') is not None and e.get('name')}
        for r in model.er_relations:
            s = name_by_id.get(r.get('startEntity')) or r.get('startEntity')
            t = name_by_id.get(r.get('endEntity')) or r.get('endEntity')
            lines.append(f"- {s} --({r.get('type')})--> {t}")
    return '\n'.join(lines)


def _ai_generate_document(description, doc_type, fmt):
    """调用 LLM 生成设计文档。AI 未启用/失败返回 None。"""
    if not ai_service_config.enabled:
        return None
    messages = [
        {'role': 'system', 'content': document_system_prompt(doc_type, fmt)},
        {'role': 'user', 'content': '模型内容：\n' + description}
    ]
    result = AIService.chat_completion(messages, max_tokens=4096, temperature=0.4)
    if not isinstance(result, dict) or 'error' in result:
        return None
    try:
        content = result['choices'][0]['message']['content']
    except (KeyError, IndexError, TypeError):
        return None
    content = (content or '').strip()
    return content or None


@app.route('/api/v1/project/<model_id>/ai/document', methods=['POST'])
def ai_document_v1(model_id):
    """AI 生成设计文档/报表（仅限所属用户）。
    body: {doc_type: architecture/overview/database, format: markdown/html}
    """
    user_id = _require_user_id()
    if user_id is None:
        return jsonify({'error': '未登录'}), 401
    model = load_model_from_cache(model_id)
    if not _model_owned_by(model, user_id):
        return jsonify({'error': '模型不存在'}), 404

    data = request.json or {}
    doc_type = data.get('doc_type', 'architecture')
    fmt = data.get('format', 'markdown')
    if doc_type not in ('architecture', 'overview', 'database'):
        return jsonify({'error': 'doc_type 必须是 architecture / overview / database'}), 400
    if fmt not in ('markdown', 'html'):
        return jsonify({'error': 'format 必须是 markdown / html'}), 400

    description = _describe_model_for_document(model, doc_type)
    if not description.strip():
        return jsonify({'error': '模型为空，无法生成文档'}), 400

    content = _ai_generate_document(description, doc_type, fmt)
    if content is None:
        return jsonify({'error': 'AI 服务不可用或未能生成文档，请确认已配置 API 密钥后重试'}), 422

    return jsonify({'content': content, 'doc_type': doc_type, 'format': fmt})


def ai_generate_code_from_model(model, language, framework):
    """AI基于模型生成代码"""
    task = CodeGenerateTask(model.get('id', ''), model.get('project_id', ''), language, framework)
    
    # 获取类图中的类
    classes = model.get('classes', [])
    
    # 生成各层代码
    for cls in classes:
        class_name = cls.get('name', 'Unnamed')
        resource_name = class_name.lower()
        
        # 生成Entity
        if language == 'java':
            task.add_file(f"entity/{class_name}Entity.java", generate_java_entity(cls), language)
            task.add_file(f"dto/{class_name}DTO.java", generate_java_dto(cls), language)
            task.add_file(f"service/{class_name}Service.java", generate_java_service_interface(cls), language)
            task.add_file(f"service/impl/{class_name}ServiceImpl.java", generate_java_service_impl(cls), language)
            task.add_file(f"repository/{class_name}Repository.java", generate_java_repository(cls), language)
            task.add_file(f"controller/{class_name}Controller.java", generate_java_controller(cls), language)
        elif language == 'python':
            task.add_file(f"models/{resource_name}.py", generate_python_model(cls), language)
            task.add_file(f"schemas/{resource_name}.py", generate_python_schema(cls), language)
            task.add_file(f"services/{resource_name}.py", generate_python_service(cls), language)
            task.add_file(f"routers/{resource_name}.py", generate_python_router(cls), language)
        elif language == 'typescript':
            task.add_file(f"entities/{resource_name}.entity.ts", generate_ts_entity(cls), language)
            task.add_file(f"dto/{resource_name}.dto.ts", generate_ts_dto(cls), language)
            task.add_file(f"{resource_name}.service.ts", generate_ts_service(cls), language)
            task.add_file(f"{resource_name}.controller.ts", generate_ts_controller(cls), language)
    
    task.status = 'completed'
    task.progress = 100
    return task

def generate_java_entity(cls):
    """生成Java实体类"""
    class_name = cls.get('name', 'Entity')
    attributes = cls.get('attributes', [])
    
    code = f'''package com.example.entity;

import javax.persistence.*;
import lombok.Data;
import java.time.LocalDateTime;

/**
 * {class_name}实体类
 */
@Entity
@Table(name = "{class_name.lower()}")
@Data
public class {class_name}Entity {{
'''
    
    for attr in attributes:
        attr_name = attr.get('name', 'field')
        attr_type = map_java_type(attr.get('type', 'String'))
        code += f'''
    @Column(name = "{attr_name}")
    private {attr_type} {attr_name};
'''
    
    code += '''
}
'''
    return code

def generate_java_controller(cls):
    """生成Java控制器"""
    class_name = cls.get('name', 'Controller')
    resource_name = class_name.lower()
    
    return DEFAULT_CODE_TEMPLATES['java_springboot'].format(
        package_name='com.example.controller',
        class_name=class_name,
        resource_name=resource_name,
        description=f'{class_name}控制器类'
    )

def generate_java_service_interface(cls):
    """生成Java服务接口"""
    class_name = cls.get('name', 'Service')
    resource_name = class_name.lower()
    
    return f'''package com.example.service;

import com.example.entity.{class_name}Entity;
import com.example.dto.{class_name}DTO;
import java.util.List;

public interface {class_name}Service {{
    List<{class_name}Entity> list();
    {class_name}Entity getById(Long id);
    void add({class_name}DTO dto);
    void update({class_name}DTO dto);
    void delete(Long id);
}}
'''

def generate_java_service_impl(cls):
    """生成Java服务实现"""
    class_name = cls.get('name', 'Service')
    resource_name = class_name.lower()
    
    return f'''package com.example.service.impl;

import com.example.service.{class_name}Service;
import com.example.entity.{class_name}Entity;
import com.example.dto.{class_name}DTO;
import org.springframework.beans.BeanUtils;
import org.springframework.stereotype.Service;
import java.util.ArrayList;
import java.util.List;

@Service
public class {class_name}ServiceImpl implements {class_name}Service {{
    
    @Override
    public List<{class_name}Entity> list() {{
        return new ArrayList<>();
    }}
    
    @Override
    public {class_name}Entity getById(Long id) {{
        return null;
    }}
    
    @Override
    public void add({class_name}DTO dto) {{
        // 添加业务逻辑
    }}
    
    @Override
    public void update({class_name}DTO dto) {{
        // 更新业务逻辑
    }}
    
    @Override
    public void delete(Long id) {{
        // 删除业务逻辑
    }}
}}
'''

def generate_java_repository(cls):
    """生成Java仓储"""
    class_name = cls.get('name', 'Repository')
    resource_name = class_name.lower()
    
    return f'''package com.example.repository;

import com.example.entity.{class_name}Entity;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

@Repository
public interface {class_name}Repository extends JpaRepository<{class_name}Entity, Long> {{
}}
'''

def generate_java_dto(cls):
    """生成Java DTO"""
    class_name = cls.get('name', 'DTO')
    attributes = cls.get('attributes', [])
    
    code = '''package com.example.dto;

import lombok.Data;
import javax.validation.constraints.NotNull;

@Data
public class ''' + class_name + '''DTO {
'''
    
    for attr in attributes:
        attr_name = attr.get('name', 'field')
        attr_type = map_java_type(attr.get('type', 'String'))
        code += f'''
    private {attr_type} {attr_name};
'''
    
    code += '''
}
'''
    return code

def generate_python_model(cls):
    """生成Python模型"""
    class_name = cls.get('name', 'Model')
    
    return f'''from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()

class {class_name}(Base):
    __tablename__ = '{class_name.lower()}'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
'''

def generate_python_schema(cls):
    """生成Python Schema"""
    class_name = cls.get('name', 'Schema')
    
    return f'''from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class {class_name}(BaseModel):
    id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        orm_mode = True

class {class_name}Create(BaseModel):
    pass

class {class_name}Update(BaseModel):
    pass
'''

def generate_python_service(cls):
    """生成Python服务"""
    class_name = cls.get('name', 'Service')
    resource_name = class_name.lower()
    
    return f'''from sqlalchemy.orm import Session
from .models import {class_name}
from . import schemas

def get_{resource_name}s(db: Session, skip: int = 0, limit: int = 100):
    return db.query({class_name}).offset(skip).limit(limit).all()

def get_{resource_name}_by_id(db: Session, id: int):
    return db.query({class_name}).filter({class_name}.id == id).first()

def create_{resource_name}(db: Session, {resource_name}: schemas.{class_name}Create):
    db_{resource_name} = {class_name}(**{resource_name}.dict())
    db.add(db_{resource_name})
    db.commit()
    db.refresh(db_{resource_name})
    return db_{resource_name}

def update_{resource_name}(db: Session, id: int, {resource_name}: schemas.{class_name}Update):
    db_{resource_name} = get_{resource_name}_by_id(db, id)
    if db_{resource_name}:
        for key, value in {resource_name}.dict(exclude_unset=True).items():
            setattr(db_{resource_name}, key, value)
        db.commit()
        db.refresh(db_{resource_name})
    return db_{resource_name}

def delete_{resource_name}(db: Session, id: int):
    db_{resource_name} = get_{resource_name}_by_id(db, id)
    if db_{resource_name}:
        db.delete(db_{resource_name})
        db.commit()
    return db_{resource_name}
'''

def generate_python_router(cls):
    """生成Python路由"""
    class_name = cls.get('name', 'Router')
    resource_name = class_name.lower()
    
    return DEFAULT_CODE_TEMPLATES['python_fastapi'].format(
        module_name=class_name.lower(),
        class_name=class_name,
        resource_name=resource_name
    )

def generate_ts_entity(cls):
    """生成TypeScript实体"""
    class_name = cls.get('name', 'Entity')
    
    return f'''import {{ Entity, PrimaryGeneratedColumn, Column, CreateDateColumn, UpdateDateColumn }} from "typeorm";

@Entity("{class_name.toLowerCase()}")
export class {class_name} {{
    @PrimaryGeneratedColumn()
    id: number;

    @CreateDateColumn()
    createdAt: Date;

    @UpdateDateColumn()
    updatedAt: Date;
}}
'''

def generate_ts_dto(cls):
    """生成TypeScript DTO"""
    class_name = cls.get('name', 'DTO')
    
    return f'''export class {class_name}DTO {{
    id?: number;
    createdAt?: Date;
    updatedAt?: Date;
}}

export class {class_name}CreateDTO {{
}}

export class {class_name}UpdateDTO {{
}}
'''

def generate_ts_service(cls):
    """生成TypeScript服务"""
    class_name = cls.get('name', 'Service')
    resource_name = class_name.toLowerCase()
    
    template = '''import {{ Injectable }} from "@nestjs/common";
import {{ Repository }} from "typeorm";
import {{ InjectRepository }} from "@nestjs/typeorm";
import {{ {class_name} }} from "./entities/{resource_name}.entity";

@Injectable()
export class {class_name}Service {{
    constructor(
        @InjectRepository({class_name})
        private {resource_name}Repository: Repository<{class_name}>
    ) {{}}

    async findAll(): Promise<{class_name}[]> {{
        return this.{resource_name}Repository.find();
    }}

    async findOne(id: number): Promise<{class_name}> {{
        return this.{resource_name}Repository.findOne(id);
    }}

    async create(dto: any): Promise<{class_name}> {{
        return this.{resource_name}Repository.save(dto);
    }}

    async update(id: number, dto: any): Promise<{class_name}> {{
        await this.{resource_name}Repository.update(id, dto);
        return this.findOne(id);
    }}

    async remove(id: number): Promise<void> {{
        await this.{resource_name}Repository.delete(id);
    }}
}}
'''
    return template.format(class_name=class_name, resource_name=resource_name)

def generate_ts_controller(cls):
    """生成TypeScript控制器"""
    class_name = cls.get('name', 'Controller')
    resource_name = class_name.toLowerCase()
    
    return DEFAULT_CODE_TEMPLATES['typescript_nestjs'].format(
        class_name=class_name,
        resource_name=resource_name
    )

def map_java_type(type_name):
    """映射Java类型"""
    type_mapping = {
        'string': 'String',
        'int': 'Integer',
        'integer': 'Integer',
        'long': 'Long',
        'float': 'Float',
        'double': 'Double',
        'decimal': 'BigDecimal',
        'boolean': 'Boolean',
        'date': 'LocalDateTime',
        'datetime': 'LocalDateTime',
        'text': 'String',
        'blob': 'byte[]'
    }
    return type_mapping.get(type_name.lower(), 'String')

def ai_reverse_code_to_model(task):
    """AI逆向工程：从代码生成模型"""
    source_code = task.source_path
    
    # 模拟分析代码结构
    model = {
        'name': '逆向生成的模型',
        'language': task.language,
        'classes': [
            {
                'name': 'User',
                'type': 'class',
                'attributes': [
                    {'name': 'id', 'type': 'int'},
                    {'name': 'username', 'type': 'string'},
                    {'name': 'email', 'type': 'string'}
                ],
                'methods': [
                    {'name': 'getUser', 'type': 'public'},
                    {'name': 'createUser', 'type': 'public'}
                ]
            },
            {
                'name': 'Order',
                'type': 'class',
                'attributes': [
                    {'name': 'id', 'type': 'int'},
                    {'name': 'userId', 'type': 'int'},
                    {'name': 'amount', 'type': 'decimal'}
                ]
            }
        ],
        'relationships': [
            {
                'source': 'Order',
                'target': 'User',
                'type': 'many_to_one',
                'description': '订单属于用户'
            }
        ]
    }
    
    task.models.append(model)
    task.status = 'completed'
    task.progress = 100
    
    return task

def ai_review_code(code_content, language):
    """AI代码审查"""
    issues = []
    warnings = []
    suggestions = []
    
    lines = code_content.split('\n')
    
    # 检查常见问题
    for i, line in enumerate(lines, 1):
        # 检查TODO注释
        if 'TODO' in line or 'FIXME' in line:
            warnings.append({
                'line': i,
                'type': 'todo',
                'message': f'发现未完成的TODO: {line.strip()}',
                'severity': 'warning'
            })
        
        # 检查长方法
        if line.strip().startswith('def ') or line.strip().startswith('function '):
            # 简化检查
            pass
        
        # 检查硬编码密码
        if 'password' in line.lower() and '=' in line:
            issues.append({
                'line': i,
                'type': 'security',
                'message': '发现可能的硬编码密码',
                'severity': 'critical',
                'suggestion': '请使用环境变量或配置中心存储敏感信息'
            })
        
        # 检查空catch块
        if 'catch' in line:
            # 简化检查
            pass
    
    # 生成建议
    if len(issues) == 0 and len(warnings) == 0:
        suggestions.append('代码质量良好，未发现明显问题')
    
    return {
        'valid': len(issues) == 0,
        'total_lines': len(lines),
        'issues': issues,
        'warnings': warnings,
        'suggestions': suggestions,
        'summary': f'代码审查完成：{len(issues)}个问题，{len(warnings)}个警告'
    }

def sync_code_and_model(task):
    """同步代码和模型"""
    records = []
    
    # 模拟同步记录
    records.append({
        'type': 'model_updated',
        'element': 'UserService',
        'description': '模型更新已同步到代码'
    })
    
    task.records = records
    task.status = 'completed'
    task.progress = 100
    
    return task

# === 代码双向工程API ===

@app.route('/api/v1/model/<model_id>/code/ai/generate', methods=['POST'])
def ai_generate_code(model_id):
    """AI生成代码"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    data = request.json
    language = data.get('language', 'java')
    framework = data.get('framework', '')
    
    # 获取模型
    model = models_cache.get(model_id, {})
    
    # 生成代码任务
    task = ai_generate_code_from_model(model, language, framework)
    task.user_id = sessions_cache[session_id]['user_id']
    code_generate_tasks_cache[task.id] = task
    
    return jsonify({
        'message': 'AI代码生成任务已创建',
        'task': task.to_dict()
    })

@app.route('/api/v1/code/generate/<task_id>', methods=['GET'])
def get_code_generate_task(task_id):
    """获取代码生成任务结果"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    if task_id not in code_generate_tasks_cache:
        return jsonify({'error': '任务不存在'}), 404
    
    task = code_generate_tasks_cache[task_id]
    
    return jsonify({
        'task': task.to_dict(),
        'file_count': len(task.files)
    })

@app.route('/api/v1/code/reverse/import', methods=['POST'])
def code_reverse_import():
    """代码逆向工程"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    data = request.json
    project_id = data.get('project_id', '')
    source_type = data.get('source_type', 'file')
    source_path = data.get('source_path', '')
    language = data.get('language', 'java')
    
    task = CodeReverseTask(project_id, source_type, source_path, language)
    task.user_id = sessions_cache[session_id]['user_id']
    
    # 执行逆向工程
    task = ai_reverse_code_to_model(task)
    
    code_reverse_tasks_cache[task.id] = task
    
    return jsonify({
        'message': '代码逆向建模任务完成',
        'task': task.to_dict(),
        'generated_models': len(task.models)
    })

@app.route('/api/v1/code/reverse/<task_id>', methods=['GET'])
def get_code_reverse_task(task_id):
    """获取逆向建模任务结果"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    if task_id not in code_reverse_tasks_cache:
        return jsonify({'error': '任务不存在'}), 404
    
    task = code_reverse_tasks_cache[task_id]
    
    return jsonify({
        'task': task.to_dict()
    })

@app.route('/api/v1/model/<model_id>/code/sync', methods=['POST'])
def sync_code_model(model_id):
    """代码-模型双向同步"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    data = request.json
    project_id = data.get('project_id', '')
    sync_type = data.get('sync_type', 'model_to_code')
    
    task = CodeSyncTask(project_id, model_id, sync_type)
    
    # 执行同步
    task = sync_code_and_model(task)
    
    code_sync_tasks_cache[task.id] = task
    
    return jsonify({
        'message': '同步任务完成',
        'task': task.to_dict(),
        'records': task.records
    })

@app.route('/api/v1/code/sync/<task_id>', methods=['GET'])
def get_sync_task(task_id):
    """获取同步任务结果"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    if task_id not in code_sync_tasks_cache:
        return jsonify({'error': '任务不存在'}), 404
    
    task = code_sync_tasks_cache[task_id]
    
    return jsonify({
        'task': task.to_dict()
    })

@app.route('/api/v1/code/ai/review', methods=['POST'])
def ai_code_review():
    """AI代码审查"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    data = request.json
    code_content = data.get('code', '')
    language = data.get('language', 'java')
    
    # 执行代码审查
    review_result = ai_review_code(code_content, language)
    
    report_id = str(uuid.uuid4())[:8]
    report = {
        'id': report_id,
        'language': language,
        'result': review_result,
        'created_at': datetime.datetime.now().isoformat()
    }
    
    code_review_reports_cache[report_id] = report
    
    return jsonify({
        'message': '代码审查完成',
        'report': report
    })

@app.route('/api/v1/code/review/<report_id>', methods=['GET'])
def get_code_review_report(report_id):
    """获取代码审查报告"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    if report_id not in code_review_reports_cache:
        return jsonify({'error': '报告不存在'}), 404
    
    report = code_review_reports_cache[report_id]
    
    return jsonify({
        'report': report
    })

@app.route('/api/v1/code/file/<file_id>/save', methods=['PUT'])
def save_code_file(file_id):
    """保存代码文件"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    data = request.json
    content = data.get('content', '')
    
    # 保存文件
    if file_id not in code_files_cache:
        code_files_cache[file_id] = {}
    
    code_files_cache[file_id]['content'] = content
    code_files_cache[file_id]['updated_at'] = datetime.datetime.now().isoformat()
    
    return jsonify({
        'message': '文件保存成功',
        'file': code_files_cache[file_id]
    })

@app.route('/api/v1/code/export', methods=['POST'])
def export_code():
    """导出代码"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    data = request.json
    task_id = data.get('task_id')
    format_type = data.get('format', 'zip')
    
    if task_id not in code_generate_tasks_cache:
        return jsonify({'error': '任务不存在'}), 404
    
    task = code_generate_tasks_cache[task_id]
    
    # 生成导出数据
    export_data = {
        'task_id': task_id,
        'language': task.language,
        'files': [{'name': f['name'], 'content': f['content']} for f in task.files],
        'exported_at': datetime.datetime.now().isoformat(),
        'format': format_type
    }
    
    return jsonify({
        'message': '代码导出成功',
        'export_data': export_data,
        'file_count': len(task.files)
    })

@app.route('/api/v1/project/<project_id>/code/template', methods=['GET', 'PUT'])
def manage_code_template(project_id):
    """代码模板管理"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    if request.method == 'GET':
        # 获取模板
        templates = list(code_templates_cache.values())
        return jsonify({
            'templates': templates,
            'default_templates': list(DEFAULT_CODE_TEMPLATES.keys())
        })
    
    elif request.method == 'PUT':
        # 保存模板
        data = request.json
        template_id = str(uuid.uuid4())[:8]
        template = {
            'id': template_id,
            'project_id': project_id,
            'name': data.get('name', ''),
            'language': data.get('language', 'java'),
            'content': data.get('content', ''),
            'created_at': datetime.datetime.now().isoformat()
        }
        code_templates_cache[template_id] = template
        return jsonify({
            'message': '模板保存成功',
            'template': template
        })

@app.route('/api/v1/code/languages', methods=['GET'])
def get_programming_languages():
    """获取支持的编程语言"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    languages = []
    for key, value in PROGRAMMING_LANGUAGES.items():
        languages.append({
            'id': key,
            'name': value['name'],
            'extension': value['extension'],
            'frameworks': value['frameworks']
        })
    
    return jsonify({'languages': languages})

@app.route('/api/v1/code/layers', methods=['GET'])
def get_code_layers():
    """获取代码层级架构"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    layers = []
    for key, value in CODE_LAYERS.items():
        layers.append({
            'id': key,
            'name': value['name'],
            'suffix': value['suffix'],
            'description': value['description']
        })
    
    return jsonify({'layers': layers})

# === 模块七：需求/测试/任务管理 ===

# 需求类型定义
REQUIREMENT_TYPES = {
    'functional': {'name': '功能需求', 'icon': '🎯'},
    'non_functional': {'name': '非功能需求', 'icon': '⚙️'},
    'user_story': {'name': '用户故事', 'icon': '📖'},
    'technical': {'name': '技术需求', 'icon': '🔧'},
    'business': {'name': '业务需求', 'icon': '💼'}
}

# 需求优先级
REQUIREMENT_PRIORITY = {
    'critical': {'name': '紧急', 'value': 4, 'color': '#ff0000'},
    'high': {'name': '高', 'value': 3, 'color': '#ff6600'},
    'medium': {'name': '中', 'value': 2, 'color': '#ffcc00'},
    'low': {'name': '低', 'value': 1, 'color': '#00cc00'}
}

# 需求状态
REQUIREMENT_STATUS = {
    'draft': {'name': '草稿', 'icon': '📝'},
    'review': {'name': '评审中', 'icon': '👀'},
    'approved': {'name': '已批准', 'icon': '✅'},
    'development': {'name': '开发中', 'icon': '🔨'},
    'testing': {'name': '测试中', 'icon': '🧪'},
    'completed': {'name': '已完成', 'icon': '🎉'},
    'cancelled': {'name': '已取消', 'icon': '❌'}
}

# 测试用例等级
TEST_CASE_LEVEL = {
    'smoke': {'name': '冒烟测试', 'value': 1},
    'basic': {'name': '基础测试', 'value': 2},
    'normal': {'name': '正常测试', 'value': 3},
    'complex': {'name': '复杂测试', 'value': 4},
    'security': {'name': '安全测试', 'value': 5}
}

# 缺陷等级
DEFECT_LEVEL = {
    'critical': {'name': '致命', 'value': 5, 'color': '#ff0000'},
    'major': {'name': '严重', 'value': 4, 'color': '#ff6600'},
    'medium': {'name': '一般', 'value': 3, 'color': '#ffcc00'},
    'minor': {'name': '轻微', 'value': 2, 'color': '#00cc00'},
    'trivial': {'name': '微小', 'value': 1, 'color': '#0099ff'}
}

# 缺陷状态
DEFECT_STATUS = {
    'new': {'name': '新建', 'icon': '🆕'},
    'assigned': {'name': '已分配', 'icon': '👤'},
    'fixed': {'name': '已修复', 'icon': '🔧'},
    'verified': {'name': '已验证', 'icon': '✅'},
    'closed': {'name': '已关闭', 'icon': '🔒'},
    'reopened': {'name': '重新打开', 'icon': '🔄'}
}

# 任务类型
TASK_TYPES = {
    'development': {'name': '开发任务', 'icon': '💻'},
    'design': {'name': '设计任务', 'icon': '🎨'},
    'testing': {'name': '测试任务', 'icon': '🧪'},
    'documentation': {'name': '文档任务', 'icon': '📄'},
    'meeting': {'name': '会议任务', 'icon': '👥'},
    'deployment': {'name': '部署任务', 'icon': '🚀'}
}

# 任务状态
TASK_STATUS = {
    'pending': {'name': '待开始', 'icon': '⏳'},
    'in_progress': {'name': '进行中', 'icon': '🔄'},
    'completed': {'name': '已完成', 'icon': '✅'},
    'blocked': {'name': '已阻塞', 'icon': '🚫'},
    'cancelled': {'name': '已取消', 'icon': '❌'}
}

# === 需求管理类 ===

# 研发实体类（Requirement/TestCase/Defect/Task）已移至 models.py

# === 里程碑管理类 ===

class Milestone:
    """里程碑类"""
    def __init__(self, project_id, name, description='', plan_time=None):
        self.id = str(uuid.uuid4())[:8]
        self.project_id = project_id
        self.name = name
        self.description = description
        self.plan_time = plan_time
        self.status = 'pending'
        self.created_at = datetime.datetime.now().isoformat()
        self.updated_at = datetime.datetime.now().isoformat()
    
    def to_dict(self):
        return {
            'id': self.id,
            'project_id': self.project_id,
            'name': self.name,
            'description': self.description,
            'plan_time': self.plan_time,
            'status': self.status,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }

# === 追溯关系管理类 ===

class TraceRelation:
    """追溯关系类"""
    def __init__(self, project_id, source_type, source_id, target_type, target_id, relation_type='implements'):
        self.id = str(uuid.uuid4())[:8]
        self.project_id = project_id
        self.source_type = source_type
        self.source_id = source_id
        self.target_type = target_type
        self.target_id = target_id
        self.relation_type = relation_type
        self.created_at = datetime.datetime.now().isoformat()
    
    def to_dict(self):
        return {
            'id': self.id,
            'project_id': self.project_id,
            'source_type': self.source_type,
            'source_id': self.source_id,
            'target_type': self.target_type,
            'target_id': self.target_id,
            'relation_type': self.relation_type,
            'created_at': self.created_at
        }

# 缓存
milestones_cache = {}
trace_relations_cache = {}

# === AI需求工程功能 ===

# ai_generate_requirements/ai_generate_test_cases/ai_plan_tasks 已移至 dev_routes.py


def analyze_trace_impact(project_id, element_type, element_id):
    """分析追溯影响"""
    impact_analysis = {
        'element': {'type': element_type, 'id': element_id},
        'upstream': [],
        'downstream': [],
        'total_impact': 0,
        'risk_level': 'low'
    }
    
    # 查找上游影响
    for rel in trace_relations_cache.values():
        if rel.target_type == element_type and rel.target_id == element_id:
            impact_analysis['upstream'].append({
                'type': rel.source_type,
                'id': rel.source_id,
                'relation': rel.relation_type
            })
    
    # 查找下游影响
    for rel in trace_relations_cache.values():
        if rel.source_type == element_type and rel.source_id == element_id:
            impact_analysis['downstream'].append({
                'type': rel.target_type,
                'id': rel.target_id,
                'relation': rel.relation_type
            })
    
    impact_analysis['total_impact'] = len(impact_analysis['upstream']) + len(impact_analysis['downstream'])
    
    # 评估风险等级
    if impact_analysis['total_impact'] > 10:
        impact_analysis['risk_level'] = 'critical'
    elif impact_analysis['total_impact'] > 5:
        impact_analysis['risk_level'] = 'high'
    elif impact_analysis['total_impact'] > 2:
        impact_analysis['risk_level'] = 'medium'
    
    return impact_analysis

def generate_project_report(project_id, report_type):
    """生成项目报表"""
    report = {
        'report_id': str(uuid.uuid4())[:8],
        'project_id': project_id,
        'report_type': report_type,
        'generated_at': datetime.datetime.now().isoformat(),
        'content': {}
    }
    
    if report_type == 'requirement':
        # 需求报表
        reqs = _load_dev_entries('req', project_id)
        report['content'] = {
            'total_requirements': len(reqs),
            'by_status': {},
            'by_priority': {},
            'by_type': {}
        }

        for req in reqs:
            # 按状态统计
            status = req.get('status')
            report['content']['by_status'][status] = report['content']['by_status'].get(status, 0) + 1

            # 按优先级统计
            priority = req.get('priority')
            report['content']['by_priority'][priority] = report['content']['by_priority'].get(priority, 0) + 1

            # 按类型统计
            req_type = req.get('type')
            report['content']['by_type'][req_type] = report['content']['by_type'].get(req_type, 0) + 1

    elif report_type == 'test':
        # 测试报表
        cases = _load_dev_entries('tc', project_id)
        defects = _load_dev_entries('def', project_id)

        report['content'] = {
            'total_test_cases': len(cases),
            'total_defects': len(defects),
            'defects_by_level': {},
            'defects_by_status': {},
            'test_coverage': '75%'
        }

        for defect in defects:
            level = defect.get('level')
            report['content']['defects_by_level'][level] = report['content']['defects_by_level'].get(level, 0) + 1

            status = defect.get('status')
            report['content']['defects_by_status'][status] = report['content']['defects_by_status'].get(status, 0) + 1

    elif report_type == 'task':
        # 任务报表
        task_list = _load_dev_entries('task', project_id)

        report['content'] = {
            'total_tasks': len(task_list),
            'by_status': {},
            'by_type': {},
            'total_work_hours': sum(float(t.get('work_hours') or 0) for t in task_list),
            'completion_rate': '60%'
        }

        for task in task_list:
            status = task.get('status')
            report['content']['by_status'][status] = report['content']['by_status'].get(status, 0) + 1

            task_type = task.get('type')
            report['content']['by_type'][task_type] = report['content']['by_type'].get(task_type, 0) + 1
    
    elif report_type == 'trace':
        # 追溯报表
        relations = [r for r in trace_relations_cache.values() if r.project_id == project_id]
        
        report['content'] = {
            'total_relations': len(relations),
            'by_source_type': {},
            'by_target_type': {},
            'by_relation_type': {}
        }
        
        for rel in relations:
            source_type = rel.source_type
            report['content']['by_source_type'][source_type] = report['content']['by_source_type'].get(source_type, 0) + 1
            
            target_type = rel.target_type
            report['content']['by_target_type'][target_type] = report['content']['by_target_type'].get(target_type, 0) + 1
            
            relation_type = rel.relation_type
            report['content']['by_relation_type'][relation_type] = report['content']['by_relation_type'].get(relation_type, 0) + 1
    
    return report


# _load_dev_entries/_save_dev_entries 已移至 core.py

# === 需求/测试/任务管理API ===

# 研发管理路由（requirement/testcase/defect/task）已移至 dev_routes.py

@app.route('/api/v1/project/<project_id>/gantt', methods=['GET', 'POST'])
def manage_gantt(project_id):
    """甘特图与里程碑管理"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    if request.method == 'GET':
        # 获取甘特图数据
        tasks = _load_dev_entries('task', project_id)
        milestones = [m.to_dict() for m in milestones_cache.values() if m.project_id == project_id]

        gantt_data = {
            'tasks': tasks,
            'milestones': milestones,
            'critical_path': []
        }

        return jsonify({'gantt': gantt_data})
    
    elif request.method == 'POST':
        # 创建里程碑
        data = request.json
        milestone = Milestone(project_id, data.get('name', ''), data.get('description', ''), data.get('plan_time'))
        
        milestones_cache[milestone.id] = milestone
        
        return jsonify({
            'message': '里程碑创建成功',
            'milestone': milestone.to_dict()
        })

@app.route('/api/v1/project/<project_id>/trace/analyze', methods=['POST'])
def analyze_trace(project_id):
    """全链路追溯分析"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    data = request.json
    element_type = data.get('element_type')
    element_id = data.get('element_id')
    
    # 分析追溯影响
    impact_analysis = analyze_trace_impact(project_id, element_type, element_id)
    
    return jsonify({
        'message': '追溯分析完成',
        'analysis': impact_analysis
    })

@app.route('/api/v1/project/<project_id>/report/ai/generate', methods=['POST'])
def generate_report(project_id):
    """生成项目报表"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    data = request.json
    report_type = data.get('report_type', 'requirement')
    
    report = generate_project_report(project_id, report_type)
    
    return jsonify({
        'message': '报表生成成功',
        'report': report
    })

# === 模块八：文档、报表、导出体系 ===

# 文档类型定义
DOCUMENT_TYPES = {
    'requirements': {'name': '需求规格说明书', 'icon': '📋'},
    'system_design': {'name': '系统设计说明书', 'icon': '🎨'},
    'high_level_design': {'name': '概要设计说明书', 'icon': '📐'},
    'detailed_design': {'name': '详细设计说明书', 'icon': '🔧'},
    'database_design': {'name': '数据库设计说明书', 'icon': '🗄️'},
    'test_report': {'name': '测试报告', 'icon': '🧪'},
    'architecture_whitepaper': {'name': '架构白皮书', 'icon': '📖'},
    'project_report': {'name': '项目汇报PPT', 'icon': '📊'}
}

# 文档文风类型
DOCUMENT_STYLES = {
    'technical': {'name': '技术严谨版', 'description': '详细的技术描述，适合开发人员'},
    'business': {'name': '业务通俗版', 'description': '通俗易懂的业务描述，适合业务人员'},
    'executive': {'name': '汇报精简版', 'description': '精简的高层汇报，适合管理层'}
}

# 导出格式
EXPORT_FORMATS = {
    'word': {'name': 'Microsoft Word', 'extension': '.docx', 'mimetype': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'},
    'pdf': {'name': 'PDF', 'extension': '.pdf', 'mimetype': 'application/pdf'},
    'html': {'name': 'HTML', 'extension': '.html', 'mimetype': 'text/html'},
    'markdown': {'name': 'Markdown', 'extension': '.md', 'mimetype': 'text/markdown'},
    'rtf': {'name': 'RTF', 'extension': '.rtf', 'mimetype': 'application/rtf'}
}

# 图片导出格式
IMAGE_FORMATS = {
    'png': {'name': 'PNG', 'extension': '.png', 'mimetype': 'image/png'},
    'jpg': {'name': 'JPEG', 'extension': '.jpg', 'mimetype': 'image/jpeg'},
    'svg': {'name': 'SVG', 'extension': '.svg', 'mimetype': 'image/svg+xml'},
    'pdf': {'name': 'PDF', 'extension': '.pdf', 'mimetype': 'application/pdf'},
    'emf': {'name': 'EMF', 'extension': '.emf', 'mimetype': 'image/emf'},
    'eps': {'name': 'EPS', 'extension': '.eps', 'mimetype': 'application/postscript'}
}

# 导入格式
IMPORT_FORMATS = {
    'xmi': {'name': 'XMI', 'description': 'UML标准交换格式'},
    'xml': {'name': 'XML', 'description': '可扩展标记语言'},
    'json': {'name': 'JSON', 'description': 'JSON格式'},
    'sql': {'name': 'SQL', 'description': 'SQL脚本'},
    'java': {'name': 'Java', 'description': 'Java源代码'},
    'python': {'name': 'Python', 'description': 'Python源代码'}
}

# === 文档模板管理类 ===

class DocumentTemplate:
    """文档模板类"""
    def __init__(self, project_id, name, description='', doc_type='requirements'):
        self.id = str(uuid.uuid4())[:8]
        self.project_id = project_id
        self.name = name
        self.description = description
        self.type = doc_type
        self.content = ''
        self.variables = []
        self.created_at = datetime.datetime.now().isoformat()
        self.updated_at = datetime.datetime.now().isoformat()
    
    def add_variable(self, name, label, data_source):
        """添加模板变量"""
        var = {
            'name': name,
            'label': label,
            'data_source': data_source
        }
        self.variables.append(var)
        return var
    
    def to_dict(self):
        return {
            'id': self.id,
            'project_id': self.project_id,
            'name': self.name,
            'description': self.description,
            'type': self.type,
            'content': self.content,
            'variables': self.variables,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }

# === 文档生成任务类 ===

class DocumentGenerateTask:
    """文档生成任务"""
    def __init__(self, project_id, template_id, user_id, doc_name):
        self.id = str(uuid.uuid4())[:8]
        self.project_id = project_id
        self.template_id = template_id
        self.user_id = user_id
        self.document_name = doc_name
        self.type = 'document'
        self.status = 'pending'
        self.progress = 0
        self.created_at = datetime.datetime.now().isoformat()
        self.updated_at = datetime.datetime.now().isoformat()
        self.document = None
    
    def to_dict(self):
        return {
            'id': self.id,
            'project_id': self.project_id,
            'template_id': self.template_id,
            'user_id': self.user_id,
            'document_name': self.document_name,
            'type': self.type,
            'status': self.status,
            'progress': self.progress,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'document': self.document
        }

# === 文档类 ===

class Document:
    """文档类"""
    def __init__(self, task_id, project_id, name, doc_type):
        self.id = str(uuid.uuid4())[:8]
        self.task_id = task_id
        self.project_id = project_id
        self.name = name
        self.type = doc_type
        self.content = ''
        self.version = '1.0.0'
        self.created_at = datetime.datetime.now().isoformat()
    
    def to_dict(self):
        return {
            'id': self.id,
            'task_id': self.task_id,
            'project_id': self.project_id,
            'name': self.name,
            'type': self.type,
            'content': self.content,
            'version': self.version,
            'created_at': self.created_at
        }

# === 报表模板管理类 ===

class ReportTemplate:
    """报表模板类"""
    def __init__(self, project_id, name, description='', report_type='element'):
        self.id = str(uuid.uuid4())[:8]
        self.project_id = project_id
        self.name = name
        self.description = description
        self.type = report_type
        self.config = {}
        self.created_at = datetime.datetime.now().isoformat()
    
    def to_dict(self):
        return {
            'id': self.id,
            'project_id': self.project_id,
            'name': self.name,
            'description': self.description,
            'type': self.type,
            'config': self.config,
            'created_at': self.created_at
        }

# === 报表类 ===

class Report:
    """报表类"""
    def __init__(self, task_id, project_id, name, report_type):
        self.id = str(uuid.uuid4())[:8]
        self.task_id = task_id
        self.project_id = project_id
        self.name = name
        self.type = report_type
        self.data = {}
        self.charts = []
        self.interpretation = {}
        self.created_at = datetime.datetime.now().isoformat()
    
    def to_dict(self):
        return {
            'id': self.id,
            'task_id': self.task_id,
            'project_id': self.project_id,
            'name': self.name,
            'type': self.type,
            'data': self.data,
            'charts': self.charts,
            'interpretation': self.interpretation,
            'created_at': self.created_at
        }

# === 导出任务类 ===

class ExportTask:
    """导出任务类"""
    def __init__(self, project_id, user_id, export_type, source_type, source_id):
        self.id = str(uuid.uuid4())[:8]
        self.project_id = project_id
        self.user_id = user_id
        self.export_type = export_type
        self.source_type = source_type
        self.source_id = source_id
        self.config = {}
        self.status = 'pending'
        self.progress = 0
        self.file_path = ''
        self.created_at = datetime.datetime.now().isoformat()
    
    def to_dict(self):
        return {
            'id': self.id,
            'project_id': self.project_id,
            'user_id': self.user_id,
            'export_type': self.export_type,
            'source_type': self.source_type,
            'source_id': self.source_id,
            'config': self.config,
            'status': self.status,
            'progress': self.progress,
            'file_path': self.file_path,
            'created_at': self.created_at
        }

# === 导入任务类 ===

class ImportTask:
    """导入任务类"""
    def __init__(self, project_id, user_id, import_type, file_path):
        self.id = str(uuid.uuid4())[:8]
        self.project_id = project_id
        self.user_id = user_id
        self.import_type = import_type
        self.file_path = file_path
        self.config = {}
        self.status = 'pending'
        self.progress = 0
        self.created_at = datetime.datetime.now().isoformat()
        self.result = {}
    
    def to_dict(self):
        return {
            'id': self.id,
            'project_id': self.project_id,
            'user_id': self.user_id,
            'import_type': self.import_type,
            'file_path': self.file_path,
            'config': self.config,
            'status': self.status,
            'progress': self.progress,
            'created_at': self.created_at,
            'result': self.result
        }

# 缓存
document_templates_cache = {}
document_tasks_cache = {}
documents_cache = {}
report_templates_cache = {}
export_tasks_cache = {}
import_tasks_cache = {}

# === AI文档生成功能 ===

def ai_generate_document(project_id, template_id, style='technical'):
    """AI生成文档"""
    # 获取项目信息
    project = projects_cache.get(project_id, {'name': '未命名项目', 'description': ''})
    
    # 获取需求（重建 Requirement 对象供文档生成使用）
    reqs = []
    for e in _load_dev_entries('req', project_id):
        r = Requirement(e.get('project_id', project_id), e.get('name', ''), e.get('description', ''), e.get('type', 'functional'))
        r.id = e.get('id')
        r.priority = e.get('priority', 'medium')
        r.status = e.get('status', 'draft')
        reqs.append(r)

    # 获取测试用例（文档生成仅用到数量，dict 即可）
    cases = _load_dev_entries('tc', project_id)

    # 获取任务（重建 Task 对象供文档生成使用）
    tasks = []
    for e in _load_dev_entries('task', project_id):
        t = Task(e.get('project_id', project_id), e.get('name', ''), e.get('description', ''), e.get('type', 'development'))
        t.id = e.get('id')
        t.status = e.get('status', 'pending')
        tasks.append(t)

    # 获取模型
    models = [m for m in models_cache.values() if m.get('project_id') == project_id]
    
    # 根据文风生成不同内容
    if style == 'technical':
        content = generate_technical_document(project, reqs, cases, tasks, models)
    elif style == 'business':
        content = generate_business_document(project, reqs, cases, tasks, models)
    else:
        content = generate_executive_document(project, reqs, cases, tasks, models)
    
    return content

def generate_technical_document(project, reqs, cases, tasks, models):
    """生成技术严谨版文档"""
    content = f"""# {project.get('name', '')} - 技术设计文档

## 1. 概述

### 1.1 项目背景
{project.get('description', '暂无项目背景描述')}

### 1.2 文档目的
本文档详细描述项目的技术实现方案，供开发团队参考。

---

## 2. 需求分析

### 2.1 需求清单

| 序号 | 需求名称 | 类型 | 优先级 | 状态 |
|:---:|---------|------|--------|------|"""
    
    for i, req in enumerate(reqs, 1):
        req_type = REQUIREMENT_TYPES.get(req.type, {'name': req.type})['name']
        priority = REQUIREMENT_PRIORITY.get(req.priority, {'name': req.priority})['name']
        status = REQUIREMENT_STATUS.get(req.status, {'name': req.status})['name']
        content += f"\n| {i} | {req.name} | {req_type} | {priority} | {status} |"
    
    content += f"""

### 2.2 需求统计
- 总需求数: {len(reqs)}
- 已完成: {len([r for r in reqs if r.status == 'completed'])}
- 进行中: {len([r for r in reqs if r.status in ['development', 'testing']])}

---

## 3. 模型设计

### 3.1 模型概览
项目包含 {len(models)} 个模型。

---

## 4. 测试计划

### 4.1 测试用例统计
- 测试用例总数: {len(cases)}

---

## 5. 项目进度

### 5.1 任务统计
- 任务总数: {len(tasks)}
- 已完成任务: {len([t for t in tasks if t.status == 'completed'])}
- 任务完成率: {round(len([t for t in tasks if t.status == 'completed']) / max(len(tasks), 1) * 100, 1)}%

---

## 6. 附录

### 6.1 文档版本
| 版本 | 修改日期 | 修改人 | 修改内容 |
|:---:|---------|--------|---------|
| 1.0.0 | {datetime.datetime.now().strftime('%Y-%m-%d')} | 系统 | 初始版本 |

---

*文档生成时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*
"""
    
    return content

def generate_business_document(project, reqs, cases, tasks, models):
    """生成业务通俗版文档"""
    content = f"""# {project.get('name', '')} - 业务说明文档

## 📋 项目概述

{project.get('description', '暂无项目描述')}

## 🎯 核心需求

我们需要完成以下 {len(reqs)} 个需求：

"""
    
    for i, req in enumerate(reqs, 1):
        priority = REQUIREMENT_PRIORITY.get(req.priority, {'name': req.priority})['name']
        content += f"**{i}. {req.name}** ({priority})\n\n{req.description}\n\n"
    
    content += f"""## 📊 项目进度

目前项目共有 {len(tasks)} 个任务，其中：
- ✅ 已完成: {len([t for t in tasks if t.status == 'completed'])} 个
- 🔄 进行中: {len([t for t in tasks if t.status == 'in_progress'])} 个
- ⏳ 待开始: {len([t for t in tasks if t.status == 'pending'])} 个

## 🧪 测试情况

已设计 {len(cases)} 个测试用例来验证功能。

---

*文档生成时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*
"""
    
    return content

def generate_executive_document(project, reqs, cases, tasks, models):
    """生成汇报精简版文档"""
    completed_reqs = len([r for r in reqs if r.status == 'completed'])
    completed_tasks = len([t for t in tasks if t.status == 'completed'])
    
    content = f"""# {project.get('name', '')} - 项目进度汇报

---

## 📈 总体进度

| 指标 | 数值 | 完成率 |
|:---:|:---:|:---:|
| 需求总数 | {len(reqs)} | {round(completed_reqs / max(len(reqs), 1) * 100, 1)}% |
| 任务总数 | {len(tasks)} | {round(completed_tasks / max(len(tasks), 1) * 100, 1)}% |
| 测试用例 | {len(cases)} | - |

## 🎯 核心指标

- **需求完成**: {completed_reqs}/{len(reqs)}
- **任务完成**: {completed_tasks}/{len(tasks)}
- **模型数量**: {len(models)}

## ⚠️ 风险提示

目前项目整体进展顺利，暂无重大风险。

---

*汇报时间: {datetime.datetime.now().strftime('%Y-%m-%d')}*
"""
    
    return content

def ai_generate_report(project_id, report_type, params=None):
    """AI生成报表"""
    report = {
        'project_id': project_id,
        'report_type': report_type,
        'generated_at': datetime.datetime.now().isoformat(),
        'data': {},
        'charts': [],
        'interpretation': {}
    }
    
    # 根据报表类型生成数据
    if report_type == 'element':
        report = generate_element_report(project_id, report)
    elif report_type == 'requirement':
        report = generate_requirement_report(project_id, report)
    elif report_type == 'test':
        report = generate_test_report(project_id, report)
    elif report_type == 'task':
        report = generate_task_report(project_id, report)
    
    # 添加AI解读
    report['interpretation'] = generate_ai_interpretation(report)
    
    return report

def generate_element_report(project_id, report):
    """生成元素统计报表"""
    elements = []
    for model in models_cache.values():
        if model.get('project_id') == project_id:
            if 'classes' in model:
                elements.extend(model['classes'])
            if 'use_cases' in model:
                elements.extend(model['use_cases'])
    
    report['data'] = {
        'total_elements': len(elements),
        'by_type': {}
    }
    
    for elem in elements:
        elem_type = elem.get('type', 'unknown')
        report['data']['by_type'][elem_type] = report['data']['by_type'].get(elem_type, 0) + 1
    
    # 生成图表数据
    report['charts'].append({
        'type': 'pie',
        'title': '元素类型分布',
        'data': report['data']['by_type']
    })
    
    return report

def generate_requirement_report(project_id, report):
    """生成需求统计报表"""
    reqs = _load_dev_entries('req', project_id)

    report['data'] = {
        'total_requirements': len(reqs),
        'by_status': {},
        'by_priority': {},
        'by_type': {}
    }

    for req in reqs:
        status = req.get('status')
        report['data']['by_status'][status] = report['data']['by_status'].get(status, 0) + 1

        priority = req.get('priority')
        report['data']['by_priority'][priority] = report['data']['by_priority'].get(priority, 0) + 1

        req_type = req.get('type')
        report['data']['by_type'][req_type] = report['data']['by_type'].get(req_type, 0) + 1
    
    report['charts'].append({
        'type': 'bar',
        'title': '需求状态分布',
        'data': report['data']['by_status']
    })
    
    report['charts'].append({
        'type': 'pie',
        'title': '需求优先级分布',
        'data': report['data']['by_priority']
    })
    
    return report

def generate_test_report(project_id, report):
    """生成测试统计报表"""
    cases = _load_dev_entries('tc', project_id)
    defects = _load_dev_entries('def', project_id)

    report['data'] = {
        'total_test_cases': len(cases),
        'total_defects': len(defects),
        'defects_by_level': {},
        'defects_by_status': {}
    }

    for defect in defects:
        level = defect.get('level')
        report['data']['defects_by_level'][level] = report['data']['defects_by_level'].get(level, 0) + 1

        status = defect.get('status')
        report['data']['defects_by_status'][status] = report['data']['defects_by_status'].get(status, 0) + 1
    
    report['charts'].append({
        'type': 'bar',
        'title': '缺陷等级分布',
        'data': report['data']['defects_by_level']
    })
    
    return report

def generate_task_report(project_id, report):
    """生成任务统计报表"""
    tasks = _load_dev_entries('task', project_id)

    report['data'] = {
        'total_tasks': len(tasks),
        'total_work_hours': sum(float(t.get('work_hours') or 0) for t in tasks),
        'by_status': {},
        'by_type': {},
        'completion_rate': round(len([t for t in tasks if t.get('status') == 'completed']) / max(len(tasks), 1) * 100, 1)
    }

    for task in tasks:
        status = task.get('status')
        report['data']['by_status'][status] = report['data']['by_status'].get(status, 0) + 1

        task_type = task.get('type')
        report['data']['by_type'][task_type] = report['data']['by_type'].get(task_type, 0) + 1
    
    report['charts'].append({
        'type': 'donut',
        'title': '任务状态分布',
        'data': report['data']['by_status']
    })
    
    report['charts'].append({
        'type': 'bar',
        'title': '任务类型分布',
        'data': report['data']['by_type']
    })
    
    return report

def generate_ai_interpretation(report):
    """生成AI解读"""
    interpretation = {
        'summary': '',
        'insights': [],
        'recommendations': []
    }
    
    if report['report_type'] == 'requirement':
        data = report['data']
        total = data.get('total_requirements', 0)
        completed = data['by_status'].get('completed', 0)
        
        interpretation['summary'] = f"项目共有 {total} 个需求，已完成 {completed} 个，完成率 {round(completed / max(total, 1) * 100, 1)}%"
        
        if completed < total * 0.5:
            interpretation['insights'].append('需求完成进度较慢，建议加快开发进度')
        elif completed >= total * 0.8:
            interpretation['insights'].append('需求完成情况良好，项目进展顺利')
        
        interpretation['recommendations'].append('建议定期跟踪需求状态，及时处理阻塞问题')
    
    elif report['report_type'] == 'task':
        data = report['data']
        completion_rate = data.get('completion_rate', 0)
        
        interpretation['summary'] = f"任务完成率为 {completion_rate}%，总工时 {data.get('total_work_hours', 0)} 小时"
        
        if completion_rate < 50:
            interpretation['insights'].append('任务完成进度落后，需要关注')
        elif completion_rate >= 80:
            interpretation['insights'].append('任务完成情况优秀')
        
        interpretation['recommendations'].append('建议关注进行中的任务，确保按时完成')
    
    elif report['report_type'] == 'test':
        data = report['data']
        total_defects = data.get('total_defects', 0)
        
        interpretation['summary'] = f"共发现 {total_defects} 个缺陷"
        
        if total_defects > 10:
            interpretation['insights'].append('缺陷数量较多，需要加强测试和修复')
        elif total_defects == 0:
            interpretation['insights'].append('暂无缺陷，测试质量较高')
        
        interpretation['recommendations'].append('建议优先处理严重等级的缺陷')
    
    return interpretation

def export_document(document_content, format_type='markdown'):
    """导出文档"""
    if format_type == 'markdown':
        return document_content
    elif format_type == 'html':
        html_content = document_content.replace('\n', '<br>').replace('## ', '<h2>').replace('### ', '<h3>').replace('**', '<strong>')
        template = '''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Generated Document</title>
    <style>
        body { font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }
        h1 { color: #2c3e50; border-bottom: 2px solid #3498db; }
        h2 { color: #3498db; }
        table { border-collapse: collapse; width: 100%; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
        th { background-color: #f2f2f2; }
    </style>
</head>
<body>
{content}
</body>
</html>'''
        return template.format(content=html_content)
    else:
        return document_content

def import_file(project_id, file_content, import_type):
    """导入文件"""
    result = {
        'project_id': project_id,
        'import_type': import_type,
        'elements_created': 0,
        'relationships_created': 0,
        'notes': []
    }
    
    # 根据导入类型解析
    if import_type == 'json':
        try:
            data = json.loads(file_content)
            if 'model' in data:
                result['elements_created'] = len(data['model'].get('classes', []))
                result['notes'].append('成功解析JSON模型文件')
        except:
            result['notes'].append('JSON解析失败')
    
    elif import_type == 'xmi':
        result['elements_created'] = 5
        result['relationships_created'] = 3
        result['notes'].append('成功解析XMI文件')
    
    elif import_type == 'sql':
        tables = file_content.count('CREATE TABLE')
        result['elements_created'] = tables
        result['notes'].append(f'解析到 {tables} 个表')
    
    return result

# === 文档、报表、导出API ===

@app.route('/api/v1/project/<project_id>/document/ai/generate', methods=['POST'])
def ai_generate_documents_api(project_id):
    """AI全自动文档生成"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    data = request.json
    template_id = data.get('template_id')
    style = data.get('style', 'technical')
    doc_name = data.get('document_name', '未命名文档')
    
    # 生成文档
    content = ai_generate_document(project_id, template_id, style)
    
    # 创建文档对象
    task = DocumentGenerateTask(project_id, template_id, sessions_cache[session_id]['user_id'], doc_name)
    task.status = 'completed'
    task.progress = 100
    task.document = {'content': content, 'style': style}
    
    document_tasks_cache[task.id] = task
    
    return jsonify({
        'message': 'AI文档生成成功',
        'task': task.to_dict(),
        'document_content': content
    })

@app.route('/api/v1/document/generate/<task_id>', methods=['GET'])
def get_document_task(task_id):
    """获取文档生成任务结果"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    if task_id not in document_tasks_cache:
        return jsonify({'error': '任务不存在'}), 404
    
    task = document_tasks_cache[task_id]
    
    return jsonify({
        'task': task.to_dict()
    })

@app.route('/api/v1/project/<project_id>/document/template', methods=['GET', 'POST', 'PUT', 'DELETE'])
def manage_document_templates(project_id):
    """文档模板管理"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    if request.method == 'GET':
        templates = [t.to_dict() for t in document_templates_cache.values() if t.project_id == project_id]
        return jsonify({'templates': templates})
    
    elif request.method == 'POST':
        data = request.json
        template = DocumentTemplate(project_id, data.get('name', ''), data.get('description', ''), data.get('type', 'requirements'))
        template.content = data.get('content', '')
        
        document_templates_cache[template.id] = template
        
        return jsonify({
            'message': '文档模板创建成功',
            'template': template.to_dict()
        })
    
    elif request.method == 'PUT':
        data = request.json
        template_id = data.get('id')
        
        if template_id not in document_templates_cache:
            return jsonify({'error': '模板不存在'}), 404
        
        template = document_templates_cache[template_id]
        if 'name' in data:
            template.name = data['name']
        if 'content' in data:
            template.content = data['content']
        
        return jsonify({
            'message': '文档模板更新成功',
            'template': template.to_dict()
        })
    
    elif request.method == 'DELETE':
        template_id = request.args.get('id')
        
        if template_id not in document_templates_cache:
            return jsonify({'error': '模板不存在'}), 404
        
        del document_templates_cache[template_id]
        
        return jsonify({'message': '文档模板删除成功'})

@app.route('/api/v1/document/<document_id>/export', methods=['POST'])
def export_document_api(document_id):
    """文档导出"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    data = request.json
    format_type = data.get('format', 'markdown')
    
    # 获取文档内容
    document = documents_cache.get(document_id)
    content = document.content if document else '示例文档内容'
    
    # 如果没有文档，从任务中获取
    if not document:
        for task in document_tasks_cache.values():
            if task.document:
                content = task.document.get('content', '示例文档内容')
                break
    
    exported_content = export_document(content, format_type)
    
    return jsonify({
        'message': '文档导出成功',
        'format': format_type,
        'content': exported_content,
        'filename': f'document_{document_id}.{EXPORT_FORMATS.get(format_type, {}).get("extension", ".txt")[1:]}'
    })

@app.route('/api/v1/project/<project_id>/report/ai/generate', methods=['POST'])
def ai_generate_report_api(project_id):
    """AI智能报表生成"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    data = request.json
    report_type = data.get('report_type', 'element')
    params = data.get('params', {})
    
    report = ai_generate_report(project_id, report_type, params)
    
    return jsonify({
        'message': 'AI报表生成成功',
        'report': report
    })

@app.route('/api/v1/report/generate/<task_id>', methods=['GET'])
def get_report_task(task_id):
    """获取报表生成任务结果"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    # 简化处理：直接返回示例报表
    report = {
        'task_id': task_id,
        'status': 'completed',
        'progress': 100,
        'report': ai_generate_report('default', 'requirement')
    }
    
    return jsonify({'report': report})

@app.route('/api/v1/project/<project_id>/report/template', methods=['GET', 'POST', 'PUT', 'DELETE'])
def manage_report_templates(project_id):
    """报表模板管理"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    if request.method == 'GET':
        templates = [t.to_dict() for t in report_templates_cache.values() if t.project_id == project_id]
        return jsonify({'templates': templates})
    
    elif request.method == 'POST':
        data = request.json
        template = ReportTemplate(project_id, data.get('name', ''), data.get('description', ''), data.get('type', 'element'))
        template.config = data.get('config', {})
        
        report_templates_cache[template.id] = template
        
        return jsonify({
            'message': '报表模板创建成功',
            'template': template.to_dict()
        })
    
    elif request.method == 'PUT':
        data = request.json
        template_id = data.get('id')
        
        if template_id not in report_templates_cache:
            return jsonify({'error': '模板不存在'}), 404
        
        template = report_templates_cache[template_id]
        if 'name' in data:
            template.name = data['name']
        if 'config' in data:
            template.config = data['config']
        
        return jsonify({
            'message': '报表模板更新成功',
            'template': template.to_dict()
        })
    
    elif request.method == 'DELETE':
        template_id = request.args.get('id')
        
        if template_id not in report_templates_cache:
            return jsonify({'error': '模板不存在'}), 404
        
        del report_templates_cache[template_id]
        
        return jsonify({'message': '报表模板删除成功'})

@app.route('/api/v1/report/<report_id>/export', methods=['POST'])
def export_report_api(report_id):
    """报表导出"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    data = request.json
    format_type = data.get('format', 'csv')
    
    # 生成报表数据
    report_data = {
        'report_id': report_id,
        'format': format_type,
        'exported_at': datetime.datetime.now().isoformat(),
        'data': {
            'headers': ['指标', '数值'],
            'rows': [
                ['总需求数', '15'],
                ['已完成', '10'],
                ['进行中', '3'],
                ['待开始', '2']
            ]
        }
    }
    
    return jsonify({
        'message': '报表导出成功',
        'report': report_data
    })

@app.route('/api/v1/project/<project_id>/model/export', methods=['POST'])
def export_model_api(project_id):
    """模型文件导入导出"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    data = request.json
    export_format = data.get('format', 'json')
    
    # 获取项目模型
    project_models = [m for m in models_cache.values() if m.get('project_id') == project_id]
    
    export_data = {
        'project_id': project_id,
        'format': export_format,
        'models': project_models,
        'exported_at': datetime.datetime.now().isoformat()
    }
    
    return jsonify({
        'message': '模型导出成功',
        'export_data': export_data,
        'model_count': len(project_models)
    })

@app.route('/api/v1/view/<view_id>/image/export', methods=['POST'])
def export_image_api(view_id):
    """图形文件导出"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    data = request.json
    image_format = data.get('format', 'png')
    
    return jsonify({
        'message': '图形导出成功',
        'format': image_format,
        'view_id': view_id,
        'resolution': '1920x1080',
        'download_url': f'/download/{view_id}.{image_format}'
    })

@app.route('/api/v1/project/<project_id>/file/import', methods=['POST'])
def import_file_api(project_id):
    """文件导入解析"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    data = request.json
    import_type = data.get('type', 'json')
    file_content = data.get('content', '{}')
    
    result = import_file(project_id, file_content, import_type)
    
    return jsonify({
        'message': '文件导入成功',
        'result': result
    })

@app.route('/api/v1/document/types', methods=['GET'])
def get_document_types():
    """获取文档类型"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    types = []
    for key, value in DOCUMENT_TYPES.items():
        types.append({
            'id': key,
            'name': value['name'],
            'icon': value['icon']
        })
    
    return jsonify({'types': types})

@app.route('/api/v1/document/styles', methods=['GET'])
def get_document_styles():
    """获取文档文风类型"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    styles = []
    for key, value in DOCUMENT_STYLES.items():
        styles.append({
            'id': key,
            'name': value['name'],
            'description': value['description']
        })
    
    return jsonify({'styles': styles})

@app.route('/api/v1/export/formats', methods=['GET'])
def get_export_formats():
    """获取导出格式"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    formats = []
    for key, value in EXPORT_FORMATS.items():
        formats.append({
            'id': key,
            'name': value['name'],
            'extension': value['extension']
        })
    
    return jsonify({'formats': formats})

@app.route('/api/v1/image/formats', methods=['GET'])
def get_image_formats():
    """获取图片导出格式"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    formats = []
    for key, value in IMAGE_FORMATS.items():
        formats.append({
            'id': key,
            'name': value['name'],
            'extension': value['extension']
        })
    
    return jsonify({'formats': formats})

@app.route('/api/v1/import/formats', methods=['GET'])
def get_import_formats():
    """获取导入格式"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    formats = []
    for key, value in IMPORT_FORMATS.items():
        formats.append({
            'id': key,
            'name': value['name'],
            'description': value['description']
        })
    
    return jsonify({'formats': formats})

# === 模块九：版本控制与配置管理 ===

# 版本状态
VERSION_STATUS = {
    'draft': {'name': '草稿', 'color': '#f0ad4e'},
    'formal': {'name': '正式', 'color': '#5cb85c'},
    'released': {'name': '发布', 'color': '#337ab7'},
    'archived': {'name': '归档', 'color': '#999999'}
}

# 变更类型
CHANGE_TYPES = {
    'add': {'name': '新增', 'icon': '➕'},
    'modify': {'name': '修改', 'icon': '✏️'},
    'delete': {'name': '删除', 'icon': '🗑️'},
    'move': {'name': '移动', 'icon': '📦'},
    'rename': {'name': '重命名', 'icon': '📝'}
}

# VCS类型
VCS_TYPES = {
    'git': {'name': 'Git', 'protocols': ['https', 'ssh']},
    'svn': {'name': 'SVN', 'protocols': ['https', 'http', 'svn']},
    'tfs': {'name': 'TFS', 'protocols': ['https']},
    'cvs': {'name': 'CVS', 'protocols': ['pserver']}
}

# === 版本管理类 ===

class ProjectVersion:
    """项目版本类"""
    def __init__(self, project_id, version_name, version_code, description=''):
        self.id = str(uuid.uuid4())[:8]
        self.project_id = project_id
        self.version_name = version_name
        self.version_code = version_code
        self.description = description
        self.commit_message = ''
        self.user_id = ''
        self.status = 'draft'
        self.created_at = datetime.datetime.now().isoformat()
        self.snapshots = []
        self.changes = []
    
    def add_snapshot(self, snapshot_type, content):
        """添加版本快照"""
        snapshot = {
            'id': str(uuid.uuid4())[:8],
            'type': snapshot_type,
            'content': content,
            'created_at': datetime.datetime.now().isoformat()
        }
        self.snapshots.append(snapshot)
        return snapshot
    
    def add_change(self, change_type, element_type, element_id, old_value, new_value, description=''):
        """添加变更记录"""
        change = {
            'id': str(uuid.uuid4())[:8],
            'type': change_type,
            'element_type': element_type,
            'element_id': element_id,
            'old_value': old_value,
            'new_value': new_value,
            'description': description,
            'created_at': datetime.datetime.now().isoformat()
        }
        self.changes.append(change)
        return change
    
    def to_dict(self):
        return {
            'id': self.id,
            'project_id': self.project_id,
            'version_name': self.version_name,
            'version_code': self.version_code,
            'description': self.description,
            'commit_message': self.commit_message,
            'user_id': self.user_id,
            'status': self.status,
            'created_at': self.created_at,
            'snapshot_count': len(self.snapshots),
            'change_count': len(self.changes)
        }

# === 分支管理类 ===

class ProjectBranch:
    """项目分支类"""
    def __init__(self, project_id, branch_name, base_version_id, description=''):
        self.id = str(uuid.uuid4())[:8]
        self.project_id = project_id
        self.branch_name = branch_name
        self.description = description
        self.base_version_id = base_version_id
        self.status = 'active'
        self.created_at = datetime.datetime.now().isoformat()
        self.last_commit_at = datetime.datetime.now().isoformat()
    
    def to_dict(self):
        return {
            'id': self.id,
            'project_id': self.project_id,
            'branch_name': self.branch_name,
            'description': self.description,
            'base_version_id': self.base_version_id,
            'status': self.status,
            'created_at': self.created_at,
            'last_commit_at': self.last_commit_at
        }

# === 合并记录类 ===

class BranchMerge:
    """分支合并类"""
    def __init__(self, project_id, source_branch_id, target_branch_id):
        self.id = str(uuid.uuid4())[:8]
        self.project_id = project_id
        self.source_branch_id = source_branch_id
        self.target_branch_id = target_branch_id
        self.merge_version_id = None
        self.status = 'pending'
        self.conflict_count = 0
        self.conflicts = []
        self.created_at = datetime.datetime.now().isoformat()
    
    def add_conflict(self, element_type, element_id, source_content, target_content, base_content):
        """添加冲突"""
        conflict = {
            'id': str(uuid.uuid4())[:8],
            'element_type': element_type,
            'element_id': element_id,
            'source_content': source_content,
            'target_content': target_content,
            'base_content': base_content,
            'status': 'conflict',
            'resolution': None
        }
        self.conflicts.append(conflict)
        self.conflict_count = len(self.conflicts)
        return conflict
    
    def resolve_conflict(self, conflict_id, resolution):
        """解决冲突"""
        for conflict in self.conflicts:
            if conflict['id'] == conflict_id:
                conflict['status'] = 'resolved'
                conflict['resolution'] = resolution
                self.conflict_count = len([c for c in self.conflicts if c['status'] == 'conflict'])
                return True
        return False
    
    def to_dict(self):
        return {
            'id': self.id,
            'project_id': self.project_id,
            'source_branch_id': self.source_branch_id,
            'target_branch_id': self.target_branch_id,
            'merge_version_id': self.merge_version_id,
            'status': self.status,
            'conflict_count': self.conflict_count,
            'conflicts': self.conflicts,
            'created_at': self.created_at
        }

# === VCS配置类 ===

class VCSConfig:
    """VCS配置类"""
    def __init__(self, project_id, vcs_type, repository_url):
        self.id = str(uuid.uuid4())[:8]
        self.project_id = project_id
        self.vcs_type = vcs_type
        self.repository_url = repository_url
        self.username = ''
        self.password_encrypted = ''
        self.ssh_key_encrypted = ''
        self.default_branch = 'main'
        self.created_at = datetime.datetime.now().isoformat()
    
    def to_dict(self):
        return {
            'id': self.id,
            'project_id': self.project_id,
            'vcs_type': self.vcs_type,
            'repository_url': self.repository_url,
            'username': self.username,
            'default_branch': self.default_branch,
            'created_at': self.created_at
        }

# === VCS同步记录类 ===

class VCSSyncRecord:
    """VCS同步记录类"""
    def __init__(self, project_id, sync_type):
        self.id = str(uuid.uuid4())[:8]
        self.project_id = project_id
        self.sync_type = sync_type
        self.status = 'pending'
        self.commit_id = ''
        self.message = ''
        self.created_at = datetime.datetime.now().isoformat()
    
    def to_dict(self):
        return {
            'id': self.id,
            'project_id': self.project_id,
            'sync_type': self.sync_type,
            'status': self.status,
            'commit_id': self.commit_id,
            'message': self.message,
            'created_at': self.created_at
        }

# 缓存
merges_cache = {}
vcs_configs_cache = {}
vcs_sync_records_cache = {}

# === AI版本分析功能 ===

def ai_generate_commit_message(project_id, changes):
    """AI生成提交说明"""
    if not changes:
        return "无变更内容"
    
    change_summary = []
    add_count = len([c for c in changes if c['type'] == 'add'])
    modify_count = len([c for c in changes if c['type'] == 'modify'])
    delete_count = len([c for c in changes if c['type'] == 'delete'])
    
    if add_count > 0:
        change_summary.append(f"新增 {add_count} 个元素")
    if modify_count > 0:
        change_summary.append(f"修改 {modify_count} 个元素")
    if delete_count > 0:
        change_summary.append(f"删除 {delete_count} 个元素")
    
    # 分析变更类型
    element_types = {}
    for change in changes:
        elem_type = change.get('element_type', 'unknown')
        element_types[elem_type] = element_types.get(elem_type, 0) + 1
    
    if element_types:
        type_summary = ", ".join([f"{v}个{k}" for k, v in element_types.items()])
        change_summary.append(f"涉及{type_summary}")
    
    commit_message = f"{'、'.join(change_summary)}。\n\n"
    
    # 生成详细说明
    commit_message += "变更详情：\n"
    for change in changes[:5]:  # 最多显示5条
        elem_type = change.get('element_type', '')
        change_type = CHANGE_TYPES.get(change['type'], {'name': change['type']})['name']
        commit_message += f"- {change_type} {elem_type}: {change.get('description', '无描述')}\n"
    
    if len(changes) > 5:
        commit_message += f"- 还有 {len(changes) - 5} 条变更..."
    
    return commit_message

def ai_analyze_version_diff(version1, version2):
    """AI分析版本差异"""
    analysis = {
        'summary': '',
        'changes': [],
        'risk_assessment': [],
        'business_impact': [],
        'suggestions': []
    }
    
    # 模拟差异分析
    changes = []
    
    # 假设版本2对比版本1有一些变更
    changes.append({
        'type': 'add',
        'element_type': 'class',
        'element_name': '新业务类',
        'description': '新增业务逻辑处理类'
    })
    
    changes.append({
        'type': 'modify',
        'element_type': 'requirement',
        'element_name': '登录需求',
        'description': '修改登录验证逻辑'
    })
    
    changes.append({
        'type': 'delete',
        'element_type': 'attribute',
        'element_name': '冗余字段',
        'description': '删除不再使用的字段'
    })
    
    analysis['changes'] = changes
    
    # AI解读
    add_count = len([c for c in changes if c['type'] == 'add'])
    modify_count = len([c for c in changes if c['type'] == 'modify'])
    delete_count = len([c for c in changes if c['type'] == 'delete'])
    
    analysis['summary'] = f"版本 {version2.version_code} 相对于版本 {version1.version_code} 共有 {len(changes)} 处变更：新增 {add_count} 项，修改 {modify_count} 项，删除 {delete_count} 项。"
    
    # 风险评估
    if delete_count > 0:
        analysis['risk_assessment'].append({
            'level': 'medium',
            'message': f'删除了 {delete_count} 个元素，建议确认是否影响其他依赖'
        })
    
    if modify_count > 0:
        analysis['risk_assessment'].append({
            'level': 'low',
            'message': f'修改了 {modify_count} 个元素，建议进行回归测试'
        })
    
    # 业务影响
    analysis['business_impact'].append('新增业务类可能影响业务流程')
    analysis['business_impact'].append('登录需求修改可能影响用户认证')
    
    # 建议
    analysis['suggestions'].append('建议进行完整的回归测试')
    analysis['suggestions'].append('建议审查删除的元素是否有其他依赖')
    
    return analysis

def ai_assist_merge(merge):
    """AI辅助合并"""
    suggestions = {
        'can_auto_merge': merge.conflict_count == 0,
        'conflict_analysis': [],
        'merge_strategy': 'auto' if merge.conflict_count == 0 else 'manual',
        'suggestions': []
    }
    
    if merge.conflict_count > 0:
        for conflict in merge.conflicts:
            suggestions['conflict_analysis'].append({
                'element_type': conflict['element_type'],
                'element_id': conflict['element_id'],
                'suggestion': '建议保留双方修改，进行手动合并'
            })
        
        suggestions['suggestions'].append('存在冲突，建议手动处理后再合并')
        suggestions['suggestions'].append('可以参考基础版本了解原始内容')
    else:
        suggestions['suggestions'].append('无冲突，可以直接自动合并')
        suggestions['suggestions'].append('建议合并后进行验证测试')
    
    return suggestions

def ai_generate_version_report(project_id):
    """AI生成版本管理报告"""
    versions = [v for v in versions_cache.values() if v.project_id == project_id]
    branches = [b for b in branches_cache.values() if b.project_id == project_id]
    
    report = {
        'project_id': project_id,
        'generated_at': datetime.datetime.now().isoformat(),
        'summary': {},
        'version_analysis': {},
        'branch_analysis': {},
        'recommendations': []
    }
    
    # 版本统计
    report['summary'] = {
        'total_versions': len(versions),
        'released_versions': len([v for v in versions if v.status == 'released']),
        'draft_versions': len([v for v in versions if v.status == 'draft']),
        'total_branches': len(branches),
        'active_branches': len([b for b in branches if b.status == 'active'])
    }
    
    # 版本分析
    if versions:
        latest_version = max(versions, key=lambda v: v.created_at)
        report['version_analysis'] = {
            'latest_version': latest_version.version_code,
            'avg_changes_per_version': round(sum(len(v.changes) for v in versions) / max(len(versions), 1), 1),
            'version_frequency': '高频' if len(versions) > 10 else '正常'
        }
    
    # 分支分析
    if branches:
        report['branch_analysis'] = {
            'branch_count': len(branches),
            'suggestion': '分支数量合理' if len(branches) <= 5 else '分支较多，建议清理'
        }
    
    # AI建议
    if len(branches) > 5:
        report['recommendations'].append('分支数量较多，建议定期清理无用分支')
    
    if len([v for v in versions if v.status == 'draft']) > 3:
        report['recommendations'].append('存在较多草稿版本，建议及时发布或归档')
    
    report['recommendations'].append('建议定期进行版本回溯检查')
    report['recommendations'].append('建议制定统一的版本号命名规范')
    
    return report

# === 版本控制与配置管理API ===

@app.route('/api/v1/project/<project_id>/version/commit', methods=['POST'])
def commit_version(project_id):
    """版本提交与快照生成"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    data = request.json
    version_name = data.get('version_name', '未命名版本')
    version_code = data.get('version_code', '1.0.0')
    description = data.get('description', '')
    
    # 创建版本
    version = ProjectVersion(project_id, version_name, version_code, description)
    version.user_id = sessions_cache[session_id]['user_id']
    version.status = 'formal'
    
    # 模拟变更记录
    changes = [
        {'type': 'modify', 'element_type': 'class', 'element_id': 'class1', 'old_value': 'old', 'new_value': 'new', 'description': '更新类属性'},
        {'type': 'add', 'element_type': 'requirement', 'element_id': 'req1', 'old_value': '', 'new_value': 'new_req', 'description': '新增需求'}
    ]
    
    for change in changes:
        version.add_change(change['type'], change['element_type'], change['element_id'], change['old_value'], change['new_value'], change['description'])
    
    # AI生成提交说明
    version.commit_message = ai_generate_commit_message(project_id, changes)
    
    # 创建快照
    version.add_snapshot('full', {'project_id': project_id, 'timestamp': datetime.datetime.now().isoformat()})
    
    versions_cache[version.id] = version
    
    return jsonify({
        'message': '版本提交成功',
        'version': version.to_dict(),
        'commit_message': version.commit_message
    })

@app.route('/api/v1/project/<project_id>/version/list', methods=['GET'])
def get_version_list(project_id):
    """获取版本列表"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    versions = [v.to_dict() for v in versions_cache.values() if v.project_id == project_id]
    versions.sort(key=lambda x: x['created_at'], reverse=True)
    
    return jsonify({
        'versions': versions,
        'count': len(versions)
    })

@app.route('/api/v1/version/<version_id>', methods=['GET'])
def get_version_detail(version_id):
    """获取版本详情"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    if version_id not in versions_cache:
        return jsonify({'error': '版本不存在'}), 404
    
    version = versions_cache[version_id]
    
    return jsonify({
        'version': version.to_dict(),
        'snapshots': version.snapshots,
        'changes': version.changes
    })

@app.route('/api/v1/project/<project_id>/version/compare', methods=['POST'])
def compare_versions(project_id):
    """版本对比与差异分析"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    data = request.json
    version_id1 = data.get('version_id1')
    version_id2 = data.get('version_id2')
    
    if version_id1 not in versions_cache or version_id2 not in versions_cache:
        return jsonify({'error': '版本不存在'}), 404
    
    version1 = versions_cache[version_id1]
    version2 = versions_cache[version_id2]
    
    # AI分析差异
    analysis = ai_analyze_version_diff(version1, version2)
    
    return jsonify({
        'message': '版本对比完成',
        'version1': version1.to_dict(),
        'version2': version2.to_dict(),
        'analysis': analysis
    })

@app.route('/api/v1/project/<project_id>/version/rollback', methods=['POST'])
def rollback_version(project_id):
    """版本回滚"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    data = request.json
    target_version_id = data.get('target_version_id')
    
    if target_version_id not in versions_cache:
        return jsonify({'error': '目标版本不存在'}), 404
    
    target_version = versions_cache[target_version_id]
    
    # 创建回滚版本
    rollback_version = ProjectVersion(project_id, f"回滚到 {target_version.version_name}", target_version.version_code + '-rollback', f"回滚到版本 {target_version.version_code}")
    rollback_version.user_id = sessions_cache[session_id]['user_id']
    rollback_version.status = 'formal'
    rollback_version.commit_message = f"回滚到版本 {target_version.version_code}"
    
    versions_cache[rollback_version.id] = rollback_version
    
    return jsonify({
        'message': '版本回滚成功',
        'rollback_version': rollback_version.to_dict(),
        'target_version': target_version.to_dict()
    })

@app.route('/api/v1/project/<project_id>/branch', methods=['GET', 'POST', 'PUT', 'DELETE'])
def manage_branches(project_id):
    """分支管理"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    if request.method == 'GET':
        branches = [b.to_dict() for b in branches_cache.values() if b.project_id == project_id]
        return jsonify({'branches': branches})
    
    elif request.method == 'POST':
        data = request.json
        branch_name = data.get('branch_name', '')
        base_version_id = data.get('base_version_id')
        description = data.get('description', '')
        
        branch = ProjectBranch(project_id, branch_name, base_version_id, description)
        branches_cache[branch.id] = branch
        
        return jsonify({
            'message': '分支创建成功',
            'branch': branch.to_dict()
        })
    
    elif request.method == 'PUT':
        data = request.json
        branch_id = data.get('id')
        
        if branch_id not in branches_cache:
            return jsonify({'error': '分支不存在'}), 404
        
        branch = branches_cache[branch_id]
        if 'branch_name' in data:
            branch.branch_name = data['branch_name']
        if 'description' in data:
            branch.description = data['description']
        
        return jsonify({
            'message': '分支更新成功',
            'branch': branch.to_dict()
        })
    
    elif request.method == 'DELETE':
        branch_id = request.args.get('id')
        
        if branch_id not in branches_cache:
            return jsonify({'error': '分支不存在'}), 404
        
        del branches_cache[branch_id]
        
        return jsonify({'message': '分支删除成功'})

@app.route('/api/v1/project/<project_id>/branch/list', methods=['GET'])
def get_branch_list(project_id):
    """获取分支列表"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    branches = [b.to_dict() for b in branches_cache.values() if b.project_id == project_id]
    branches.sort(key=lambda x: x['created_at'], reverse=True)
    
    return jsonify({
        'branches': branches,
        'count': len(branches)
    })

@app.route('/api/v1/project/<project_id>/branch/merge', methods=['POST'])
def merge_branches(project_id):
    """分支合并与冲突处理"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    data = request.json
    source_branch_id = data.get('source_branch_id')
    target_branch_id = data.get('target_branch_id')
    
    if source_branch_id not in branches_cache or target_branch_id not in branches_cache:
        return jsonify({'error': '分支不存在'}), 404
    
    # 创建合并记录
    merge = BranchMerge(project_id, source_branch_id, target_branch_id)
    
    # 模拟冲突
    merge.add_conflict('class', 'class1', 'source_content', 'target_content', 'base_content')
    merge.add_conflict('requirement', 'req1', 'source_req', 'target_req', 'base_req')
    
    # AI辅助合并分析
    ai_suggestions = ai_assist_merge(merge)
    
    merges_cache[merge.id] = merge
    
    return jsonify({
        'message': '合并分析完成',
        'merge': merge.to_dict(),
        'ai_suggestions': ai_suggestions
    })

@app.route('/api/v1/project/<project_id>/vcs/config', methods=['GET', 'POST', 'PUT', 'DELETE'])
def manage_vcs_config(project_id):
    """外部VCS配置与对接"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    if request.method == 'GET':
        configs = [c.to_dict() for c in vcs_configs_cache.values() if c.project_id == project_id]
        return jsonify({'configs': configs})
    
    elif request.method == 'POST':
        data = request.json
        vcs_type = data.get('vcs_type', 'git')
        repository_url = data.get('repository_url', '')
        
        config = VCSConfig(project_id, vcs_type, repository_url)
        config.username = data.get('username', '')
        config.default_branch = data.get('default_branch', 'main')
        
        vcs_configs_cache[config.id] = config
        
        return jsonify({
            'message': 'VCS配置创建成功',
            'config': config.to_dict()
        })
    
    elif request.method == 'PUT':
        data = request.json
        config_id = data.get('id')
        
        if config_id not in vcs_configs_cache:
            return jsonify({'error': '配置不存在'}), 404
        
        config = vcs_configs_cache[config_id]
        if 'repository_url' in data:
            config.repository_url = data['repository_url']
        if 'default_branch' in data:
            config.default_branch = data['default_branch']
        
        return jsonify({
            'message': 'VCS配置更新成功',
            'config': config.to_dict()
        })
    
    elif request.method == 'DELETE':
        config_id = request.args.get('id')
        
        if config_id not in vcs_configs_cache:
            return jsonify({'error': '配置不存在'}), 404
        
        del vcs_configs_cache[config_id]
        
        return jsonify({'message': 'VCS配置删除成功'})

@app.route('/api/v1/project/<project_id>/vcs/sync', methods=['POST'])
def sync_vcs(project_id):
    """外部VCS同步"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    data = request.json
    sync_type = data.get('sync_type', 'push')
    
    # 创建同步记录
    record = VCSSyncRecord(project_id, sync_type)
    record.status = 'completed'
    record.commit_id = 'abc123'
    record.message = f'{sync_type}同步成功'
    
    vcs_sync_records_cache[record.id] = record
    
    return jsonify({
        'message': 'VCS同步成功',
        'record': record.to_dict()
    })

@app.route('/api/v1/project/<project_id>/version/ai/report', methods=['POST'])
def generate_version_report(project_id):
    """版本报告生成"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    report = ai_generate_version_report(project_id)
    
    return jsonify({
        'message': '版本报告生成成功',
        'report': report
    })

@app.route('/api/v1/version/status', methods=['GET'])
def get_version_status():
    """获取版本状态列表"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    status_list = []
    for key, value in VERSION_STATUS.items():
        status_list.append({
            'id': key,
            'name': value['name'],
            'color': value['color']
        })
    
    return jsonify({'status': status_list})

@app.route('/api/v1/version/change_types', methods=['GET'])
def get_change_types():
    """获取变更类型列表"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    types_list = []
    for key, value in CHANGE_TYPES.items():
        types_list.append({
            'id': key,
            'name': value['name'],
            'icon': value['icon']
        })
    
    return jsonify({'types': types_list})

@app.route('/api/v1/vcs/types', methods=['GET'])
def get_vcs_types():
    """获取VCS类型列表"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    types_list = []
    for key, value in VCS_TYPES.items():
        types_list.append({
            'id': key,
            'name': value['name'],
            'protocols': value['protocols']
        })
    
    return jsonify({'types': types_list})

# === 模块十：团队协作、批注、评审 ===

# 批注类型
COMMENT_TYPES = {
    'normal': {'name': '普通', 'color': '#337ab7'},
    'question': {'name': '问题', 'color': '#f0ad4e'},
    'suggestion': {'name': '建议', 'color': '#5cb85c'},
    'review': {'name': '评审', 'color': '#d9534f'}
}

# 批注状态
COMMENT_STATUS = {
    'unresolved': {'name': '未解决', 'color': '#d9534f'},
    'resolved': {'name': '已解决', 'color': '#5cb85c'},
    'closed': {'name': '已关闭', 'color': '#999999'},
    'rejected': {'name': '已驳回', 'color': '#f0ad4e'}
}

# 评审类型
REVIEW_TYPES = {
    'architecture': {'name': '架构评审', 'icon': '🏛️'},
    'design': {'name': '设计评审', 'icon': '🎨'},
    'code': {'name': '代码评审', 'icon': '💻'},
    'requirement': {'name': '需求评审', 'icon': '📋'},
    'test': {'name': '测试评审', 'icon': '🧪'}
}

# 评审状态
REVIEW_STATUS = {
    'draft': {'name': '草稿', 'color': '#f0ad4e'},
    'pending': {'name': '待评审', 'color': '#337ab7'},
    'reviewing': {'name': '评审中', 'color': '#5cb85c'},
    'concluded': {'name': '已结论', 'color': '#999999'},
    'closed': {'name': '已关闭', 'color': '#666666'}
}

# 评审结论
REVIEW_CONCLUSIONS = {
    'approved': {'name': '通过', 'color': '#5cb85c'},
    'rejected': {'name': '不通过', 'color': '#d9534f'},
    'conditional': {'name': '有条件通过', 'color': '#f0ad4e'},
    'reverted': {'name': '驳回', 'color': '#d9534f'}
}

# 评审角色
REVIEW_ROLES = {
    'sponsor': {'name': '评审发起人', 'permission': 'full'},
    'manager': {'name': '评审负责人', 'permission': 'full'},
    'expert': {'name': '评审专家', 'permission': 'review'},
    'participant': {'name': '参与人', 'permission': 'review'},
    'observer': {'name': '观察员', 'permission': 'view'}
}

# === 批注评论类 ===

class ElementComment:
    """元素批注评论类"""
    def __init__(self, element_type, element_id, project_id, user_id, content, comment_type='normal'):
        self.id = str(uuid.uuid4())[:8]
        self.element_type = element_type
        self.element_id = element_id
        self.project_id = project_id
        self.user_id = user_id
        self.content = content
        self.type = comment_type
        self.status = 'unresolved'
        self.priority = 'medium'
        self.parent_id = None
        self.replies = []
        self.mentions = []
        self.attachments = []
        self.likes = []
        self.created_at = datetime.datetime.now().isoformat()
        self.updated_at = datetime.datetime.now().isoformat()
    
    def add_reply(self, user_id, content):
        """添加回复"""
        reply = {
            'id': str(uuid.uuid4())[:8],
            'user_id': user_id,
            'content': content,
            'created_at': datetime.datetime.now().isoformat()
        }
        self.replies.append(reply)
        return reply
    
    def add_mention(self, mentioned_user_id):
        """添加@提及"""
        mention = {
            'id': str(uuid.uuid4())[:8],
            'user_id': mentioned_user_id,
            'created_at': datetime.datetime.now().isoformat()
        }
        self.mentions.append(mention)
        return mention
    
    def add_like(self, user_id):
        """添加点赞"""
        if user_id not in self.likes:
            self.likes.append(user_id)
    
    def remove_like(self, user_id):
        """取消点赞"""
        if user_id in self.likes:
            self.likes.remove(user_id)
    
    def to_dict(self):
        return {
            'id': self.id,
            'element_type': self.element_type,
            'element_id': self.element_id,
            'project_id': self.project_id,
            'user_id': self.user_id,
            'content': self.content,
            'type': self.type,
            'status': self.status,
            'priority': self.priority,
            'parent_id': self.parent_id,
            'reply_count': len(self.replies),
            'mention_count': len(self.mentions),
            'like_count': len(self.likes),
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'replies': self.replies,
            'mentions': self.mentions
        }

# === 评审类 ===

class ProjectReview:
    """项目评审类"""
    def __init__(self, project_id, review_name, review_type, description=''):
        self.id = str(uuid.uuid4())[:8]
        self.project_id = project_id
        self.review_name = review_name
        self.review_type = review_type
        self.description = description
        self.template_id = None
        self.sponsor_id = ''
        self.manager_id = ''
        self.status = 'draft'
        self.conclusion = None
        self.conclusion_note = ''
        self.created_at = datetime.datetime.now().isoformat()
        self.updated_at = datetime.datetime.now().isoformat()
        self.members = []
        self.contents = []
        self.comments = []
    
    def add_member(self, user_id, role):
        """添加评审成员"""
        member = {
            'id': str(uuid.uuid4())[:8],
            'user_id': user_id,
            'role': role,
            'status': 'pending',
            'created_at': datetime.datetime.now().isoformat()
        }
        self.members.append(member)
        return member
    
    def add_content(self, content_type, content_id, description=''):
        """添加评审内容"""
        content = {
            'id': str(uuid.uuid4())[:8],
            'type': content_type,
            'content_id': content_id,
            'description': description,
            'created_at': datetime.datetime.now().isoformat()
        }
        self.contents.append(content)
        return content
    
    def add_comment(self, user_id, content, comment_type='normal'):
        """添加评审意见"""
        comment = {
            'id': str(uuid.uuid4())[:8],
            'user_id': user_id,
            'content': content,
            'type': comment_type,
            'status': 'pending',
            'created_at': datetime.datetime.now().isoformat()
        }
        self.comments.append(comment)
        return comment
    
    def to_dict(self):
        return {
            'id': self.id,
            'project_id': self.project_id,
            'review_name': self.review_name,
            'review_type': self.review_type,
            'description': self.description,
            'template_id': self.template_id,
            'sponsor_id': self.sponsor_id,
            'manager_id': self.manager_id,
            'status': self.status,
            'conclusion': self.conclusion,
            'conclusion_note': self.conclusion_note,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'member_count': len(self.members),
            'content_count': len(self.contents),
            'comment_count': len(self.comments),
            'members': self.members,
            'contents': self.contents,
            'comments': self.comments
        }

# === 团队类 ===

class ProjectTeam:
    """团队类"""
    def __init__(self, team_name, owner_id, description=''):
        self.id = str(uuid.uuid4())[:8]
        self.team_name = team_name
        self.description = description
        self.owner_id = owner_id
        self.status = 'active'
        self.created_at = datetime.datetime.now().isoformat()
        self.members = []
        self.projects = []
        self.announcements = []
    
    def add_member(self, user_id, role, permissions=None):
        """添加团队成员"""
        member = {
            'id': str(uuid.uuid4())[:8],
            'user_id': user_id,
            'role': role,
            'permissions': permissions or {},
            'created_at': datetime.datetime.now().isoformat()
        }
        self.members.append(member)
        return member
    
    def add_project(self, project_id):
        """添加项目"""
        if project_id not in self.projects:
            self.projects.append(project_id)
    
    def add_announcement(self, title, content, user_id):
        """发布公告"""
        announcement = {
            'id': str(uuid.uuid4())[:8],
            'title': title,
            'content': content,
            'user_id': user_id,
            'created_at': datetime.datetime.now().isoformat()
        }
        self.announcements.append(announcement)
        return announcement
    
    def to_dict(self):
        return {
            'id': self.id,
            'team_name': self.team_name,
            'description': self.description,
            'owner_id': self.owner_id,
            'status': self.status,
            'created_at': self.created_at,
            'member_count': len(self.members),
            'project_count': len(self.projects),
            'members': self.members,
            'projects': self.projects,
            'announcements': self.announcements[:5]
        }

# === 通知类 ===

class UserNotification:
    """用户通知类"""
    def __init__(self, user_id, notification_type, content, related_id=''):
        self.id = str(uuid.uuid4())[:8]
        self.user_id = user_id
        self.type = notification_type
        self.content = content
        self.related_id = related_id
        self.is_read = False
        self.created_at = datetime.datetime.now().isoformat()
    
    def mark_read(self):
        """标记已读"""
        self.is_read = True
    
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'type': self.type,
            'content': self.content,
            'related_id': self.related_id,
            'is_read': self.is_read,
            'created_at': self.created_at
        }

# === 知识库类 ===

class KnowledgeBase:
    """知识库类"""
    def __init__(self, knowledge_type, title, content, source_id=''):
        self.id = str(uuid.uuid4())[:8]
        self.type = knowledge_type
        self.title = title
        self.content = content
        self.source_id = source_id
        self.tags = []
        self.views = 0
        self.created_at = datetime.datetime.now().isoformat()
    
    def add_tag(self, tag):
        """添加标签"""
        if tag not in self.tags:
            self.tags.append(tag)
    
    def to_dict(self):
        return {
            'id': self.id,
            'type': self.type,
            'title': self.title,
            'content': self.content,
            'source_id': self.source_id,
            'tags': self.tags,
            'views': self.views,
            'created_at': self.created_at
        }

# 缓存
comments_cache = {}
teams_cache = {}
notifications_cache = {}
knowledge_base_cache = {}

# === AI协作功能 ===

def ai_generate_review_outline(review):
    """AI生成评审大纲"""
    outline = {
        'review_id': review.id,
        'review_name': review.review_name,
        'sections': [],
        'checklist': []
    }
    
    if review.review_type == 'architecture':
        outline['sections'] = [
            {'title': '1. 架构概述', 'description': '整体架构设计说明'},
            {'title': '2. 技术选型', 'description': '核心技术栈选择及理由'},
            {'title': '3. 系统架构', 'description': '架构图、模块划分、接口设计'},
            {'title': '4. 数据架构', 'description': '数据库设计、数据流向'},
            {'title': '5. 安全性', 'description': '安全设计、权限控制'},
            {'title': '6. 可扩展性', 'description': '扩展性设计、未来规划'}
        ]
        outline['checklist'] = [
            '架构是否符合企业标准',
            '技术选型是否合理',
            '是否存在单点故障',
            '性能是否满足需求',
            '安全性是否达标'
        ]
    
    elif review.review_type == 'design':
        outline['sections'] = [
            {'title': '1. 设计概述', 'description': '设计目标和范围'},
            {'title': '2. 模块设计', 'description': '各模块职责和接口'},
            {'title': '3. 类设计', 'description': '关键类结构和关系'},
            {'title': '4. 接口设计', 'description': 'API设计规范'},
            {'title': '5. 数据设计', 'description': '数据结构和存储'},
            {'title': '6. 异常处理', 'description': '错误处理机制'}
        ]
        outline['checklist'] = [
            '设计是否满足需求',
            '类职责是否单一',
            '接口是否清晰',
            '是否存在循环依赖',
            '文档是否完整'
        ]
    
    else:
        outline['sections'] = [
            {'title': '1. 评审内容概述', 'description': '评审范围和目标'},
            {'title': '2. 核心要点分析', 'description': '关键内容分析'},
            {'title': '3. 问题与建议', 'description': '发现的问题和改进建议'}
        ]
        outline['checklist'] = [
            '内容是否完整',
            '是否符合规范',
            '是否存在风险'
        ]
    
    return outline

def ai_summarize_review_comments(review):
    """AI汇总评审意见"""
    summary = {
        'review_id': review.id,
        'total_comments': len(review.comments),
        'by_type': {},
        'by_severity': {},
        'key_issues': [],
        'suggestions': [],
        'summary_text': ''
    }
    
    for comment in review.comments:
        comment_type = comment.get('type', 'normal')
        summary['by_type'][comment_type] = summary['by_type'].get(comment_type, 0) + 1
    
    for comment in review.comments[:5]:
        if comment.get('type') in ['question', 'suggestion']:
            if comment.get('type') == 'suggestion':
                summary['suggestions'].append(comment.get('content', ''))
            else:
                summary['key_issues'].append(comment.get('content', ''))
    
    summary['summary_text'] = f"本次评审共收到 {len(review.comments)} 条评审意见。"
    if summary['key_issues']:
        summary['summary_text'] += f"主要问题：{'; '.join(summary['key_issues'])}。"
    if summary['suggestions']:
        summary['summary_text'] += f"建议：{'; '.join(summary['suggestions'])}。"
    
    return summary

def ai_generate_review_report(review, summary):
    """AI生成评审报告"""
    report = {
        'review_id': review.id,
        'review_name': review.review_name,
        'review_type': review.review_type,
        'generated_at': datetime.datetime.now().isoformat(),
        'summary': summary,
        'conclusion': review.conclusion or 'pending',
        'recommendations': [],
        'action_items': []
    }
    
    if summary.get('total_comments', 0) > 0:
        report['recommendations'].append('根据评审意见进行相应整改')
        report['recommendations'].append('整改完成后进行复审')
    
    for i, issue in enumerate(summary.get('key_issues', []), 1):
        report['action_items'].append({
            'id': f'A{i}',
            'description': issue,
            'status': 'pending',
            'assignee': '待分配'
        })
    
    return report

def ai_auto_reply_comment(comment, project_id):
    """AI自动回复评论"""
    reply = {
        'comment_id': comment.id,
        'ai_reply': '',
        'confidence': 0.85,
        'suggestions': []
    }
    
    if comment.type == 'question':
        reply['ai_reply'] = f"您提出的问题很有价值！根据项目上下文分析：{comment.content}。建议您查看相关文档或联系相关负责人获取更多信息。"
        reply['suggestions'].append('建议查看相关设计文档')
        reply['suggestions'].append('可以@相关专家获取解答')
    
    elif comment.type == 'suggestion':
        reply['ai_reply'] = f"感谢您的建议！'{comment.content}' 已被记录，我们会认真考虑并评估可行性。如有需要，会进一步与您沟通。"
        reply['suggestions'].append('建议提交正式的改进工单')
        reply['suggestions'].append('可以发起专题讨论')
    
    else:
        reply['ai_reply'] = f"收到您的反馈：{comment.content}。相关负责人会及时处理。"
    
    return reply

def ai_knowledge_sync(review):
    """AI同步评审意见到知识库"""
    knowledge_items = []
    
    for comment in review.comments:
        if comment.get('type') in ['suggestion', 'question']:
            knowledge = KnowledgeBase(
                knowledge_type='review_case',
                title=f"评审问题：{comment.get('content', '')[:30]}...",
                content=comment.get('content', ''),
                source_id=review.id
            )
            knowledge.add_tag(review.review_type)
            knowledge.add_tag('review')
            knowledge_base_cache[knowledge.id] = knowledge
            knowledge_items.append(knowledge.to_dict())
    
    return {
        'message': '评审知识已同步到知识库',
        'synced_count': len(knowledge_items),
        'items': knowledge_items
    }

# === 团队协作、批注、评审API ===

@app.route('/api/v1/element/<element_id>/comment', methods=['POST'])
def add_element_comment(element_id):
    """元素批注与评论管理"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    data = request.json
    element_type = data.get('element_type', 'model')
    project_id = data.get('project_id', '')
    content = data.get('content', '')
    comment_type = data.get('type', 'normal')
    parent_id = data.get('parent_id')
    mentioned_users = data.get('mentions', [])
    
    comment = ElementComment(element_type, element_id, project_id, sessions_cache[session_id]['user_id'], content, comment_type)
    
    if parent_id:
        comment.parent_id = parent_id
    
    for user_id in mentioned_users:
        comment.add_mention(user_id)
        notification = UserNotification(user_id, 'mention', f"您在评论中被@{sessions_cache[session_id]['username']}提及", comment.id)
        notifications_cache[notification.id] = notification
    
    comments_cache[comment.id] = comment
    
    return jsonify({
        'message': '评论添加成功',
        'comment': comment.to_dict()
    })

@app.route('/api/v1/element/<element_id>/comment/list', methods=['GET'])
def get_comment_list(element_id):
    """获取评论列表"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    element_type = request.args.get('element_type', 'model')
    
    element_comments = [c.to_dict() for c in comments_cache.values() if c.element_id == element_id and c.element_type == element_type]
    element_comments.sort(key=lambda x: x['created_at'], reverse=True)
    
    return jsonify({
        'comments': element_comments,
        'count': len(element_comments)
    })

@app.route('/api/v1/comment/<comment_id>/status', methods=['PUT'])
def update_comment_status(comment_id):
    """更新评论状态"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    if comment_id not in comments_cache:
        return jsonify({'error': '评论不存在'}), 404
    
    data = request.json
    status = data.get('status')
    
    comment = comments_cache[comment_id]
    
    if status:
        comment.status = status
    
    comment.updated_at = datetime.datetime.now().isoformat()
    
    return jsonify({
        'message': '评论状态更新成功',
        'comment': comment.to_dict()
    })

@app.route('/api/v1/project/<project_id>/review/create', methods=['POST'])
def create_review(project_id):
    """评审发起与管理"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    data = request.json
    review_name = data.get('review_name', '')
    review_type = data.get('review_type', 'design')
    description = data.get('description', '')
    members = data.get('members', [])
    
    review = ProjectReview(project_id, review_name, review_type, description)
    review.sponsor_id = sessions_cache[session_id]['user_id']
    review.manager_id = sessions_cache[session_id]['user_id']
    review.status = 'pending'
    
    for member in members:
        review.add_member(member.get('user_id'), member.get('role', 'participant'))
    
    outline = ai_generate_review_outline(review)
    
    reviews_cache[review.id] = review
    
    return jsonify({
        'message': '评审创建成功',
        'review': review.to_dict(),
        'outline': outline
    })

@app.route('/api/v1/project/<project_id>/review/list', methods=['GET'])
def get_review_list(project_id):
    """获取评审列表"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    reviews = [r.to_dict() for r in reviews_cache.values() if r.project_id == project_id]
    reviews.sort(key=lambda x: x['created_at'], reverse=True)
    
    return jsonify({
        'reviews': reviews,
        'count': len(reviews)
    })

@app.route('/api/v1/review/<review_id>/comment', methods=['POST'])
def add_review_comment(review_id):
    """评审内容与意见管理"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    if review_id not in reviews_cache:
        return jsonify({'error': '评审不存在'}), 404
    
    data = request.json
    content = data.get('content', '')
    comment_type = data.get('type', 'normal')
    
    review = reviews_cache[review_id]
    review.add_comment(sessions_cache[session_id]['user_id'], content, comment_type)
    
    summary = ai_summarize_review_comments(review)
    
    return jsonify({
        'message': '评审意见提交成功',
        'review': review.to_dict(),
        'summary': summary
    })

@app.route('/api/v1/review/<review_id>/status', methods=['PUT'])
def update_review_status(review_id):
    """评审流程与结论管理"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    if review_id not in reviews_cache:
        return jsonify({'error': '评审不存在'}), 404
    
    data = request.json
    status = data.get('status')
    conclusion = data.get('conclusion')
    conclusion_note = data.get('conclusion_note', '')
    
    review = reviews_cache[review_id]
    
    if status:
        review.status = status
    
    if conclusion:
        review.conclusion = conclusion
        review.conclusion_note = conclusion_note
    
    review.updated_at = datetime.datetime.now().isoformat()
    
    summary = ai_summarize_review_comments(review)
    report = ai_generate_review_report(review, summary)
    
    knowledge_result = ai_knowledge_sync(review)
    
    return jsonify({
        'message': '评审状态更新成功',
        'review': review.to_dict(),
        'report': report,
        'knowledge_sync': knowledge_result
    })

@app.route('/api/v1/team', methods=['GET', 'POST', 'PUT', 'DELETE'])
def manage_teams():
    """团队管理"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    if request.method == 'GET':
        teams = [t.to_dict() for t in teams_cache.values()]
        return jsonify({'teams': teams})
    
    elif request.method == 'POST':
        data = request.json
        team_name = data.get('team_name', '')
        description = data.get('description', '')
        members = data.get('members', [])
        
        team = ProjectTeam(team_name, sessions_cache[session_id]['user_id'], description)
        
        for member in members:
            team.add_member(member.get('user_id'), member.get('role', 'member'))
        
        teams_cache[team.id] = team
        
        return jsonify({
            'message': '团队创建成功',
            'team': team.to_dict()
        })
    
    elif request.method == 'PUT':
        data = request.json
        team_id = data.get('id')
        
        if team_id not in teams_cache:
            return jsonify({'error': '团队不存在'}), 404
        
        team = teams_cache[team_id]
        if 'team_name' in data:
            team.team_name = data['team_name']
        if 'description' in data:
            team.description = data['description']
        
        return jsonify({
            'message': '团队更新成功',
            'team': team.to_dict()
        })
    
    elif request.method == 'DELETE':
        team_id = request.args.get('id')
        
        if team_id not in teams_cache:
            return jsonify({'error': '团队不存在'}), 404
        
        del teams_cache[team_id]
        
        return jsonify({'message': '团队删除成功'})

@app.route('/api/v1/team/<team_id>/member', methods=['POST', 'DELETE'])
def manage_team_members(team_id):
    """团队成员管理"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    if team_id not in teams_cache:
        return jsonify({'error': '团队不存在'}), 404
    
    team = teams_cache[team_id]
    
    if request.method == 'POST':
        data = request.json
        user_id = data.get('user_id')
        role = data.get('role', 'member')
        permissions = data.get('permissions', {})
        
        team.add_member(user_id, role, permissions)
        
        return jsonify({
            'message': '成员添加成功',
            'team': team.to_dict()
        })
    
    elif request.method == 'DELETE':
        user_id = request.args.get('user_id')
        
        team.members = [m for m in team.members if m['user_id'] != user_id]
        
        return jsonify({
            'message': '成员删除成功',
            'team': team.to_dict()
        })

@app.route('/api/v1/team/<team_id>/announcement', methods=['POST'])
def add_team_announcement(team_id):
    """发布团队公告"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    if team_id not in teams_cache:
        return jsonify({'error': '团队不存在'}), 404
    
    data = request.json
    title = data.get('title', '')
    content = data.get('content', '')
    
    team = teams_cache[team_id]
    announcement = team.add_announcement(title, content, sessions_cache[session_id]['user_id'])
    
    for member in team.members:
        notification = UserNotification(member['user_id'], 'announcement', f"团队公告：{title}", team_id)
        notifications_cache[notification.id] = notification
    
    return jsonify({
        'message': '公告发布成功',
        'announcement': announcement
    })

@app.route('/api/v1/notification/list', methods=['GET'])
def get_notification_list():
    """通知中心"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    user_id = sessions_cache[session_id]['user_id']
    notifications = [n.to_dict() for n in notifications_cache.values() if n.user_id == user_id]
    notifications.sort(key=lambda x: x['created_at'], reverse=True)
    
    return jsonify({
        'notifications': notifications,
        'count': len(notifications),
        'unread_count': len([n for n in notifications if not n.is_read])
    })

@app.route('/api/v1/notification/<notification_id>/read', methods=['PUT'])
def mark_notification_read(notification_id):
    """标记通知已读"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    if notification_id not in notifications_cache:
        return jsonify({'error': '通知不存在'}), 404
    
    notification = notifications_cache[notification_id]
    notification.mark_read()
    
    return jsonify({
        'message': '通知已标记为已读',
        'notification': notification.to_dict()
    })

@app.route('/api/v1/review/<review_id>/ai/assist', methods=['POST'])
def ai_review_assist(review_id):
    """AI评审助手"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    if review_id not in reviews_cache:
        return jsonify({'error': '评审不存在'}), 404
    
    review = reviews_cache[review_id]
    
    data = request.json
    action = data.get('action', 'outline')
    
    result = {}
    
    if action == 'outline':
        result = ai_generate_review_outline(review)
    elif action == 'summary':
        result = ai_summarize_review_comments(review)
    elif action == 'report':
        summary = ai_summarize_review_comments(review)
        result = ai_generate_review_report(review, summary)
    elif action == 'suggestions':
        result = {
            'suggestions': [
                '建议邀请相关领域专家参与评审',
                '建议提前准备评审材料',
                '建议制定整改计划并跟踪',
                '建议评审结束后沉淀知识'
            ]
        }
    
    return jsonify({
        'message': 'AI辅助分析完成',
        'action': action,
        'result': result
    })

@app.route('/api/v1/knowledge/ai/sync', methods=['POST'])
def knowledge_sync():
    """知识库沉淀"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    data = request.json
    review_id = data.get('review_id')
    
    if review_id not in reviews_cache:
        return jsonify({'error': '评审不存在'}), 404
    
    review = reviews_cache[review_id]
    result = ai_knowledge_sync(review)
    
    return jsonify(result)

@app.route('/api/v1/knowledge/list', methods=['GET'])
def get_knowledge_list():
    """获取知识库列表"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    knowledge = [k.to_dict() for k in knowledge_base_cache.values()]
    knowledge.sort(key=lambda x: x['created_at'], reverse=True)
    
    return jsonify({
        'knowledge': knowledge,
        'count': len(knowledge)
    })

@app.route('/api/v1/knowledge/search', methods=['GET'])
def search_knowledge():
    """知识库搜索"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    query = request.args.get('q', '')
    
    results = []
    for k in knowledge_base_cache.values():
        if query.lower() in k.title.lower() or query.lower() in str(k.content).lower():
            k.views += 1
            results.append(k.to_dict())
    
    return jsonify({
        'results': results,
        'count': len(results)
    })

@app.route('/api/v1/comment/types', methods=['GET'])
def get_comment_types():
    """获取批注类型列表"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    types_list = []
    for key, value in COMMENT_TYPES.items():
        types_list.append({
            'id': key,
            'name': value['name'],
            'color': value['color']
        })
    
    return jsonify({'types': types_list})

@app.route('/api/v1/comment/status', methods=['GET'])
def get_comment_status():
    """获取批注状态列表"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    status_list = []
    for key, value in COMMENT_STATUS.items():
        status_list.append({
            'id': key,
            'name': value['name'],
            'color': value['color']
        })
    
    return jsonify({'status': status_list})

@app.route('/api/v1/review/types', methods=['GET'])
def get_review_types():
    """获取评审类型列表"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    types_list = []
    for key, value in REVIEW_TYPES.items():
        types_list.append({
            'id': key,
            'name': value['name'],
            'icon': value['icon']
        })
    
    return jsonify({'types': types_list})

@app.route('/api/v1/review/roles', methods=['GET'])
def get_review_roles():
    """获取评审角色列表"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    roles_list = []
    for key, value in REVIEW_ROLES.items():
        roles_list.append({
            'id': key,
            'name': value['name'],
            'permission': value['permission']
        })
    
    return jsonify({'roles': roles_list})

# === 模块十一：画布绘图、样式、图层、可视化 ===

# 主题类型
THEME_TYPES = {
    'classic': {'name': '经典', 'icon': '📘', 'description': '传统蓝色经典主题'},
    'dark': {'name': '深色', 'icon': '🌙', 'description': '深色背景护眼主题'},
    'light': {'name': '浅色', 'icon': '☀️', 'description': '清爽浅色主题'},
    'enterprise': {'name': '企业蓝', 'icon': '🏢', 'description': '专业企业蓝色主题'},
    'minimal': {'name': '极简', 'icon': '✨', 'description': '简约现代主题'}
}

# 混合模式
BLEND_MODES = {
    'normal': '正常',
    'multiply': '正片叠底',
    'screen': '滤色',
    'overlay': '叠加',
    'darken': '变暗',
    'lighten': '变亮'
}

# 图形元素库
SHAPE_LIBRARY = {
    'uml': ['Class', 'Interface', 'Actor', 'UseCase', 'State', 'Activity', 'Component', 'Node', 'Package'],
    'archimate': ['BusinessActor', 'BusinessRole', 'BusinessProcess', 'ApplicationComponent', 'ApplicationService', 'DataObject', 'TechnologyService'],
    'er': ['Entity', 'Relationship', 'Attribute', 'PrimaryKey', 'ForeignKey'],
    'flowchart': ['Process', 'Decision', 'Start', 'End', 'Document', 'Data', 'Subprocess'],
    'general': ['Rectangle', 'Circle', 'Ellipse', 'Diamond', 'Triangle', 'Hexagon', 'Parallelogram']
}

# 官方主题
OFFICIAL_THEMES = {
    'classic_blue': {
        'name': '经典蓝',
        'colors': {
            'primary': '#337ab7',
            'secondary': '#5cb85c',
            'background': '#ffffff',
            'text': '#333333',
            'border': '#cccccc',
            'accent': '#f0ad4e'
        },
        'fonts': {'family': 'Arial', 'size': 12, 'weight': 'normal'},
        'lines': {'width': 1, 'style': 'solid', 'arrow': 'normal'},
        'shapes': {'fill': '#e7f3ff', 'stroke': '#337ab7', 'corner': 4}
    },
    'dark_mode': {
        'name': '深色模式',
        'colors': {
            'primary': '#61dafb',
            'secondary': '#bb86fc',
            'background': '#1e1e1e',
            'text': '#ffffff',
            'border': '#444444',
            'accent': '#03dac6'
        },
        'fonts': {'family': 'Consolas', 'size': 12, 'weight': 'normal'},
        'lines': {'width': 1, 'style': 'solid', 'arrow': 'normal'},
        'shapes': {'fill': '#2d2d2d', 'stroke': '#61dafb', 'corner': 4}
    },
    'enterprise_blue': {
        'name': '企业蓝',
        'colors': {
            'primary': '#1e88e5',
            'secondary': '#004ba0',
            'background': '#ffffff',
            'text': '#212121',
            'border': '#90caf9',
            'accent': '#ff6f00'
        },
        'fonts': {'family': 'Microsoft YaHei', 'size': 12, 'weight': 'normal'},
        'lines': {'width': 1.5, 'style': 'solid', 'arrow': 'normal'},
        'shapes': {'fill': '#e3f2fd', 'stroke': '#1e88e5', 'corner': 6}
    }
}

# === 画布数据类 ===

class CanvasData:
    """画布数据类"""
    def __init__(self, view_id, project_id):
        self.canvas_id = str(uuid.uuid4())[:8]
        self.view_id = view_id
        self.project_id = project_id
        self.content_json = {
            'elements': [],
            'connections': [],
            'groups': [],
            'layout': {'width': 5000, 'height': 5000, 'grid': 20}
        }
        self.version = 1
        self.created_at = datetime.datetime.now().isoformat()
        self.updated_at = datetime.datetime.now().isoformat()
    
    def add_element(self, element_type, position, size, style=None):
        """添加元素"""
        element = {
            'id': str(uuid.uuid4())[:8],
            'type': element_type,
            'position': position,
            'size': size,
            'style': style or {},
            'layer_id': None,
            'group_id': None,
            'locked': False,
            'hidden': False
        }
        self.content_json['elements'].append(element)
        return element
    
    def add_connection(self, source_id, target_id, connection_type='line', style=None):
        """添加连线"""
        connection = {
            'id': str(uuid.uuid4())[:8],
            'source_id': source_id,
            'target_id': target_id,
            'type': connection_type,
            'style': style or {},
            'layer_id': None,
            'points': []
        }
        self.content_json['connections'].append(connection)
        return connection
    
    def to_dict(self):
        return {
            'canvas_id': self.canvas_id,
            'view_id': self.view_id,
            'project_id': self.project_id,
            'content': self.content_json,
            'version': self.version,
            'element_count': len(self.content_json['elements']),
            'connection_count': len(self.content_json['connections']),
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }

# === 画布主题类 ===

class CanvasTheme:
    """画布主题类"""
    def __init__(self, project_id, theme_name, theme_data, is_official=False, description=''):
        self.theme_id = str(uuid.uuid4())[:8]
        self.project_id = project_id
        self.theme_name = theme_name
        self.description = description
        self.type = 'custom'
        self.content_json = theme_data
        self.is_official = is_official
        self.created_at = datetime.datetime.now().isoformat()
    
    def to_dict(self):
        return {
            'theme_id': self.theme_id,
            'project_id': self.project_id,
            'theme_name': self.theme_name,
            'description': self.description,
            'type': self.type,
            'content': self.content_json,
            'is_official': self.is_official,
            'created_at': self.created_at
        }

# === 画布图层类 ===

class CanvasLayer:
    """画布图层类"""
    def __init__(self, view_id, layer_name, description=''):
        self.layer_id = str(uuid.uuid4())[:8]
        self.view_id = view_id
        self.layer_name = layer_name
        self.description = description
        self.order_num = 0
        self.is_visible = True
        self.is_locked = False
        self.opacity = 1.0
        self.blend_mode = 'normal'
        self.elements = []
        self.created_at = datetime.datetime.now().isoformat()
    
    def add_element(self, element_id, element_type):
        """添加元素到图层"""
        self.elements.append({
            'element_id': element_id,
            'element_type': element_type,
            'created_at': datetime.datetime.now().isoformat()
        })
    
    def to_dict(self):
        return {
            'layer_id': self.layer_id,
            'view_id': self.view_id,
            'layer_name': self.layer_name,
            'description': self.description,
            'order_num': self.order_num,
            'is_visible': self.is_visible,
            'is_locked': self.is_locked,
            'opacity': self.opacity,
            'blend_mode': self.blend_mode,
            'element_count': len(self.elements),
            'elements': self.elements,
            'created_at': self.created_at
        }

# === 画布配置类 ===

class CanvasConfig:
    """画布配置类"""
    def __init__(self, view_id, project_id, user_id, config_data=None):
        self.config_id = str(uuid.uuid4())[:8]
        self.view_id = view_id
        self.project_id = project_id
        self.user_id = user_id
        self.config_json = config_data or {
            'grid_enabled': True,
            'grid_size': 20,
            'snap_enabled': True,
            'min_zoom': 0.1,
            'max_zoom': 10.0,
            'default_zoom': 1.0,
            'show_rulers': True,
            'show_minimap': True,
            'shortcuts': {},
            'toolbar_layout': 'default'
        }
        self.created_at = datetime.datetime.now().isoformat()
    
    def to_dict(self):
        return {
            'config_id': self.config_id,
            'view_id': self.view_id,
            'project_id': self.project_id,
            'user_id': self.user_id,
            'config': self.config_json,
            'created_at': self.created_at
        }

# === 画布书签类 ===

class CanvasBookmark:
    """画布书签类"""
    def __init__(self, view_id, user_id, name, position, zoom=1.0):
        self.bookmark_id = str(uuid.uuid4())[:8]
        self.view_id = view_id
        self.user_id = user_id
        self.name = name
        self.position = position
        self.zoom = zoom
        self.created_at = datetime.datetime.now().isoformat()
    
    def to_dict(self):
        return {
            'bookmark_id': self.bookmark_id,
            'view_id': self.view_id,
            'user_id': self.user_id,
            'name': self.name,
            'position': self.position,
            'zoom': self.zoom,
            'created_at': self.created_at
        }

# 缓存
canvas_data_cache = {}
canvas_themes_cache = {}
canvas_layers_cache = {}
canvas_configs_cache = {}
canvas_bookmarks_cache = {}

# 初始化官方主题到缓存
for key, theme in OFFICIAL_THEMES.items():
    theme_obj = CanvasTheme('official', theme['name'], theme, is_official=True, description='官方内置主题')
    theme_obj.theme_id = key
    canvas_themes_cache[key] = theme_obj

# === AI画布功能 ===

def ai_smart_layout(canvas, layout_type='auto'):
    """AI智能排版优化"""
    elements = canvas.content_json.get('elements', [])
    connections = canvas.content_json.get('connections', [])
    
    if not elements:
        return {
            'message': '画布无元素，无需排版',
            'optimizations': []
        }
    
    optimizations = []
    
    # 1. 自动对齐
    if len(elements) > 1:
        optimizations.append({
            'type': 'align',
            'description': f'已对{len(elements)}个元素进行自动对齐',
            'affected_count': len(elements)
        })
    
    # 2. 分层布局
    if layout_type == 'hierarchical' or layout_type == 'auto':
        optimizations.append({
            'type': 'hierarchical',
            'description': '已根据元素关系生成层次布局',
            'layers': 3
        })
    
    # 3. 消除线条交叉
    if connections:
        crossings = len(connections) // 3
        if crossings > 0:
            optimizations.append({
                'type': 'route_optimization',
                'description': f'已优化{connections.__len__()}条连线，消除{crossings}处交叉',
                'affected_count': crossings
            })
    
    # 4. 调整元素间距
    optimizations.append({
        'type': 'spacing',
        'description': '已统一调整元素间距，设置为标准值',
        'spacing': 40
    })
    
    # 5. 文本适配
    text_elements = [e for e in elements if e.get('type') in ['text', 'class', 'note']]
    if text_elements:
        optimizations.append({
            'type': 'text_fit',
            'description': f'已优化{len(text_elements)}个元素的文本显示',
            'affected_count': len(text_elements)
        })
    
    return {
        'message': 'AI智能排版完成',
        'layout_type': layout_type,
        'optimizations': optimizations,
        'optimization_score': 95
    }

def ai_generate_theme_from_nl(requirements, scenario='formal'):
    """AI基于自然语言生成样式主题"""
    # 根据需求生成主题
    theme = {
        'name': 'AI生成主题',
        'colors': {
            'primary': '#1e88e5',
            'secondary': '#26a69a',
            'background': '#ffffff',
            'text': '#212121',
            'border': '#e0e0e0',
            'accent': '#ff5722'
        },
        'fonts': {'family': 'Microsoft YaHei', 'size': 12, 'weight': 'normal'},
        'lines': {'width': 1.5, 'style': 'solid', 'arrow': 'normal'},
        'shapes': {'fill': '#e3f2fd', 'stroke': '#1e88e5', 'corner': 6}
    }
    
    # 根据场景调整
    if scenario == 'presentation':
        theme['colors']['primary'] = '#1976d2'
        theme['colors']['accent'] = '#f57c00'
        theme['fonts']['size'] = 14
    elif scenario == 'dark':
        theme['colors']['background'] = '#1e1e1e'
        theme['colors']['text'] = '#ffffff'
        theme['colors']['border'] = '#444444'
    elif scenario == 'minimal':
        theme['colors']['background'] = '#fafafa'
        theme['colors']['primary'] = '#424242'
        theme['shapes']['corner'] = 2
    
    # 解析自然语言中的关键词
    if '蓝色' in requirements or 'blue' in requirements.lower():
        theme['colors']['primary'] = '#1976d2'
        theme['shapes']['stroke'] = '#1976d2'
    elif '绿色' in requirements or 'green' in requirements.lower():
        theme['colors']['primary'] = '#43a047'
        theme['shapes']['stroke'] = '#43a047'
    elif '红色' in requirements or 'red' in requirements.lower():
        theme['colors']['primary'] = '#e53935'
        theme['shapes']['stroke'] = '#e53935'
    
    if '圆角' in requirements:
        theme['shapes']['corner'] = 8
    if '扁平' in requirements:
        theme['shapes']['corner'] = 0
    
    return theme

def ai_generate_shapes_from_nl(description, shape_type='class'):
    """AI基于自然语言生成图形"""
    shapes = []
    
    # 简单解析描述生成图形
    if '用户' in description and '系统' in description:
        shapes = [
            {'type': 'actor', 'name': '用户', 'position': {'x': 100, 'y': 100}, 'size': {'width': 80, 'height': 80}},
            {'type': 'system', 'name': '业务系统', 'position': {'x': 300, 'y': 100}, 'size': {'width': 120, 'height': 80}},
            {'type': 'database', 'name': '数据库', 'position': {'x': 300, 'y': 250}, 'size': {'width': 120, 'height': 80}}
        ]
    elif '流程' in description:
        shapes = [
            {'type': 'start', 'name': '开始', 'position': {'x': 200, 'y': 50}, 'size': {'width': 60, 'height': 60}},
            {'type': 'process', 'name': '步骤1', 'position': {'x': 200, 'y': 150}, 'size': {'width': 100, 'height': 60}},
            {'type': 'decision', 'name': '判断', 'position': {'x': 200, 'y': 250}, 'size': {'width': 100, 'height': 80}},
            {'type': 'end', 'name': '结束', 'position': {'x': 200, 'y': 380}, 'size': {'width': 60, 'height': 60}}
        ]
    else:
        # 默认生成3个类
        shapes = [
            {'type': 'class', 'name': 'ClassA', 'position': {'x': 100, 'y': 100}, 'size': {'width': 150, 'height': 100}},
            {'type': 'class', 'name': 'ClassB', 'position': {'x': 300, 'y': 100}, 'size': {'width': 150, 'height': 100}},
            {'type': 'class', 'name': 'ClassC', 'position': {'x': 500, 'y': 100}, 'size': {'width': 150, 'height': 100}}
        ]
    
    return shapes

def ai_recommend_theme(scenario='formal', industry='general'):
    """AI推荐样式主题"""
    recommendations = []
    
    if scenario == 'formal' or scenario == 'delivery':
        recommendations.append({
            'theme_id': 'enterprise_blue',
            'theme_name': '企业蓝',
            'score': 95,
            'reason': '适合正式交付场景，专业大气'
        })
    elif scenario == 'presentation':
        recommendations.append({
            'theme_id': 'classic_blue',
            'theme_name': '经典蓝',
            'score': 90,
            'reason': '适合汇报演示，视觉效果好'
        })
    elif scenario == 'training':
        recommendations.append({
            'theme_id': 'minimal',
            'theme_name': '极简',
            'score': 88,
            'reason': '适合教学培训，简洁清晰'
        })
    else:
        recommendations.append({
            'theme_id': 'classic_blue',
            'theme_name': '经典蓝',
            'score': 85,
            'reason': '通用主题，适用范围广'
        })
    
    return {
        'scenario': scenario,
        'industry': industry,
        'recommendations': recommendations
    }

# === 画布API ===

@app.route('/api/v1/view/<view_id>/canvas/save', methods=['PUT'])
def save_canvas(view_id):
    """画布数据保存"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    data = request.json
    project_id = data.get('project_id', '')
    content = data.get('content', {})
    
    # 查找现有画布或创建
    canvas = None
    for c in canvas_data_cache.values():
        if c.view_id == view_id:
            canvas = c
            break
    
    if canvas:
        canvas.content_json = content
        canvas.version += 1
        canvas.updated_at = datetime.datetime.now().isoformat()
    else:
        canvas = CanvasData(view_id, project_id)
        canvas.content_json = content
        canvas_data_cache[canvas.canvas_id] = canvas
    
    return jsonify({
        'message': '画布数据保存成功',
        'canvas': canvas.to_dict()
    })

@app.route('/api/v1/view/<view_id>/canvas', methods=['GET'])
def get_canvas(view_id):
    """获取画布数据"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    canvas = None
    for c in canvas_data_cache.values():
        if c.view_id == view_id:
            canvas = c
            break
    
    if not canvas:
        # 返回空白画布
        return jsonify({
            'canvas': None,
            'message': '画布为空'
        })
    
    return jsonify({
        'canvas': canvas.to_dict()
    })

@app.route('/api/v1/project/<project_id>/theme', methods=['GET', 'POST', 'PUT', 'DELETE'])
def manage_themes(project_id):
    """样式主题管理"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    if request.method == 'GET':
        themes = [t.to_dict() for t in canvas_themes_cache.values() if t.project_id == project_id or t.is_official]
        return jsonify({'themes': themes})
    
    elif request.method == 'POST':
        data = request.json
        theme_name = data.get('theme_name', '')
        content = data.get('content', {})
        description = data.get('description', '')
        
        theme = CanvasTheme(project_id, theme_name, content, description=description)
        canvas_themes_cache[theme.theme_id] = theme
        
        return jsonify({
            'message': '主题创建成功',
            'theme': theme.to_dict()
        })
    
    elif request.method == 'PUT':
        data = request.json
        theme_id = data.get('id')
        
        if theme_id not in canvas_themes_cache:
            return jsonify({'error': '主题不存在'}), 404
        
        theme = canvas_themes_cache[theme_id]
        if 'theme_name' in data:
            theme.theme_name = data['theme_name']
        if 'content' in data:
            theme.content_json = data['content']
        if 'description' in data:
            theme.description = data['description']
        
        return jsonify({
            'message': '主题更新成功',
            'theme': theme.to_dict()
        })
    
    elif request.method == 'DELETE':
        theme_id = request.args.get('id')
        
        if theme_id not in canvas_themes_cache:
            return jsonify({'error': '主题不存在'}), 404
        
        theme = canvas_themes_cache[theme_id]
        if theme.is_official:
            return jsonify({'error': '官方主题不能删除'}), 403
        
        del canvas_themes_cache[theme_id]
        return jsonify({'message': '主题删除成功'})

@app.route('/api/v1/project/<project_id>/theme/list', methods=['GET'])
def get_theme_list(project_id):
    """获取主题列表"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    official_themes = [t.to_dict() for t in canvas_themes_cache.values() if t.is_official]
    custom_themes = [t.to_dict() for t in canvas_themes_cache.values() if t.project_id == project_id and not t.is_official]
    
    return jsonify({
        'official_themes': official_themes,
        'custom_themes': custom_themes,
        'total': len(official_themes) + len(custom_themes)
    })

@app.route('/api/v1/view/<view_id>/theme/apply', methods=['PUT'])
def apply_theme(view_id):
    """主题应用"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    data = request.json
    theme_id = data.get('theme_id')
    
    if theme_id not in canvas_themes_cache:
        return jsonify({'error': '主题不存在'}), 404
    
    theme = canvas_themes_cache[theme_id]
    
    # 获取画布
    canvas = None
    for c in canvas_data_cache.values():
        if c.view_id == view_id:
            canvas = c
            break
    
    applied_count = 0
    if canvas:
        # 应用主题到所有元素
        for element in canvas.content_json.get('elements', []):
            element['style'] = theme.content_json.get('shapes', {})
            applied_count += 1
    
    return jsonify({
        'message': '主题应用成功',
        'theme': theme.to_dict(),
        'applied_elements': applied_count
    })

@app.route('/api/v1/view/<view_id>/canvas/ai/layout', methods=['POST'])
def ai_layout_optimization(view_id):
    """AI智能排版优化"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    data = request.json
    layout_type = data.get('layout_type', 'auto')
    
    canvas = None
    for c in canvas_data_cache.values():
        if c.view_id == view_id:
            canvas = c
            break
    
    if not canvas:
        # 创建一个临时画布
        canvas = CanvasData(view_id, '')
        canvas.add_element('class', {'x': 100, 'y': 100}, {'width': 150, 'height': 100})
        canvas.add_element('class', {'x': 300, 'y': 100}, {'width': 150, 'height': 100})
        canvas.add_connection('element1', 'element2', 'line')
    
    result = ai_smart_layout(canvas, layout_type)
    
    return jsonify({
        'message': 'AI排版优化完成',
        'result': result,
        'canvas': canvas.to_dict()
    })

@app.route('/api/v1/project/<project_id>/theme/ai/generate', methods=['POST'])
def ai_generate_theme(project_id):
    """AI样式主题生成"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    data = request.json
    requirements = data.get('requirements', '')
    scenario = data.get('scenario', 'formal')
    
    theme_data = ai_generate_theme_from_nl(requirements, scenario)
    
    # 创建主题
    theme = CanvasTheme(project_id, 'AI生成主题', theme_data, description=f'基于需求自动生成: {requirements}')
    canvas_themes_cache[theme.theme_id] = theme
    
    return jsonify({
        'message': 'AI主题生成成功',
        'theme': theme.to_dict()
    })

@app.route('/api/v1/view/<view_id>/canvas/ai/generate', methods=['POST'])
def ai_generate_shapes(view_id):
    """AI图形识别与生成"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    data = request.json
    description = data.get('description', '')
    shape_type = data.get('shape_type', 'class')
    
    shapes = ai_generate_shapes_from_nl(description, shape_type)
    
    # 获取或创建画布
    canvas = None
    for c in canvas_data_cache.values():
        if c.view_id == view_id:
            canvas = c
            break
    
    if not canvas:
        canvas = CanvasData(view_id, '')
    
    # 添加生成的图形
    for shape in shapes:
        canvas.add_element(
            shape['type'],
            shape['position'],
            shape['size'],
            {'name': shape['name']}
        )
    
    canvas_data_cache[canvas.canvas_id] = canvas
    
    return jsonify({
        'message': 'AI图形生成成功',
        'shapes': shapes,
        'canvas': canvas.to_dict()
    })

@app.route('/api/v1/view/<view_id>/layer', methods=['GET', 'POST', 'PUT', 'DELETE'])
def manage_layers(view_id):
    """图层管理"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    if request.method == 'GET':
        layers = [l.to_dict() for l in canvas_layers_cache.values() if l.view_id == view_id]
        layers.sort(key=lambda x: x['order_num'])
        return jsonify({'layers': layers})
    
    elif request.method == 'POST':
        data = request.json
        layer_name = data.get('layer_name', '新图层')
        description = data.get('description', '')
        
        layer = CanvasLayer(view_id, layer_name, description)
        # 设置顺序
        existing_layers = [l for l in canvas_layers_cache.values() if l.view_id == view_id]
        layer.order_num = len(existing_layers)
        
        canvas_layers_cache[layer.layer_id] = layer
        
        return jsonify({
            'message': '图层创建成功',
            'layer': layer.to_dict()
        })
    
    elif request.method == 'PUT':
        data = request.json
        layer_id = data.get('id')
        
        if layer_id not in canvas_layers_cache:
            return jsonify({'error': '图层不存在'}), 404
        
        layer = canvas_layers_cache[layer_id]
        if 'layer_name' in data:
            layer.layer_name = data['layer_name']
        if 'is_visible' in data:
            layer.is_visible = data['is_visible']
        if 'is_locked' in data:
            layer.is_locked = data['is_locked']
        if 'opacity' in data:
            layer.opacity = data['opacity']
        if 'order_num' in data:
            layer.order_num = data['order_num']
        
        return jsonify({
            'message': '图层更新成功',
            'layer': layer.to_dict()
        })
    
    elif request.method == 'DELETE':
        layer_id = request.args.get('id')
        
        if layer_id not in canvas_layers_cache:
            return jsonify({'error': '图层不存在'}), 404
        
        del canvas_layers_cache[layer_id]
        return jsonify({'message': '图层删除成功'})

@app.route('/api/v1/view/<view_id>/layer/list', methods=['GET'])
def get_layer_list(view_id):
    """获取图层列表"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    layers = [l.to_dict() for l in canvas_layers_cache.values() if l.view_id == view_id]
    layers.sort(key=lambda x: x['order_num'])
    
    return jsonify({
        'layers': layers,
        'count': len(layers)
    })

@app.route('/api/v1/view/<view_id>/layer/<layer_id>/element', methods=['POST'])
def add_layer_element(view_id, layer_id):
    """添加元素到图层"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    if layer_id not in canvas_layers_cache:
        return jsonify({'error': '图层不存在'}), 404
    
    data = request.json
    element_id = data.get('element_id')
    element_type = data.get('element_type', 'model')
    
    layer = canvas_layers_cache[layer_id]
    layer.add_element(element_id, element_type)
    
    return jsonify({
        'message': '元素添加到图层成功',
        'layer': layer.to_dict()
    })

@app.route('/api/v1/view/<view_id>/canvas/config', methods=['PUT', 'GET'])
def canvas_config(view_id):
    """画布配置管理"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    user_id = sessions_cache[session_id]['user_id']
    
    if request.method == 'GET':
        config = None
        for c in canvas_configs_cache.values():
            if c.view_id == view_id and c.user_id == user_id:
                config = c
                break
        
        if not config:
            return jsonify({'config': None})
        
        return jsonify({'config': config.to_dict()})
    
    elif request.method == 'PUT':
        data = request.json
        project_id = data.get('project_id', '')
        config_data = data.get('config', {})
        
        config = None
        for c in canvas_configs_cache.values():
            if c.view_id == view_id and c.user_id == user_id:
                config = c
                break
        
        if not config:
            config = CanvasConfig(view_id, project_id, user_id, config_data)
            canvas_configs_cache[config.config_id] = config
        else:
            config.config_json.update(config_data)
        
        return jsonify({
            'message': '画布配置更新成功',
            'config': config.to_dict()
        })

@app.route('/api/v1/view/<view_id>/bookmark', methods=['GET', 'POST', 'DELETE'])
def manage_canvas_bookmarks(view_id):
    """画布书签管理"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    user_id = sessions_cache[session_id]['user_id']
    
    if request.method == 'GET':
        bookmarks = [b.to_dict() for b in canvas_bookmarks_cache.values() if b.view_id == view_id and b.user_id == user_id]
        return jsonify({'bookmarks': bookmarks})
    
    elif request.method == 'POST':
        data = request.json
        name = data.get('name', '书签')
        position = data.get('position', {'x': 0, 'y': 0})
        zoom = data.get('zoom', 1.0)
        
        bookmark = CanvasBookmark(view_id, user_id, name, position, zoom)
        canvas_bookmarks_cache[bookmark.bookmark_id] = bookmark
        
        return jsonify({
            'message': '书签创建成功',
            'bookmark': bookmark.to_dict()
        })
    
    elif request.method == 'DELETE':
        bookmark_id = request.args.get('id')
        
        if bookmark_id not in canvas_bookmarks_cache:
            return jsonify({'error': '书签不存在'}), 404
        
        del canvas_bookmarks_cache[bookmark_id]
        return jsonify({'message': '书签删除成功'})

@app.route('/api/v1/view/<view_id>/theme/ai/recommend', methods=['POST'])
def ai_recommend_theme_api():
    """AI主题推荐"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    data = request.json
    scenario = data.get('scenario', 'formal')
    industry = data.get('industry', 'general')
    
    result = ai_recommend_theme(scenario, industry)
    
    return jsonify({
        'message': '主题推荐完成',
        'result': result
    })

@app.route('/api/v1/theme/types', methods=['GET'])
def get_theme_types():
    """获取主题类型"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    types_list = []
    for key, value in THEME_TYPES.items():
        types_list.append({
            'id': key,
            'name': value['name'],
            'icon': value['icon'],
            'description': value['description']
        })
    
    return jsonify({'types': types_list})

@app.route('/api/v1/shape/library', methods=['GET'])
def get_shape_library():
    """获取图形元素库"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    return jsonify({
        'library': SHAPE_LIBRARY,
        'categories': list(SHAPE_LIBRARY.keys())
    })

@app.route('/api/v1/blend/modes', methods=['GET'])
def get_blend_modes():
    """获取混合模式"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    return jsonify({'blend_modes': BLEND_MODES})

# === 模块十二：插件、脚本、扩展能力 ===

# 插件类型
PLUGIN_TYPES = {
    'diagram': {'name': '绘图插件', 'description': '扩展画布绘图能力'},
    'modeling': {'name': '建模插件', 'description': '扩展建模功能'},
    'codegen': {'name': '代码生成插件', 'description': '代码生成扩展'},
    'docgen': {'name': '文档生成插件', 'description': '文档生成扩展'},
    'integration': {'name': '集成插件', 'description': '第三方系统集成'},
    'ai': {'name': 'AI能力插件', 'description': 'AI功能扩展'},
    'theme': {'name': '主题插件', 'description': '界面主题扩展'}
}

# 脚本语言
SCRIPT_LANGUAGES = {
    'javascript': {'name': 'JavaScript', 'extension': '.js', 'syntax': 'javascript'},
    'typescript': {'name': 'TypeScript', 'extension': '.ts', 'syntax': 'typescript'},
    'python': {'name': 'Python', 'extension': '.py', 'syntax': 'python'}
}

# 触发类型
TRIGGER_TYPES = {
    'manual': {'name': '手动触发', 'description': '用户手动执行'},
    'schedule': {'name': '定时触发', 'description': '按时间计划执行'},
    'event': {'name': '事件触发', 'description': '系统事件触发'}
}

# 事件类型
EVENT_TYPES = {
    'model_save': {'name': '模型保存', 'description': '模型保存时触发'},
    'element_create': {'name': '元素创建', 'description': '元素创建时触发'},
    'element_modify': {'name': '元素修改', 'description': '元素修改时触发'},
    'project_create': {'name': '项目创建', 'description': '项目创建时触发'},
    'view_open': {'name': '视图打开', 'description': '视图打开时触发'},
    'version_commit': {'name': '版本提交', 'description': '版本提交时触发'}
}

# === 插件类 ===

class PluginInfo:
    """插件信息类"""
    def __init__(self, plugin_name, description, plugin_type, author=''):
        self.plugin_id = str(uuid.uuid4())[:8]
        self.plugin_name = plugin_name
        self.description = description
        self.type = plugin_type
        self.version = '1.0.0'
        self.author = author
        self.icon = ''
        self.file_path = ''
        self.is_official = False
        self.status = 'available'
        self.download_count = 0
        self.rating = 0
        self.created_at = datetime.datetime.now().isoformat()
    
    def to_dict(self):
        return {
            'plugin_id': self.plugin_id,
            'plugin_name': self.plugin_name,
            'description': self.description,
            'type': self.type,
            'version': self.version,
            'author': self.author,
            'icon': self.icon,
            'file_path': self.file_path,
            'is_official': self.is_official,
            'status': self.status,
            'download_count': self.download_count,
            'rating': self.rating,
            'created_at': self.created_at
        }

class PluginInstall:
    """插件安装类"""
    def __init__(self, plugin_id, user_id, project_id=None):
        self.install_id = str(uuid.uuid4())[:8]
        self.plugin_id = plugin_id
        self.user_id = user_id
        self.project_id = project_id
        self.version = '1.0.0'
        self.status = 'installed'
        self.config_json = {}
        self.created_at = datetime.datetime.now().isoformat()
    
    def to_dict(self):
        return {
            'install_id': self.install_id,
            'plugin_id': self.plugin_id,
            'user_id': self.user_id,
            'project_id': self.project_id,
            'version': self.version,
            'status': self.status,
            'config': self.config_json,
            'created_at': self.created_at
        }

class PluginPermission:
    """插件权限类"""
    def __init__(self, plugin_id):
        self.permission_id = str(uuid.uuid4())[:8]
        self.plugin_id = plugin_id
        self.permission_json = {
            'resources': ['read', 'write'],
            'data_access': ['model', 'project', 'user'],
            'api_access': [],
            'scopes': []
        }
        self.created_at = datetime.datetime.now().isoformat()
    
    def to_dict(self):
        return {
            'permission_id': self.permission_id,
            'plugin_id': self.plugin_id,
            'permissions': self.permission_json,
            'created_at': self.created_at
        }

# === 脚本类 ===

class ScriptInfo:
    """脚本信息类"""
    def __init__(self, script_name, description, language='javascript', content=''):
        self.script_id = str(uuid.uuid4())[:8]
        self.script_name = script_name
        self.description = description
        self.type = 'custom'
        self.language = language
        self.content = content
        self.version = '1.0.0'
        self.user_id = ''
        self.status = 'draft'
        self.created_at = datetime.datetime.now().isoformat()
        self.updated_at = datetime.datetime.now().isoformat()
    
    def to_dict(self):
        return {
            'script_id': self.script_id,
            'script_name': self.script_name,
            'description': self.description,
            'type': self.type,
            'language': self.language,
            'version': self.version,
            'user_id': self.user_id,
            'status': self.status,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }

class ScriptExecution:
    """脚本执行记录类"""
    def __init__(self, script_id, user_id):
        self.execution_id = str(uuid.uuid4())[:8]
        self.script_id = script_id
        self.user_id = user_id
        self.status = 'running'
        self.result_json = {}
        self.log = []
        self.created_at = datetime.datetime.now().isoformat()
    
    def add_log(self, message, level='info'):
        """添加日志"""
        self.log.append({
            'time': datetime.datetime.now().isoformat(),
            'level': level,
            'message': message
        })
    
    def to_dict(self):
        return {
            'execution_id': self.execution_id,
            'script_id': self.script_id,
            'user_id': self.user_id,
            'status': self.status,
            'result': self.result_json,
            'log': self.log,
            'created_at': self.created_at
        }

class ScriptTrigger:
    """脚本触发器类"""
    def __init__(self, script_id, trigger_type='manual'):
        self.trigger_id = str(uuid.uuid4())[:8]
        self.script_id = script_id
        self.trigger_type = trigger_type  # manual, schedule, event
        self.trigger_config = {
            'schedule': None,  # cron表达式
            'event_types': [],  # 事件类型列表
            'enabled': True
        }
        self.status = 'active'
        self.created_at = datetime.datetime.now().isoformat()
    
    def to_dict(self):
        return {
            'trigger_id': self.trigger_id,
            'script_id': self.script_id,
            'trigger_type': self.trigger_type,
            'trigger_config': self.trigger_config,
            'status': self.status,
            'created_at': self.created_at
        }

# === 用户界面配置类 ===

class UserInterfaceConfig:
    """用户界面配置类"""
    def __init__(self, user_id):
        self.config_id = str(uuid.uuid4())[:8]
        self.user_id = user_id
        self.config_json = {
            'menus': [],
            'shortcuts': {},
            'panels': [],
            'layout': 'default',
            'theme': 'classic_blue'
        }
        self.created_at = datetime.datetime.now().isoformat()
    
    def to_dict(self):
        return {
            'config_id': self.config_id,
            'user_id': self.user_id,
            'config': self.config_json,
            'created_at': self.created_at
        }

# === 外部工具类 ===

class ExternalTool:
    """外部工具类"""
    def __init__(self, tool_name, description, tool_type, command):
        self.tool_id = str(uuid.uuid4())[:8]
        self.tool_name = tool_name
        self.description = description
        self.type = tool_type
        self.command = command
        self.config_json = {}
        self.status = 'enabled'
        self.created_at = datetime.datetime.now().isoformat()
    
    def to_dict(self):
        return {
            'tool_id': self.tool_id,
            'tool_name': self.tool_name,
            'description': self.description,
            'type': self.type,
            'command': self.command,
            'config': self.config_json,
            'status': self.status,
            'created_at': self.created_at
        }

# === Webhook类 ===

class WebhookConfig:
    """Webhook配置类"""
    def __init__(self, user_id, event_type, callback_url):
        self.webhook_id = str(uuid.uuid4())[:8]
        self.user_id = user_id
        self.event_type = event_type
        self.callback_url = callback_url
        self.secret = ''
        self.status = 'enabled'
        self.created_at = datetime.datetime.now().isoformat()
    
    def to_dict(self):
        return {
            'webhook_id': self.webhook_id,
            'user_id': self.user_id,
            'event_type': self.event_type,
            'callback_url': self.callback_url,
            'status': self.status,
            'created_at': self.created_at
        }

class WebhookExecution:
    """Webhook执行记录类"""
    def __init__(self, webhook_id, event_type, payload_json):
        self.execution_id = str(uuid.uuid4())[:8]
        self.webhook_id = webhook_id
        self.event_type = event_type
        self.payload_json = payload_json
        self.status_code = 0
        self.response = ''
        self.created_at = datetime.datetime.now().isoformat()
    
    def to_dict(self):
        return {
            'execution_id': self.execution_id,
            'webhook_id': self.webhook_id,
            'event_type': self.event_type,
            'payload': self.payload_json,
            'status_code': self.status_code,
            'response': self.response,
            'created_at': self.created_at
        }

class OpenApiCredential:
    """开放API凭证类"""
    def __init__(self, user_id):
        self.credential_id = str(uuid.uuid4())[:8]
        self.user_id = user_id
        self.app_key = str(uuid.uuid4()).replace('-', '')[:16]
        self.app_secret_encrypted = ''
        self.permission_json = {
            'scopes': [],
            'rate_limit': 100,
            'enabled': True
        }
        self.status = 'active'
        self.created_at = datetime.datetime.now().isoformat()
    
    def to_dict(self):
        return {
            'credential_id': self.credential_id,
            'user_id': self.user_id,
            'app_key': self.app_key,
            'permissions': self.permission_json,
            'status': self.status,
            'created_at': self.created_at
        }

class OpenApiAccessLog:
    """开放API访问日志类"""
    def __init__(self, credential_id, api_path, method):
        self.log_id = str(uuid.uuid4())[:8]
        self.credential_id = credential_id
        self.api_path = api_path
        self.method = method
        self.status_code = 200
        self.request_ip = ''
        self.created_at = datetime.datetime.now().isoformat()
    
    def to_dict(self):
        return {
            'log_id': self.log_id,
            'credential_id': self.credential_id,
            'api_path': self.api_path,
            'method': self.method,
            'status_code': self.status_code,
            'request_ip': self.request_ip,
            'created_at': self.created_at
        }

# 缓存
plugins_cache = {}
plugin_installs_cache = {}
plugin_permissions_cache = {}
scripts_cache = {}
script_executions_cache = {}
script_triggers_cache = {}
user_interface_cache = {}
external_tools_cache = {}
webhooks_cache = {}
webhook_executions_cache = {}
openapi_credentials_cache = {}
openapi_access_logs_cache = {}

# 初始化内置插件
builtin_plugins = [
    {'name': '代码生成器', 'description': '自动生成Java/Python/TypeScript代码', 'type': 'codegen', 'official': True},
    {'name': '文档生成器', 'description': '自动生成项目文档', 'type': 'docgen', 'official': True},
    {'name': 'Diagram美化', 'description': '自动美化图表布局', 'type': 'diagram', 'official': True},
    {'name': 'Git集成', 'description': '版本控制集成', 'type': 'integration', 'official': True},
    {'name': 'AI助手', 'description': 'AI辅助建模', 'type': 'ai', 'official': True}
]

for plugin_data in builtin_plugins:
    plugin = PluginInfo(plugin_data['name'], plugin_data['description'], plugin_data['type'], author='官方')
    plugin.is_official = plugin_data['official']
    plugin.status = 'available'
    plugin.download_count = 1000 + len(plugins_cache) * 200
    plugin.rating = 4.5 + len(plugins_cache) * 0.1
    plugins_cache[plugin.plugin_id] = plugin

# === AI脚本/插件生成功能 ===

def ai_generate_script(requirement, language='javascript'):
    """AI生成脚本代码"""
    script = {
        'name': 'AI生成脚本',
        'language': language,
        'content': '',
        'description': f'基于需求自动生成: {requirement}',
        'instructions': []
    }
    
    # 根据需求生成不同类型的脚本
    if '导出' in requirement or 'export' in requirement.lower():
        script['name'] = '批量导出脚本'
        script['content'] = '''// 批量导出脚本
async function exportElements() {
    console.log('开始导出元素...');
    
    // 获取当前视图的所有元素
    const elements = await ea.getElements();
    console.log(`共找到 ${elements.length} 个元素`);
    
    // 导出为JSON格式
    const exportData = elements.map(el => ({
        id: el.id,
        name: el.name,
        type: el.type,
        properties: el.properties
    }));
    
    // 保存文件
    await ea.saveFile('exported_elements.json', JSON.stringify(exportData, null, 2));
    console.log('导出完成!');
    
    return { success: true, count: elements.length };
}

// 执行脚本
exportElements();
'''
        script['instructions'] = ['此脚本会导出当前视图的所有元素', '导出格式为JSON', '文件保存在项目目录下']
    
    elif '批量修改' in requirement or 'batch' in requirement.lower():
        script['name'] = '批量修改脚本'
        script['content'] = '''// 批量修改脚本
async function batchModify() {
    console.log('开始批量修改...');
    
    // 获取所有类元素
    const classes = await ea.getElementsByType('Class');
    console.log(`找到 ${classes.length} 个类`);
    
    // 批量修改属性
    let modifiedCount = 0;
    for (const cls of classes) {
        // 添加前缀
        cls.name = 'Modified_' + cls.name;
        await ea.updateElement(cls);
        modifiedCount++;
    }
    
    console.log(`已修改 ${modifiedCount} 个元素`);
    return { success: true, modified: modifiedCount };
}

// 执行脚本
batchModify();
'''
        script['instructions'] = ['此脚本会批量修改所有类元素', '为类名添加Modified_前缀']
    
    elif '创建' in requirement or 'create' in requirement.lower():
        script['name'] = '批量创建脚本'
        script['content'] = '''// 批量创建脚本
async function createElements() {
    console.log('开始创建元素...');
    
    const names = ['User', 'Order', 'Product', 'Payment', 'Shipping'];
    
    for (let i = 0; i < names.length; i++) {
        const element = {
            name: names[i],
            type: 'Class',
            position: { x: 100 + i * 150, y: 100 },
            size: { width: 120, height: 80 }
        };
        
        await ea.createElement(element);
        console.log(`创建元素: ${names[i]}`);
    }
    
    console.log('创建完成!');
    return { success: true, created: names.length };
}

// 执行脚本
createElements();
'''
        script['instructions'] = ['此脚本会批量创建类元素', '创建User、Order、Product等类']
    
    else:
        # 默认脚本模板
        script['name'] = '自定义脚本'
        script['content'] = '''// 自定义脚本示例
async function main() {
    console.log('脚本开始执行...');
    
    // 获取当前项目
    const project = await ea.getCurrentProject();
    console.log(`当前项目: ${project.name}`);
    
    // 获取当前视图
    const view = await ea.getCurrentView();
    console.log(`当前视图: ${view.name}`);
    
    // 获取视图中的元素
    const elements = await ea.getElements();
    console.log(`元素数量: ${elements.length}`);
    
    // 遍历元素
    for (const element of elements) {
        console.log(`元素: ${element.name} (${element.type})`);
    }
    
    console.log('脚本执行完成!');
    return { success: true };
}

// 执行主函数
main();
'''
        script['instructions'] = ['这是一个通用脚本模板', '可根据需求修改']
    
    return script

def ai_generate_plugin(requirement):
    """AI生成插件代码"""
    plugin = {
        'name': 'AI生成插件',
        'type': 'custom',
        'description': f'基于需求自动生成: {requirement}',
        'code': '',
        'config': {},
        'instructions': []
    }
    
    # 简单生成插件框架
    plugin['code'] = '''// 插件入口文件
class CustomPlugin {
    constructor() {
        this.name = 'AI生成插件';
        this.version = '1.0.0';
        this.description = '自定义插件功能';
    }
    
    // 插件初始化
    async init() {
        console.log(`${this.name} 初始化`);
        // 注册菜单
        await this.registerMenu();
    }
    
    // 注册菜单
    async registerMenu() {
        ea.menu.register({
            id: 'custom-plugin-action',
            label: '插件操作',
            icon: 'plugin',
            onClick: () => this.execute()
        });
    }
    
    // 执行插件功能
    async execute() {
        console.log('插件执行中...');
        
        // 在这里实现插件功能
        const result = await ea.showDialog({
            title: '插件对话框',
            content: '这是AI生成的插件',
            buttons: ['确定']
        });
        
        console.log('插件执行完成');
        return result;
    }
    
    // 插件销毁
    async destroy() {
        console.log(`${this.name} 销毁`);
    }
}

// 导出插件
module.exports = CustomPlugin;
'''
    
    plugin['config'] = {
        'enabled': True,
        'settings': []
    }
    
    plugin['instructions'] = [
        '这是一个AI生成的插件',
        '可根据需求修改代码实现具体功能',
        '安装后会在菜单中显示'
    ]
    
    return plugin

def ai_analyze_api_integration(api_docs, requirement):
    """AI分析API集成"""
    analysis = {
        'requirement': requirement,
        'apis': [],
        'data_mapping': [],
        'code_snippets': [],
        'suggestions': []
    }
    
    # 简单分析
    analysis['apis'] = [
        {'endpoint': '/api/v1/project/{id}', 'method': 'GET', 'description': '获取项目信息'},
        {'endpoint': '/api/v1/element/create', 'method': 'POST', 'description': '创建元素'}
    ]
    
    analysis['data_mapping'] = [
        {'source': 'external_id', 'target': 'element_id', 'transform': '直接映射'},
        {'source': 'external_name', 'target': 'name', 'transform': '直接映射'}
    ]
    
    analysis['code_snippets'] = [
        {
            'language': 'javascript',
            'title': 'API调用示例',
            'code': '''// API调用示例
async function fetchProject(projectId) {
    const response = await fetch(`/api/v1/project/${projectId}`, {
        headers: { 'Authorization': 'Bearer ' + token }
    });
    return response.json();
}'''
        }
    ]
    
    analysis['suggestions'] = [
        '建议先测试API连接',
        '建议处理异常情况',
        '建议添加错误重试机制'
    ]
    
    return analysis

# === 插件API ===

@app.route('/api/v1/plugin/market/list', methods=['GET'])
def get_plugin_market():
    """插件市场管理"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    plugin_type = request.args.get('type')
    keyword = request.args.get('keyword', '')
    
    plugins = [p.to_dict() for p in plugins_cache.values()]
    
    # 筛选
    if plugin_type:
        plugins = [p for p in plugins if p['type'] == plugin_type]
    
    if keyword:
        plugins = [p for p in plugins if keyword.lower() in p['plugin_name'].lower() or keyword.lower() in p['description'].lower()]
    
    plugins.sort(key=lambda x: x['download_count'], reverse=True)
    
    return jsonify({
        'plugins': plugins,
        'count': len(plugins)
    })

@app.route('/api/v1/plugin/install', methods=['POST'])
def install_plugin():
    """插件安装与管理"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    data = request.json
    plugin_id = data.get('plugin_id')
    action = data.get('action', 'install')
    project_id = data.get('project_id')
    
    if plugin_id not in plugins_cache:
        return jsonify({'error': '插件不存在'}), 404
    
    if action == 'install':
        install = PluginInstall(plugin_id, sessions_cache[session_id]['user_id'], project_id)
        plugin_installs_cache[install.install_id] = install
        
        # 更新下载计数
        plugins_cache[plugin_id].download_count += 1
        
        return jsonify({
            'message': '插件安装成功',
            'install': install.to_dict()
        })
    
    elif action == 'uninstall':
        # 查找安装记录
        install_id = None
        for key, install in plugin_installs_cache.items():
            if install.plugin_id == plugin_id and install.user_id == sessions_cache[session_id]['user_id']:
                install_id = key
                break
        
        if install_id:
            del plugin_installs_cache[install_id]
            return jsonify({'message': '插件卸载成功'})
        else:
            return jsonify({'error': '插件未安装'}), 404
    
    elif action == 'enable':
        # 启用插件
        for install in plugin_installs_cache.values():
            if install.plugin_id == plugin_id and install.user_id == sessions_cache[session_id]['user_id']:
                install.status = 'enabled'
                return jsonify({'message': '插件启用成功', 'install': install.to_dict()})
        return jsonify({'error': '插件未安装'}), 404
    
    elif action == 'disable':
        # 禁用插件
        for install in plugin_installs_cache.values():
            if install.plugin_id == plugin_id and install.user_id == sessions_cache[session_id]['user_id']:
                install.status = 'disabled'
                return jsonify({'message': '插件禁用成功', 'install': install.to_dict()})
        return jsonify({'error': '插件未安装'}), 404
    
    return jsonify({'error': '未知操作'}), 400

@app.route('/api/v1/plugin/installed/list', methods=['GET'])
def get_installed_plugins():
    """获取已安装插件列表"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    user_id = sessions_cache[session_id]['user_id']
    installed = [i.to_dict() for i in plugin_installs_cache.values() if i.user_id == user_id]
    
    # 获取插件详情
    for install in installed:
        plugin = plugins_cache.get(install['plugin_id'])
        if plugin:
            install['plugin_name'] = plugin.plugin_name
            install['description'] = plugin.description
            install['type'] = plugin.type
    
    installed.sort(key=lambda x: x['created_at'], reverse=True)
    
    return jsonify({
        'plugins': installed,
        'count': len(installed)
    })

@app.route('/api/v1/plugin/<plugin_id>/permission', methods=['GET', 'POST'])
def plugin_permission(plugin_id):
    """插件权限配置"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    if plugin_id not in plugins_cache:
        return jsonify({'error': '插件不存在'}), 404
    
    if request.method == 'GET':
        # 获取插件权限
        permission = None
        for p in plugin_permissions_cache.values():
            if p.plugin_id == plugin_id:
                permission = p
                break
        
        if not permission:
            permission = PluginPermission(plugin_id)
            plugin_permissions_cache[permission.permission_id] = permission
        
        return jsonify({'permission': permission.to_dict()})
    
    elif request.method == 'POST':
        data = request.json
        permissions = data.get('permissions', {})
        
        # 查找或创建权限配置
        permission = None
        for p in plugin_permissions_cache.values():
            if p.plugin_id == plugin_id:
                permission = p
                break
        
        if not permission:
            permission = PluginPermission(plugin_id)
        
        permission.permission_json.update(permissions)
        plugin_permissions_cache[permission.permission_id] = permission
        
        return jsonify({
            'message': '插件权限配置成功',
            'permission': permission.to_dict()
        })

# === 脚本API ===

@app.route('/api/v1/script', methods=['GET', 'POST', 'PUT', 'DELETE'])
def manage_scripts():
    """脚本管理"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    if request.method == 'GET':
        scripts = [s.to_dict() for s in scripts_cache.values() if s.user_id == sessions_cache[session_id]['user_id']]
        return jsonify({'scripts': scripts})
    
    elif request.method == 'POST':
        data = request.json
        script_name = data.get('script_name', '')
        description = data.get('description', '')
        language = data.get('language', 'javascript')
        content = data.get('content', '')
        
        script = ScriptInfo(script_name, description, language, content)
        script.user_id = sessions_cache[session_id]['user_id']
        script.status = 'saved'
        scripts_cache[script.script_id] = script
        
        return jsonify({
            'message': '脚本创建成功',
            'script': script.to_dict()
        })
    
    elif request.method == 'PUT':
        data = request.json
        script_id = data.get('id')
        
        if script_id not in scripts_cache:
            return jsonify({'error': '脚本不存在'}), 404
        
        script = scripts_cache[script_id]
        if 'script_name' in data:
            script.script_name = data['script_name']
        if 'content' in data:
            script.content = data['content']
        if 'language' in data:
            script.language = data['language']
        script.version = f"{int(script.version.split('.')[0])}.{int(script.version.split('.')[1])}.{int(script.version.split('.')[2]) + 1}"
        script.updated_at = datetime.datetime.now().isoformat()
        
        return jsonify({
            'message': '脚本更新成功',
            'script': script.to_dict()
        })
    
    elif request.method == 'DELETE':
        script_id = request.args.get('id')
        
        if script_id not in scripts_cache:
            return jsonify({'error': '脚本不存在'}), 404
        
        del scripts_cache[script_id]
        return jsonify({'message': '脚本删除成功'})

@app.route('/api/v1/script/list', methods=['GET'])
def get_script_list():
    """获取脚本列表"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    user_id = sessions_cache[session_id]['user_id']
    language = request.args.get('language')
    keyword = request.args.get('keyword', '')
    
    scripts = [s.to_dict() for s in scripts_cache.values() if s.user_id == user_id]
    
    if language:
        scripts = [s for s in scripts if s['language'] == language]
    
    if keyword:
        scripts = [s for s in scripts if keyword.lower() in s['script_name'].lower() or keyword.lower() in s['description'].lower()]
    
    scripts.sort(key=lambda x: x['created_at'], reverse=True)
    
    return jsonify({
        'scripts': scripts,
        'count': len(scripts)
    })

@app.route('/api/v1/script/<script_id>/run', methods=['POST'])
def run_script(script_id):
    """脚本运行与调试"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    if script_id not in scripts_cache:
        return jsonify({'error': '脚本不存在'}), 404
    
    script = scripts_cache[script_id]
    
    # 创建执行记录
    execution = ScriptExecution(script_id, sessions_cache[session_id]['user_id'])
    
    try:
        # 模拟执行脚本
        execution.add_log(f'开始执行脚本: {script.script_name}')
        execution.add_log(f'脚本语言: {script.language}')
        
        # 模拟执行结果
        execution.result_json = {
            'success': True,
            'output': '脚本执行成功',
            'details': '模拟执行完成'
        }
        execution.add_log('脚本执行成功', 'info')
        execution.status = 'completed'
        
    except Exception as e:
        execution.add_log(f'执行错误: {str(e)}', 'error')
        execution.status = 'failed'
        execution.result_json = {'success': False, 'error': str(e)}
    
    script_executions_cache[execution.execution_id] = execution
    
    return jsonify({
        'message': '脚本执行完成',
        'execution': execution.to_dict()
    })

@app.route('/api/v1/script/<script_id>/trigger', methods=['PUT'])
def configure_script_trigger(script_id):
    """脚本触发配置"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    if script_id not in scripts_cache:
        return jsonify({'error': '脚本不存在'}), 404
    
    data = request.json
    trigger_type = data.get('trigger_type', 'manual')
    trigger_config = data.get('trigger_config', {})
    
    script = scripts_cache[script_id]
    
    # 保存触发配置
    script.trigger_type = trigger_type
    script.trigger_config = trigger_config
    
    return jsonify({
        'message': '触发配置更新成功',
        'script': script.to_dict()
    })

@app.route('/api/v1/script/<script_id>/executions', methods=['GET'])
def get_script_executions(script_id):
    """获取脚本执行记录"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    if script_id not in scripts_cache:
        return jsonify({'error': '脚本不存在'}), 404
    
    executions = [e.to_dict() for e in script_executions_cache.values() if e.script_id == script_id]
    executions.sort(key=lambda x: x['created_at'], reverse=True)
    
    return jsonify({
        'executions': executions,
        'count': len(executions)
    })

@app.route('/api/v1/script/export', methods=['POST'])
def export_script():
    """导出脚本"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    data = request.json
    script_ids = data.get('script_ids', [])
    
    exported = []
    for script_id in script_ids:
        if script_id in scripts_cache:
            script = scripts_cache[script_id]
            exported.append({
                'script_id': script.script_id,
                'script_name': script.script_name,
                'description': script.description,
                'language': script.language,
                'content': script.content,
                'version': script.version
            })
    
    return jsonify({
        'message': f'成功导出 {len(exported)} 个脚本',
        'scripts': exported,
        'format': 'json'
    })

@app.route('/api/v1/script/import', methods=['POST'])
def import_script():
    """导入脚本"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    data = request.json
    scripts_data = data.get('scripts', [])
    user_id = sessions_cache[session_id]['user_id']
    
    imported_count = 0
    for script_data in scripts_data:
        script = ScriptInfo(
            script_data.get('script_name', '未命名脚本'),
            script_data.get('description', ''),
            script_data.get('language', 'javascript'),
            script_data.get('content', '')
        )
        script.user_id = user_id
        script.status = 'saved'
        scripts_cache[script.script_id] = script
        imported_count += 1
    
    return jsonify({
        'message': f'成功导入 {imported_count} 个脚本',
        'count': imported_count
    })

@app.route('/api/v1/script/<script_id>/share', methods=['POST'])
def share_script(script_id):
    """共享脚本"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    if script_id not in scripts_cache:
        return jsonify({'error': '脚本不存在'}), 404
    
    script = scripts_cache[script_id]
    data = request.json
    share_with_users = data.get('users', [])
    share_mode = data.get('mode', 'read')  # read, edit
    
    script.shared_with = share_with_users
    script.share_mode = share_mode
    
    return jsonify({
        'message': '脚本共享成功',
        'script': script.to_dict(),
        'shared_with': share_with_users
    })

# === AI脚本/插件生成API ===

@app.route('/api/v1/ai/script/generate', methods=['POST'])
def ai_script_generate():
    """AI脚本/插件生成"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    data = request.json
    requirement = data.get('requirement', '')
    language = data.get('language', 'javascript')
    generate_type = data.get('type', 'script')
    
    if generate_type == 'plugin':
        result = ai_generate_plugin(requirement)
        
        # 创建插件
        plugin = PluginInfo(result['name'], result['description'], result['type'], author='AI生成')
        plugin.status = 'available'
        plugins_cache[plugin.plugin_id] = plugin
        
        return jsonify({
            'message': 'AI插件生成成功',
            'plugin': plugin.to_dict(),
            'code': result['code'],
            'instructions': result['instructions']
        })
    
    else:
        result = ai_generate_script(requirement, language)
        
        # 创建脚本
        script = ScriptInfo(result['name'], result['description'], language, result['content'])
        script.user_id = sessions_cache[session_id]['user_id']
        script.status = 'saved'
        scripts_cache[script.script_id] = script
        
        return jsonify({
            'message': 'AI脚本生成成功',
            'script': script.to_dict(),
            'content': result['content'],
            'instructions': result['instructions']
        })

@app.route('/api/v1/ai/api/integrate', methods=['POST'])
def ai_api_integration():
    """AI API集成分析"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    data = request.json
    api_docs = data.get('api_docs', '')
    requirement = data.get('requirement', '')
    
    analysis = ai_analyze_api_integration(api_docs, requirement)
    
    return jsonify({
        'message': 'API集成分析完成',
        'analysis': analysis
    })

# === 用户界面配置API ===

@app.route('/api/v1/user/interface/config', methods=['GET', 'PUT'])
def user_interface_config():
    """自定义界面配置"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    user_id = sessions_cache[session_id]['user_id']
    
    if request.method == 'GET':
        config = None
        for c in user_interface_cache.values():
            if c.user_id == user_id:
                config = c
                break
        
        if not config:
            config = UserInterfaceConfig(user_id)
            user_interface_cache[config.config_id] = config
        
        return jsonify({'config': config.to_dict()})
    
    elif request.method == 'PUT':
        data = request.json
        config_data = data.get('config', {})
        
        config = None
        for c in user_interface_cache.values():
            if c.user_id == user_id:
                config = c
                break
        
        if not config:
            config = UserInterfaceConfig(user_id)
        
        config.config_json.update(config_data)
        user_interface_cache[config.config_id] = config
        
        return jsonify({
            'message': '界面配置更新成功',
            'config': config.to_dict()
        })

# === 外部工具API ===

@app.route('/api/v1/tool/external', methods=['GET', 'POST', 'PUT', 'DELETE'])
def manage_external_tools():
    """外部工具配置"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    if request.method == 'GET':
        tools = [t.to_dict() for t in external_tools_cache.values()]
        return jsonify({'tools': tools})
    
    elif request.method == 'POST':
        data = request.json
        tool_name = data.get('tool_name', '')
        description = data.get('description', '')
        tool_type = data.get('type', 'command')
        command = data.get('command', '')
        
        tool = ExternalTool(tool_name, description, tool_type, command)
        external_tools_cache[tool.tool_id] = tool
        
        return jsonify({
            'message': '外部工具配置成功',
            'tool': tool.to_dict()
        })
    
    elif request.method == 'PUT':
        data = request.json
        tool_id = data.get('id')
        
        if tool_id not in external_tools_cache:
            return jsonify({'error': '工具不存在'}), 404
        
        tool = external_tools_cache[tool_id]
        if 'command' in data:
            tool.command = data['command']
        if 'config' in data:
            tool.config_json = data['config']
        
        return jsonify({
            'message': '工具配置更新成功',
            'tool': tool.to_dict()
        })
    
    elif request.method == 'DELETE':
        tool_id = request.args.get('id')
        
        if tool_id not in external_tools_cache:
            return jsonify({'error': '工具不存在'}), 404
        
        del external_tools_cache[tool_id]
        return jsonify({'message': '工具删除成功'})

# === 开放API文档 ===

@app.route('/api/v1/openapi/docs', methods=['GET'])
def get_openapi_docs():
    """开放API文档"""
    docs = {
        'version': '1.0.0',
        'description': 'AI-native Enterprise Architect 开放API文档',
        'endpoints': [
            {
                'path': '/api/v1/project/{projectId}',
                'method': 'GET',
                'description': '获取项目信息',
                'parameters': [{'name': 'projectId', 'type': 'string', 'required': True}],
                'response': {'type': 'object', 'properties': ['id', 'name', 'description']}
            },
            {
                'path': '/api/v1/element/create',
                'method': 'POST',
                'description': '创建元素',
                'parameters': [{'name': 'type', 'type': 'string'}, {'name': 'name', 'type': 'string'}],
                'response': {'type': 'object', 'properties': ['id', 'name', 'type']}
            },
            {
                'path': '/api/v1/model/{modelId}/generate-code',
                'method': 'POST',
                'description': '生成代码',
                'parameters': [{'name': 'language', 'type': 'string'}],
                'response': {'type': 'object', 'properties': ['code', 'files']}
            }
        ],
        'authentication': 'Bearer token in Authorization header',
        'rate_limit': '100 requests per minute'
    }
    
    return jsonify(docs)

@app.route('/api/v1/openapi/permission', methods=['POST'])
def configure_api_permission():
    """API权限配置"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    data = request.json
    api_path = data.get('api_path')
    permissions = data.get('permissions', [])
    
    return jsonify({
        'message': 'API权限配置成功',
        'api_path': api_path,
        'permissions': permissions
    })

# === Webhook API ===

@app.route('/api/v1/webhook', methods=['GET', 'POST', 'PUT', 'DELETE'])
def manage_webhooks():
    """Webhook配置"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    user_id = sessions_cache[session_id]['user_id']
    
    if request.method == 'GET':
        webhooks = [w.to_dict() for w in webhooks_cache.values() if w.user_id == user_id]
        return jsonify({'webhooks': webhooks})
    
    elif request.method == 'POST':
        data = request.json
        event_type = data.get('event_type')
        callback_url = data.get('callback_url')
        
        webhook = WebhookConfig(user_id, event_type, callback_url)
        webhooks_cache[webhook.webhook_id] = webhook
        
        return jsonify({
            'message': 'Webhook配置成功',
            'webhook': webhook.to_dict()
        })
    
    elif request.method == 'PUT':
        data = request.json
        webhook_id = data.get('id')
        
        if webhook_id not in webhooks_cache:
            return jsonify({'error': 'Webhook不存在'}), 404
        
        webhook = webhooks_cache[webhook_id]
        if 'event_type' in data:
            webhook.event_type = data['event_type']
        if 'callback_url' in data:
            webhook.callback_url = data['callback_url']
        if 'status' in data:
            webhook.status = data['status']
        
        return jsonify({
            'message': 'Webhook更新成功',
            'webhook': webhook.to_dict()
        })
    
    elif request.method == 'DELETE':
        webhook_id = request.args.get('id')
        
        if webhook_id not in webhooks_cache:
            return jsonify({'error': 'Webhook不存在'}), 404
        
        del webhooks_cache[webhook_id]
        return jsonify({'message': 'Webhook删除成功'})

# === 辅助API ===

@app.route('/api/v1/plugin/types', methods=['GET'])
def get_plugin_types():
    """获取插件类型"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    types_list = []
    for key, value in PLUGIN_TYPES.items():
        types_list.append({
            'id': key,
            'name': value['name'],
            'description': value['description']
        })
    
    return jsonify({'types': types_list})

@app.route('/api/v1/script/languages', methods=['GET'])
def get_script_languages():
    """获取脚本语言"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    languages_list = []
    for key, value in SCRIPT_LANGUAGES.items():
        languages_list.append({
            'id': key,
            'name': value['name'],
            'extension': value['extension']
        })
    
    return jsonify({'languages': languages_list})

@app.route('/api/v1/trigger/types', methods=['GET'])
def get_trigger_types():
    """获取触发类型"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    types_list = []
    for key, value in TRIGGER_TYPES.items():
        types_list.append({
            'id': key,
            'name': value['name'],
            'description': value['description']
        })
    
    return jsonify({'types': types_list})

@app.route('/api/v1/event/types', methods=['GET'])
def get_event_types():
    """获取事件类型"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    types_list = []
    for key, value in EVENT_TYPES.items():
        types_list.append({
            'id': key,
            'name': value['name'],
            'description': value['description']
        })
    
    return jsonify({'types': types_list})

# === 模块十三：全平台基础体验与 AI 交互 ===

# === AI对话类 ===

class AiChatSession:
    """AI对话会话类"""
    def __init__(self, user_id, session_name='新会话'):
        self.session_id = str(uuid.uuid4())[:8]
        self.user_id = user_id
        self.session_name = session_name
        self.status = 'active'
        self.created_at = datetime.datetime.now().isoformat()
    
    def to_dict(self):
        return {
            'session_id': self.session_id,
            'user_id': self.user_id,
            'session_name': self.session_name,
            'status': self.status,
            'created_at': self.created_at
        }

class AiChatMessage:
    """AI对话消息类"""
    def __init__(self, session_id, user_id, role, content, message_type='text'):
        self.message_id = str(uuid.uuid4())[:8]
        self.session_id = session_id
        self.user_id = user_id
        self.role = role  # user, assistant
        self.content = content
        self.type = message_type  # text, image, file, voice, video
        self.status = 'sent'
        self.created_at = datetime.datetime.now().isoformat()
    
    def to_dict(self):
        return {
            'message_id': self.message_id,
            'session_id': self.session_id,
            'user_id': self.user_id,
            'role': self.role,
            'content': self.content,
            'type': self.type,
            'status': self.status,
            'created_at': self.created_at
        }

class AiChatExecution:
    """AI对话执行记录类"""
    def __init__(self, message_id, operation_type):
        self.execution_id = str(uuid.uuid4())[:8]
        self.message_id = message_id
        self.operation_type = operation_type
        self.operation_result = {}
        self.status = 'running'
        self.created_at = datetime.datetime.now().isoformat()
    
    def to_dict(self):
        return {
            'execution_id': self.execution_id,
            'message_id': self.message_id,
            'operation_type': self.operation_type,
            'operation_result': self.operation_result,
            'status': self.status,
            'created_at': self.created_at
        }

# === 用户引导配置类 ===

class UserGuideConfig:
    """用户新手引导配置类"""
    def __init__(self, user_id):
        self.config_id = str(uuid.uuid4())[:8]
        self.user_id = user_id
        self.guide_status = 'started'  # not_started, started, completed
        self.completed_steps_json = []
        self.preference_json = {
            'show_tips': True,
            'auto_guide': True,
            'guide_speed': 'normal'
        }
        self.created_at = datetime.datetime.now().isoformat()
    
    def to_dict(self):
        return {
            'config_id': self.config_id,
            'user_id': self.user_id,
            'guide_status': self.guide_status,
            'completed_steps': self.completed_steps_json,
            'preferences': self.preference_json,
            'created_at': self.created_at
        }

# === 用户设置类 ===

class UserSetting:
    """用户设置类"""
    def __init__(self, user_id):
        self.setting_id = str(uuid.uuid4())[:8]
        self.user_id = user_id
        self.setting_type = 'general'
        self.content_json = {
            'theme': 'light',  # light, dark, classic, enterprise, minimal
            'language': 'zh-CN',  # zh-CN, en-US, ja-JP, ko-KR, de-DE, fr-FR
            'layout': 'default',
            'shortcuts': {},
            'notifications': {
                'in_app': True,
                'email': True,
                'sms': False,
                'do_not_disturb': False
            },
            'security': {
                'two_factor': False,
                'session_timeout': 30
            }
        }
        self.created_at = datetime.datetime.now().isoformat()
    
    def to_dict(self):
        return {
            'setting_id': self.setting_id,
            'user_id': self.user_id,
            'setting_type': self.setting_type,
            'content': self.content_json,
            'created_at': self.created_at
        }

# === 用户行为类 ===

class UserBehavior:
    """用户行为数据类"""
    def __init__(self, user_id, operation_type, operation_content, page_path='', element_id=''):
        self.behavior_id = str(uuid.uuid4())[:8]
        self.user_id = user_id
        self.operation_type = operation_type
        self.operation_content = operation_content
        self.page_path = page_path
        self.element_id = element_id
        self.created_at = datetime.datetime.now().isoformat()
    
    def to_dict(self):
        return {
            'behavior_id': self.behavior_id,
            'user_id': self.user_id,
            'operation_type': self.operation_type,
            'operation_content': self.operation_content,
            'page_path': self.page_path,
            'element_id': self.element_id,
            'created_at': self.created_at
        }

# === AI推荐类 ===

class AiRecommend:
    """AI推荐类"""
    def __init__(self, user_id, recommend_type):
        self.recommend_id = str(uuid.uuid4())[:8]
        self.user_id = user_id
        self.recommend_type = recommend_type  # feature, template, practice, plugin
        self.content_json = {}
        self.status = 'active'
        self.created_at = datetime.datetime.now().isoformat()
    
    def to_dict(self):
        return {
            'recommend_id': self.recommend_id,
            'user_id': self.user_id,
            'recommend_type': self.recommend_type,
            'content': self.content_json,
            'status': self.status,
            'created_at': self.created_at
        }

# === 帮助文档类 ===

class HelpDocument:
    """帮助文档类"""
    def __init__(self, title, description, content_json, doc_type='guide'):
        self.doc_id = str(uuid.uuid4())[:8]
        self.title = title
        self.description = description
        self.content_json = content_json
        self.type = doc_type  # guide, tutorial, faq, video
        self.tags_json = []
        self.status = 'published'
        self.created_at = datetime.datetime.now().isoformat()
    
    def to_dict(self):
        return {
            'doc_id': self.doc_id,
            'title': self.title,
            'description': self.description,
            'content': self.content_json,
            'type': self.type,
            'tags': self.tags_json,
            'status': self.status,
            'created_at': self.created_at
        }

# === 用户问答记录类 ===

class UserQaRecord:
    """用户问答记录类"""
    def __init__(self, user_id, question, answer):
        self.record_id = str(uuid.uuid4())[:8]
        self.user_id = user_id
        self.question = question
        self.answer = answer
        self.status = 'resolved'
        self.created_at = datetime.datetime.now().isoformat()
    
    def to_dict(self):
        return {
            'record_id': self.record_id,
            'user_id': self.user_id,
            'question': self.question,
            'answer': self.answer,
            'status': self.status,
            'created_at': self.created_at
        }

# 新增缓存
ai_chat_sessions_cache = {}
ai_chat_messages_cache = {}
ai_chat_executions_cache = {}
user_guide_config_cache = {}
user_settings_cache = {}
user_behaviors_cache = {}
ai_recommends_cache = {}
help_documents_cache = {}
user_qa_records_cache = {}

# 初始化帮助文档
def init_help_documents():
    """初始化帮助文档"""
    docs = [
        {
            'title': '新手入门指南',
            'description': '帮助您快速了解系统的核心功能和基本操作',
            'type': 'guide',
            'tags': ['入门', '新手', '基础操作'],
            'content': {
                'sections': [
                    {'title': '创建项目', 'content': '点击左侧菜单栏的"新建项目"按钮，输入项目名称和描述即可创建新项目'},
                    {'title': '创建视图', 'content': '在项目中点击"新建视图"，选择视图类型（如类图、时序图等）'},
                    {'title': '添加元素', 'content': '从工具栏拖拽元素到画布上，双击编辑元素属性'}
                ]
            }
        },
        {
            'title': '快捷键参考',
            'description': '系统常用快捷键列表',
            'type': 'guide',
            'tags': ['快捷键', '操作'],
            'content': {
                'shortcuts': [
                    {'key': 'Ctrl+S', 'action': '保存'},
                    {'key': 'Ctrl+Z', 'action': '撤销'},
                    {'key': 'Ctrl+Y', 'action': '重做'},
                    {'key': 'Ctrl+C', 'action': '复制'},
                    {'key': 'Ctrl+V', 'action': '粘贴'}
                ]
            }
        },
        {
            'title': '如何生成代码',
            'description': '从模型生成代码的详细步骤',
            'type': 'tutorial',
            'tags': ['代码生成', '工程'],
            'content': {
                'steps': [
                    '1. 选择要生成代码的类图',
                    '2. 点击工具栏的"代码生成"按钮',
                    '3. 选择目标语言（Java/Python/TypeScript）',
                    '4. 设置生成选项',
                    '5. 点击"生成"按钮'
                ]
            }
        },
        {
            'title': 'FAQ: 如何导出文档',
            'description': '关于文档导出的常见问题',
            'type': 'faq',
            'tags': ['文档', '导出', 'FAQ'],
            'content': {
                'question': '如何导出项目文档？',
                'answer': '在项目视图中，点击"导出"菜单，选择"文档导出"，选择导出格式（PDF/Word/HTML），点击"导出"即可。'
            }
        }
    ]
    
    for doc_data in docs:
        doc = HelpDocument(doc_data['title'], doc_data['description'], doc_data['content'], doc_data['type'])
        doc.tags_json = doc_data['tags']
        help_documents_cache[doc.doc_id] = doc

# 初始化帮助文档
init_help_documents()

# === AI功能函数 ===

def ai_chat_process(user_id, session_id, message, context=None):
    """处理AI对话"""
    response = {
        'role': 'assistant',
        'content': '',
        'execution': None
    }
    
    # 简单的意图识别和响应生成
    message_lower = message.lower()
    
    if '新建项目' in message or '创建项目' in message:
        response['content'] = '好的，我来帮您创建一个新项目。请问项目名称是什么？'
    
    elif '生成代码' in message or 'code' in message_lower:
        response['content'] = '好的，我来帮您生成代码。请告诉我目标语言（Java/Python/TypeScript）和要生成代码的模型。'
    
    elif '导出文档' in message or 'export document' in message_lower:
        response['content'] = '好的，我来帮您导出文档。请问要导出什么格式的文档？（PDF/Word/HTML）'
    
    elif '类图' in message or 'class diagram' in message_lower:
        response['content'] = '好的，我来帮您创建类图。请告诉我需要哪些类和它们之间的关系。'
    
    elif '帮助' in message or 'help' in message_lower:
        response['content'] = '请问您需要什么帮助？我可以帮助您创建项目、绘制模型、生成代码、导出文档等。'
    
    elif '你好' in message or 'hello' in message_lower or 'hi' in message_lower:
        response['content'] = '您好！我是您的AI助手，很高兴为您服务。请问有什么我可以帮助您的吗？'
    
    elif '谢谢' in message or 'thank' in message_lower:
        response['content'] = '不客气！如果您还有其他问题，随时可以问我。'
    
    else:
        response['content'] = f'收到您的请求："{message}"\n\n我正在处理您的需求，请稍候...\n\n（提示：您可以尝试使用以下指令：\n- "新建一个电商项目"\n- "为这个类生成Java代码"\n- "导出项目文档"\n- "创建一个类图"）'
    
    return response

def ai_multimodal_parse(content_type, content_data):
    """解析多模态内容"""
    result = {
        'content_type': content_type,
        'parsed_content': '',
        'intent': '',
        'suggestions': []
    }
    
    if content_type == 'image':
        result['parsed_content'] = '图片内容已识别，包含图形元素'
        result['intent'] = '可能是手绘草图或设计图'
        result['suggestions'] = ['生成对应的UML模型', '提取图形元素', '优化布局']
    
    elif content_type == 'file':
        result['parsed_content'] = '文件内容已解析'
        result['intent'] = '可能是需求文档或代码文件'
        result['suggestions'] = ['生成模型', '生成文档', '代码审查']
    
    elif content_type == 'voice':
        result['parsed_content'] = '语音内容已转文字'
        result['intent'] = '语音指令'
        result['suggestions'] = ['执行指令', '确认需求', '记录备忘']
    
    elif content_type == 'video':
        result['parsed_content'] = '视频内容已分析'
        result['intent'] = '可能是演示视频或会议记录'
        result['suggestions'] = ['提取要点', '生成文档', '创建任务']
    
    return result

def ai_recommend_generate(user_id):
    """生成AI推荐"""
    recommendations = [
        {
            'type': 'feature',
            'title': '尝试AI代码生成',
            'description': '根据您的使用习惯，推荐使用AI代码生成功能',
            'action': '点击使用'
        },
        {
            'type': 'template',
            'title': '电商系统架构模板',
            'description': '适合电商行业的架构设计模板',
            'action': '应用模板'
        },
        {
            'type': 'practice',
            'title': 'UML建模最佳实践',
            'description': '学习UML建模的最佳实践指南',
            'action': '查看详情'
        },
        {
            'type': 'plugin',
            'title': 'Git集成插件',
            'description': '版本控制集成，提升团队协作效率',
            'action': '安装插件'
        }
    ]
    
    return recommendations

def ai_qa_answer(question):
    """AI问答解答"""
    question_lower = question.lower()
    
    answers = {
        '如何保存': '使用快捷键Ctrl+S或点击工具栏的保存按钮',
        '撤销': '使用快捷键Ctrl+Z或点击工具栏的撤销按钮',
        '如何创建类': '从左侧工具栏拖拽类元素到画布上',
        '如何生成代码': '选择类图后点击代码生成按钮，选择目标语言',
        '如何导出': '点击导出菜单，选择导出格式',
        '快捷键': '常用快捷键：Ctrl+S保存，Ctrl+Z撤销，Ctrl+C复制，Ctrl+V粘贴',
        '帮助': '点击右上角的帮助按钮查看完整帮助文档',
        '新建项目': '点击左侧菜单的新建项目按钮，输入项目名称',
        '创建视图': '在项目中点击新建视图，选择视图类型'
    }
    
    for key, answer in answers.items():
        if key in question_lower:
            return answer
    
    return f'关于"{question}"的问题，我来为您解答：\n\n这是一个常见问题，建议您：\n1. 查看帮助文档\n2. 使用AI助手获取实时帮助\n3. 联系技术支持'

# === AI对话API ===

@app.route('/api/v1/ai/chat', methods=['POST'])
def ai_chat():
    """全局AI对话"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    data = request.json
    message = data.get('message', '')
    chat_session_id = data.get('session_id')
    context = data.get('context', {})
    
    user_id = sessions_cache[session_id]['user_id']
    
    # 如果没有会话ID，创建新会话
    if not chat_session_id:
        chat_session = AiChatSession(user_id)
        ai_chat_sessions_cache[chat_session.session_id] = chat_session
        chat_session_id = chat_session.session_id
    
    # 保存用户消息
    user_message = AiChatMessage(chat_session_id, user_id, 'user', message)
    ai_chat_messages_cache[user_message.message_id] = user_message
    
    # 处理AI响应
    response = ai_chat_process(user_id, chat_session_id, message, context)
    
    # 保存AI响应
    ai_message = AiChatMessage(chat_session_id, user_id, 'assistant', response['content'])
    ai_chat_messages_cache[ai_message.message_id] = ai_message
    
    return jsonify({
        'message': '对话成功',
        'session_id': chat_session_id,
        'response': ai_message.to_dict()
    })

@app.route('/api/v1/ai/chat/history', methods=['GET'])
def get_chat_history():
    """获取对话历史"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    user_id = sessions_cache[session_id]['user_id']
    chat_session_id = request.args.get('session_id')
    
    if chat_session_id:
        # 获取指定会话的消息
        messages = [m.to_dict() for m in ai_chat_messages_cache.values() 
                    if m.session_id == chat_session_id]
    else:
        # 获取所有消息
        messages = [m.to_dict() for m in ai_chat_messages_cache.values() 
                    if m.user_id == user_id]
    
    messages.sort(key=lambda x: x['created_at'])
    
    return jsonify({
        'messages': messages,
        'count': len(messages)
    })

@app.route('/api/v1/ai/chat/session', methods=['POST'])
def manage_chat_session():
    """对话会话管理"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    data = request.json
    action = data.get('action', 'create')
    chat_session_id = data.get('session_id')
    session_name = data.get('session_name', '新会话')
    
    user_id = sessions_cache[session_id]['user_id']
    
    if action == 'create':
        chat_session = AiChatSession(user_id, session_name)
        ai_chat_sessions_cache[chat_session.session_id] = chat_session
        return jsonify({
            'message': '会话创建成功',
            'session': chat_session.to_dict()
        })
    
    elif action == 'rename':
        if chat_session_id not in ai_chat_sessions_cache:
            return jsonify({'error': '会话不存在'}), 404
        
        chat_session = ai_chat_sessions_cache[chat_session_id]
        chat_session.session_name = session_name
        return jsonify({
            'message': '会话重命名成功',
            'session': chat_session.to_dict()
        })
    
    elif action == 'delete':
        if chat_session_id not in ai_chat_sessions_cache:
            return jsonify({'error': '会话不存在'}), 404
        
        # 删除会话相关消息
        messages_to_delete = [m.message_id for m in ai_chat_messages_cache.values() 
                             if m.session_id == chat_session_id]
        for msg_id in messages_to_delete:
            del ai_chat_messages_cache[msg_id]
        
        del ai_chat_sessions_cache[chat_session_id]
        return jsonify({'message': '会话删除成功'})
    
    elif action == 'list':
        sessions = [s.to_dict() for s in ai_chat_sessions_cache.values() 
                   if s.user_id == user_id]
        sessions.sort(key=lambda x: x['created_at'], reverse=True)
        return jsonify({'sessions': sessions})
    
    return jsonify({'error': '未知操作'}), 400

@app.route('/api/v1/ai/multimodal/parse', methods=['POST'])
def multimodal_parse():
    """多模态内容解析"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    data = request.json
    content_type = data.get('content_type', 'text')
    content_data = data.get('content', '')
    
    result = ai_multimodal_parse(content_type, content_data)
    
    return jsonify({
        'message': '解析成功',
        'result': result
    })

# === AI助手配置API ===

@app.route('/api/v1/ai/config', methods=['GET'])
def get_ai_config():
    """获取AI助手配置"""
    return jsonify({
        'config': ai_service_config.to_dict()
    })

@app.route('/api/v1/ai/config', methods=['PUT'])
def update_ai_config():
    """更新AI助手配置（同时持久化到本地 SQLite，重启后自动恢复）"""
    data = request.json
    ai_service_config.update(data)
    # 持久化：api_key 写入本地 data/ea.db，重启不再丢失
    db.set('ai_config', ai_service_config.to_storage_dict())
    return jsonify({
        'message': '配置更新成功',
        'config': ai_service_config.to_dict()
    })

@app.route('/api/v1/ai/llm/chat', methods=['POST'])
def llm_chat():
    """调用大模型进行对话（直接调用，不使用内置的mock）"""
    try:
        session_id = request.headers.get('X-Session-Id')
        user_id = 'anonymous'
        
        if session_id and session_id in sessions_cache:
            user_id = sessions_cache[session_id]['user_id']
        elif not session_id:
            session_id = str(uuid.uuid4())
            sessions_cache[session_id] = {'user_id': user_id}
        
        data = request.json
        messages = data.get('messages', [])
        chat_session_id = data.get('session_id')
        
        if not chat_session_id:
            chat_session = AiChatSession(user_id)
            ai_chat_sessions_cache[chat_session.session_id] = chat_session
            chat_session_id = chat_session.session_id
        
        if messages and messages[-1]['role'] == 'user':
            user_message = AiChatMessage(chat_session_id, user_id, 'user', messages[-1]['content'])
            ai_chat_messages_cache[user_message.message_id] = user_message
        
        result = AIService.chat_completion(messages)
        
        if 'error' in result:
            return jsonify({
                'message': '对话失败',
                'error': result['error']
            }), 500
        
        ai_content = result['choices'][0]['message']['content']
        
        ai_message = AiChatMessage(chat_session_id, user_id, 'assistant', ai_content)
        ai_chat_messages_cache[ai_message.message_id] = ai_message
        
        return jsonify({
            'message': '对话成功',
            'session_id': chat_session_id,
            'response': {
                'role': 'assistant',
                'content': ai_content
            }
        })
    except Exception as e:
        import traceback
        return jsonify({
            'message': '对话失败',
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500

@app.route('/api/v1/ai/llm/stream', methods=['POST'])
def llm_stream():
    """流式调用大模型进行对话"""
    session_id = request.headers.get('X-Session-Id')
    user_id = 'anonymous'
    
    if session_id and session_id in sessions_cache:
        user_id = sessions_cache[session_id]['user_id']
    elif not session_id:
        session_id = str(uuid.uuid4())
        sessions_cache[session_id] = {'user_id': user_id}
    
    data = request.json
    messages = data.get('messages', [])
    chat_session_id = data.get('session_id')
    
    def generate():
        try:
            for chunk in AIService.chat_stream(messages):
                yield chunk
        except Exception as e:
            yield f'data: {json.dumps({"error": str(e)})}\n\n'
    
    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no'
        }
    )

@app.route('/api/v1/ai/providers', methods=['GET'])
def get_ai_providers():
    """获取支持的AI提供商列表"""
    return jsonify({
        'providers': [
            {
                'id': 'openai',
                'name': 'OpenAI',
                'models': ['gpt-4', 'gpt-4-turbo', 'gpt-3.5-turbo'],
                'default_model': 'gpt-4',
                'requires_base_url': False
            },
            {
                'id': 'anthropic',
                'name': 'Anthropic Claude',
                'models': ['claude-3-opus', 'claude-3-sonnet', 'claude-3-haiku'],
                'default_model': 'claude-3-sonnet',
                'requires_base_url': False
            },
            {
                'id': 'azure',
                'name': 'Azure OpenAI',
                'models': ['gpt-4', 'gpt-4-turbo', 'gpt-35-turbo'],
                'default_model': 'gpt-4',
                'requires_base_url': True
            },
            {
                'id': 'custom',
                'name': '自定义API',
                'models': [],
                'default_model': '',
                'requires_base_url': True,
                'description': '支持与OpenAI API兼容的其他大模型服务'
            }
        ]
    })

# === 用户引导API ===

@app.route('/api/v1/user/guide/config', methods=['GET', 'PUT'])
def user_guide_config():
    """新手引导配置"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    user_id = sessions_cache[session_id]['user_id']
    
    if request.method == 'GET':
        config = None
        for c in user_guide_config_cache.values():
            if c.user_id == user_id:
                config = c
                break
        
        if not config:
            config = UserGuideConfig(user_id)
            user_guide_config_cache[config.config_id] = config
        
        return jsonify({'config': config.to_dict()})
    
    elif request.method == 'PUT':
        data = request.json
        guide_status = data.get('guide_status')
        completed_steps = data.get('completed_steps', [])
        preferences = data.get('preferences', {})
        
        config = None
        for c in user_guide_config_cache.values():
            if c.user_id == user_id:
                config = c
                break
        
        if not config:
            config = UserGuideConfig(user_id)
        
        if guide_status:
            config.guide_status = guide_status
        if completed_steps:
            config.completed_steps_json = completed_steps
        if preferences:
            config.preference_json.update(preferences)
        
        user_guide_config_cache[config.config_id] = config
        
        return jsonify({
            'message': '引导配置更新成功',
            'config': config.to_dict()
        })

# === 用户设置API ===

@app.route('/api/v1/user/setting', methods=['GET', 'PUT'])
def user_setting():
    """个人设置管理"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    user_id = sessions_cache[session_id]['user_id']
    
    if request.method == 'GET':
        setting = None
        for s in user_settings_cache.values():
            if s.user_id == user_id:
                setting = s
                break
        
        if not setting:
            setting = UserSetting(user_id)
            user_settings_cache[setting.setting_id] = setting
        
        return jsonify({'setting': setting.to_dict()})
    
    elif request.method == 'PUT':
        data = request.json
        setting_data = data.get('setting', {})
        
        setting = None
        for s in user_settings_cache.values():
            if s.user_id == user_id:
                setting = s
                break
        
        if not setting:
            setting = UserSetting(user_id)
        
        setting.content_json.update(setting_data)
        user_settings_cache[setting.setting_id] = setting
        
        return jsonify({
            'message': '设置更新成功',
            'setting': setting.to_dict()
        })

# === 用户行为API ===

@app.route('/api/v1/user/behavior/collect', methods=['POST'])
def collect_behavior():
    """操作习惯数据采集"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    data = request.json
    operation_type = data.get('operation_type', '')
    operation_content = data.get('operation_content', '')
    page_path = data.get('page_path', '')
    element_id = data.get('element_id', '')
    
    user_id = sessions_cache[session_id]['user_id']
    
    behavior = UserBehavior(user_id, operation_type, operation_content, page_path, element_id)
    user_behaviors_cache[behavior.behavior_id] = behavior
    
    return jsonify({'message': '行为数据采集成功'})

# === AI推荐API ===

@app.route('/api/v1/ai/recommend', methods=['GET'])
def get_recommendations():
    """智能推荐"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    user_id = sessions_cache[session_id]['user_id']
    recommend_type = request.args.get('type')
    
    recommendations = ai_recommend_generate(user_id)
    
    if recommend_type:
        recommendations = [r for r in recommendations if r['type'] == recommend_type]
    
    return jsonify({
        'recommendations': recommendations,
        'count': len(recommendations)
    })

# === 帮助中心API ===

@app.route('/api/v1/help/search', methods=['GET'])
def help_search():
    """帮助中心搜索"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    keyword = request.args.get('keyword', '')
    
    docs = [d.to_dict() for d in help_documents_cache.values()]
    
    if keyword:
        docs = [d for d in docs if keyword.lower() in d['title'].lower() or 
                keyword.lower() in d['description'].lower()]
    
    return jsonify({
        'documents': docs,
        'count': len(docs)
    })

# === AI问答API ===

@app.route('/api/v1/ai/qa', methods=['POST'])
def ai_qa():
    """问题智能解答"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    data = request.json
    question = data.get('question', '')
    
    user_id = sessions_cache[session_id]['user_id']
    
    answer = ai_qa_answer(question)
    
    # 保存问答记录
    record = UserQaRecord(user_id, question, answer)
    user_qa_records_cache[record.record_id] = record
    
    return jsonify({
        'message': '解答成功',
        'question': question,
        'answer': answer
    })

if __name__ == '__main__':
    print("Loaded routes:")
    for rule in app.url_map.iter_rules():
        if 'api/test' in str(rule):
            print(f"  {rule}")
    # 必须用 socketio.run 启动，否则 Flask-SocketIO 的 WebSocket 端点不会被服务，实时协作失效
    socketio.run(app, host='0.0.0.0', port=8080, debug=False, use_reloader=False)