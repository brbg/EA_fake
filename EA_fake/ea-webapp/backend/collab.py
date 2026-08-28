"""SocketIO 实时协作：在线用户追踪、加入/离开项目房间、模型更新广播。

按「拆巨石」计划从 app.py 抽出，共享状态从 core.py 导入。
"""
from flask import request
from flask_socketio import emit, join_room, leave_room
from core import socketio, sessions_cache, collab_users_cache

# 连接 sid -> (project_id, user_id)，用于断开时清理
_collab_conns = {}


def _resolve_user(session_id):
    if session_id and session_id in sessions_cache:
        s = sessions_cache[session_id]
        return s.get('user_id'), s.get('username')
    return None, None


def _broadcast_users(project_id):
    # 用实例 emit + 显式 namespace：socket 处理器和 HTTP 路由上下文都能调用
    users = list(collab_users_cache.get(project_id, {}).values())
    socketio.emit('collab_users', {'project_id': project_id, 'users': users},
                  room=project_id, namespace='/')


def emit_proposal(project_id, event, payload):
    """向项目房间广播协作变更事件（proposal_submitted / approved / rejected）。"""
    socketio.emit(event, {'project_id': project_id, **payload}, room=project_id, namespace='/')


def kick_user(project_id, user_id):
    """把某用户从项目的协作房间移除并通知其被移出（被 owner 取消 / 主动退出时调用）。

    注意：从 HTTP 路由上下文调用，不能用 flask_socketio 模块级 emit
    （它会读 flask.request.namespace，路由上下文里不存在）；改用 socketio.emit 实例方法。
    """
    for sid, (pid, uid) in list(_collab_conns.items()):
        if pid == project_id and uid == user_id:
            leave_room(project_id, sid, namespace='/')
            socketio.emit('collab_revoked', {'project_id': project_id}, to=sid, namespace='/')
            _collab_conns.pop(sid, None)
    if collab_users_cache.get(project_id, {}).pop(user_id, None) is not None:
        socketio.emit('user_left', {'username': '协作者'}, room=project_id, namespace='/')
        _broadcast_users(project_id)


@socketio.on('join_project')
def handle_join_project(data):
    project_id = data.get('project_id')
    session_id = data.get('session_id')
    # collab=true 表示用户已进入协作模式：才计入在线用户并广播加入
    # 未进协作模式仅加入房间（用于收协作变更通知），不打扰其他协作者
    collab = bool(data.get('collab'))
    user_id, username = _resolve_user(session_id)
    join_room(project_id)
    _collab_conns[request.sid] = (project_id, user_id)
    if user_id and collab:
        collab_users_cache.setdefault(project_id, {})[user_id] = username or user_id
        emit('user_joined', {'username': username or '协作者'}, room=project_id, include_self=False)
        _broadcast_users(project_id)


@socketio.on('leave_project')
def handle_leave_project(data):
    project_id = data.get('project_id')
    session_id = data.get('session_id')
    user_id, username = _resolve_user(session_id)
    leave_room(project_id)
    if user_id:
        collab_users_cache.get(project_id, {}).pop(user_id, None)
        emit('user_left', {'username': username or '协作者'}, room=project_id)
        _broadcast_users(project_id)
    if request.sid in _collab_conns:
        _collab_conns.pop(request.sid, None)


@socketio.on('element_update')
def handle_element_update(data):
    project_id = data.get('project_id')
    session_id = data.get('session_id')
    _, username = _resolve_user(session_id)
    emit('element_updated', {'username': username or '协作者'}, room=project_id, include_self=False)


@socketio.on('disconnect')
def handle_disconnect():
    info = _collab_conns.pop(request.sid, None)
    if info:
        project_id, user_id = info
        if user_id:
            collab_users_cache.get(project_id, {}).pop(user_id, None)
            _broadcast_users(project_id)
