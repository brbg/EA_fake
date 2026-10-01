"""AI 生成质量保障：issue 归一化 / 确定性打分 / 编辑报告 / 跨图命名对齐。

全是纯函数，不调 LLM、不碰数据库。

**硬约束：本模块不能 import app。**
`run.bat` 用 `python app.py` 启动时 app.py 的模块名是 `__main__`，
任何 `from app import ...` 都会二次导入整个 Flask 应用（重复 app 对象、
重复内存缓存、重复 `db.init_db()`）。需要 app 侧的东西一律由调用方注入
——与既有 `agent.py` 的「实现由调用方注入」风格一致。

**另一条硬约束：打分函数永不接受 model 对象。**
`validate_uml_model` / `review_archimate_model` **看起来**像纯校验器，
实际内部会调 LLM 做语义评审（uml_ai.py:585、app.py:4989）。若打分器直接吃
model，一次 best-of-N 会静默产生 3×2 次额外 LLM 调用、结果不可复现、
离线测试必然随机失败。所以打分器只接受 issue 列表 + 结构统计量。
"""

import re

# ---------------------------------------------------------------- issue 归一化

#: 严重度权重。error 是「模型坏了」（悬空关系／未命名元素／表无主键），必须压倒性。
#: warning 取 4.5 而非 4：让 3 个 error（36）严格小于 9 个 warning（40.5），
#: 消掉 12/4=3 这类整除带来的歧义。
SEVERITY_WEIGHT = {'error': 12.0, 'warning': 4.5, 'minor': 1.5, 'suggestion': 0.5}
DEFAULT_SEVERITY_WEIGHT = 4.0

ALL_KINDS = ('uml', 'archimate', 'er')

#: 「画布为空」这类提示，两处都要特殊对待：
#: - 修复循环里**追不动**：ops 是按名字寻址的，空画布没有名字可寻址，
#:   该由生成步骤去填充，不该让修复循环反复重试（还会把一个只有 ER 的
#:   健康模型误判成「有问题」，白花一次 LLM 调用）。
#: - 打分时**不重复算**：覆盖度惩罚（empty_maps）已经单独扣过分了。
STRUCTURAL_EMPTY_TYPES = frozenset({'empty'})


def is_structural_empty(issue):
    return str(issue.get('type') or '').lower() in STRUCTURAL_EMPTY_TYPES


def repairable_issues(issues):
    """滤掉修复循环追不动的提示（空画布）。"""
    return [i for i in (issues or []) if not is_structural_empty(i)]

#: ER 四个 checker 的 message 模板未契约化，改文案就会静默失效。
#: 所以优先读结构化键（er_routes 里加法式补的 entity_name/field_name），
#: 读不到才退回正则——正则只是保底适配。
_ER_ENTITY_RE = re.compile(r"实体'([^']+)'")
_ER_FIELD_RE = re.compile(r"(?:属性|外键|金额字段)'([^']+)'")


def _where_from_uml(issue):
    """从 UML/ArchiMate 校验器的 issue 里拼出人能读的位置。

    优先用「名字 / 关系两端」而不是不透明的 id——回喂给模型时，
    「关系 1 → 2」比「关系 #7」更能指明该改哪里。
    """
    if issue.get('element_name'):
        return f"元素「{issue['element_name']}」"
    src, dst = issue.get('source'), issue.get('target')
    if src is not None and dst is not None:
        return f"关系 {src} → {dst}"
    if issue.get('element_id') is not None:
        return f"元素 #{issue['element_id']}"
    if issue.get('relationship_id') is not None:
        return f"关系 #{issue['relationship_id']}"
    return ''


def _where_from_er(issue):
    entity = issue.get('entity_name')
    field = issue.get('field_name')
    if not entity:
        m = _ER_ENTITY_RE.search(str(issue.get('message') or ''))
        entity = m.group(1) if m else ''
    if not field:
        m = _ER_FIELD_RE.search(str(issue.get('message') or ''))
        field = m.group(1) if m else ''
    if entity and field:
        return f"实体「{entity}」的字段「{field}」"
    if entity:
        return f"实体「{entity}」"
    if field:
        return f"字段「{field}」"
    return ''


def normalize_uml_issues(result, kind='uml'):
    """`validate_uml_model` / `review_archimate_model` 的返回 dict → 统一 issue 列表。

    **排除 `type == 'semantic'`**：那是 LLM 语义评审的产物，不是确定性规则，
    纳入评分会让 best-of-N 不可复现（同一个候选每次得分都可能不同）。
    """
    if not isinstance(result, dict):
        return []
    out = []
    for bucket, default_sev in (('errors', 'error'), ('warnings', 'warning')):
        for issue in result.get(bucket) or []:
            if not isinstance(issue, dict):
                continue
            if issue.get('type') == 'semantic':
                continue
            if not issue.get('message'):
                continue
            out.append({
                'kind': kind,
                'type': str(issue.get('type') or ''),
                'severity': str(issue.get('severity') or default_sev).lower(),
                'message': str(issue['message']),
                'where': _where_from_uml(issue),
                'suggestion': str(issue.get('suggestion') or ''),
            })
    return out


def normalize_er_issues(issues, kind='er'):
    """ER 四个 `check_*` 的 `list[dict]` → 统一 issue 列表。"""
    out = []
    for issue in issues or []:
        if not isinstance(issue, dict) or not issue.get('message'):
            continue
        out.append({
            'kind': kind,
            'type': str(issue.get('type') or ''),
            'severity': str(issue.get('severity') or 'warning').lower(),
            'message': str(issue['message']),
            'where': _where_from_er(issue),
            'suggestion': str(issue.get('suggestion') or ''),
        })
    return out


def group_by_kind(issues):
    """按图种类分组——修复时只把某张图的问题发给那张图。"""
    grouped = {}
    for issue in issues or []:
        grouped.setdefault(issue.get('kind') or 'uml', []).append(issue)
    return grouped


def issues_to_instruction(issues, limit=12, budget=900):
    """把 issue 列表拼成回喂给模型的修复指令（沿用健康度优化链路的预算：12 条 / 800 字符）。"""
    lines = []
    used = 0
    for issue in (issues or [])[:limit]:
        line = f"- [{issue.get('severity')}]"
        where = issue.get('where')
        if where:
            line += f" {where}"
        line += f" {issue.get('message')}"
        tip = issue.get('suggestion')
        if tip:
            line += f"（建议：{tip}）"
        if used + len(line) > budget:
            break
        lines.append(line)
        used += len(line)
    if not lines:
        return ''
    return '请只修复下列已检出的问题，不要改动其它内容：\n' + '\n'.join(lines)


# ------------------------------------------------------------------ ER 视图适配

#: 画布词表（VARCHAR(255)/INT…）→ ER checker 词表（string/integer/bigint/decimal/text/json…）。
#: 顺序敏感：长的先匹配（BIGINT 必须在 INT 之前）。
_ER_BASE_TYPES = (
    ('BIGINT', 'bigint'),
    ('SMALLINT', 'integer'),
    ('TINYINT', 'integer'),
    ('MEDIUMINT', 'integer'),
    ('INT', 'integer'),
    ('INTEGER', 'integer'),
    ('VARCHAR', 'string'),
    ('NVARCHAR', 'string'),
    ('CHAR', 'string'),
    ('LONGTEXT', 'text'),
    ('MEDIUMTEXT', 'text'),
    ('TINYTEXT', 'text'),
    ('TEXT', 'text'),
    ('CLOB', 'text'),
    ('JSON', 'json'),
    ('DECIMAL', 'decimal'),
    ('NUMERIC', 'decimal'),
    ('MONEY', 'decimal'),
    ('FLOAT', 'decimal'),
    ('DOUBLE', 'decimal'),
    ('REAL', 'decimal'),
    ('DATETIME', 'datetime'),
    ('TIMESTAMP', 'datetime'),
    ('DATE', 'datetime'),
    ('TIME', 'datetime'),
    ('BOOLEAN', 'boolean'),
    ('BOOL', 'boolean'),
    ('BLOB', 'binary'),
)


#: 画布 ER 字段类型的闭合词表（大写基类型，可带长度/精度）
ER_FIELD_TYPES = {
    'INT', 'INTEGER', 'BIGINT', 'SMALLINT', 'TINYINT', 'MEDIUMINT',
    'VARCHAR', 'CHAR', 'TEXT', 'LONGTEXT', 'MEDIUMTEXT', 'TINYTEXT', 'CLOB',
    'DECIMAL', 'NUMERIC', 'FLOAT', 'DOUBLE', 'MONEY', 'REAL',
    'DATE', 'DATETIME', 'TIMESTAMP', 'TIME',
    'BOOLEAN', 'BOOL', 'JSON', 'BLOB',
}

#: canonical 提示词要求模型给逻辑类型（string/integer/decimal…），
#: 这里映射到画布惯用的具体类型，免得画布上出现 `STRING` 这种半截写法。
_ER_LOGICAL_ALIASES = {
    'STRING': 'VARCHAR(255)',
    'INTEGER': 'INT',
    'DECIMAL': 'DECIMAL(10,2)',
}


def normalize_er_field_type(raw, report=None, default='VARCHAR(255)'):
    """把自由文本的字段类型收敛到画布词表。

    以前这里是 `str(... or 'string').upper()`：既不校验（`FOO` 直接进模型），
    默认值本身也是坏的（`'string'.upper()` = `'STRING'`，不在任何 SQL 词表里）。
    """
    text = str(raw or '').strip().upper()
    if not text:
        return default
    m = re.match(r'^([A-Z]+)\s*(?:\(\s*\d+\s*(?:,\s*\d+\s*)?\))?$', text)
    base = m.group(1) if m else ''
    if base in _ER_LOGICAL_ALIASES:
        return _ER_LOGICAL_ALIASES[base]
    if base in ER_FIELD_TYPES:
        return text
    if report is not None:
        report.append(f'未知字段类型「{raw}」，已按 {default} 处理')
    return default


def er_base_type(raw):
    """画布类型 → `(checker 词表基类型, 长度或 None)`。

    映射错会产出假 warning → 触发假「修复」→ 越修越坏，所以这里逐条覆盖。
    """
    text = str(raw or '').strip().upper()
    m = re.match(r'^([A-Z]+)\s*(?:\(\s*(\d+)\s*(?:,\s*\d+\s*)?\))?', text)
    if not m:
        return 'string', None
    name, length = m.group(1), m.group(2)
    for prefix, base in _ER_BASE_TYPES:
        if name == prefix or name.startswith(prefix):
            return base, (int(length) if length and base == 'string' else None)
    return 'string', None


class _ERViewShim:
    """`check_*` 期望的 view 形状：`.entities` / `.relationships` / `.indexes`。"""

    def __init__(self, entities, relationships, indexes):
        self.entities = entities
        self.relationships = relationships
        self.indexes = indexes


def er_view_shim(er_entities, er_relations, indexes=None):
    """画布的 ER 实体/关系 → ER checker 的 view（字段名与类型词表都做映射）。"""
    entities = []
    for e in er_entities or []:
        if not isinstance(e, dict):
            continue
        attrs = []
        for f in e.get('fields') or []:
            if not isinstance(f, dict) or not f.get('name'):
                continue
            base, length = er_base_type(f.get('type'))
            attr = {
                'name': str(f['name']),
                'data_type': base,
                'is_primary_key': bool(f.get('isPrimary')),
                'is_foreign_key': bool(f.get('isForeign')),
            }
            if length is not None:
                attr['length'] = length
            attrs.append(attr)
        entities.append({'id': e.get('id'), 'name': str(e.get('name') or ''), 'attributes': attrs})

    relationships = []
    for r in er_relations or []:
        if not isinstance(r, dict):
            continue
        relationships.append({
            'source_entity_id': r.get('startEntity'),
            'target_entity_id': r.get('endEntity'),
        })
    return _ERViewShim(entities, relationships, list(indexes or []))


# -------------------------------------------------------------------- 确定性打分

#: 关系里指向元素 id 的键（三张图各用自己的命名）
_REL_ENDPOINT_KEYS = ('startElement', 'endElement', 'startEntity', 'endEntity', 'source', 'target')


def _kind_stats(items, rels):
    """单张图的重名数与孤立元素数。"""
    seen = {}
    ids = set()
    for it in items or []:
        if not isinstance(it, dict):
            continue
        name = str(it.get('name') or '').strip()
        if name:
            seen[name] = seen.get(name, 0) + 1
        if it.get('id') is not None:
            ids.add(it['id'])

    referenced = set()
    for r in rels or []:
        if not isinstance(r, dict):
            continue
        for key in _REL_ENDPOINT_KEYS:
            if r.get(key) is not None:
                referenced.add(r[key])

    dup = sum(c - 1 for c in seen.values() if c > 1)
    isolated = sum(1 for i in ids if i not in referenced)
    return len(seen), dup, isolated


def structure_stats(uml_elements=(), archimate_elements=(), er_entities=(),
                    uml_rels=(), archimate_rels=(), er_rels=()):
    """从纯数组算结构统计量（不碰 model 对象、不调 LLM）。

    刻意按图各自统计——三张图的元素 id 会撞号（UML #3 与 ER #3 不是同一个元素），
    混在一起算会把孤立元素漏掉。
    """
    countable = {}
    dup_names = 0
    isolated = 0
    for kind, items, rels in (
        ('uml', uml_elements, uml_rels),
        ('archimate', archimate_elements, archimate_rels),
        ('er', er_entities, er_rels),
    ):
        n, dup, iso = _kind_stats(items, rels)
        countable[kind] = n
        dup_names += dup
        isolated += iso
    return {'counts': countable, 'dup_names': dup_names, 'isolated': isolated}


def model_structure_stats(model):
    """从 model 取数组喂给 `structure_stats`（只读，不调 LLM）。"""
    return structure_stats(
        getattr(model, 'elements', None) or [],
        getattr(model, 'archimate_elements', None) or [],
        getattr(model, 'er_entities', None) or [],
        getattr(model, 'relationships', None) or [],
        getattr(model, 'archimate_connections', None) or [],
        getattr(model, 'er_relations', None) or [],
    )


def score_issues(issues, *, empty_maps=0, dup_names=0, isolated=0):
    """0~100 分，越高越干净。确定性，可离线断言。"""
    penalty = sum(SEVERITY_WEIGHT.get(str(i.get('severity') or '').lower(), DEFAULT_SEVERITY_WEIGHT)
                  for i in issues or [])
    # 覆盖度惩罚：防「空模型因无错拿满分」——打分器最容易犯的错
    penalty += 40.0 * max(0, empty_maps)
    penalty += 8.0 * max(0, dup_names)
    penalty += min(10.0, 1.0 * max(0, isolated))
    return max(0.0, min(100.0, 100.0 - penalty))


def candidate_score(kind_issues, stats=None):
    """`(分数, 明细)`。只吃 issue 列表与统计量，**永不接受 model**。"""
    stats = stats or {}
    if isinstance(kind_issues, dict):
        flat = [i for ks in kind_issues.values() for i in ks]
    else:
        flat = list(kind_issues or [])
    # 「画布为空」不参与逐条扣分：覆盖度惩罚已经单独扣过，重复算会双倍惩罚
    flat = [i for i in flat if not is_structural_empty(i)]
    counts = stats.get('counts') or {}
    empty_maps = sum(1 for k in ALL_KINDS if not counts.get(k))
    score = score_issues(flat, empty_maps=empty_maps,
                         dup_names=stats.get('dup_names', 0),
                         isolated=stats.get('isolated', 0))
    detail = {
        'score': round(score, 2),
        'issues': len(flat),
        'errors': sum(1 for i in flat if i.get('severity') == 'error'),
        'warnings': sum(1 for i in flat if i.get('severity') == 'warning'),
        'empty_kinds': empty_maps,
        'dup_names': stats.get('dup_names', 0),
        'isolated': stats.get('isolated', 0),
    }
    return score, detail


def pick_best(candidates):
    """择优。排序键全确定（便于离线断言）：

    分数降序 → 元素+关系总数降序 → 关系数降序 → 序号升序。
    """
    if not candidates:
        return None, {'reason': 'no_candidates'}

    def sort_key(c):
        total = int(c.get('element_count', 0)) + int(c.get('relation_count', 0))
        return (-float(c.get('score', 0)), -total, -int(c.get('relation_count', 0)), int(c.get('index', 0)))

    best = sorted(candidates, key=sort_key)[0]
    return best, {
        'samples': len(candidates),
        'best_index': best.get('index'),
        'best_score': round(float(best.get('score', 0)), 2),
        'scores': [round(float(c.get('score', 0)), 2) for c in candidates],
    }


def sample_count_from(raw, default=3, lo=1, hi=5):
    """采样次数的容错解析。"""
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


# ---------------------------------------------------------------------- 编辑报告

class EditReport:
    """把「模型说了要改几步」和「实际改成了几步」分开记。

    `applied` = 真正改动了模型的 op 数。「合法但无效果」的操作
    （如 delete_field 指向不存在的字段）计入 discarded —— 用户说了要改、
    实际没改，这正是必须让用户看到的差额。
    """

    def __init__(self):
        self.applied = 0
        self.discarded = []
        self._by_kind = {}
        self._kind = None

    def begin(self, kind):
        """切换当前处理的图种类。"""
        self._kind = kind

    def ok(self):
        self.applied += 1
        kind = self._kind or 'unknown'
        self._by_kind[kind] = self._by_kind.get(kind, 0) + 1

    def skip(self, op, reason, detail=''):
        op_name = ''
        if isinstance(op, dict):
            op_name = str(op.get('op') or '')
        self.discarded.append({'op': op_name, 'reason': reason, 'detail': str(detail)})

    def applied_for(self, kind):
        return self._by_kind.get(kind, 0)

    def summary(self):
        return {
            'applied': self.applied,
            'by_kind': dict(self._by_kind),
            'discarded': self.discarded,
            'discarded_count': len(self.discarded),
        }

    def summary_text(self, limit=3):
        """给用户看的一句话。"""
        if not self.discarded:
            return f'生效 {self.applied} 步'
        head = '、'.join(
            f"{d['op'] or '操作'}（{d['reason']}）" for d in self.discarded[:limit]
        )
        more = f" 等 {len(self.discarded)} 步" if len(self.discarded) > limit else ''
        return f'生效 {self.applied} 步，未生效 {head}{more}'


# ------------------------------------------------------------------ 跨图命名对齐

#: 不规则复数
_IRREGULAR = {
    'people': 'person', 'children': 'child', 'men': 'man', 'women': 'woman',
    'indices': 'index', 'statuses': 'status', 'data': 'data',
}
#: 后缀表（长的在前）
_PLURAL_SUFFIX = (('ies', 'y'), ('sses', 'ss'), ('xes', 'x'), ('ches', 'ch'),
                  ('shes', 'sh'), ('ses', 's'), ('s', ''))
#: 表名前缀/后缀（按 token 剥，剥完仍相同 → 高置信同义）
_AFFIX_PREFIX_TOKENS = {'t', 'tb', 'tbl', 'sys', 'biz', 'app'}
_AFFIX_SUFFIX_TOKENS = {'table', 'info', 'record', 'list'}
#: 保守同义词表。只放几乎不会误判的，宁可漏判不可错改。
_SYNONYM_SETS = (
    {'user', 'account', 'member'},
    {'dept', 'department'},
    {'role', 'authority'},
    {'product', 'goods', 'item'},
    {'customer', 'client'},
    {'category', 'type'},
    {'log', 'record'},
    {'employee', 'staff'},
    {'student', 'pupil'},
    {'order', 'trade'},
)

_KIND_LABEL = {'uml': 'UML 类', 'archimate': 'ArchiMate 元素', 'er': 'ER 实体'}

#: 跨图「角色后缀」是惯用写法而非命名不一致：ArchiMate 的 XxxService/XxxComponent
#: 本来就对应 UML 的 Xxx 类，ER 的 xxx_record 也是同一回事。若把它们都报出来，
#: 报告会被这类正常模式淹没，真正该看的反倒被埋掉。
_GENERIC_TOKENS = {
    'service', 'system', 'component', 'manager', 'handler', 'helper', 'impl',
    'info', 'data', 'object', 'entity', 'table', 'view', 'api',
    'controller', 'dto', 'vo', 'po', 'bo', 'record',
}


def _tokens(name):
    """camel / Pascal / snake / kebab / 空格 / 点 全折叠成小写 token 列表。"""
    s = str(name or '')
    s = re.sub(r'([a-z0-9])([A-Z])', r'\1 \2', s)          # camelCase → camel Case
    s = re.sub(r'[^0-9A-Za-z一-鿿]+', ' ', s)
    return [t.lower() for t in s.split() if t]


def _singular(tok):
    """保守单数化。ss/us/is 结尾直接返回，避免误伤 address / status / analysis。

    末尾裸 `s` 的词干要求 ≥3 字符：否则 `sys` → `sy`、`gas` → `ga`
    这类短词会被改烂（`tags` → `tag` 恰好是 3 字符，仍然生效）。
    """
    if len(tok) < 4:
        return tok
    if tok in _IRREGULAR:
        return _IRREGULAR[tok]
    if tok.endswith(('ss', 'us', 'is')):
        return tok
    for suffix, rep in _PLURAL_SUFFIX:
        stem = len(tok) - len(suffix)
        if tok.endswith(suffix) and stem >= (3 if suffix == 's' else 2):
            return tok[:-len(suffix)] + rep
    return tok


def name_key(name):
    """归一化后的比较键：token 拆开 + 单数化 + 小写。"""
    return '_'.join(_singular(t) for t in _tokens(name))


def _strip_affix_tokens(tokens):
    """按 token 剥表名前缀/后缀，返回 `(新 token 列表, 是否剥过)`。

    必须在单数化**之前**按 token 剥：`sys_user` 先单数化会变成 `sy_user`，
    前缀就再也匹配不上了。
    """
    out = list(tokens)
    stripped = False
    if len(out) >= 2 and out[0] in _AFFIX_PREFIX_TOKENS:
        out = out[1:]
        stripped = True
    if len(out) >= 2 and out[-1] in _AFFIX_SUFFIX_TOKENS:
        out = out[:-1]
        stripped = True
    return out, stripped


def _affix_key(name):
    """剥掉表名前缀/后缀后的比较键。"""
    toks, stripped = _strip_affix_tokens(_tokens(name))
    return '_'.join(_singular(t) for t in toks), stripped


def convention_of(name):
    s = str(name or '').strip()
    if not s:
        return 'empty'
    if re.search(r'[一-鿿]', s):
        return 'cjk'
    if '_' in s:
        return 'snake'
    if '-' in s:
        return 'kebab'
    if ' ' in s:
        return 'spaced'
    if re.match(r'^[A-Z][a-zA-Z0-9]*$', s):
        return 'pascal'
    if re.match(r'^[a-z][a-zA-Z0-9]*$', s):
        return 'camel'
    return 'mixed'


def _synonym(a, b):
    return any(a in group and b in group for group in _SYNONYM_SETS)


def classify_name_pair(a, b):
    """`(判定, 规则名)`：`same` / `high`（可自动改） / `different`（只报告）。"""
    ka, kb = name_key(a), name_key(b)
    if not ka or not kb:
        return 'different', 'empty_key'
    ca, cb = convention_of(a), convention_of(b)
    if 'cjk' in (ca, cb) or 'empty' in (ca, cb):
        # 中文名与英文名绝不互改
        return 'different', 'cjk_or_empty'
    if len(ka) < 3 or len(kb) < 3 or ka.isdigit() or kb.isdigit():
        return 'different', 'too_short_or_numeric'
    if ka == kb:
        # 跨命名约定（UML `Order` ↔ ER `orders`）视为设计使然：不改也不报
        return ('same', 'identical_key') if ca == cb else ('same', 'cross_convention')

    aa, a_stripped = _affix_key(a)
    ab, b_stripped = _affix_key(b)
    if (a_stripped or b_stripped) and aa == ab:
        return 'high', 'affix_strip'

    ta, tb = ka.split('_'), kb.split('_')
    if len(ta) == 1 and len(tb) == 1 and _synonym(ta[0], tb[0]):
        return 'high', 'synonym_token'
    if len(ta) >= 2 and len(tb) >= 2 and ta[:-1] == tb[:-1] and _synonym(ta[-1], tb[-1]):
        return 'high', 'synonym_last_token'
    return 'different', 'none'


def _collect_names(model):
    """按图种类收集 (name, 定位信息) —— 只读，不改。"""
    buckets = {'uml': [], 'archimate': [], 'er': []}
    for kind, attr in (('uml', 'elements'), ('archimate', 'archimate_elements'), ('er', 'er_entities')):
        for idx, it in enumerate(getattr(model, attr, None) or []):
            if isinstance(it, dict) and str(it.get('name') or '').strip():
                buckets[kind].append((str(it['name']).strip(), idx))
    return buckets


def cross_map_diff(model, base_kind='uml'):
    """三图命名对照。返回 `{'renames': [...], 'reports': [...], 'same': n}`。

    `renames` 是高置信、可自动改的项（以 `base_kind` 为基准）；
    `reports` 是「像同一概念但名字不同」的人工确认项。

    v1 只对齐元素/实体名，不对齐字段名（避开 model 存 `fields`、
    canonical 存 `attributes` 的键名差异）。

    中文名之间不做 token 匹配（CJK 串没有词边界），一律不判定也不报告。
    """
    buckets = _collect_names(model)
    base = buckets.get(base_kind) or []
    renames, reports = [], []
    same_count = 0

    if not base:
        return {'renames': renames, 'reports': reports, 'same': 0}

    base_names = [n for n, _ in base]
    for kind in ALL_KINDS:
        if kind == base_kind:
            continue
        for name, idx in buckets[kind]:
            verdicts = [(classify_name_pair(name, bn), bn) for bn in base_names]
            highs = [(v, bn) for v, bn in verdicts if v[0] == 'high']
            sames = [bn for v, bn in verdicts if v[0] == 'same']
            if sames:
                same_count += 1
                continue
            if len(highs) > 1:
                # 多义：匹配到多个候选，降级为只报告，避免改错
                reports.append(
                    f'{_KIND_LABEL[kind]}「{name}」可能对应多个 {_KIND_LABEL[base_kind]}'
                    f'（{("、".join(bn for _, bn in highs))}），未自动对齐'
                )
                continue
            if len(highs) == 1:
                rule, target = highs[0][0][1], highs[0][1]
                renames.append({'kind': kind, 'index': idx, 'from': name,
                                'to': target, 'rule': rule})
                continue
            # 分享至少一个 token → 像同一概念但名字确实不同 → 报告
            ktoks = set(name_key(name).split('_'))
            for other, _oi in base:
                otoks = set(name_key(other).split('_'))
                if not (ktoks & otoks):
                    continue
                if (ktoks ^ otoks) <= _GENERIC_TOKENS:
                    continue     # 只差一个角色后缀 → 惯用写法，不算不一致
                reports.append(
                    f'{_KIND_LABEL[kind]}「{name}」与 {_KIND_LABEL[base_kind]}「{other}」'
                    f'像是同一概念但命名不同，建议统一'
                )
    return {'renames': renames, 'reports': reports, 'same': same_count}


def apply_cross_map_renames(model, renames):
    """应用高置信改名。返回实际改成的条数。

    只会重命名**不会**造成同图内重名的项；关系按 id 引用，无需级联。
    """
    if not renames:
        return 0
    attr_of = {'uml': 'elements', 'archimate': 'archimate_elements', 'er': 'er_entities'}
    done = 0
    for item in renames:
        items = getattr(model, attr_of.get(item.get('kind'), ''), None)
        if not isinstance(items, list):
            continue
        idx = item.get('index')
        if not isinstance(idx, int) or not (0 <= idx < len(items)):
            continue
        target = items[idx]
        if not isinstance(target, dict) or str(target.get('name') or '').strip() != item.get('from'):
            continue     # 期间被改过 → 放弃这一条，不做错误配对
        existing = {str(x.get('name') or '').strip() for x in items if isinstance(x, dict)}
        if item.get('to') in existing:
            continue     # 会造成重名 → 放弃
        target['name'] = item['to']
        done += 1
    return done


def cross_map_report_lines(model, limit=8):
    """给健康度用的「只报告」文案。"""
    diff = cross_map_diff(model)
    lines = list(diff['reports'])[:limit]
    if diff['renames']:
        head = '、'.join(f"{r['from']} → {r['to']}" for r in diff['renames'][:3])
        more = f" 等 {len(diff['renames'])} 项" if len(diff['renames']) > 3 else ''
        lines.insert(0, f'跨图命名已自动对齐 {len(diff["renames"])} 项：{head}{more}')
    return lines
