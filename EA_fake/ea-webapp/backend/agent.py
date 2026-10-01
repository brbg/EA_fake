"""AI 智能体工具调用循环（Phase2）。

与 app.py 解耦：本模块只负责「带 tools 的 LLM 多步循环」，
具体工具实现由调用方以 executors 字典注入（{name: fn(args)->(ok, summary, data)}）。
"""
import json

from core import AIService, ai_service_config


# 工具声明（OpenAI function-calling 格式）。执行体在 app.py 注入。
TOOL_SPECS = [
    {
        'type': 'function',
        'function': {
            'name': 'create_project',
            'description': '新建一个建模项目（当用户要「设计/搭建/生成一套新的架构」而当前尚未绑定项目时先调用它）。建好后会自动绑定为当前项目。',
            'parameters': {
                'type': 'object',
                'properties': {'name': {'type': 'string', 'description': '项目名称，取自业务描述（如「智慧农业平台」）'}},
                'required': ['name'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'generate_architecture',
            'description': '根据一段业务描述，在当前项目生成完整企业架构（UML 类图 + ArchiMate + ER 数据模型）并保存。'
                           '若当前尚未绑定项目，会先自动新建一个项目再生成。',
            'parameters': {
                'type': 'object',
                'properties': {'description': {'type': 'string', 'description': '业务描述/需求，一句话到一段话'}},
                'required': ['description'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'edit_model',
            'description': '用自然语言指令增量修改当前项目的某个模型（只改提到的部分，不动其它）。',
            'parameters': {
                'type': 'object',
                'properties': {
                    'kind': {'type': 'string', 'enum': ['uml', 'archimate', 'er'], 'description': '要改哪套图'},
                    'instruction': {'type': 'string', 'description': '修改指令，如「给 Order 类加一个 status 属性」'},
                },
                'required': ['kind', 'instruction'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'get_health',
            'description': '对当前项目做健康度体检，返回评分、问题与改进建议。',
            'parameters': {'type': 'object', 'properties': {}, 'required': []},
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'optimize_from_health',
            'description': '读取当前项目健康度的问题与建议，自动对三套模型做最小必要修正并保存。',
            'parameters': {'type': 'object', 'properties': {}, 'required': []},
        },
    },
]


def tool_names():
    return [t['function']['name'] for t in TOOL_SPECS]


def run_tool_agent(messages, executors, max_steps=6, max_tokens=2048):
    """带工具的多步循环（生成器）：逐事件 yield，便于 SSE 实时展示工具轨迹。

    messages: OpenAI 格式消息数组（会被就地追加 assistant/tool 消息）
    executors: {name: fn(args_dict) -> (ok: bool, summary: str, data: any)}
    yield 事件：{type: tool_call|tool_result|final|fatal, ...}
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
                'content': json.dumps({'ok': ok, 'summary': summary, 'data': data}, ensure_ascii=False)[:4000],
            })
    yield {'type': 'final', 'content': '（已达到工具调用上限，先给你当前进展，可继续追问。）'}

