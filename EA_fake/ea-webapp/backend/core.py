"""共享基础设施：Flask app、SocketIO、内存缓存、公共辅助函数、AI 服务。

供 app.py 与各 Blueprint 模块导入，避免循环依赖。
按「拆巨石」计划从 app.py 抽取，保持行为不变。
"""
import os
import secrets
import json
import datetime
import bcrypt
import requests
import db
from models import Project, SimpleModel
from flask import Flask, request
from flask_cors import CORS
from flask_socketio import SocketIO

# === Flask 应用 ===
app = Flask(__name__, template_folder='templates', static_folder='../dist')
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY') or secrets.token_hex(32)
app.config['UPLOAD_FOLDER'] = '../uploads'
app.config['MODEL_FOLDER'] = '../models'
app.config['USER_FOLDER'] = '../users'
app.config['VERSION_FOLDER'] = '../versions'

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['MODEL_FOLDER'], exist_ok=True)
os.makedirs(app.config['USER_FOLDER'], exist_ok=True)
os.makedirs(app.config['VERSION_FOLDER'], exist_ok=True)

CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# 内存缓存（读穿缓存：命中直接返回，未命中从 db 加载并回填）
models_cache = {}
users_cache = {}
projects_cache = {}
sessions_cache = {}
bookmarks_cache = {}
snapshots_cache = {}
operation_logs_cache = {}
file_locks_cache = {}
er_views_cache = {}
data_dictionary_cache = {}
versions_cache = {}
branches_cache = {}
reviews_cache = {}
# SocketIO 协作：project_id -> {user_id: username}
collab_users_cache = {}

# 初始化 SQLite 持久化
db.init_db()


def migrate_json_to_db():
    """一次性迁移：把旧的 JSON 文件数据导入 SQLite（仅当 DB 为空时执行）。"""
    if db.keys():
        return
    model_dir = app.config['MODEL_FOLDER']
    if os.path.isdir(model_dir):
        for filename in os.listdir(model_dir):
            if filename.endswith('.json') and not filename.endswith('_project.json') and not filename.endswith('_comments.json'):
                model_id = filename[:-5]
                try:
                    with open(os.path.join(model_dir, filename), 'r', encoding='utf-8') as f:
                        db.set(f'model:{model_id}', json.load(f))
                except (json.JSONDecodeError, OSError):
                    pass
            elif filename.endswith('_project.json'):
                project_id = filename[:-13]
                try:
                    with open(os.path.join(model_dir, filename), 'r', encoding='utf-8') as f:
                        db.set(f'project:{project_id}', json.load(f))
                except (json.JSONDecodeError, OSError):
                    pass
    users_path = os.path.join(app.config['USER_FOLDER'], 'users.json')
    if os.path.exists(users_path):
        try:
            with open(users_path, 'r', encoding='utf-8') as f:
                db.set('users', json.load(f))
        except (json.JSONDecodeError, OSError):
            pass


migrate_json_to_db()


# === 用户管理 ===

def hash_password(password):
    """使用 bcrypt 对密码进行加盐哈希"""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def verify_password(password, hashed):
    """校验密码（bcrypt），哈希格式非法时安全返回 False"""
    try:
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
    except (ValueError, TypeError):
        return False


def load_users():
    """加载用户数据"""
    return db.get('users', {})


def save_users(users):
    """保存用户数据"""
    db.set('users', users)


def generate_collab_id(users):
    """生成一个未被占用的 6 位随机账户 id 码（100000-999999），用于协作互认。"""
    existing = {str(u.get('id', '')) for u in users.values()}
    while True:
        code = str(secrets.randbelow(900000) + 100000)
        if code not in existing:
            return code


def ensure_admin_account():
    """首次启动幂等创建管理员账号 admin/admin123（role=admin）。"""
    users = load_users()
    if 'admin' in users:
        return
    users['admin'] = {
        'id': 'admin',
        'username': 'admin',
        'email': 'admin@localhost',
        'password': hash_password('admin123'),
        'created_at': datetime.datetime.now().isoformat(),
        'role': 'admin'
    }
    save_users(users)


ensure_admin_account()


# === 项目管理 ===

def load_projects():
    """加载项目数据"""
    projects = {}
    for key in db.keys('project:'):
        project_id = key[len('project:'):]
        data = db.get(key)
        if data is not None:
            try:
                projects[project_id] = Project.from_dict(data)
            except Exception:
                pass
    return projects


def save_project(project):
    """保存项目"""
    db.set(f'project:{project.id}', project.to_dict())


def migrate_collab_ids():
    """把存量用户 id 迁移成 6 位数字码（幂等：已是 6 位数字则跳过）。

    同时更新项目 owner_id / permissions / members 及活跃会话里引用的旧 id。
    须在 load_projects/save_project 定义后调用。
    """
    users = load_users()
    old_to_new = {}
    for username, u in list(users.items()):
        uid = str(u.get('id', ''))
        if len(uid) == 6 and uid.isdigit():
            continue
        old_to_new[uid] = generate_collab_id(users)
        u['id'] = old_to_new[uid]
    if not old_to_new:
        return
    for project in load_projects().values():
        if project.owner_id in old_to_new:
            project.owner_id = old_to_new[project.owner_id]
        project.permissions = {old_to_new.get(k, k): v for k, v in project.permissions.items()}
        for m in project.members:
            if m.get('user_id') in old_to_new:
                m['user_id'] = old_to_new[m['user_id']]
        save_project(project)
    for s in sessions_cache.values():
        if s.get('user_id') in old_to_new:
            s['user_id'] = old_to_new[s['user_id']]
    save_users(users)


migrate_collab_ids()


# === AI服务配置 ===

class AIServiceConfig:
    """AI服务配置类"""
    def __init__(self):
        self.provider = 'openai'  # openai, anthropic, azure, custom
        self.api_key = os.getenv('OPENAI_API_KEY', '')
        self.base_url = os.getenv('OPENAI_BASE_URL', 'https://api.openai.com/v1')
        self.model = os.getenv('OPENAI_MODEL', 'gpt-4')
        self.reasoning_model = os.getenv('OPENAI_REASONING_MODEL', '')
        self.max_tokens = 2000
        self.temperature = 0.7
        self.stream = True
        self.include_context = True
        self.enabled = bool(self.api_key)

    def to_dict(self):
        return {
            'provider': self.provider,
            'base_url': self.base_url,
            'model': self.model,
            'reasoning_model': self.reasoning_model,
            'max_tokens': self.max_tokens,
            'temperature': self.temperature,
            'stream': self.stream,
            'includeContext': self.include_context,
            'enabled': self.enabled,
            'has_api_key': bool(self.api_key)
        }

    def to_storage_dict(self):
        """落库用的完整配置（含 api_key，只写入本地 SQLite，不对外返回）"""
        return {
            'provider': self.provider,
            'api_key': self.api_key,
            'base_url': self.base_url,
            'model': self.model,
            'reasoning_model': self.reasoning_model,
            'max_tokens': self.max_tokens,
            'temperature': self.temperature,
            'stream': self.stream,
            'includeContext': self.include_context,
            'enabled': self.enabled
        }

    def update(self, config_dict):
        """更新配置"""
        if 'provider' in config_dict:
            self.provider = config_dict['provider']
        if 'api_key' in config_dict:
            self.api_key = config_dict['api_key']
            self.enabled = bool(self.api_key)
        if 'base_url' in config_dict:
            self.base_url = config_dict['base_url']
        if 'model' in config_dict:
            self.model = config_dict['model']
        if 'reasoning_model' in config_dict:
            self.reasoning_model = config_dict['reasoning_model']
        if 'max_tokens' in config_dict:
            self.max_tokens = config_dict['max_tokens']
        if 'temperature' in config_dict:
            self.temperature = config_dict['temperature']
        if 'stream' in config_dict:
            self.stream = config_dict['stream']
        if 'includeContext' in config_dict:
            self.include_context = bool(config_dict['includeContext'])


ai_service_config = AIServiceConfig()


def _load_ai_config_from_db():
    """启动时从持久层恢复 AI 配置（环境变量作默认，落库配置优先）"""
    saved = db.get('ai_config')
    if isinstance(saved, dict) and saved:
        ai_service_config.update(saved)


_load_ai_config_from_db()


class AIService:
    """AI服务类 - 统一接口调用大模型（兼容OpenAI格式）"""

    @staticmethod
    def chat_completion(messages, config=None, max_tokens=None, temperature=None, use_reasoning=False):
        """调用大模型进行对话。use_reasoning=True 时走推理模型（未配置则回退普通模型）。"""
        if config is None:
            config = ai_service_config
        if not config.enabled:
            return {'error': 'AI服务未启用，请配置API密钥'}
        try:
            return AIService._call_api(messages, config, max_tokens=max_tokens,
                                       temperature=temperature, use_reasoning=use_reasoning)
        except Exception as e:
            return {'error': f'AI服务调用失败: {str(e)}'}

    @staticmethod
    def _call_api(messages, config, max_tokens=None, temperature=None, use_reasoning=False):
        """通用API调用（兼容OpenAI格式）。推理模型不支持 temperature，调用时去掉。"""
        model = config.model
        include_temperature = True
        if use_reasoning and getattr(config, 'reasoning_model', ''):
            model = config.reasoning_model
            include_temperature = False

        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {config.api_key}'
        }
        payload = {
            'model': model,
            'messages': messages,
            'max_tokens': max_tokens if max_tokens is not None else config.max_tokens,
            'stream': False
        }
        if include_temperature:
            payload['temperature'] = temperature if temperature is not None else config.temperature

        response = requests.post(
            f'{config.base_url.rstrip("/")}/chat/completions',
            headers=headers,
            json=payload,
            timeout=60
        )
        if response.status_code != 200:
            return {'error': f'API调用失败: {response.status_code} - {response.text}'}
        return response.json()

    @staticmethod
    def chat_stream(messages, config=None, use_reasoning=False):
        """流式调用大模型。use_reasoning=True 时走推理模型（如 deepseek-reasoner）：
        去掉 temperature（推理模型不支持）、加大 max_tokens 容纳思考过程 + 答案。"""
        if config is None:
            config = ai_service_config
        if not config.enabled:
            yield f'data: {json.dumps({"error": "AI服务未启用，请配置API密钥"})}\n\n'
            return
        try:
            model = config.model
            include_temperature = True
            max_tokens = config.max_tokens
            if use_reasoning and getattr(config, 'reasoning_model', ''):
                model = config.reasoning_model
                include_temperature = False
                max_tokens = 8192  # 推理模型需要更大空间（思考过程 + 最终答案）
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {config.api_key}'
            }
            payload = {
                'model': model,
                'messages': messages,
                'max_tokens': max_tokens,
                'stream': True
            }
            if include_temperature:
                payload['temperature'] = config.temperature
            response = requests.post(
                f'{config.base_url.rstrip("/")}/chat/completions',
                headers=headers,
                json=payload,
                timeout=60,
                stream=True
            )
            if response.status_code != 200:
                yield f'data: {json.dumps({"error": f"API调用失败: {response.status_code}"})}\n\n'
                return
            for line in response.iter_lines():
                if line:
                    decoded_line = line.decode('utf-8')
                    if decoded_line.startswith('data:'):
                        yield decoded_line + '\n\n'
        except Exception as e:
            yield f'data: {json.dumps({"error": str(e)})}\n\n'


# === 模型与鉴权辅助 ===

def load_model_from_cache(model_id):
    """从缓存加载模型（缓存未命中时从 db 读穿）"""
    if model_id in models_cache:
        return models_cache[model_id]
    data = db.get(f'model:{model_id}')
    if data is not None:
        model = SimpleModel.from_dict(data)
        models_cache[model_id] = model
        return model
    return None


def save_model(model_id, model):
    """保存模型"""
    db.set(f'model:{model_id}', model.to_dict())
    models_cache[model_id] = model


def _require_user_id():
    """从请求头取会话，返回当前用户 id；未登录返回 None"""
    session_id = request.headers.get('X-Session-Id')
    if session_id in sessions_cache:
        return sessions_cache[session_id]['user_id']
    return None


def _model_owned_by(model, user_id):
    """模型是否属于该用户（无 owner 的旧数据不属于任何人）"""
    return model is not None and getattr(model, 'owner_id', '') == user_id


def _can_access_model(model, user_id, model_id):
    """是否可访问模型：owner，或该模型对应项目的成员（协作加入者）。"""
    if _model_owned_by(model, user_id):
        return True
    project = load_projects().get(model_id)
    return project is not None and user_id in project.permissions


def get_knowledge(project_id, limit=30):
    """读取项目知识库（历次 AI 操作的关键结论）。"""
    return (db.get(f'knowledge:{project_id}', []) or [])[:limit]


def log_knowledge(project_id, source, summary):
    """向项目知识库追加一条关键结论（自动记录每次 AI 调用）。"""
    if not summary:
        return
    entries = db.get(f'knowledge:{project_id}', []) or []
    entries.insert(0, {
        'id': 'k' + secrets.token_hex(4),
        'project_id': project_id,
        'source': str(source)[:20],
        'summary': str(summary)[:500],
        'created_at': datetime.datetime.now().isoformat(),
    })
    db.set(f'knowledge:{project_id}', entries[:100])


def build_knowledge_context(project_id, limit=8):
    """把项目知识库拼成提示词前缀，注入到后续 AI 调用，实现个性化/上下文感知。"""
    entries = get_knowledge(project_id, limit)
    if not entries:
        return ''
    lines = [f"- [{e['created_at'][:16]}] {e['source']}: {e['summary']}" for e in entries]
    return ('【项目知识库 · 历次 AI 操作的关键结论，供你参考，生成/诊断时结合这些背景】\n'
            + '\n'.join(lines) + '\n\n')


def _ai_parse_json_response(content):
    """从LLM返回内容中提取JSON对象（容忍markdown代码围栏/前后杂文本）。"""
    content = content.strip()
    if content.startswith('```'):
        lines = content.split('\n')
        if lines and lines[0].strip().startswith('```'):
            lines = lines[1:]
        if lines and lines[-1].strip() == '```':
            lines = lines[:-1]
        content = '\n'.join(lines).strip()
    try:
        return json.loads(content)
    except (json.JSONDecodeError, TypeError):
        start = content.find('{')
        end = content.rfind('}')
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(content[start:end + 1])
            except (json.JSONDecodeError, TypeError):
                return None
        return None


def _load_dev_entries(kind, project_id):
    """读取项目某类研发条目（kind: req/tc/def/task）。"""
    data = db.get(f'{kind}:{project_id}', {}) or {}
    entries = data.get('entries')
    return entries if isinstance(entries, list) else []


def _save_dev_entries(kind, project_id, entries):
    """保存项目某类研发条目。"""
    db.set(f'{kind}:{project_id}', {'entries': entries})


def _require_admin():
    """返回当前管理员用户 dict；未登录或非 admin 返回 None。"""
    user_id = _require_user_id()
    if not user_id:
        return None
    for u in load_users().values():
        if u.get('id') == user_id and u.get('role') == 'admin':
            return u
    return None


def _find_user_by_id(user_id):
    for u in load_users().values():
        if u.get('id') == user_id:
            return u
    return None


def _delete_project_data(project_id, model_id):
    """级联删除一个项目的所有数据（db key + 内存缓存）。"""
    for key in (f'model:{model_id}', f'project:{project_id}', f'comments:{model_id}',
                f'memory:{model_id}', f'operation_logs:{project_id}', f'snapshots:{project_id}',
                f'req:{project_id}', f'tc:{project_id}', f'def:{project_id}', f'task:{project_id}',
                f'knowledge:{project_id}', f'collab_proposals:{project_id}'):
        db.delete(key)
    for k in db.keys('snapshot:'):
        v = db.get(k)
        if isinstance(v, dict) and v.get('project_id') == project_id:
            db.delete(k)
    models_cache.pop(model_id, None)
    operation_logs_cache.pop(project_id, None)
    snapshots_cache.pop(project_id, None)
    for k in list(bookmarks_cache):
        if bookmarks_cache[k] and any(
            b.get('model_id') == model_id or b.get('project_id') == project_id
            for b in bookmarks_cache[k]
        ):
            bookmarks_cache.pop(k, None)
    for v in list(er_views_cache.values()):
        if getattr(v, 'project_id', None) == project_id:
            er_views_cache.pop(v.id, None)
    data_dictionary_cache.pop(project_id, None)
    for cache in (versions_cache, branches_cache, reviews_cache):
        for k in [k for k, v in cache.items() if getattr(v, 'project_id', None) == project_id]:
            cache.pop(k, None)
