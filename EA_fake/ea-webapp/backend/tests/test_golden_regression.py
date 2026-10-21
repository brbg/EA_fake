"""黄金样例回归（不依赖 pytest）。

    py backend/tests/test_golden_regression.py            # 离线：打桩喂 canonical，断言结构不变量
    py backend/tests/test_golden_regression.py --live      # 可选：真调 LLM，只断言必然成立的不变量

**为什么离线模式能抓到东西**：它不测「模型说了什么」，只测「拿到这样一份产出之后，
后端的加工链路是否自洽」—— id 是否连续、关系端点是否都解析得到、类型是否越界、
布局是否重叠、打分器是否真的在排序。这些正是 prompt 改坏时最先崩的地方，
而且完全可复现。

**离线必须强制关掉 AI**：core.py 在 **import 时**就读数据库里的 ai_config，
开发机存过 key 的话 enabled 会是 True，「离线」测试就会真的联网并随机失败。
所以这里学 test_ruoyi_api.py 的做法：把 enabled 置 False，并把 chat_completion
换成会抛异常的桩（双保险），finally 还原。
"""

import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8')   # Windows 控制台默认 GBK，中文与 emoji 会炸
except Exception:   # noqa: BLE001
    pass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core                     # noqa: E402
import app as A                 # noqa: E402
import json as _json            # noqa: E402
import ai_quality as Q          # noqa: E402
from constants import ELEMENT_TYPES, RELATIONSHIP_TYPES   # noqa: E402
from models import SimpleModel  # noqa: E402
from golden_cases import CANONICAL_CASES, SCORER_SAMPLES, LIVE_CASES   # noqa: E402

FAILED = []
LLM_CALLS = []


def check(cond, label):
    if cond:
        print(f'  ok   {label}')
    else:
        print(f'  FAIL {label}')
        FAILED.append(label)


def _forbidden(*_a, **_kw):
    LLM_CALLS.append(1)
    raise AssertionError('离线模式不该发 LLM 请求！')


def _endpoints(rel):
    """关系两端（兼容三张图各自的键名）。"""
    for a, b in (('startElement', 'endElement'), ('startEntity', 'endEntity'), ('source', 'target')):
        if rel.get(a) is not None and rel.get(b) is not None:
            return rel[a], rel[b]
    return None, None


def _materialize(case, report=None):
    m = SimpleModel(case['id'])
    counts = A._apply_canonical_to_model(m, case['canonical'], report)
    return m, counts


def test_structural_invariants():
    print('== 结构不变量（canonical → 三图物化） ==')
    for case in CANONICAL_CASES:
        cid = case['id']
        m, counts = _materialize(case)
        exp = case['expect']
        print(f'  -- {cid} --')
        check(len(m.elements) >= exp.get('min_uml', 0),
              f"{cid}: UML 元素数 ≥ {exp.get('min_uml')}（实得 {len(m.elements)}）")
        check(len(m.archimate_elements) >= exp.get('min_archimate', 0),
              f"{cid}: ArchiMate 元素数 ≥ {exp.get('min_archimate')}（实得 {len(m.archimate_elements)}）")
        check(len(m.er_entities) >= exp.get('min_er', 0),
              f"{cid}: ER 实体数 ≥ {exp.get('min_er')}（实得 {len(m.er_entities)}）")

        # 元素 id 从 1 起连续，且关系端点全部能解析（0 悬空）——这是重名覆盖类缺陷的探针
        for label, items in (('UML', m.elements), ('ArchiMate', m.archimate_elements)):
            ids = sorted(i['id'] for i in items if isinstance(i.get('id'), int))
            check(ids == list(range(1, len(items) + 1)),
                  f'{cid}: {label} id 从 1 起连续（实得 {ids}）')
        for label, items, rels in (('UML', m.elements, m.relationships),
                                   ('ArchiMate', m.archimate_elements, m.archimate_connections)):
            ids = {i['id'] for i in items}
            dangling = []
            for r in rels:
                s, t = _endpoints(r)
                if s not in ids or t not in ids:
                    dangling.append((s, t))
            check(not dangling, f'{cid}: {label} 关系端点全部命中元素 id（悬空 {dangling}）')

        # 每个 kind 内无重名
        for label, items in (('UML', m.elements), ('ArchiMate', m.archimate_elements), ('ER', m.er_entities)):
            names = [str(i.get('name') or '') for i in items]
            check(len(names) == len(set(names)), f'{cid}: {label} 无重名元素（{names}）')

        # 元素类型不越界
        allowed_uml = set(ELEMENT_TYPES['uml']) | {'Enum'}
        bad_uml = sorted({i.get('type') for i in m.elements if i.get('type') not in allowed_uml})
        check(not bad_uml, f'{cid}: UML 元素类型都在白名单内（越界 {bad_uml}）')
        bad_rel = sorted({r.get('type') for r in m.relationships if r.get('type') not in RELATIONSHIP_TYPES})
        check(not bad_rel, f'{cid}: UML 关系类型都在白名单内（越界 {bad_rel}）')

        # ArchiMate 白名单（2026-10 补：此前只查 UML，ArchiMate 完全不校验）
        from constants import (ARCHIMATE_ELEMENT_TYPES, ARCHIMATE_REL_TYPES,
                               ARCHIMATE_LAYERS, ARCHIMATE_LAYER_BANDS)
        bad_ae = sorted({e.get('type') for e in m.archimate_elements
                         if e.get('type') not in ARCHIMATE_ELEMENT_TYPES})
        check(not bad_ae, f'{cid}: ArchiMate 元素类型都在白名单内（越界 {bad_ae}）')
        bad_al = sorted({e.get('layer') for e in m.archimate_elements
                         if e.get('layer') not in ARCHIMATE_LAYERS})
        check(not bad_al, f'{cid}: ArchiMate 层次都在白名单内（越界 {bad_al}）')
        bad_ar = sorted({c.get('type') for c in m.archimate_connections
                         if c.get('type') not in ARCHIMATE_REL_TYPES})
        check(not bad_ar, f'{cid}: ArchiMate 关系类型都在白名单内（越界 {bad_ar}）')

        # 布局器必须把元素放进**本层**的带内，且不溢出画布逻辑高 600
        # （此前 layer_y[technology]=560 + 高 70 = 630，被裁掉 30px）
        off_band = []
        for e in m.archimate_elements:
            band = ARCHIMATE_LAYER_BANDS.get(e.get('layer'))
            if not band:
                continue
            top, bottom = band
            y, h = e.get('y'), e.get('height') or 0
            if not (top <= y and y + h <= bottom):
                off_band.append((e.get('name'), e.get('layer'), y, h, band))
        check(not off_band, f'{cid}: ArchiMate 元素都落在本层带内且不溢出（越界 {off_band}）')

        # 新技术类型必须原样保留：布局器对未知类型会回落（技术层→node），
        # 常量若没加对，这里会被悄悄改掉，部署视图退化成清一色节点
        for t in exp.get('must_keep_types', ()):
            hit = [e for e in m.archimate_elements if e.get('type') == t]
            check(bool(hit), f'{cid}: 技术类型「{t}」未被降级（实得 {len(hit)} 个）')
        if exp.get('must_keep_rel'):
            rt = exp['must_keep_rel']
            hit = [c for c in m.archimate_connections if c.get('type') == rt]
            check(bool(hit), f'{cid}: 关系类型「{rt}」未被降级（实得 {len(hit)} 条）')

        # ER 每个实体至少一个主键；字段类型必须落在闭合词表内
        bad_er = []
        for e in m.er_entities:
            fields = e.get('fields') or []
            check(any(f.get('isPrimary') for f in fields), f"{cid}: ER 实体 {e['name']} 有主键")
            check(all(f.get('type') for f in fields), f"{cid}: ER 实体 {e['name']} 字段类型非空")
            for f in fields:
                text = str(f.get('type') or '')
                m_base = re.match(r'^([A-Z]+)', text)
                if not m_base or m_base.group(1) not in Q.ER_FIELD_TYPES:
                    bad_er.append((e.get('name'), f.get('name'), text))
        check(not bad_er, f'{cid}: ER 字段类型都在词表内（越界 {bad_er}）')
        # 'STRING' 是旧代码 `str(x or "string").upper()` 留下的半截类型，不该再出现
        check(not any(str(f.get('type')) == 'STRING'
                      for e in m.er_entities for f in (e.get('fields') or [])),
              f'{cid}: 没有 STRING 这种半截类型')

        # 布局不重叠、坐标是数字
        for label, items in (('UML', m.elements), ('ArchiMate', m.archimate_elements), ('ER', m.er_entities)):
            coords = [(i.get('x'), i.get('y')) for i in items]
            check(all(isinstance(x, (int, float)) and isinstance(y, (int, float)) for x, y in coords),
                  f'{cid}: {label} 坐标是数字')
            check(len(coords) == len(set(coords)), f'{cid}: {label} 无重叠坐标（{coords}）')

        # counts 与模型一致（counts 是 [元素数, 关系数]，按下标消费）
        check(counts['uml'][0] == len(m.elements), f'{cid}: counts.uml 与模型一致')
        check(counts['er'][0] == len(m.er_entities), f'{cid}: counts.er 与模型一致')


def test_scorer_on_real_models():
    print('\n== 打分器在真实物化模型上的表现 ==')
    scores = {}
    for case in CANONICAL_CASES:
        m, _c = _materialize(case)
        stats = Q.model_structure_stats(m)
        issues = Q.group_by_kind(
            Q.normalize_uml_issues(A.review_archimate_model(m, use_ai=False), 'archimate')
        )
        score, detail = Q.candidate_score(issues, stats)
        scores[case['id']] = (score, detail)
        print(f"  {case['id']}: {score}  明细={detail}")

    full = scores['farm'][0]
    check(full == 100.0, f'命名一致的完整用例拿满分（实得 {full}）')
    partial = scores['partial']
    check(partial[1]['empty_kinds'] == 2, f"半成品用例识别出 2 张空图（实得 {partial[1]['empty_kinds']}）")
    check(partial[0] < full, f'缺两张图的得分严格低于完整用例（{partial[0]} < {full}）')
    if 'messy' in scores:
        check(scores['messy'][0] < full, f"脏产出用例得分低于干净用例（{scores['messy'][0]} < {full}）")

    print('\n== 打分器纯度（打桩后一次 LLM 都不调） ==')
    for label, kind_issues, stats, want in SCORER_SAMPLES:
        score, _d = Q.candidate_score(kind_issues, stats)
        check(score == want, f'{label} → {score}（期望 {want}）')
    check(LLM_CALLS == [], f'全程 0 次 LLM 调用（实得 {len(LLM_CALLS)}）')


def test_fallback_path():
    print('\n== 降级路径（canonical 拿不到时的三图各自生成） ==')
    m = SimpleModel('fallback')
    counts = A._agent_apply_fallback(m, '一个简单的图书借阅系统：读者、图书、借阅记录')

    # UML 走关键词回退、ArchiMate 走 _mock_archimate，都是确定性的，AI 关了也必须出图。
    check(counts['uml'][0] > 0, f'UML 有确定性兜底，必须出内容（counts={counts["uml"]}）')
    check(counts['archimate'][0] > 0, f'ArchiMate 有 _mock 兜底，必须出内容（counts={counts["archimate"]}）')

    # 已发现的缺口（非本次范围，不修）：`_agent_apply_fallback` 直接调 `_ai_generate_er_data`，
    # 拿不到就记 [0,0]；而 ER 单图路由走的是 `ai_generate_er_model`，那里会退到
    # `extract_entities_from_requirements` 关键词解析。也就是说**同一个 AI 关闭场景，
    # 单图路由能出 ER、智能体降级路径不能**。若将来补上兜底，把下面这条改成 > 0。
    print(f"  [已知缺口] ER 在降级路径无确定性兜底（counts={counts['er']}）；"
          f"单图路由有 extract_entities_from_requirements 兜底，两条路不一致")

    for label, items, rels in (('UML', m.elements, m.relationships),
                               ('ER', m.er_entities, m.er_relations),
                               ('ArchiMate', m.archimate_elements, m.archimate_connections)):
        ids = {i['id'] for i in items}
        dangling = [(_endpoints(r)) for r in rels if any(x not in ids for x in _endpoints(r))]
        check(not dangling, f'{label} 降级后关系端点无悬空（{dangling}）')


def test_cross_map_expectations():
    print('\n== 跨图命名：用例期望 ==')
    for case in CANONICAL_CASES:
        exp = case['expect']
        if 'cross_map_renames' not in exp:
            continue
        report = []
        m, _c = _materialize(case, report)
        joined = '\n'.join(report)
        # 物化时就自动对齐过了，所以事后再看应当没有可改项（幂等）
        after = Q.cross_map_diff(m)
        check(after['renames'] == [],
              f"{case['id']}: 物化后无可改项（实得 {after['renames']}）")
        if exp['cross_map_renames']:
            check('跨图命名已统一' in joined,
                  f"{case['id']}: 自动对齐被记入 layout_report（实得 {report}）")
        else:
            check('跨图命名已统一' not in joined, f"{case['id']}: 没有该统一的（无误改）")
        if 'cross_map_reports' in exp:
            check(len(after['reports']) == exp['cross_map_reports'],
                  f"{case['id']}: 只报告数 {len(after['reports'])}（期望 {exp['cross_map_reports']}）：{after['reports']}")
        if 'cross_map_same' in exp:
            check(after['same'] == exp['cross_map_same'],
                  f"{case['id']}: 已一致数 {after['same']}（期望 {exp['cross_map_same']}）")


def test_layout_report():
    """违规产出必须被改写**并**如实记录——只改不记等于把问题藏起来。"""
    print('\n== 产出修正记录（fail-open 口子的探针） ==')
    for case in CANONICAL_CASES:
        need = case['expect'].get('report_at_least')
        if not need:
            continue
        report = []
        m, _c = _materialize(case, report)
        check(len(report) >= need, f"{case['id']}: 修正记录 ≥ {need} 条（实得 {len(report)}）")
        for line in report:
            print(f'    · {line}')
        joined = '\n'.join(report)
        check('WeirdThing' in joined, f"{case['id']}: 非法 UML 元素类型被记录")
        check('Bogus' in joined, f"{case['id']}: 非法 UML 关系类型被记录")
        check('NoSuchElement' in joined, f"{case['id']}: 悬空关系被记录")
        check('Actor1' in joined, f"{case['id']}: ArchiMate 重名被记录")
        check('weirdtype' in joined, f"{case['id']}: 非法 ArchiMate 元素类型被记录")
        check('nosuchlayer' in joined, f"{case['id']}: 非法 ArchiMate 层次被记录")
        check('bogus_rel' in joined, f"{case['id']}: 非法 ArchiMate 关系类型被记录")
        check('FOOBAR' in joined, f"{case['id']}: 非法 ER 字段类型被记录")

        types = {e['name']: e['type'] for e in m.elements}
        check(types.get('Status') == 'Enum',
              f"{case['id']}: 合法 Enum 没被降级（实得 {types.get('Status')}）")
        check('Status' not in joined, f"{case['id']}: 合法 Enum 不进报告")
        blob = [f for e in m.er_entities for f in (e.get('fields') or []) if f['name'] == 'blob_col']
        check(bool(blob) and blob[0]['type'] == 'VARCHAR(255)',
              f"{case['id']}: 逻辑类型 string → VARCHAR(255)（实得 {blob}）")


def test_edit_report_integration():
    """applied_ops 必须是**真实生效数**，不能是模型自称的步数。"""
    print('\n== 诚实计数（EditReport 贯穿三个 apply 函数） ==')
    elements = [{'id': 1, 'name': 'Alpha', 'type': 'Class', 'attributes': [], 'methods': []}]

    report = Q.EditReport()
    A._apply_uml_edits(elements, [], [
        {'op': 'add_relationship', 'source': 'Alpha', 'target': 'NoSuch', 'type': 'Association'}], report)
    check(report.applied == 0 and report.discarded[0]['reason'] == 'unresolved_endpoint',
          f"悬空端点算丢弃不算生效（{report.discarded}）")

    report = Q.EditReport()
    A._apply_uml_edits(elements, [], [{'op': 'frobnicate'}], report)
    check(report.applied == 0 and report.discarded[0]['reason'] == 'unknown_op',
          f"未知 op 被记录（{report.discarded}）")

    report = Q.EditReport()
    A._apply_uml_edits(elements, [], [{'op': 'delete_element', 'name': 'NotThere'}], report)
    check(report.applied == 0 and report.discarded[0]['reason'] == 'unknown_element',
          '删不存在的元素算丢弃')

    report = Q.EditReport()
    A._apply_uml_edits(elements, [], [{'op': 'update_element', 'name': 'Alpha'}], report)
    check(report.applied == 0 and report.discarded[0]['reason'] == 'no_changes',
          f"什么都没改的 update 不算生效（{report.discarded}）")

    ents = [{'id': 1, 'name': 'User', 'fields': [{'name': 'id', 'type': 'INT', 'isPrimary': True}]}]
    report = Q.EditReport()
    A._apply_er_edits(ents, [], [{'op': 'delete_field', 'entity': 'User', 'field_name': 'nope'}], report)
    check(report.applied == 0 and report.discarded[0]['reason'] == 'no_such_field',
          f"删不存在的字段算丢弃（{report.discarded}）")

    report = Q.EditReport()
    A._apply_archimate_edits([{'id': 1, 'name': 'A', 'type': 'service', 'layer': 'business'}], [],
                             [{'op': 'delete_element', 'name': 'Ghost'}], report)
    check(report.applied == 0 and report.discarded[0]['reason'] == 'unknown_element',
          'ArchiMate 通路同样记账')

    # 混装：一半生效、一半丢弃
    report = Q.EditReport()
    A._apply_uml_edits(elements, [], [
        {'op': 'add_element', 'name': 'Beta'},
        {'op': 'add_element', 'name': 'Alpha'},        # 重名
        {'op': 'add_relationship', 'source': 'Alpha', 'target': 'Beta', 'type': 'Association'},
        {'op': 'bogus'},                               # 未知
    ], report)
    check(report.applied == 2, f'真实生效 2 步（实得 {report.applied}）')
    check(report.summary()['discarded_count'] == 2, f"丢弃 2 步（{report.discarded}）")
    check(report.applied_for('uml') == 2, '按图计数')

    print('\n== 别名回归（浅拷贝曾让调用方的模型被原地改） ==')
    ents = [{'id': 1, 'name': 'User', 'fields': [{'name': 'id', 'type': 'INT', 'isPrimary': True}]}]
    before = len(ents[0]['fields'])
    report = Q.EditReport()
    new_ents, _r = A._apply_er_edits(ents, [], [
        {'op': 'add_field', 'entity': 'User', 'field': {'name': 'email', 'type': 'VARCHAR(255)'}}], report)
    check(len(ents[0]['fields']) == before,
          f'调用方模型不被原地修改（{before} → {len(ents[0]["fields"])}）')
    check(len(new_ents[0]['fields']) == before + 1 and report.applied == 1,
          '返回值里确实加上了字段')


def test_edit_api_contract():
    """HTTP 契约：前端只读 applied_ops，必须是真实生效数。"""
    print('\n== 编辑接口契约 ==')
    import json as _json
    from core import sessions_cache
    sid = 'golden-edit-session'
    pid = 'golden-edit-probe'
    sessions_cache[sid] = {'user_id': 'golden-user'}

    m = SimpleModel('契约探针')
    m.owner_id = 'golden-user'
    m.elements = [{'id': 1, 'name': 'Alpha', 'type': 'Class', 'x': 0, 'y': 0, 'width': 120, 'height': 80}]
    m.relationships = []
    A.models_cache[pid] = m           # 只进内存缓存，不写库，避免污染开发数据

    real_chat = core.AIService.chat_completion
    real_log = A.log_knowledge
    was_enabled = core.ai_service_config.enabled
    stub_ops = [
        {'op': 'add_element', 'name': 'Beta'},
        {'op': 'add_relationship', 'source': 'Alpha', 'target': 'Ghost'},   # 端点不存在 → 丢弃
        {'op': 'wat'},                                                      # 未知 op → 丢弃
    ]
    core.ai_service_config.enabled = True
    core.AIService.chat_completion = staticmethod(lambda *a, **kw: {
        'choices': [{'finish_reason': 'stop',
                     'message': {'content': _json.dumps({'operations': stub_ops})}}]})
    A.log_knowledge = lambda *a, **kw: None
    try:
        c = A.app.test_client()
        r = c.post(f'/api/v1/project/{pid}/ai/edit-model',
                   json={'kind': 'uml', 'instruction': '加个 Beta',
                         'elements': m.elements, 'connections': []},
                   headers={'X-Session-Id': sid})
        check(r.status_code == 200, f'HTTP 200（实得 {r.status_code}）')
        body = r.get_json() or {}
        check(body.get('applied_ops') == 1,
              f"applied_ops = 真实生效 1（实得 {body.get('applied_ops')}）")
        check(body.get('claimed_ops') == 3,
              f"claimed_ops = 模型提出 3（实得 {body.get('claimed_ops')}）")
        check(body.get('discarded_count') == 2,
              f"discarded_count = 2（实得 {body.get('discarded_count')}）")
        reasons = {d['reason'] for d in (body.get('discarded') or [])}
        check(reasons == {'unresolved_endpoint', 'unknown_op'},
              f'丢弃原因齐备（实得 {reasons}）')
        check(len(body.get('elements') or []) == 2, '画布拿到 2 个元素')
    finally:
        core.AIService.chat_completion = real_chat
        A.log_knowledge = real_log
        core.ai_service_config.enabled = was_enabled
        A.models_cache.pop(pid, None)
        sessions_cache.pop(sid, None)


def test_auto_repair():
    """校验 → 把错误回喂模型 → 重校验。断言机制，也断言早退不浪费调用。"""
    print('\n== 校验-回喂修复循环 ==')
    real_chat = core.AIService.chat_completion
    was_enabled = core.ai_service_config.enabled
    core.ai_service_config.enabled = True
    seen = []

    # 可修的错：ER 实体没有主键 → 用 add_field(isPrimary=True) 正好能补上。
    # （注意：UML 的「未命名元素」「悬空关系」反而**修不了**——ops 是按名字寻址的，
    #  而坏掉的东西没有合法名字。这是本机制的真实边界，见 docstring。）
    def stub_fix(messages, **kw):
        seen.append(messages)
        body = _json.dumps({'operations': [
            {'op': 'add_field', 'entity': 'User',
             'field': {'name': 'id', 'type': 'BIGINT', 'isPrimary': True}}]})
        return {'choices': [{'finish_reason': 'stop', 'message': {'content': body}}]}

    core.AIService.chat_completion = staticmethod(stub_fix)
    try:
        m = SimpleModel('repair')
        m.er_entities = [{'id': 1, 'name': 'User', 'fields': [
            {'name': 'name', 'type': 'VARCHAR(255)', 'isPrimary': False, 'isForeign': False}]}]
        m.er_relations = []
        raw = A._quality_issues_for_model(m)
        before = Q.repairable_issues(raw)
        check(len(raw) >= 2, f'原始校验如实包含「画布为空」提示（实得 {[(i["kind"], i["message"]) for i in raw]}）')
        check(len(before) == 1 and before[0]['kind'] == 'er',
              f'滤掉空画布后只剩 1 条可修问题（实得 {[(i["kind"], i["message"]) for i in before]}）')

        res = A._auto_repair_once(m, '')
        check(res.get('skipped') is False, f"未跳过（{res}）")
        check(res['after'] < res['before'], f"问题数下降 {res['before']} → {res['after']}")
        check(res['applied'].get('er', 0) >= 1, f"确有生效步数（{res['applied']}）")
        check(any(f.get('isPrimary') for f in m.er_entities[0]['fields']),
              '修复后实体有主键了')
        check(len(seen) == 1, f'只调了 1 次 LLM（实得 {len(seen)}）——按 kind 分组，不重复发')
        content = seen[0][1]['content'] if len(seen[0]) > 1 else ''
        check('没有定义主键' in content, '校验错误原文被回喂给模型')
        check('请只修复下列已检出的问题' in content, '指令带「只修这些」的约束语')

        print('\n== 修复循环：没病就不该吃药 ==')
        seen.clear()
        h = SimpleModel('healthy')
        h.er_entities = [{'id': 1, 'name': 'User', 'fields': [
            {'name': 'id', 'type': 'BIGINT', 'isPrimary': True, 'isForeign': False}]}]
        h.er_relations = []
        res2 = A._auto_repair_once(h, '')
        check(res2.get('skipped') is True, f"结构无问题 → skipped（{res2}）")
        check(seen == [], f'一次 LLM 都没调（实得 {len(seen)}）——早退生效')

        print('\n== 修复循环：AI 未启用时不折腾 ==')
        core.ai_service_config.enabled = False
        seen.clear()
        res3 = A._auto_repair_once(m, '')
        check(res3.get('skipped') is True and '未启用' in str(res3.get('reason')), f'{res3}')
        check(seen == [], '依旧 0 次调用')
    finally:
        core.AIService.chat_completion = real_chat
        core.ai_service_config.enabled = was_enabled


def test_best_of_n():
    """采样 N 次、用确定性校验器择优——不留长尾烂输出。"""
    print('\n== Best-of-N 采样择优 ==')
    from golden_cases import FARM
    real_chat = core.AIService.chat_completion
    was_enabled = core.ai_service_config.enabled
    core.ai_service_config.enabled = True

    bad = {'project_name': '差', 'uml': {'elements': [
        {'type': 'Class', 'name': 'A', 'attributes': [], 'methods': []},
        {'type': 'Class', 'name': 'A', 'attributes': [], 'methods': []}],       # 重名
        'relationships': [{'source': 'A', 'target': 'Ghost', 'type': 'Association'}]},
        'archimate': {'elements': [], 'relationships': []},
        'er': {'entities': [], 'relationships': []}}
    good = FARM['canonical']

    seq = [bad, good]
    calls = []

    def stub(messages, **kw):
        calls.append(kw.get('temperature'))
        return {'choices': [{'finish_reason': 'stop',
                             'message': {'content': _json.dumps(seq[min(len(calls) - 1, len(seq) - 1)])}}]}

    core.AIService.chat_completion = staticmethod(stub)
    try:
        payload, meta = A._generate_canonical_best_of_n('x', 3)
        # 注意不能用 `is`：候选是 JSON 解析出来的新 dict，不是原字面量
        check(payload is not None and payload.get('project_name') == good['project_name'],
              f"选中的是干净候选而非脏候选（实得 {payload and payload.get('project_name')}）")
        check(meta['tried'] == 2, f"采了 2 个候选就早退（实得 {meta['tried']}）")
        check(len(calls) == 2, f"第 3 次没再发请求（实得 {len(calls)} 次）")
        check(meta['best_score'] == 100.0, f"最高分 100（实得 {meta['best_score']}）")
        check(meta['scores'][0] < meta['scores'][1],
              f"脏候选得分更低（{meta['scores']}）")
        check(calls[0] == 0.3 and calls[1] != 0.3,
              f"第 1 次沿用原温度、后续调高（实得 {calls}）")

        print('\n== Best-of-N：采样全失败时立刻降级 ==')
        calls.clear()

        def failing(messages, **kw):
            calls.append(1)
            return {'choices': [{'finish_reason': 'length', 'message': {'content': '{"a"'}}]}

        core.AIService.chat_completion = staticmethod(failing)
        payload2, meta2 = A._generate_canonical_best_of_n('x', 3)
        check(payload2 is None, '没有可用候选')
        check(len(calls) == 1, f"第一次失败就不再空耗（实得 {len(calls)} 次）")
        check(meta2['failure_reasons'] == ['truncated'],
              f"失败原因被记下（实得 {meta2['failure_reasons']}）")
    finally:
        core.AIService.chat_completion = real_chat
        core.ai_service_config.enabled = was_enabled


def test_architect_agent_flow():
    """一键生成整条链路：建项目 → 三图 → 自动修复 → 基线 → 健康度 → 优化 → done。

    打桩 LLM 并拦掉落盘，所以既不发真请求、也不往开发库里写数据。
    """
    print('\n== 一键生成编排（7 步链路，打桩） ==')
    from golden_cases import FARM
    canonical = FARM['canonical']

    def stub(messages, **kw):
        sys_text = messages[0].get('content') or ''
        if 'project_name' in sys_text:
            return {'choices': [{'finish_reason': 'stop',
                                 'message': {'content': _json.dumps(canonical)}}]}
        if '健康度' in sys_text or 'score' in sys_text:
            return {'choices': [{'finish_reason': 'stop', 'message': {'content': _json.dumps(
                {'score': 88, 'issues': ['缺少服务层抽象'], 'suggestions': ['抽出服务接口'],
                 'summary': '结构基本合理'})}}]}
        return {'choices': [{'finish_reason': 'stop',
                             'message': {'content': _json.dumps({'operations': []})}}]}

    real_chat = core.AIService.chat_completion
    real_save_model, real_save_project, real_log = A.save_model, A.save_project, A.log_knowledge
    was_enabled = core.ai_service_config.enabled
    core.ai_service_config.enabled = True
    core.AIService.chat_completion = staticmethod(stub)
    # 拦掉落盘：只写内存缓存，不碰 SQLite
    A.save_model = lambda mid, m: A.models_cache.__setitem__(mid, m)
    A.save_project = lambda p: None
    A.log_knowledge = lambda *a, **kw: None
    before_keys = set(A.models_cache)
    try:
        steps, all_ids, done, gen_ok, repair_ok = [], [], None, None, None
        for ev in A._run_architect_agent('一个简单的电商系统', 'golden-user', True, 2):
            if ev.get('type') == 'step':
                all_ids.append(ev['step'])
                if ev.get('status') == 'running':
                    steps.append(ev['step'])
                if ev.get('step') == 'gen_uml' and ev.get('status') == 'ok':
                    gen_ok = ev.get('detail')
                if ev.get('step') == 'auto_repair' and ev.get('status') == 'ok':
                    repair_ok = ev.get('detail')
            if ev.get('type') == 'done':
                done = ev.get('result')

        print(f"    步骤序列：{' → '.join(steps)}")
        print(f"    全部步骤事件：{'、'.join(all_ids)}")
        # 注意：canonical 路径只发一个合并的「生成 UML/ArchiMate/ER」running 步骤，
        # 三图各自是 ok 事件——所以成员断言要看全部事件，顺序断言才看 running
        for want in ('create_project', 'gen_uml', 'gen_archimate', 'gen_er',
                     'auto_repair', 'save_version', 'health', 'apply_optimization'):
            check(want in all_ids, f'链路包含 {want} 步')
        check(steps.index('auto_repair') < steps.index('save_version'),
              '自动修复在保存基线快照**之前**（基线该记录已修复的模型）')
        check(steps.index('auto_repair') > steps.index('gen_uml'),
              '自动修复在三图生成**之后**')
        check(done is not None, '收到了 done 事件')
        if done:
            check(bool(done.get('project_id')), f"done 带 project_id（{done.get('project_id')}）")
            summary = str(done.get('chat_summary') or '')
            check('UML 类图' in summary and 'ER 数据模型' in summary, '摘要含三图统计')
            # 这个桩每次都返回同一个干净候选 → 第 1 个就 100 分 → 早退，只采了 1 个。
            # 此时**不该**声称「从 N 个候选中择优」——那种话只在真比较过时才说。
            check(gen_ok is not None, f'gen_uml 的 ok 事件带 detail（{gen_ok}）')
            if gen_ok:
                check(gen_ok['sample']['tried'] == 1,
                      f"第 1 个候选就满分 → 只采 1 个（实得 {gen_ok['sample']['tried']}）")
                check(gen_ok['sample']['requested'] == 2, f"请求了 2 次（实得 {gen_ok['sample']['requested']}）")
                check(gen_ok['sample']['best_score'] == 100.0, 'best_score 记在事件里')
            check('已从' not in summary, f'只采 1 个时不谈「择优」（{summary[:80]}）')
            check((repair_ok or {}).get('skipped') is True
                  and (repair_ok or {}).get('reason') == '结构校验无问题',
                  f"干净模型上修复循环早退（{repair_ok}）")
        created = set(A.models_cache) - before_keys
        check(len(created) == 1, f'恰好新建 1 个项目（实得 {len(created)}）')
        for mid in created:
            A.models_cache.pop(mid, None)     # 清理，别把测试项目留在内存里
    finally:
        core.AIService.chat_completion = real_chat
        A.save_model, A.save_project, A.log_knowledge = real_save_model, real_save_project, real_log
        core.ai_service_config.enabled = was_enabled


def test_archimate_prompt_drift():
    """防漂移：提示词里的 ArchiMate 枚举必须与 constants.py 的白名单一致。

    这组值原先散在三处（app.py 校验用 / prompts.py 提示词 / 前端调色板），
    改一处忘一处就会「提示词让模型输出 A，后端白名单只认 B」——模型照着提示词
    给出的类型被后端静默改写，很难查。收敛到 constants.py 后，用这条断言锁住。
    """
    print('\n== ArchiMate 枚举防漂移 ==')
    from constants import (ARCHIMATE_ELEMENT_TYPES, ARCHIMATE_REL_TYPES, ARCHIMATE_LAYERS,
                           ARCHIMATE_ELEMENT_ENUM, ARCHIMATE_REL_ENUM, ARCHIMATE_LAYER_ENUM)

    # 常量之间的自洽：枚举串必须覆盖集合里的每一项（拼串时漏了就会被抓）
    for label, enum, items in (('元素', ARCHIMATE_ELEMENT_ENUM, ARCHIMATE_ELEMENT_TYPES),
                               ('关系', ARCHIMATE_REL_ENUM, ARCHIMATE_REL_TYPES),
                               ('层次', ARCHIMATE_LAYER_ENUM, ARCHIMATE_LAYERS)):
        missing = [t for t in items if t not in enum.split('/')]
        check(not missing, f'{label}枚举串覆盖白名单全部（缺 {missing}）')
        extra = [t for t in enum.split('/') if t not in items]
        check(not extra, f'{label}枚举串没有多余项（多 {extra}）')

    # 三处提示词的正文里必须逐个出现
    import prompts
    prompts_texts = {
        'edit_model_system_prompt(archimate)': prompts.edit_model_system_prompt('archimate'),
        'ARCHIMATE_GENERATE_SYSTEM_PROMPT': prompts.ARCHIMATE_GENERATE_SYSTEM_PROMPT,
        'ARCHITECT_GENERATE_SYSTEM_PROMPT': prompts.ARCHITECT_GENERATE_SYSTEM_PROMPT,
    }
    for name, text in prompts_texts.items():
        miss_e = [t for t in ARCHIMATE_ELEMENT_TYPES if t not in text]
        miss_r = [t for t in ARCHIMATE_REL_TYPES if t not in text]
        miss_l = [t for t in ARCHIMATE_LAYERS if t not in text]
        check(not miss_e, f'{name} 含全部元素类型（缺 {miss_e}）')
        check(not miss_r, f'{name} 含全部关系类型（缺 {miss_r}）')
        check(not miss_l, f'{name} 含全部层次（缺 {miss_l}）')

    # JSON 示例的大括号没被 f-string 吃掉（重构时最容易错的地方）
    for name, text in prompts_texts.items():
        check('{{' not in text and '}}' not in text,
              f'{name} 没有残留的转义大括号（f-string 忘了还原）')
    # 后端布局器与前端配色用的层色必须一致（值本身写死在两处语言里，至少锁住后端这份）
    from constants import ARCH_HEAD, ARCH_BODY
    check(set(ARCH_HEAD) == set(ARCHIMATE_LAYERS), 'ARCH_HEAD 的键与层次白名单一致')
    check(set(ARCH_BODY) == set(ARCHIMATE_LAYERS), 'ARCH_BODY 的键与层次白名单一致')


def test_truncation_signal():
    """截断必须单独成一个信号——不能与「模型答错」混为一谈。"""
    print('\n== 截断信号（core.chat_json） ==')
    real_chat = core.AIService.chat_completion
    was_enabled = core.ai_service_config.enabled

    def stub(payload):
        core.AIService.chat_completion = staticmethod(lambda *a, **kw: payload)

    core.ai_service_config.enabled = True   # 让函数进到调用分支，真正的拦截靠打桩
    try:
        stub({'choices': [{'finish_reason': 'stop', 'message': {'content': '{"a": 1}'}}]})
        check(core.chat_json([]) == ({'a': 1}, ''), '正常 JSON → (data, "")')

        stub({'choices': [{'finish_reason': 'length', 'message': {'content': '{"a": 1'}}]})
        data, reason = core.chat_json([])
        check(data is None and reason == 'truncated',
              f'截断 → (None, truncated)（实得 {data!r}, {reason!r}）')

        stub({'choices': [{'finish_reason': 'stop', 'message': {'content': '这不是 JSON'}}]})
        check(core.chat_json([])[1] == 'invalid_json', '坏 JSON → invalid_json')

        stub({'choices': [{'finish_reason': 'stop', 'message': {'content': '   '}}]})
        check(core.chat_json([])[1] == 'empty', '空内容 → empty')

        stub({'error': 'AI服务未启用，请配置API密钥'})
        check(core.chat_json([])[1].startswith('error:'), '错误 dict → error:')

        stub({'oops': 1})
        check(core.chat_json([])[1] == 'error:no_choices',
              f'缺 choices → 明确原因（实得 {core.chat_json([])[1]}）')

        # 关键回归：截断的 canonical 绝不能当成功
        stub({'choices': [{'finish_reason': 'length',
                           'message': {'content': '{"project_name": "半截"}'}}]})
        cand, reason = A._agent_generate_canonical('x')
        check(cand is None and reason == 'truncated',
              f'canonical 遇截断必须返回 None（实得 {cand!r}, {reason!r}）')

        stub({'choices': [{'finish_reason': 'stop', 'message': {
            'content': '{"project_name":"X","uml":{"elements":[],"relationships":[]}}'}}]})
        cand, reason = A._agent_generate_canonical('x')
        check(isinstance(cand, dict) and reason == '', f'合法 canonical 正常返回（reason={reason!r}）')

        stub({'choices': [{'finish_reason': 'stop', 'message': {'content': '{"project_name":"X"}'}}]})
        cand, reason = A._agent_generate_canonical('x')
        check(cand is None and reason == 'no_uml', f'缺 uml 段 → no_uml（实得 {reason!r}）')

        stub({'choices': [{'finish_reason': 'length',
                           'message': {'content': '{"operations": ['}}]})
        ops, reason = A._ai_edit_model_verbose('uml', '当前模型', '加个字段', '')
        check(ops is None and reason == 'truncated',
              f'编辑操作被截断也要暴露（实得 {ops!r}, {reason!r}）')
    finally:
        core.AIService.chat_completion = real_chat
        core.ai_service_config.enabled = was_enabled


def test_validators_use_ai_flag():
    print('\n== 校验器 use_ai 开关（打分路径不得触发 LLM） ==')
    import uml_ai
    m, _c = _materialize(CANONICAL_CASES[0])

    r_arch = A.review_archimate_model(m, use_ai=False)
    check(not any(w.get('type') == 'semantic' for w in (r_arch.get('warnings') or [])),
          'ArchiMate use_ai=False 时不产出语义类问题')
    r_uml = uml_ai.validate_uml_model(m, use_ai=False)
    check(not any(w.get('type') == 'semantic' for w in (r_uml.get('warnings') or [])),
          'UML use_ai=False 时不产出语义类问题')
    check(isinstance(r_uml.get('errors'), list) and isinstance(r_arch.get('errors'), list),
          '结构规则仍然照常返回（不是整个短路）')
    check(LLM_CALLS == [], f'两条校验路径全程 0 次 LLM 调用（实得 {len(LLM_CALLS)}）')
    # 默认值必须是 True，否则既有调用方的行为会变
    import inspect
    check(inspect.signature(A.review_archimate_model).parameters['use_ai'].default is True,
          'review_archimate_model 的 use_ai 默认 True（既有调用方行为不变）')
    check(inspect.signature(uml_ai.validate_uml_model).parameters['use_ai'].default is True,
          'validate_uml_model 的 use_ai 默认 True')


def run_live():
    """真调 LLM。只断言任何合理输出都成立的不变量，因此永不随机失败。"""
    print('== --live：真实生成（只断言必然成立的不变量） ==')
    if not core.ai_service_config.enabled:
        print('  SKIP 未配置 API 密钥，--live 全部跳过')
        return
    for case in LIVE_CASES:
        texts = []
        for i in range(case['repeats']):
            cand, reason = A._agent_generate_canonical(case['text'])
            if cand is None:
                print(f"  {case['id']} 第 {i + 1} 次：返回 None（原因 {reason}）")
                continue
            m = SimpleModel(case['id'])
            try:
                A._apply_canonical_to_model(m, cand)
            except Exception as e:   # noqa: BLE001
                check(False, f"{case['id']} 第 {i + 1} 次物化抛异常：{e}")
                continue
            stats = Q.model_structure_stats(m)
            issues = Q.group_by_kind(Q.normalize_uml_issues(A.review_archimate_model(m), 'archimate'))
            score, detail = Q.candidate_score(issues, stats)
            texts.append((score, detail))
            print(f"  {case['id']} 第 {i + 1} 次：评分 {score}，明细 {detail}")
            check(all(v > 0 for v in stats['counts'].values()),
                  f"{case['id']} 第 {i + 1} 次：三图都非空 {stats['counts']}")
            for e in m.er_entities:
                if not any(f.get('isPrimary') for f in (e.get('fields') or [])):
                    check(False, f"{case['id']}：ER 实体 {e['name']} 没有主键")
        if len(texts) >= 2:
            spread = max(t[0] for t in texts) - min(t[0] for t in texts)
            print(f"  [信息] {case['id']} 同一输入 {len(texts)} 次采样的评分极差 = {spread}（不断言）")


def main():
    live = '--live' in sys.argv

    was_enabled = core.ai_service_config.enabled
    real_chat = core.AIService.chat_completion
    core.ai_service_config.enabled = False
    core.AIService.chat_completion = staticmethod(_forbidden)
    try:
        if live:
            # --live 要真网络，恢复真实配置
            core.ai_service_config.enabled = was_enabled
            core.AIService.chat_completion = real_chat
            run_live()
        else:
            test_structural_invariants()
            test_layout_report()
            test_scorer_on_real_models()
            test_fallback_path()
            test_cross_map_expectations()
            test_validators_use_ai_flag()
            test_edit_report_integration()
            test_edit_api_contract()
            test_auto_repair()
            test_archimate_prompt_drift()
            test_best_of_n()
            test_architect_agent_flow()
            test_truncation_signal()
    finally:
        core.ai_service_config.enabled = was_enabled
        core.AIService.chat_completion = real_chat

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
