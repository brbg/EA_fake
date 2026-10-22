"""AI 智能体工具调用循环（Phase2）。

与 app.py 解耦：本模块只负责「带 tools 的 LLM 多步循环」，
具体工具实现由调用方以 executors 字典注入（{name: fn(args)->(ok, summary, data)}）。
"""
import json

from core import AIService, ai_service_config


def _fn(name, description, properties=None, required=None):
    """构造一个 function-calling 工具声明（省掉重复的样板）。"""
    return {
        'type': 'function',
        'function': {
            'name': name,
            'description': description,
            'parameters': {
                'type': 'object',
                'properties': properties or {},
                'required': required or [],
            },
        },
    }


# 工具声明（OpenAI function-calling 格式）。执行体在 app.py 注入。
#
# 覆盖范围是**高频业务闭环**，不是全部端点——平台的纯前端操作（撤销/重做/清空/
# 导出图片/手工拖拽）没有后端接口，原理上无法由对话触发，故不在列。
# 研发管理用 5 个 dev_* 通用工具覆盖 4 类实体 × CRUD + AI 生成（否则要 17 个工具）。
# description 纪律：≤2 行、含「何时调用」，不放示例长文（19 个 spec 的 token 成本要可控）。
TOOL_SPECS = [
    _fn('create_project',
        '新建建模项目并自动绑定为当前项目。用户要「设计/搭建一套新的架构」而当前没绑项目时先调用。',
        {'name': {'type': 'string', 'description': '项目名称，取自业务描述'}},
        ['name']),
    _fn('generate_architecture',
        '按业务描述在当前项目生成完整企业架构（UML + ArchiMate + ER）并保存；未绑项目会自动先新建。',
        {'description': {'type': 'string', 'description': '业务描述/需求'}},
        ['description']),
    _fn('edit_model',
        '用自然语言增量修改当前项目的某套模型（只改提到的部分，其余不动）。',
        {'kind': {'type': 'string', 'enum': ['uml', 'archimate', 'er'], 'description': '改哪套图'},
         'instruction': {'type': 'string', 'description': '修改指令，如「给 Order 加 status 属性」'}},
        ['kind', 'instruction']),
    _fn('get_health', '对当前项目做健康度体检，返回评分、问题与改进建议。'),
    _fn('optimize_from_health', '读健康度的问题与建议，自动对三套模型做最小修正并保存。'),
    _fn('rename_project',
        '重命名当前项目。',
        {'name': {'type': 'string', 'description': '新项目名'}},
        ['name']),
    _fn('delete_project',
        '删除当前项目（**不可逆**）。必须先向用户复述影响并得到肯定答复，再以 confirm=true 重调；'
        '不带 confirm 时不会删任何东西，只返回待确认信息。',
        {'confirm': {'type': 'boolean', 'description': '必须为 true 才真正执行删除'}},
        ['confirm']),
    _fn('review_model',
        '校验/评审模型结构，返回问题清单（元素未命名、关系悬空、技术层缺可部署元素等）。',
        {'kind': {'type': 'string', 'enum': ['uml', 'archimate', 'er', 'all'], 'description': '评审哪套，默认 all'}}),
    _fn('generate_code',
        '按当前模型生成代码（Java/Python/TypeScript/C#）。返回代码文本，不落盘。',
        {'language': {'type': 'string', 'enum': ['java', 'python', 'typescript', 'csharp']},
         'output_type': {'type': 'string', 'enum': ['entity', 'controller', 'service', 'pojo'],
                         'description': '生成哪一层，默认 entity'},
         'source': {'type': 'string', 'enum': ['uml', 'er'], 'description': '从哪套模型生成，默认 uml'},
         'framework': {'type': 'string', 'description': '如 spring/django，可留空'}}),
    _fn('generate_ruoyi_module',
        '按当前 ER 模型生成整套若依 RuoYi-Vue3 后端模块（domain/mapper/service/controller/SQL/前端页面），'
        '返回文件清单。生成的是源码树，接入步骤见随包 INTEGRATION.md。',
        {'module_name': {'type': 'string', 'description': '模块名，如 business'},
         'package_base': {'type': 'string', 'description': '包名，默认 com.ruoyi'},
         'table_prefix': {'type': 'string', 'description': '要去掉的表前缀，如 biz_'}}),
    _fn('reverse_code',
        '粘贴一段源码，反推出模型并**写入当前项目**（覆盖对应的那套图）。',
        {'target': {'type': 'string', 'enum': ['uml', 'er'], 'description': '反推成哪套图'},
         'code': {'type': 'string', 'description': '源码文本'}},
        ['target', 'code']),
    _fn('generate_document',
        '生成项目设计文档（架构说明/概览/数据库设计），返回 Markdown 文本。',
        {'doc_type': {'type': 'string', 'enum': ['architecture', 'overview', 'database'], 'description': '默认 architecture'},
         'format': {'type': 'string', 'enum': ['markdown', 'html'], 'description': '默认 markdown'}}),
    _fn('version_control',
        '版本管理：list 列出版本、save 存快照、restore 回滚到某版本。'
        'restore 会覆盖当前模型（不可逆），必须先向用户复述并得到肯定答复，再以 confirm=true 重调。',
        {'action': {'type': 'string', 'enum': ['list', 'save', 'restore']},
         'comment': {'type': 'string', 'description': 'save 时的说明'},
         'index': {'type': 'integer', 'description': 'restore 时的版本序号（先用 list 查）'},
         'confirm': {'type': 'boolean', 'description': 'restore 时必须为 true'}},
        ['action']),
    _fn('remember',
        '记住一条项目级长期约束或偏好（如「本项目的金额一律用 BigDecimal」），后续生成会遵循。',
        {'text': {'type': 'string', 'description': '要记住的内容'}},
        ['text']),
    _fn('dev_list',
        '列出当前项目的研发条目。kind：requirement 需求 / testcase 测试用例 / defect 缺陷 / task 任务。',
        {'kind': {'type': 'string', 'enum': ['requirement', 'testcase', 'defect', 'task']}},
        ['kind']),
    _fn('dev_create',
        '新建一条研发条目。fields 只填该类型支持的键，多余的会被忽略。'
        'requirement: name/description/type/priority/status；testcase: name/description/level；'
        'defect: name/description/level/status；task: name/description/type/priority/work_hours。',
        {'kind': {'type': 'string', 'enum': ['requirement', 'testcase', 'defect', 'task']},
         'fields': {'type': 'object', 'description': '条目字段'}},
        ['kind', 'fields']),
    _fn('dev_update',
        '修改一条研发条目（按 id）。',
        {'kind': {'type': 'string', 'enum': ['requirement', 'testcase', 'defect', 'task']},
         'id': {'type': 'string', 'description': '条目 id（先用 dev_list 查）'},
         'fields': {'type': 'object', 'description': '要改的字段'}},
        ['kind', 'id', 'fields']),
    _fn('dev_delete',
        '删除一条研发条目（**不可逆**）。必须先向用户复述是哪一条并得到肯定答复，再以 confirm=true 重调。',
        {'kind': {'type': 'string', 'enum': ['requirement', 'testcase', 'defect', 'task']},
         'id': {'type': 'string', 'description': '条目 id'},
         'confirm': {'type': 'boolean', 'description': '必须为 true 才真正执行'}},
        ['kind', 'id', 'confirm']),
    _fn('dev_ai_generate',
        '用 AI 批量生成研发条目：需求 / 测试用例 / 任务排期（**缺陷没有 AI 生成**）。',
        {'kind': {'type': 'string', 'enum': ['requirement', 'testcase', 'task']}},
        ['kind']),
]


def tool_names():
    return [t['function']['name'] for t in TOOL_SPECS]


# 破坏性工具：执行体在无 confirm 时必须零副作用
DESTRUCTIVE_TOOLS = ('delete_project', 'dev_delete')


def run_tool_agent(messages, executors, max_steps=12, max_tokens=4096):
    """带工具的多步循环（生成器）：逐事件 yield，便于 SSE 实时展示工具轨迹。

    messages: OpenAI 格式消息数组（会被就地追加 assistant/tool 消息）
    executors: {name: fn(args_dict) -> (ok: bool, summary: str, data: any)}
    yield 事件：{type: tool_call|tool_result|final|fatal, ...}

    预算说明（2026-10 上调）：工具从 5 个增到 19 个后，
    max_steps 6 对「研发流」（生成需求→规划任务→列清单）不够用；max_tokens 2048
    会让多工具后的中文总结被截断。两者都留了裕量且仍有界。
    """
    if not ai_service_config.enabled:
        yield {'type': 'fatal', 'error': 'AI 服务未启用，请先配置 API 密钥'}
        return
    for _ in range(max_steps):
        result = AIService.chat_completion(messages, max_tokens=max_tokens, tools=TOOL_SPECS)
        if not isinstance(result, dict) or result.get('error'):
            yield {'type': 'fatal', 'error': (result or {}).get('error', 'AI 调用失败')}
            return
        try:
            msg = result['choices'][0].get('message') or {}
        except (KeyError, IndexError, TypeError):
            yield {'type': 'fatal', 'error': 'AI 返回格式异常'}
            return
        tool_calls = msg.get('tool_calls')
        if not tool_calls:
            yield {'type': 'final', 'content': msg.get('content') or ''}
            return
        messages.append({'role': 'assistant', 'content': msg.get('content') or '', 'tool_calls': tool_calls})
        for tc in tool_calls:
            fn_name = ((tc.get('function') or {}).get('name') or '').strip()
            raw_args = (tc.get('function') or {}).get('arguments') or '{}'
            try:
                args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
            except Exception:
                args = {}
            yield {'type': 'tool_call', 'name': fn_name, 'args': args}
            fn = executors.get(fn_name)
            if fn is None:
                ok, summary, data = False, f'未知工具 {fn_name}', None
            else:
                try:
                    ok, summary, data = fn(args)
                except Exception as ex:
                    ok, summary, data = False, f'工具执行失败：{ex}', None
            # data 中若含新建/绑定的项目信息，透传给前端（让页面自动绑定该项目）
            proj = None
            if isinstance(data, dict) and data.get('project_id'):
                proj = {'project_id': str(data.get('project_id')), 'project_name': str(data.get('project_name') or '')}
            yield {'type': 'tool_result', 'name': fn_name, 'ok': ok, 'summary': summary, 'project': proj}
            messages.append({
                'role': 'tool',
                'tool_call_id': tc.get('id'),
                'content': json.dumps({'ok': ok, 'summary': summary, 'data': data}, ensure_ascii=False)[:8000],
            })
    yield {'type': 'final', 'content': '（已达到工具调用上限，先给你当前进展，可继续追问。）'}

