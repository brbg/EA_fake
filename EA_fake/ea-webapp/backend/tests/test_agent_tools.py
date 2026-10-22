"""智能体工具的自测（不依赖 pytest，直接 `py backend/tests/test_agent_tools.py` 运行）。

覆盖：工具声明形状（19 个、名字唯一、enum 合法）、执行体三元组返回、
研发管理 4 类实体的增删改查、**破坏性工具无 confirm 时零副作用**、
工具循环的步数上限/未知工具不中止/结果截断。

全部离线：打桩 AIService.chat_completion，不联网。
"""

import os
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:   # noqa: BLE001
    pass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core                    # noqa: E402
import agent                   # noqa: E402
import app as A                # noqa: E402
from models import SimpleModel  # noqa: E402

FAILED = []


def check(cond, label):
    print(('  ok   ' if cond else '  FAIL ') + label)
    if not cond:
        FAILED.append(label)


# ---------------------------------------------------------------- 工具声明形状

def test_specs():
    print('== 工具声明 ==')
    specs = agent.TOOL_SPECS
    names = agent.tool_names()
    check(len(names) == 19, f'19 个工具（实得 {len(names)}）')
    check(len(set(names)) == len(names), '工具名唯一')
    check(all(t.get('type') == 'function' for t in specs), 'type 都是 function')

    bad_desc = [n for n, t in zip(names, specs)
                if not t['function'].get('description') or len(t['function']['description']) > 260]
    check(not bad_desc, f'description 非空且不过长（越界 {bad_desc}）')

    # 参数 schema 合法：有 type=object、properties 是 dict、required 都是已声明的键
    bad = []
    for t in specs:
        f = t['function']
        p = f.get('parameters') or {}
        if p.get('type') != 'object' or not isinstance(p.get('properties'), dict):
            bad.append(f['name'])
            continue
        for r in p.get('required') or []:
            if r not in p['properties']:
                bad.append(f'{f["name"]}.{r}')
    check(not bad, f'参数 schema 合法（越界 {bad}）')

    # enum 取值合法
    for t in specs:
        props = (t['function'].get('parameters') or {}).get('properties') or {}
        for k, v in props.items():
            if 'enum' in v:
                check(isinstance(v['enum'], list) and len(v['enum']) >= 2,
                      f"{t['function']['name']}.{k} 的 enum 非空")
    # 破坏性工具必须带 confirm 参数
    for n in agent.DESTRUCTIVE_TOOLS:
        spec = next(t for t in specs if t['function']['name'] == n)
        props = spec['function']['parameters']['properties']
        check('confirm' in props, f'破坏性工具 {n} 声明了 confirm 参数')


# ---------------------------------------------------------------- 执行体

def _execs(pid='t-pid'):
    return A._agent_tool_executors(pid, 'u1')


def _stub_ai(payload):
    core.AIService.chat_completion = staticmethod(lambda *a, **kw: payload)


def test_executors_shape():
    print('\n== 执行体：注册齐全 + 三元组返回 ==')
    ex = _execs()
    check(set(ex) == set(agent.tool_names()),
          f'执行体与声明一一对应（多 {set(ex) - set(agent.tool_names())}，少 {set(agent.tool_names()) - set(ex)}）')

    # 未绑定项目时，需要项目的工具应给出「先新建/打开项目」而不是抛异常
    no_proj = A._agent_tool_executors('', 'u1')
    for n in ('rename_project', 'delete_project', 'review_model', 'generate_code',
              'generate_ruoyi_module', 'reverse_code', 'generate_document',
              'version_control', 'remember', 'dev_list', 'dev_create', 'dev_ai_generate'):
        r = no_proj[n]({})
        check(isinstance(r, tuple) and len(r) == 3 and r[0] is False and isinstance(r[1], str),
              f'{n} 未绑项目时返回 (False, 说明, None)')


def test_dev_crud():
    print('\n== 研发管理：4 类实体 × CRUD ==')
    store = {}
    real_load, real_save = A._load_dev_entries, A._save_dev_entries
    A._load_dev_entries = lambda kind, pid: list(store.get(kind, []))
    A._save_dev_entries = lambda kind, pid, entries: store.__setitem__(kind, list(entries))
    try:
        ex = _execs('p1')
        for kind, key in (('requirement', 'req'), ('testcase', 'tc'),
                          ('defect', 'def'), ('task', 'task')):
            ok, summary, data = ex['dev_create']({'kind': kind, 'fields': {'name': f'{kind}-1', 'description': 'd'}})
            check(ok and data.get('id'), f'{kind} 新建成功（{summary}）')
            rid = data['id']

            ok2, s2, d2 = ex['dev_list']({'kind': kind})
            check(ok2 and d2.get('count') == 1, f'{kind} 列表 1 条')

            # 用四类都有的字段改（status 只有 requirement/defect/task 有）
            ok3, s3, _ = ex['dev_update']({'kind': kind, 'id': rid, 'fields': {'description': 'updated'}})
            check(ok3, f'{kind} 修改成功')
            # 传该类型不支持的字段 → 明确拒绝而不是静默无操作
            if kind == 'testcase':
                check(ex['dev_update']({'kind': kind, 'id': rid, 'fields': {'status': 'x'}})[0] is False,
                      'testcase 不支持 status，被拒')

            # 删除需确认：无 confirm 时**数据不变**
            ok4, s4, d4 = ex['dev_delete']({'kind': kind, 'id': rid})
            check(ok4 and d4.get('needs_confirmation') is True, f'{kind} 删除需确认')
            check(len(store.get(key) or []) == 1, f'{kind} 无 confirm 时**数据未变**')

            ok5, s5, _ = ex['dev_delete']({'kind': kind, 'id': rid, 'confirm': True})
            check(ok5 and not store.get(key), f'{kind} 带 confirm 才真删')

        # 非法 kind / 找不到 id
        check(ex['dev_list']({'kind': 'nope'})[0] is False, '非法 kind 被拒')
        check(ex['dev_create']({'kind': 'task', 'fields': {}})[0] is False, '缺 name 被拒')
        check(ex['dev_update']({'kind': 'task', 'id': 'zzz', 'fields': {'status': 'x'}})[0] is False,
              '找不到 id 被拒')
        # 字段白名单：非法键被忽略
        ok, _, d = ex['dev_create']({'kind': 'task', 'fields': {'name': 'x', '不存在的键': 1}})
        check(ok, '多余字段被忽略而不是报错')
        check('不存在的键' not in (store['task'][0] if store.get('task') else {}), '多余字段没进库')
        # 缺陷没有 AI 生成
        check(ex['dev_ai_generate']({'kind': 'defect'})[0] is False, '缺陷不支持 AI 生成')
    finally:
        A._load_dev_entries, A._save_dev_entries = real_load, real_save


def test_destructive_project():
    print('\n== 破坏性工具：delete_project ==')
    pid = 'del-probe'
    m = SimpleModel('待删项目')
    m.owner_id = 'u1'
    A.models_cache[pid] = m
    saved = {}
    real_save = A.save_model
    A.save_model = lambda mid, mod: saved.__setitem__(mid, mod)
    real_log = A.log_knowledge
    A.log_knowledge = lambda *a, **kw: None
    was = core.ai_service_config.enabled
    core.ai_service_config.enabled = True
    try:
        ex = _execs(pid)
        # 无 confirm：零副作用
        ok, summary, data = ex['delete_project']({})
        check(ok and data.get('needs_confirmation') is True, f'无 confirm 返回待确认（{summary[:30]}…）')
        check(pid in A.models_cache, '无 confirm 时项目**仍在**')

        # 带 confirm：真删
        ok2, s2, d2 = ex['delete_project']({'confirm': True})
        check(ok2 and d2.get('deleted') is True, f'带 confirm 才真删（{s2}）')
        check(pid not in A.models_cache, '已从缓存移除')
        # 删除前留了备份文件
        d = os.path.join('..', 'data', 'deleted')
        made = [f for f in (os.listdir(d) if os.path.isdir(d) else []) if f.startswith(pid)]
        check(bool(made), f'删除前留了备份文件（{made[:1]}）')
        for f in made:
            try:
                os.remove(os.path.join(d, f))
            except OSError:
                pass
    finally:
        A.models_cache.pop(pid, None)
        A.save_model = real_save
        A.log_knowledge = real_log
        core.ai_service_config.enabled = was


def test_review_and_version():
    print('\n== 评审 / 版本 ==')
    pid = 'rev-probe'
    m = SimpleModel('评审探针')
    m.owner_id = 'u1'
    m.elements = [{'id': 1, 'name': '', 'type': 'Class', 'attributes': [], 'methods': [],
                   'x': 0, 'y': 0, 'width': 120, 'height': 80}]     # 未命名 → 应有 error
    m.relationships = []
    A.models_cache[pid] = m
    real_save = A.save_model
    A.save_model = lambda mid, mod: A.models_cache.__setitem__(mid, mod)
    try:
        ex = _execs(pid)
        ok, summary, data = ex['review_model']({'kind': 'uml'})
        check(ok and data['uml']['errors'] >= 1, f'评审报出未命名元素（{summary}）')

        ok2, s2, d2 = ex['version_control']({'action': 'list'})
        check(ok2 and isinstance(d2.get('versions'), list), 'version list 可用')

        ok3, s3, _ = ex['version_control']({'action': 'save', 'comment': '基线'})
        check(ok3, f'version save 可用（{s3}）')

        # restore 无 confirm → 零副作用
        ok4, s4, d4 = ex['version_control']({'action': 'restore', 'index': 0})
        check(ok4 and d4.get('needs_confirmation') is True, 'restore 需确认')
        check(ex['version_control']({'action': 'restore', 'index': 999})[0] is False, '越界序号被拒')
        check(ex['version_control']({'action': 'nope'})[0] is False, '未知 action 被拒')
    finally:
        A.models_cache.pop(pid, None)
        A.save_model = real_save


def test_tool_loop():
    print('\n== 工具循环 ==')
    was = core.ai_service_config.enabled
    core.ai_service_config.enabled = True
    try:
        # 未知工具不中止循环，且能走到 final
        calls = []

        def scripted(*a, **kw):
            calls.append(1)
            if len(calls) == 1:
                return {'choices': [{'message': {'content': '', 'tool_calls': [
                    {'id': 'c1', 'function': {'name': '不存在的工具', 'arguments': '{}'}}]}}]}
            return {'choices': [{'message': {'content': '完成'}}]}

        core.AIService.chat_completion = staticmethod(scripted)
        evs = list(agent.run_tool_agent([], {'echo': lambda a: (True, 'ok', None)}))
        check(any(e.get('type') == 'tool_result' and e.get('ok') is False for e in evs),
              '未知工具返回 ok=False')
        check(any(e.get('type') == 'final' for e in evs), '未知工具**不中止**循环，仍走到 final')

        # 工具抛异常也不中止（第 1 次返回工具调用，第 2 次返回 final）
        n = [0]

        def boom(*a, **kw):
            n[0] += 1
            if n[0] == 1:
                return {'choices': [{'message': {'content': '', 'tool_calls': [
                    {'id': 'c2', 'function': {'name': 'bad', 'arguments': '{}'}}]}}]}
            return {'choices': [{'message': {'content': '好了'}}]}

        core.AIService.chat_completion = staticmethod(boom)

        def raiser(a):
            raise ValueError('工具炸了')

        evs2 = list(agent.run_tool_agent([], {'bad': raiser}))
        check(any(e.get('type') == 'tool_result' and '工具执行失败' in str(e.get('summary')) for e in evs2),
              '工具异常被捕获并回喂')
        check(any(e.get('type') == 'final' for e in evs2), '异常后仍走到 final（不中止）')

        # 步数上限
        def always_tool(*a, **kw):
            return {'choices': [{'message': {'content': '', 'tool_calls': [
                {'id': 'c', 'function': {'name': 'echo', 'arguments': '{}'}}]}}]}

        core.AIService.chat_completion = staticmethod(always_tool)
        evs3 = list(agent.run_tool_agent([], {'echo': lambda a: (True, 'ok', None)}, max_steps=3))
        finals = [e for e in evs3 if e.get('type') == 'final']
        check(len(finals) == 1 and '上限' in finals[0].get('content', ''), '到步数上限给出明确提示')

        # 结果截断：让模型真的去调 big 工具，再检查回喂给模型的 tool 消息长度
        n2 = [0]

        def call_big(*a, **kw):
            n2[0] += 1
            if n2[0] == 1:
                return {'choices': [{'message': {'content': '', 'tool_calls': [
                    {'id': 'cb', 'function': {'name': 'big', 'arguments': '{}'}}]}}]}
            return {'choices': [{'message': {'content': '完'}}]}

        core.AIService.chat_completion = staticmethod(call_big)
        msgs = []
        list(agent.run_tool_agent(msgs, {'big': lambda a: (True, 'ok', 'x' * 20000)}))
        tool_msgs = [m for m in msgs if m.get('role') == 'tool']
        check(tool_msgs and len(tool_msgs[0]['content']) <= 8000,
              f"工具结果被截断到 8000（实得 {len(tool_msgs[0]['content']) if tool_msgs else '无 tool 消息'}）")
    finally:
        core.ai_service_config.enabled = was


def main():
    test_specs()
    test_executors_shape()
    test_dev_crud()
    test_destructive_project()
    test_review_and_version()
    test_tool_loop()
    print()
    if FAILED:
        print(f'{len(FAILED)} 项失败：')
        for f in FAILED:
            print('  -', f)
        return 1
    print('全部通过 ✅')
    return 0


if __name__ == '__main__':
    sys.exit(main())
