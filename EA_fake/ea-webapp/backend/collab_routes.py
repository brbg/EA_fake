"""协作 HTTP API：按账户 id 加入他人项目、查看/取消/退出协作者。

安全说明：加入即把当前用户加为目标项目的 editor 成员。任何登录用户知道对方
6 位账户 id 即可加入，适合本地/演示场景的协作共享；生产环境应加 owner 批准或邀请制。
"""
from flask import Blueprint, jsonify
from core import (
    _require_user_id, _find_user_by_id, load_users, load_projects, save_project,
)
from collab import kick_user

collab_routes_bp = Blueprint('collab', __name__)


def _is_member(project, user_id):
    """owner 或 permissions 成员均视为可协作。"""
    return project.owner_id == user_id or user_id in project.permissions


def _username_of(user_id):
    """按账户 id 反查用户名（找不到则回退 id 本身）。"""
    user = _find_user_by_id(user_id)
    return user.get('username', user_id) if user else user_id


@collab_routes_bp.route('/api/v1/users/<user_id>/projects', methods=['GET'])
def list_user_projects(user_id):
    """列出指定账户 id 拥有的项目（用于协作：输入对方 id 后查看其项目）。"""
    if _require_user_id() is None:
        return jsonify({'error': '未登录'}), 401
    projects = [
        {'id': p.id, 'name': p.name, 'description': p.description, 'created_at': p.created_at}
        for p in load_projects().values() if p.owner_id == user_id
    ]
    return jsonify({'projects': projects})


@collab_routes_bp.route('/api/v1/project/<project_id>/join', methods=['POST'])
def join_project(project_id):
    """加入一个项目为 editor 协作者。"""
    user_id = _require_user_id()
    if user_id is None:
        return jsonify({'error': '未登录'}), 401
    projects = load_projects()
    project = projects.get(project_id)
    if project is None:
        return jsonify({'error': '项目不存在'}), 404
    if project.owner_id == user_id:
        return jsonify({'error': '这是你自己的项目'}), 400
    if user_id not in project.permissions:
        project.add_member(user_id, 'editor')
        save_project(project)
    return jsonify({'message': '已加入项目协作', 'project': {'id': project.id, 'name': project.name}})


@collab_routes_bp.route('/api/v1/project/<project_id>/collaborators', methods=['GET'])
def list_collaborators(project_id):
    """列出项目的协作者（owner 或成员可查）。"""
    user_id = _require_user_id()
    if user_id is None:
        return jsonify({'error': '未登录'}), 401
    project = load_projects().get(project_id)
    if project is None:
        return jsonify({'error': '项目不存在'}), 404
    if not _is_member(project, user_id):
        return jsonify({'error': '无权限查看该项目协作者'}), 403
    members = [
        {'user_id': m.get('user_id'), 'username': _username_of(m.get('user_id')),
         'role': m.get('role'), 'joined_at': m.get('joined_at')}
        for m in project.members
    ]
    return jsonify({'owner_id': project.owner_id, 'owner_name': _username_of(project.owner_id),
                    'members': members})


@collab_routes_bp.route('/api/v1/project/<project_id>/collaborators/<collab_user_id>', methods=['DELETE'])
def revoke_collaborator(project_id, collab_user_id):
    """项目 owner 取消指定协作者（移出成员 + 踢出实时房间）。"""
    user_id = _require_user_id()
    if user_id is None:
        return jsonify({'error': '未登录'}), 401
    project = load_projects().get(project_id)
    if project is None:
        return jsonify({'error': '项目不存在'}), 404
    if project.owner_id != user_id:
        return jsonify({'error': '只有项目拥有者可以取消协作'}), 403
    if collab_user_id not in project.permissions:
        return jsonify({'error': '该用户不是本项目协作者'}), 404
    project.remove_member(collab_user_id)
    save_project(project)
    kick_user(project_id, collab_user_id)
    return jsonify({'message': '已取消该协作者'})


@collab_routes_bp.route('/api/v1/project/<project_id>/leave', methods=['POST'])
def leave_project(project_id):
    """协作者主动退出项目协作。"""
    user_id = _require_user_id()
    if user_id is None:
        return jsonify({'error': '未登录'}), 401
    project = load_projects().get(project_id)
    if project is None:
        return jsonify({'error': '项目不存在'}), 404
    if project.owner_id == user_id:
        return jsonify({'error': '项目拥有者不能退出，可取消协作者'}), 400
    if user_id in project.permissions:
        project.remove_member(user_id)
        save_project(project)
        kick_user(project_id, user_id)
    return jsonify({'message': '已退出协作'})
