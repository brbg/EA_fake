"""后台管理 API（Blueprint，仅管理员）。

按「拆巨石」计划从 app.py 抽出，共享辅助从 core.py 导入。
"""
import datetime
from flask import Blueprint, request, jsonify
from core import (
    _require_admin, _find_user_by_id, _delete_project_data,
    load_users, save_users, load_projects, hash_password, sessions_cache,
    generate_collab_id,
)

admin_bp = Blueprint('admin', __name__)


@admin_bp.route('/api/admin/users', methods=['GET'])
def admin_list_users():
    """管理员：用户列表（含项目数；password 绝不下发）"""
    admin = _require_admin()
    if admin is None:
        return jsonify({'error': '需要管理员权限'}), 403
    projects = load_projects()
    result = []
    for u in load_users().values():
        project_count = sum(1 for p in projects.values() if p.owner_id == u.get('id'))
        result.append({
            'id': u.get('id'), 'username': u.get('username'), 'email': u.get('email'),
            'role': u.get('role', 'user'), 'created_at': u.get('created_at'),
            'project_count': project_count
        })
    return jsonify({'users': result})


@admin_bp.route('/api/admin/users', methods=['POST'])
def admin_create_user():
    """管理员：代建用户"""
    admin = _require_admin()
    if admin is None:
        return jsonify({'error': '需要管理员权限'}), 403
    data = request.json or {}
    username = (data.get('username') or '').strip()
    email = (data.get('email') or '').strip()
    password = data.get('password') or ''
    role = data.get('role', 'user')
    if not username or not email or not password:
        return jsonify({'error': '缺少必要字段'}), 400
    if role not in ('user', 'admin'):
        return jsonify({'error': '角色必须是 user 或 admin'}), 400
    users = load_users()
    if username in users:
        return jsonify({'error': '用户名已存在'}), 400
    if email in [u['email'] for u in users.values()]:
        return jsonify({'error': '邮箱已被注册'}), 400
    users[username] = {
        'id': generate_collab_id(users),
        'username': username,
        'email': email,
        'password': hash_password(password),
        'created_at': datetime.datetime.now().isoformat(),
        'role': role
    }
    save_users(users)
    return jsonify({'message': '用户创建成功', 'username': username})


@admin_bp.route('/api/admin/users/<user_id>', methods=['PUT'])
def admin_update_user(user_id):
    """管理员：编辑用户（email/密码/角色）"""
    admin = _require_admin()
    if admin is None:
        return jsonify({'error': '需要管理员权限'}), 403
    target = _find_user_by_id(user_id)
    if target is None:
        return jsonify({'error': '用户不存在'}), 404
    data = request.json or {}
    users = load_users()
    user = users.get(target['username'])
    if user is None:
        return jsonify({'error': '用户不存在'}), 404
    if data.get('email'):
        new_email = data['email'].strip()
        if new_email != user['email'] and new_email in [u['email'] for u in users.values()]:
            return jsonify({'error': '邮箱已被注册'}), 400
        user['email'] = new_email
    if data.get('password'):
        user['password'] = hash_password(data['password'])
    if data.get('role') in ('user', 'admin'):
        if user['id'] == admin['id'] and data['role'] != 'admin':
            return jsonify({'error': '不能取消自己的管理员权限'}), 400
        user['role'] = data['role']
    save_users(users)
    return jsonify({'message': '用户已更新'})


@admin_bp.route('/api/admin/users/<user_id>', methods=['DELETE'])
def admin_delete_user(user_id):
    """管理员：删除用户（级联删其项目；禁止删自己）"""
    admin = _require_admin()
    if admin is None:
        return jsonify({'error': '需要管理员权限'}), 403
    if user_id == admin['id']:
        return jsonify({'error': '不能删除自己'}), 403
    target = _find_user_by_id(user_id)
    if target is None:
        return jsonify({'error': '用户不存在'}), 404
    deleted = 0
    for p in list(load_projects().values()):
        if p.owner_id == user_id:
            _delete_project_data(p.id, p.model_id or p.id)
            deleted += 1
    users = load_users()
    if target['username'] in users:
        del users[target['username']]
        save_users(users)
    for sid in [s for s, v in sessions_cache.items() if v.get('user_id') == user_id]:
        sessions_cache.pop(sid, None)
    return jsonify({'message': '用户已删除', 'deleted_projects': deleted})


@admin_bp.route('/api/admin/users/<user_id>/projects', methods=['GET'])
def admin_list_user_projects(user_id):
    """管理员：某用户的项目列表"""
    admin = _require_admin()
    if admin is None:
        return jsonify({'error': '需要管理员权限'}), 403
    projects = [p.to_dict() for p in load_projects().values() if p.owner_id == user_id]
    return jsonify({'projects': projects})


@admin_bp.route('/api/admin/projects/<project_id>', methods=['DELETE'])
def admin_delete_project(project_id):
    """管理员：删除单个项目"""
    admin = _require_admin()
    if admin is None:
        return jsonify({'error': '需要管理员权限'}), 403
    project = load_projects().get(project_id)
    if project is None:
        return jsonify({'error': '项目不存在'}), 404
    _delete_project_data(project_id, project.model_id or project_id)
    return jsonify({'message': '项目已删除'})
