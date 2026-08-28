"""协作 HTTP API：按账户 id 加入他人项目、查看/取消/退出协作者、协作变更申请审批。

安全说明：加入即把当前用户加为目标项目的 editor 成员。任何登录用户知道对方
6 位账户 id 即可加入，适合本地/演示场景的协作共享；生产环境应加 owner 批准或邀请制。
协作者不能直接保存模型，需提交「变更申请」由项目拥有者审批后落库（类 GitHub PR）。
"""
import db
import datetime
import uuid
from flask import Blueprint, request, jsonify
from core import (
    _require_user_id, _find_user_by_id, load_users, load_projects, save_project,
    load_model_from_cache, save_model,
    get_knowledge, log_knowledge, build_knowledge_context,
)
from collab import kick_user, emit_proposal, _collab_conns

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


# === 协作变更申请（类 GitHub PR：协作者提交 → owner 审批后落库）===

def _load_proposals(project_id):
    return db.get(f'collab_proposals:{project_id}', []) or []


def _save_proposals(project_id, proposals):
    db.set(f'collab_proposals:{project_id}', proposals)


def _apply_model_data(model, data):
    """把变更快照写入模型对象（与 update_model 一致）。"""
    if not isinstance(data, dict):
        return
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


@collab_routes_bp.route('/api/v1/project/join-current', methods=['POST'])
def join_current_project():
    """按 owner 账户 id 加入其当前打开的项目（不列全部项目，直接进当前项目）。"""
    user_id = _require_user_id()
    if user_id is None:
        return jsonify({'error': '未登录'}), 401
    data = request.json or {}
    owner_id = (data.get('owner_user_id') or data.get('user_id') or '').strip()
    if not owner_id:
        return jsonify({'error': '请提供对方账户 ID'}), 400
    # 从 socket 连接里找 owner 当前打开的项目（owner 打开项目即 join 房间）
    owner_project = None
    for sid, (pid, uid) in reversed(list(_collab_conns.items())):
        if uid == owner_id:
            owner_project = pid
            break
    if not owner_project:
        return jsonify({'error': '该用户当前未打开任何项目'}), 404
    project = load_projects().get(owner_project)
    if project is None:
        return jsonify({'error': '项目不存在'}), 404
    if project.owner_id == user_id:
        return jsonify({'error': '这是你自己的项目'}), 400
    if user_id not in project.permissions:
        project.add_member(user_id, 'editor')
        save_project(project)
    return jsonify({'message': '已加入协作', 'project': {'id': project.id, 'name': project.name}})


@collab_routes_bp.route('/api/v1/project/<project_id>/proposals', methods=['GET'])
def list_proposals(project_id):
    """列出项目的变更申请（owner 或成员可查；不含 data 快照，保持列表轻量）。"""
    user_id = _require_user_id()
    if user_id is None:
        return jsonify({'error': '未登录'}), 401
    project = load_projects().get(project_id)
    if project is None:
        return jsonify({'error': '项目不存在'}), 404
    if not _is_member(project, user_id):
        return jsonify({'error': '无权限查看该项目'}), 403
    proposals = _load_proposals(project_id)
    return jsonify({'proposals': [
        {k: p[k] for k in ('id', 'project_id', 'submitter_id', 'submitter_name',
                           'title', 'status', 'created_at', 'applied_at')}
        for p in proposals
    ]})


@collab_routes_bp.route('/api/v1/project/<project_id>/proposals', methods=['POST'])
def submit_proposal(project_id):
    """协作者提交变更申请（携带模型快照；owner 不能提交，可直接保存）。"""
    user_id = _require_user_id()
    if user_id is None:
        return jsonify({'error': '未登录'}), 401
    project = load_projects().get(project_id)
    if project is None:
        return jsonify({'error': '项目不存在'}), 404
    if project.owner_id == user_id:
        return jsonify({'error': '你是项目拥有者，可直接保存，无需提交变更申请'}), 400
    if user_id not in project.permissions:
        return jsonify({'error': '你不是本项目协作者'}), 403
    data = request.json or {}
    title = (data.get('title') or '变更申请').strip()[:100]
    proposal = {
        'id': str(uuid.uuid4())[:8],
        'project_id': project_id,
        'submitter_id': user_id,
        'submitter_name': _username_of(user_id),
        'title': title,
        'data': data.get('data') or {},
        'status': 'pending',
        'created_at': datetime.datetime.now().isoformat(),
        'applied_at': None,
    }
    proposals = _load_proposals(project_id)
    proposals.insert(0, proposal)
    _save_proposals(project_id, proposals)
    emit_proposal(project_id, 'proposal_submitted',
                  {'submitter': proposal['submitter_name'], 'title': title})
    return jsonify({'message': '变更申请已提交，等待项目拥有者审批',
                    'proposal': {'id': proposal['id'], 'status': proposal['status']}})


@collab_routes_bp.route('/api/v1/project/<project_id>/proposals/<proposal_id>/approve', methods=['POST'])
def approve_proposal(project_id, proposal_id):
    """项目拥有者批准变更：把快照写入模型，标记已批准。"""
    user_id = _require_user_id()
    if user_id is None:
        return jsonify({'error': '未登录'}), 401
    project = load_projects().get(project_id)
    if project is None:
        return jsonify({'error': '项目不存在'}), 404
    if project.owner_id != user_id:
        return jsonify({'error': '只有项目拥有者可以审批变更'}), 403
    proposals = _load_proposals(project_id)
    p = next((x for x in proposals if x['id'] == proposal_id), None)
    if p is None:
        return jsonify({'error': '变更申请不存在'}), 404
    if p['status'] != 'pending':
        return jsonify({'error': '该申请已处理'}), 400
    model = load_model_from_cache(project_id)
    if model is None:
        return jsonify({'error': '模型不存在'}), 404
    _apply_model_data(model, p.get('data') or {})
    save_model(project_id, model)
    p['status'] = 'approved'
    p['applied_at'] = datetime.datetime.now().isoformat()
    _save_proposals(project_id, proposals)
    emit_proposal(project_id, 'proposal_approved', {'title': p['title']})
    return jsonify({'message': '已批准并应用该变更'})


@collab_routes_bp.route('/api/v1/project/<project_id>/proposals/<proposal_id>/reject', methods=['POST'])
def reject_proposal(project_id, proposal_id):
    """项目拥有者拒绝变更。"""
    user_id = _require_user_id()
    if user_id is None:
        return jsonify({'error': '未登录'}), 401
    project = load_projects().get(project_id)
    if project is None:
        return jsonify({'error': '项目不存在'}), 404
    if project.owner_id != user_id:
        return jsonify({'error': '只有项目拥有者可以审批变更'}), 403
    proposals = _load_proposals(project_id)
    p = next((x for x in proposals if x['id'] == proposal_id), None)
    if p is None:
        return jsonify({'error': '变更申请不存在'}), 404
    if p['status'] != 'pending':
        return jsonify({'error': '该申请已处理'}), 400
    p['status'] = 'rejected'
    _save_proposals(project_id, proposals)
    emit_proposal(project_id, 'proposal_rejected', {'title': p['title']})
    return jsonify({'message': '已拒绝该变更申请'})


# === 项目知识库（AI 每次调用自动记录关键结论，供后续调用注入上下文）===

@collab_routes_bp.route('/api/v1/project/<project_id>/knowledge', methods=['GET'])
def list_knowledge(project_id):
    """列出项目知识库条目。"""
    user_id = _require_user_id()
    if user_id is None:
        return jsonify({'error': '未登录'}), 401
    project = load_projects().get(project_id)
    if project is None:
        return jsonify({'error': '项目不存在'}), 404
    if not _is_member(project, user_id):
        return jsonify({'error': '无权限'}), 403
    return jsonify({'knowledge': get_knowledge(project_id)})


@collab_routes_bp.route('/api/v1/project/<project_id>/knowledge', methods=['POST'])
def add_knowledge(project_id):
    """手动添加一条知识（如 AI 助手「记住：xxx」也可落到这里）。"""
    user_id = _require_user_id()
    if user_id is None:
        return jsonify({'error': '未登录'}), 401
    project = load_projects().get(project_id)
    if project is None:
        return jsonify({'error': '项目不存在'}), 404
    if not _is_member(project, user_id):
        return jsonify({'error': '无权限'}), 403
    data = request.json or {}
    summary = data.get('summary') or data.get('content') or ''
    if not summary.strip():
        return jsonify({'error': '内容不能为空'}), 400
    log_knowledge(project_id, data.get('source') or '手动', summary)
    return jsonify({'message': '已记录到项目知识库'})


@collab_routes_bp.route('/api/v1/project/<project_id>/knowledge/<entry_id>', methods=['DELETE'])
def delete_knowledge(project_id, entry_id):
    """删除一条知识。"""
    user_id = _require_user_id()
    if user_id is None:
        return jsonify({'error': '未登录'}), 401
    project = load_projects().get(project_id)
    if project is None:
        return jsonify({'error': '项目不存在'}), 404
    if not _is_member(project, user_id):
        return jsonify({'error': '无权限'}), 403
    entries = [e for e in get_knowledge(project_id, 200) if e.get('id') != entry_id]
    db.set(f'knowledge:{project_id}', entries)
    return jsonify({'message': '已删除'})
