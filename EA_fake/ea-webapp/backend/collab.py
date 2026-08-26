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
    users = list(collab_users_cache.get(project_id, {}).values())
    emit('collab_users', {'project_id': project_id, 'users': users}, room=project_id)


@socketio.on('join_project')
def handle_join_project(data):
    project_id = data.get('project_id')
    session_id = data.get('session_id')
    user_id, username = _resolve_user(session_id)
    join_room(project_id)
    _collab_conns[request.sid] = (project_id, user_id)
    if user_id:
        collab_users_cache.setdefault(project_id, {})[user_id] = username or user_id
        emit('user_joined', {'username': username or '协作者'}, room=project_id)
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
