"""用户认证 API（Blueprint）：注册 / 登录 / 登出 / 会话验证。

按「拆巨石」计划从 app.py 抽出的独立模块，共享状态从 core.py 导入。
"""
import uuid
import datetime
from flask import Blueprint, request, jsonify
from core import load_users, save_users, hash_password, verify_password, sessions_cache, generate_collab_id

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/api/auth/register', methods=['POST'])
def register():
    """用户注册"""
    data = request.json
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')

    if not username or not email or not password:
        return jsonify({'error': '缺少必要字段'}), 400

    users = load_users()

    if username in users:
        return jsonify({'error': '用户名已存在'}), 400

    if email in [u['email'] for u in users.values()]:
        return jsonify({'error': '邮箱已被注册'}), 400

    user_id = generate_collab_id(users)
    users[username] = {
        'id': user_id,
        'username': username,
        'email': email,
        'password': hash_password(password),
        'created_at': datetime.datetime.now().isoformat(),
        'role': 'user',
        'tour_pending': True  # 首次注册后登录时返回 is_new，前端据此自动弹出引导
    }

    save_users(users)

    return jsonify({
        'message': '注册成功',
        'user': {
            'id': user_id,
            'username': username,
            'email': email
        }
    })


@auth_bp.route('/api/auth/login', methods=['POST'])
def login():
    """用户登录"""
    data = request.json
    username = data.get('username')
    password = data.get('password')

    users = load_users()

    if username not in users:
        return jsonify({'error': '用户名或密码错误'}), 401

    user = users[username]
    if not verify_password(password, user['password']):
        return jsonify({'error': '用户名或密码错误'}), 401

    # 首次注册后的首次登录：返回 is_new，消费掉 tour_pending（一次性）
    is_new = bool(user.get('tour_pending'))
    if is_new:
        user['tour_pending'] = False
        save_users(users)

    # 创建会话
    session_id = str(uuid.uuid4())
    sessions_cache[session_id] = {
        'user_id': user['id'],
        'username': username,
        'login_time': datetime.datetime.now().isoformat()
    }

    return jsonify({
        'message': '登录成功',
        'session_id': session_id,
        'is_new': is_new,
        'user': {
            'id': user['id'],
            'username': username,
            'email': user['email'],
            'role': user['role']
        }
    })


@auth_bp.route('/api/auth/logout', methods=['POST'])
def logout():
    """用户登出"""
    session_id = request.headers.get('X-Session-Id')
    if session_id in sessions_cache:
        del sessions_cache[session_id]
    return jsonify({'message': '登出成功'})


@auth_bp.route('/api/auth/validate', methods=['GET'])
def validate_session():
    """验证会话"""
    session_id = request.headers.get('X-Session-Id')
    if session_id in sessions_cache:
        session_data = sessions_cache[session_id]
        role = 'user'
        for u in load_users().values():
            if u.get('id') == session_data['user_id']:
                role = u.get('role', 'user')
                break
        return jsonify({
            'valid': True,
            'user': {
                'id': session_data['user_id'],
                'username': session_data['username'],
                'role': role
            }
        })
    return jsonify({'valid': False}), 401
