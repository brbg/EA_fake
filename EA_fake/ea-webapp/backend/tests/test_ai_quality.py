"""ai_quality.py 的纯函数自测（不依赖 pytest，直接 `py backend/tests/test_ai_quality.py` 运行）。

覆盖：issue 归一化（含 semantic 过滤）、ER 视图适配（类型词表映射）、
确定性打分器（单调性 / 空模型惩罚 / 纯度）、择优排序、EditReport、跨图命名判定表。

全部离线：本文件不调 LLM，也不依赖 AIService 是否启用。
"""

import os
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8')   # Windows 控制台默认 GBK，中文与 emoji 会炸
except Exception:   # noqa: BLE001
    pass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ai_quality as Q   # noqa: E402

FAILED = []


def check(cond, label):
    if cond:
        print(f'  ok   {label}')
    else:
        print(f'  FAIL {label}')
        FAILED.append(label)


def _issues(severity, n, kind='uml', type_='naming'):
    return [{'kind': kind, 'type': type_, 'severity': severity,
             'message': f'{severity} #{i}', 'where': '', 'suggestion': ''} for i in range(n)]


def test_issue_normalization():
    print('== issue 归一化 ==')
    result = {
        'errors': [
            {'type': 'naming', 'severity': 'error', 'message': '元素未命名',
             'element_id': 3, 'element_name': ''},
            {'type': 'relationship', 'severity': 'error', 'message': '关系悬空',
             'relationship_id': 7, 'source': 1, 'target': 2},
        ],
        'warnings': [
            {'type': 'semantic', 'severity': 'error', 'message': 'AI 觉得这个设计不好'},
            {'type': 'attribute', 'severity': 'warning', 'message': '属性过多', 'element_name': 'Order'},
        ],
    }
    issues = Q.normalize_uml_issues(result)
    check(len(issues) == 3, f'3 条（semantic 被排除，实得 {len(issues)}）')
    check(all(i['severity'] != 'error' or i['type'] != 'semantic' for i in issues),
          'type=semantic 的条目一条都没进来')
    check(issues[0]['where'] == '元素 #3', f"无名字时退回 id：{issues[0]['where']}")
    check(issues[1]['where'] == '关系 1 → 2', f"关系位置：{issues[1]['where']}")
    check(issues[2]['where'] == '元素「Order」', f"有名字用名字：{issues[2]['where']}")
    check(all(i['kind'] == 'uml' for i in issues), 'kind 全部标注为 uml')
    check(Q.normalize_uml_issues(None) == [], 'None 输入返回空列表不抛')
    check(Q.normalize_uml_issues({'errors': ['不是 dict']}) == [], '脏数据被跳过')

    print('\n== ER issue（结构化键优先，正则保底） ==')
    er_structured = Q.normalize_er_issues([
        {'type': 'no_primary_key', 'severity': 'error',
         'message': "实体'订单'没有定义主键", 'suggestion': '加主键',
         'entity_name': '订单'},
    ])
    check(er_structured[0]['where'] == '实体「订单」', f"结构化键：{er_structured[0]['where']}")
    check(er_structured[0]['severity'] == 'error', 'severity 保留')
    er_regex = Q.normalize_er_issues([
        {'type': 'wrong_id_type', 'severity': 'warning',
         'message': "实体'sys_user'的属性'user_id'使用了不合适的数据类型'string'"},
        {'type': 'missing_fk_index', 'severity': 'warning',
         'message': "实体'sys_order'的外键'product_id'缺少索引"},
        {'type': 'wrong_amount_type', 'severity': 'warning',
         'message': "实体'sys_order'的金额字段'price'使用了'string'类型"},
        {'type': 'entity_name_space', 'severity': 'warning',
         'message': "实体'my table'名称包含空格"},
    ])
    check(er_regex[0]['where'] == '实体「sys_user」的字段「user_id」', f"正则保底：{er_regex[0]['where']}")
    check(er_regex[1]['where'] == '实体「sys_order」的字段「product_id」', f"外键：{er_regex[1]['where']}")
    check(er_regex[2]['where'] == '实体「sys_order」的字段「price」', f"金额字段：{er_regex[2]['where']}")
    check(er_regex[3]['where'] == '实体「my table」', f"只有实体：{er_regex[3]['where']}")

    print('\n== 分组与指令 ==')
    grouped = Q.group_by_kind(_issues('error', 1, 'uml') + _issues('warning', 2, 'er'))
    check(set(grouped) == {'uml', 'er'} and len(grouped['er']) == 2, '按 kind 分组正确')
    instr = Q.issues_to_instruction(_issues('error', 3, 'uml'))
    check('请只修复下列已检出的问题' in instr and instr.count('- [error]') == 3, '指令含 3 条且带约束语')
    check(Q.issues_to_instruction([]) == '', '空 issue 返回空串')
    many = Q.issues_to_instruction(_issues('error', 40), limit=12)
    check(many.count('- [error]') <= 12, f'条数受 limit 限制（实得 {many.count("- [error]")}）')


def test_er_view_shim():
    print('\n== ER 视图适配（承重：词表映射错了会产出假问题） ==')
    entities = [{
        'id': 1, 'name': 'sys_user', 'fields': [
            {'name': 'id', 'type': 'INT', 'isPrimary': True},
            {'name': 'name', 'type': 'VARCHAR(255)'},
            {'name': 'memo', 'type': 'TEXT'},
            {'name': 'tags', 'type': 'JSON'},
            {'name': 'price', 'type': 'DECIMAL(10,2)'},
            {'name': 'created_at', 'type': 'DATETIME'},
            {'name': 'ok', 'type': 'BOOLEAN'},
            {'name': 'amount', 'type': 'MONEY'},
            {'name': 'big', 'type': 'BIGINT'},
            {'name': 'unknown_thing', 'type': 'WEIRD'},
        ],
    }]
    view = Q.er_view_shim(entities, [{'id': 1, 'startEntity': 1, 'endEntity': 1}])
    by_name = {a['name']: a for a in view.entities[0]['attributes']}
    expected = {
        'id': 'integer', 'name': 'string', 'memo': 'text', 'tags': 'json',
        'price': 'decimal', 'created_at': 'datetime', 'ok': 'boolean',
        'amount': 'decimal', 'big': 'bigint', 'unknown_thing': 'string',
    }
    for name, want in expected.items():
        check(by_name[name]['data_type'] == want, f"{name}: {by_name[name]['data_type']} == {want}")
    check(by_name['name'].get('length') == 255, "VARCHAR(255) 带出 length=255")
    check(by_name['id'].get('length') is None, 'INT 不带 length（避免误触字符串长度检查）')
    check(by_name['id']['is_primary_key'] is True and by_name['id']['is_foreign_key'] is False, '主/外键标记')
    check(view.relationships[0] == {'source_entity_id': 1, 'target_entity_id': 1}, '关系端点键名映射')
    check(view.indexes == [], 'indexes 缺省为空列表（check_indexes 会遍历它）')

    # 真实串起来跑一遍四个 checker，证明 shim 的形状能被它们消费
    import er_routes as ER
    checks = (ER.check_normal_forms(view) + ER.check_indexes(view)
              + ER.check_data_types(view) + ER.check_naming_conventions(view))
    check(isinstance(checks, list), f'四个 checker 可消费 shim（产出 {len(checks)} 条）')
    # price 是 decimal → 不该报「金额字段类型不对」；amount 也是 decimal → 同样不报
    check(not any('金额字段' in i['message'] for i in checks),
          f"decimal 金额字段未被误报（实得 {[i['message'] for i in checks if '金额' in i['message']]}）")
    # memo 是 text 且非主键 → 不该报 1NF
    check(not any(i['type'] == '1nf_violation' for i in checks),
          '非主键的 TEXT 未误报 1NF')
    # user_id 这种 id 结尾的字段在这里没有，id 是 integer → 不该报 wrong_id_type
    check(not any(i['type'] == 'wrong_id_type' for i in checks),
          f"integer 主键未误报 ID 类型（实得 {[i['message'] for i in checks if i['type'] == 'wrong_id_type']}）")


def test_er_field_type():
    print('\n== ER 字段类型闭合校验 ==')
    # 旧实现是 `str(x or 'string').upper()`：既不校验、默认值也是坏的
    check(Q.normalize_er_field_type(None) == 'VARCHAR(255)', '缺省不再是坏的 STRING')
    check(Q.normalize_er_field_type('') == 'VARCHAR(255)', '空串走默认')
    check(Q.normalize_er_field_type('VARCHAR(100)') == 'VARCHAR(100)', '合法类型原样保留（带长度）')
    check(Q.normalize_er_field_type('DECIMAL(10,2)') == 'DECIMAL(10,2)', '合法精度原样保留')
    check(Q.normalize_er_field_type('bigint') == 'BIGINT', '小写归一成大写')
    # canonical 给的是逻辑类型，要映射到画布惯用写法
    check(Q.normalize_er_field_type('string') == 'VARCHAR(255)', 'string → VARCHAR(255)')
    check(Q.normalize_er_field_type('integer') == 'INT', 'integer → INT')
    check(Q.normalize_er_field_type('decimal') == 'DECIMAL(10,2)', 'decimal → DECIMAL(10,2)')
    check(Q.normalize_er_field_type('datetime') == 'DATETIME', 'datetime 原样')
    check(Q.normalize_er_field_type('boolean') == 'BOOLEAN', 'boolean 原样')

    report = []
    check(Q.normalize_er_field_type('FOOBAR', report) == 'VARCHAR(255)', '非法类型回落默认')
    check(len(report) == 1 and 'FOOBAR' in report[0], f'并记录原因：{report}')
    check(Q.normalize_er_field_type('VARCHAR(255); DROP TABLE x', report) == 'VARCHAR(255)',
          '带杂质的值不被当成合法类型放行')
    check(len(report) == 2, '也记了一条')
    for base in ('INT', 'BIGINT', 'VARCHAR', 'TEXT', 'JSON', 'DECIMAL', 'DATETIME', 'BOOLEAN', 'BLOB'):
        check(base in Q.ER_FIELD_TYPES, f'{base} 在词表内')
    check('STRING' not in Q.ER_FIELD_TYPES, 'STRING 不在词表内（它是旧实现造出来的）')


def test_scorer():
    print('\n== 打分器 ==')
    check(Q.score_issues([]) == 100.0, '无问题 → 100 分')
    # 逐条严重度必须单调：error > warning > minor > suggestion
    w = Q.SEVERITY_WEIGHT
    check(w['error'] > w['warning'] > w['minor'] > w['suggestion'], f'严重度权重单调：{w}')
    check(Q.score_issues(_issues('error', 1)) < Q.score_issues(_issues('warning', 1)),
          '1 个 error 比 1 个 warning 扣得多')
    check(Q.score_issues(_issues('error', 3)) != Q.score_issues(_issues('warning', 9)),
          '3 error 与 9 warning 不会打平（消除 12/4 的整除歧义）')
    # 既定取舍：warning 权重取 4.5，于是 9 个 warning(40.5) 比 3 个 error(36) 扣得多。
    # 这只是刻度选择，best-of-N 只需要单调排序；真要改刻度请连着这条断言一起改。
    check(Q.score_issues(_issues('warning', 9)) < Q.score_issues(_issues('error', 3)),
          '9 个 warning 比 3 个 error 扣得多（4.5 权重的既定取舍）')
    check(Q.score_issues(_issues('error', 1)) == 88.0, '1 个 error 扣 12')
    check(Q.score_issues([{'severity': '未知级别'}]) == 96.0, '未知严重度按 4 分扣')
    check(Q.score_issues(_issues('error', 20)) == 0.0, '扣穿后 clamp 到 0')
    check(Q.score_issues([], empty_maps=3) == 0.0, '三个 kind 全空 → 0 分（防空模型拿满分）')
    check(Q.score_issues([], isolated=100) == 90.0, '孤立惩罚封顶 10')

    stats_full = {'counts': {'uml': 5, 'archimate': 5, 'er': 4}, 'dup_names': 0, 'isolated': 0}
    stats_empty = {'counts': {'uml': 0, 'archimate': 0, 'er': 0}, 'dup_names': 0, 'isolated': 0}
    good, detail = Q.candidate_score({'uml': [], 'archimate': [], 'er': []}, stats_full)
    empty, _ = Q.candidate_score({'uml': [], 'archimate': [], 'er': []}, stats_empty)
    check(good == 100.0 and detail['empty_kinds'] == 0, f'有内容且无错 → 100（实得 {good}）')
    check(empty < good, f'空模型严格低于有内容的（{empty} < {good}）')

    print('\n== 打分器纯度（关键：不得触发 LLM） ==')
    import core
    real_chat = core.AIService.chat_completion
    real_enabled = core.ai_service_config.enabled
    calls = []

    def boom(*a, **kw):
        calls.append(1)
        raise AssertionError('打分器不该调 LLM！')

    core.AIService.chat_completion = staticmethod(boom)
    core.ai_service_config.enabled = True
    try:
        issues = Q.normalize_uml_issues({'errors': [{'type': 'naming', 'severity': 'error',
                                                     'message': 'x', 'element_id': 1}]})
        score, _d = Q.candidate_score(Q.group_by_kind(issues), stats_full)
        check(score == 88.0, f'打分不抛异常（实得 {score}）')
        check(Q.pick_best([])[0] is None, 'pick_best 空输入不抛')
        check(calls == [], f'全程 0 次 LLM 调用（实得 {len(calls)}）')
    finally:
        core.AIService.chat_completion = real_chat
        core.ai_service_config.enabled = real_enabled

    print('\n== 择优排序（全确定） ==')
    cands = [
        {'index': 0, 'score': 90.0, 'element_count': 5, 'relation_count': 3},
        {'index': 1, 'score': 90.0, 'element_count': 5, 'relation_count': 4},
        {'index': 2, 'score': 95.0, 'element_count': 2, 'relation_count': 1},
        {'index': 3, 'score': 90.0, 'element_count': 5, 'relation_count': 4},
    ]
    best, report = Q.pick_best(cands)
    check(best['index'] == 2, f'分数优先（实得 index={best["index"]}）')
    check(report['samples'] == 4 and report['best_score'] == 95.0, f'报告完整：{report}')
    tied = Q.pick_best([c for c in cands if c['score'] == 90.0])[0]
    check(tied['index'] == 1, f'同分比关系数再比序号（实得 index={tied["index"]}）')
    check(Q.pick_best([]) == (None, {'reason': 'no_candidates'}), '空输入有明确报告')
    check(Q.sample_count_from(None) == 3 and Q.sample_count_from('2') == 2, '采样次数解析')
    check(Q.sample_count_from(99) == 5 and Q.sample_count_from(0) == 1, '采样次数被 clamp 到 [1,5]')


def test_edit_report():
    print('\n== 编辑报告 ==')
    r = Q.EditReport()
    r.begin('uml')
    r.ok()
    r.ok()
    r.begin('er')
    r.ok()
    r.skip({'op': 'add_relationship', 'source': 'X'}, 'unknown_element', 'X 不存在')
    r.skip('不是 dict', 'bad_op')
    check(r.applied == 3, f'生效数 3（实得 {r.applied}）')
    check(r.applied_for('uml') == 2 and r.applied_for('er') == 1, '按图分别计数')
    check(r.applied_for('archimate') == 0, '没碰过的图返回 0')
    s = r.summary()
    check(s['applied'] == 3 and s['discarded_count'] == 2, f"summary：{s['applied']}/{s['discarded_count']}")
    check(s['discarded'][1]['op'] == '' and s['discarded'][0]['op'] == 'add_relationship',
          '非 dict 的 op 不会让报告崩')
    check('生效 3 步' in r.summary_text() and '未生效' in r.summary_text(), f'文案：{r.summary_text()}')
    clean = Q.EditReport()
    clean.begin('uml')
    clean.ok()
    check('未生效' not in clean.summary_text(), f"无丢弃时文案干净：{clean.summary_text()}")


def test_naming():
    print('\n== 跨图命名：判定表 ==')
    cases = [
        ('Order', 'Order', ('same', 'identical_key')),
        ('orders', 'orders', ('same', 'identical_key')),
        # 跨命名约定 = 设计使然，不改也不报
        ('Order', 'orders', ('same', 'cross_convention')),
        ('order_item', 'OrderItem', ('same', 'cross_convention')),
        # 去前后缀
        ('sys_user', 'user', ('high', 'affix_strip')),
        ('OrderInfo', 'Order', ('high', 'affix_strip')),
        # 同义词
        ('dept', 'department', ('high', 'synonym_token')),
        ('user_order', 'user_trade', ('high', 'synonym_last_token')),
        # 真的不同
        ('Order', 'Customer', ('different', 'none')),
        ('order_item', 'Customer', ('different', 'none')),
    ]
    for a, b, want in cases:
        got = Q.classify_name_pair(a, b)
        check(got == want, f'{a!r} vs {b!r} → {got}（期望 {want}）')

    print('\n== 跨图命名：安全阀 ==')
    check(Q.classify_name_pair('用户', 'User')[0] == 'different', '中文名不与英文名互判')
    check(Q.classify_name_pair('用户', '用户表')[0] == 'different', '中文名之间也不自动改')
    check(Q.classify_name_pair('', 'Order')[0] == 'different', '空名不判定')
    check(Q.classify_name_pair('ab', 'Order')[1] == 'too_short_or_numeric', '过短名不判定')
    check(Q.classify_name_pair('123', '456')[1] == 'too_short_or_numeric', '纯数字不判定')

    print('\n== 跨图命名：单数化不误伤 ==')
    for word in ('address', 'status', 'analysis', 'business'):
        check(Q._singular(word) == word, f'{word} 不被误单数化')
    check(Q._singular('orders') == 'order', 'orders → order')
    check(Q._singular('categories') == 'category', 'categories → category')
    check(Q._singular('statuses') == 'status', 'statuses → status')
    check(Q._singular('boxes') == 'box', 'boxes → box')
    check(Q.name_key('OrderItems') == 'order_item', f"OrderItems → {Q.name_key('OrderItems')}")
    check(Q.name_key('order_items') == 'order_item', f"order_items → {Q.name_key('order_items')}")
    check(Q.name_key('sys_user') == 'sys_user', f"sys_user 不被单数化搞坏（实得 {Q.name_key('sys_user')}）")
    check(Q.name_key('gas') == 'gas' and Q.name_key('bus') == 'bus', '短词不被误单数化')
    check(Q.convention_of('Order') == 'pascal' and Q.convention_of('order') == 'camel',
          '命名约定识别')

    print('\n== 跨图命名：对照与改名 ==')
    class _M:
        pass

    m = _M()
    m.elements = [{'id': 1, 'name': 'Order'}, {'id': 2, 'name': 'Customer'}]
    m.archimate_elements = []
    m.er_entities = [
        {'id': 1, 'name': 'sys_order', 'fields': []},      # 去前缀 → 可自动改
        {'id': 2, 'name': 'Customer', 'fields': []},       # 已一致
        {'id': 3, 'name': 'order_entry', 'fields': []},    # 共享 token 但名字不同 → 只报告
    ]
    diff = Q.cross_map_diff(m)
    check(len(diff['renames']) == 1, f"1 项可自动改（实得 {diff['renames']}）")
    check(diff['renames'][0]['from'] == 'sys_order' and diff['renames'][0]['to'] == 'Order',
          f"改名项正确：{diff['renames'][0]}")
    check(diff['same'] == 1, f"1 项已一致（实得 {diff['same']}）")
    check(any('order_entry' in r for r in diff['reports']), f"只报告项含 order_entry：{diff['reports']}")

    print('\n== 跨图命名：角色后缀不当作不一致 ==')
    # ArchiMate 的 XxxService 对应 UML 的 Xxx 类是三图之间的惯用写法，
    # 报出来只会淹没真正该看的问题
    class _M4:
        pass

    m4 = _M4()
    m4.elements = [{'id': 1, 'name': 'Order'}, {'id': 2, 'name': 'Product'}]
    m4.er_entities = []
    m4.archimate_elements = [
        {'id': 1, 'name': 'OrderService'},
        {'id': 2, 'name': 'ProductComponent'},
        {'id': 3, 'name': 'OrderManager'},
    ]
    d4 = Q.cross_map_diff(m4)
    check(d4['reports'] == [], f'只差角色后缀不报告（实得 {d4["reports"]}）')
    # 但非角色后缀的差异仍要报
    m4.archimate_elements.append({'id': 4, 'name': 'OrderEntry'})
    d4b = Q.cross_map_diff(m4)
    check(len(d4b['reports']) == 1 and 'OrderEntry' in d4b['reports'][0],
          f'非角色后缀的差异仍报告（实得 {d4b["reports"]}）')

    applied = Q.apply_cross_map_renames(m, diff['renames'])
    check(applied == 1 and m.er_entities[0]['name'] == 'Order', f'改名生效（{applied} 条）')
    check(Q.cross_map_diff(m)['renames'] == [], '幂等：再跑一次无可改项')

    # 会造成重名时不改
    m2 = _M()
    m2.elements = [{'id': 1, 'name': 'Order'}]
    m2.archimate_elements = []
    m2.er_entities = [{'id': 1, 'name': 'sys_order'}, {'id': 2, 'name': 'Order'}]
    d2 = Q.cross_map_diff(m2)
    check(Q.apply_cross_map_renames(m2, d2['renames']) == 0, '改名会撞重名 → 放弃不改')

    # 同名匹配到多个候选 → 降级只报告
    m3 = _M()
    m3.elements = [{'id': 1, 'name': 'Order'}, {'id': 2, 'name': 'OrderInfo'}]
    m3.archimate_elements = []
    m3.er_entities = [{'id': 1, 'name': 'sys_order'}]
    d3 = Q.cross_map_diff(m3)
    check(d3['renames'] == [] and any('多个' in r for r in d3['reports']),
          f"多义时降级为报告：{d3['reports']}")
    check(Q.apply_cross_map_renames(m3, []) == 0, '空 renames 安全')


def main():
    test_issue_normalization()
    test_er_view_shim()
    test_er_field_type()
    test_scorer()
    test_edit_report()
    test_naming()

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
