"""若依 RuoYi-Vue3 整套模块生成：命名 / 类型 / 规则降级 / 建模 / 编排 / 打包。

设计约定（对齐 prompts.py 的「内容与逻辑分离」）：
- 本文件只做「ER 模型 → 结构化 schema」与「编排、打包」，不含代码模板正文（模板见 ruoyi_templates.py）。
- 代码骨架**不调 LLM**：确定性生成，零 max_tokens 截断风险，未启用 AI 也能产出完整可用模块。
- LLM 只用于补一件小事——表/字段的中文注释与列标签（见 app.py 的 _ai_annotate_ruoyi）。
  但每个字段都必须有**确定性兜底**，AI 挂了也照样有像样的中文标签。
"""

import io
import re
import zipfile
from dataclasses import dataclass

# ---------------------------------------------------------------- 常量

#: 若依 BaseEntity 自带字段：不入 domain，但必须进 resultMap 与建表 SQL
SUPER_COLUMNS = ('create_by', 'create_time', 'update_by', 'update_time', 'remark')

#: 审计列的标准定义（缺失时按此补齐）
AUDIT_COLUMN_DEFS = {
    'create_by': ('VARCHAR', 64, "创建者", "''", '创建者'),
    'create_time': ('DATETIME', None, "", None, '创建时间'),
    'update_by': ('VARCHAR', 64, "", "''", '更新者'),
    'update_time': ('DATETIME', None, "", None, '更新时间'),
    'remark': ('VARCHAR', 500, "", None, '备注'),
}

#: 审计列的常见别名：命中则**重命名**而非并存（避免 create_time / created_at 两列同时出现）
AUDIT_ALIASES = {
    'created_at': 'create_time',
    'created_time': 'create_time',
    'gmt_create': 'create_time',
    'create_at': 'create_time',
    'created_by': 'create_by',
    'creator': 'create_by',
    'updated_at': 'update_time',
    'updated_time': 'update_time',
    'gmt_modified': 'update_time',
    'modify_time': 'update_time',
    'updated_by': 'update_by',
    'modifier': 'update_by',
}

#: 若依自带字典白名单（连同选项文本——@Excel 的 readConverterExp 要用）。
#: 宁可留空也不猜：猜错字典会让前端 dict-tag 渲染成空白。
DICT_OPTIONS = {
    'sys_user_sex': [('0', '男'), ('1', '女'), ('2', '未知')],
    'sys_show_hide': [('0', '显示'), ('1', '隐藏')],
    'sys_normal_disable': [('0', '正常'), ('1', '停用')],
    'sys_yes_no': [('Y', '是'), ('N', '否')],
    'sys_notice_type': [('1', '通知'), ('2', '公告')],
    'sys_notice_status': [('0', '正常'), ('1', '关闭')],
    'sys_oper_type': [('1', '新增'), ('2', '修改'), ('3', '删除'), ('4', '授权'), ('5', '导出'), ('6', '导入'), ('7', '强退'), ('8', '生成代码'), ('9', '清空数据')],
    'sys_common_status': [('0', '正常'), ('1', '停用')],
    'sys_job_group': [('default', '默认'), ('SYSTEM', '系统')],
    'sys_job_status': [('0', '正常'), ('1', '暂停')],
}

#: 字段名 → 中文词表（表注释与列标签的确定性兜底）
WORD_CN = {
    'user': '用户', 'order': '订单', 'product': '商品', 'goods': '商品', 'role': '角色',
    'dept': '部门', 'department': '部门', 'menu': '菜单', 'log': '日志', 'config': '配置',
    'notice': '公告', 'dict': '字典', 'post': '岗位', 'file': '文件', 'task': '任务',
    'item': '明细', 'detail': '详情', 'info': '信息', 'record': '记录', 'type': '类型',
    'status': '状态', 'name': '名称', 'code': '编码', 'data': '数据', 'group': '分组',
    'title': '标题', 'content': '内容', 'remark': '备注', 'desc': '说明', 'description': '描述',
    'address': '地址', 'amount': '金额', 'price': '价格', 'count': '数量', 'num': '数量',
    'number': '编号', 'sort': '排序', 'version': '版本', 'score': '分数', 'level': '等级',
    'category': '分类', 'tag': '标签', 'image': '图片', 'icon': '图标', 'url': '链接',
    'phone': '手机号码', 'mobile': '手机号码', 'email': '邮箱', 'sex': '性别', 'gender': '性别',
    'age': '年龄', 'birthday': '生日', 'password': '密码', 'account': '账号', 'company': '公司',
    'customer': '客户', 'supplier': '供应商', 'warehouse': '仓库', 'student': '学生',
    'teacher': '教师', 'course': '课程', 'class': '班级', 'project': '项目', 'farm': '农田',
    'crop': '作物', 'machine': '农机', 'equipment': '设备', 'device': '设备', 'area': '面积',
    'total': '合计', 'sum': '合计', 'start': '开始', 'end': '结束', 'begin': '开始',
    'flag': '标志', 'state': '状态', 'kind': '类型', 'note': '备注', 'label': '标签',
    'value': '值', 'key': '键', 'path': '路径', 'host': '主机', 'port': '端口',
    'duration': '时长', 'time': '时间', 'date': '日期', 'year': '年份', 'month': '月份',
    'day': '日期', 'hour': '小时', 'minute': '分钟', 'second': '秒', 'size': '大小',
    'email_addr': '邮箱', 'avatar': '头像', 'link': '链接', 'parent': '父级',
    'order_num': '排序', 'is': '是否', 'has': '是否', 'enable': '启用', 'enabled': '启用',
    'visible': '显示', 'delete': '删除', 'deleted': '删除', 'image_url': '图片',
}

#: 审计列的固定标签（优先于模式匹配）
AUDIT_LABELS = {
    'id': '主键', 'create_by': '创建者', 'create_time': '创建时间',
    'update_by': '更新者', 'update_time': '更新时间', 'remark': '备注',
    'del_flag': '删除标志', 'delete_flag': '删除标志', 'is_deleted': '删除标志',
}

#: 精确列名 → 标签（模式匹配兜底不到的高频词）
EXACT_LABELS = {
    'email': '邮箱', 'phone': '手机号码', 'mobile': '手机号码', 'url': '链接地址',
    'avatar': '头像地址', 'status': '状态', 'name': '名称', 'code': '编码',
    'type': '类型', 'title': '标题', 'content': '内容', 'sort': '排序', 'version': '版本',
    'sex': '性别', 'gender': '性别', 'age': '年龄', 'password': '密码', 'amount': '金额',
    'price': '价格', 'count': '数量', 'address': '地址', 'category': '分类', 'level': '等级',
}

HTML_TYPES = ('input', 'textarea', 'select', 'radio', 'checkbox', 'datetime', 'imageUpload', 'fileUpload')
QUERY_TYPES = ('EQ', 'NE', 'GT', 'GTE', 'LT', 'LTE', 'LIKE', 'BETWEEN')
FRONTEND_EXT = {'java', 'xml', 'vue', 'js', 'ts', 'sql', 'md'}

#: 类型基线 → Java 类型（主键会被强制成 Long）
JAVA_BY_BASE = {
    'INT': 'Integer', 'INTEGER': 'Integer', 'MEDIUMINT': 'Integer', 'SMALLINT': 'Integer', 'TINYINT': 'Integer',
    'BIGINT': 'Long',
    'VARCHAR': 'String', 'CHAR': 'String', 'TEXT': 'String', 'TINYTEXT': 'String',
    'MEDIUMTEXT': 'String', 'LONGTEXT': 'String', 'JSON': 'String', 'ENUM': 'String', 'SET': 'String',
    'BLOB': 'String', 'LONGBLOB': 'String', 'BINARY': 'String', 'VARBINARY': 'String',
    'DECIMAL': 'BigDecimal', 'NUMERIC': 'BigDecimal',
    'DOUBLE': 'Double', 'FLOAT': 'Double', 'REAL': 'Double',
    'DATE': 'Date', 'DATETIME': 'Date', 'TIMESTAMP': 'Date', 'TIME': 'Date',
    'BOOLEAN': 'Boolean', 'BOOL': 'Boolean', 'BIT': 'Boolean',
}

#: 允许出现在生成物里的 SQL 基线集合（其余一律退化为 VARCHAR 并告警）
KNOWN_BASES = set(JAVA_BY_BASE)

#: DDL 里的默认长度（若依 ry_*.sql 风格：bigint(20) / int(11)）
DEFAULT_LENGTH = {'BIGINT': 20, 'INT': 11, 'INTEGER': 11, 'SMALLINT': 6, 'TINYINT': 4, 'MEDIUMINT': 9}

_SQL_TYPE_RE = re.compile(r'^\s*([A-Za-z]+)\s*(?:\(\s*(\d+)\s*(?:,\s*(\d+)\s*)?\))?\s*$')


# ---------------------------------------------------------------- 配置

@dataclass
class RuoYiConfig:
    """若依生成配置（前端 codeConfig.ruoyi 映射而来）。"""
    package_base: str = 'com.ruoyi'
    module_name: str = 'system'
    table_prefix: str = ''
    business_name: str = ''
    class_name: str = ''
    author: str = 'ruoyi'
    parent_menu_id: int = 3
    servlet_api: str = 'jakarta'   # jakarta(Spring Boot 3 / 若依 3.9.x) | javax(2.x)
    frontend_ts: bool = True
    db_type: str = 'mysql'

    @property
    def package_name(self) -> str:
        return f'{self.package_base}.{self.module_name}'

    @property
    def package_path(self) -> str:
        return self.package_name.replace('.', '/')

    @property
    def frontend_ext(self) -> str:
        return 'ts' if self.frontend_ts else 'js'


_PKG_RE = re.compile(r'^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$')
_MODULE_RE = re.compile(r'^[a-z][a-z0-9_]*$')


def normalize_config(raw):
    """校验并归一化前端传来的配置。返回 (cfg, error)；error 非空表示参数非法。"""
    raw = raw or {}
    cfg = RuoYiConfig(
        # 包名/模块名按用户输入**原样**校验，不做静默小写化：产出的 package 声明错了会在编译期炸，早失败早好
        package_base=str(raw.get('packageBase') or 'com.ruoyi').strip(),
        module_name=str(raw.get('moduleName') or 'system').strip(),
        table_prefix=str(raw.get('tablePrefix') or '').strip().lower(),
        business_name=str(raw.get('businessName') or '').strip(),
        class_name=str(raw.get('className') or '').strip(),
        author=str(raw.get('author') or 'ruoyi').strip() or 'ruoyi',
        servlet_api='javax' if str(raw.get('servletApi') or '').lower() == 'javax' else 'jakarta',
        frontend_ts=bool(raw.get('frontendTs', True)),
        db_type=str(raw.get('dbType') or 'mysql').strip().lower(),
    )
    try:
        cfg.parent_menu_id = int(raw.get('parentMenuId', 3))
    except (TypeError, ValueError):
        return cfg, '父菜单 ID 必须是数字'
    if cfg.parent_menu_id <= 0:
        return cfg, '父菜单 ID 必须是正整数'
    if not _PKG_RE.match(cfg.package_base):
        # 包名写错会在编译期炸，早失败早好，不做静默修正
        return cfg, f'包名不合法：「{cfg.package_base}」（只允许小写字母/数字/下划线，用点分隔，如 com.ruoyi）'
    if not _MODULE_RE.match(cfg.module_name):
        return cfg, f'模块名不合法：「{cfg.module_name}」（只允许小写字母/数字/下划线，如 system）'
    if cfg.db_type != 'mysql':
        return cfg, f'当前仅支持 MySQL，收到「{cfg.db_type}」'
    return cfg, None


# ---------------------------------------------------------------- 命名

def split_words(name):
    """'UserOrder' / 'user-order' / 'user_order' → ['user', 'order']（非 ASCII 字符被剔除）。"""
    s = str(name or '').strip()
    s = re.sub(r'[\s\-\.]+', '_', s)
    s = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', s)      # camelCase → camel_Case
    s = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1_\2', s)   # HTTPUser → HTTP_User
    s = re.sub(r'[^0-9A-Za-z_]+', '_', s)
    return [w for w in re.split(r'_+', s) if w]


def to_snake(name):
    return '_'.join(w.lower() for w in split_words(name))


def to_pascal(name):
    return ''.join(w[:1].upper() + w[1:].lower() for w in split_words(name))


def to_camel(name):
    p = to_pascal(name)
    return p[:1].lower() + p[1:] if p else ''


def normalize_table_name(raw, index=0):
    """ER 画布里的表名可能任意（'用户表' / 'UserOrder' / 't-order'）。返回 (表名, warnings)。"""
    warnings = []
    name = to_snake(raw)
    if not name:
        name = f't_{index + 1}'
        warnings.append(f'表名「{raw}」无法转成合法英文表名，已用 {name} 占位，请在若依里改成业务名')
    elif not name[0].isalpha():
        name = 't_' + name
        warnings.append(f'表名「{raw}」以数字开头，已规范化为 {name}')
    if len(name) > 60:
        name = name[:60]
        warnings.append(f'表名「{raw}」过长，已截断为 {name}')
    return name, warnings


def strip_table_prefix(table, prefix):
    """'sys_user' 去掉 'sys_' → 'user'（用于推导类名/业务名）。"""
    p = str(prefix or '').strip().lower()
    if p and not p.endswith('_'):
        p += '_'
    if p and table.startswith(p) and len(table) > len(p):
        return table[len(p):]
    return table


# ---------------------------------------------------------------- 类型

def parse_sql_type(raw):
    """'VARCHAR(255)' → ('VARCHAR', 255, None, warnings)。未知类型退化为 VARCHAR(255)。"""
    warnings = []
    m = _SQL_TYPE_RE.match(str(raw or ''))
    if not m:
        return 'VARCHAR', 255, None, [f'字段类型「{raw}」无法识别，已按 VARCHAR(255) 处理']
    base = m.group(1).upper()
    length = int(m.group(2)) if m.group(2) else None
    scale = int(m.group(3)) if m.group(3) else None
    if base not in KNOWN_BASES:
        return 'VARCHAR', 255, None, [f'字段类型「{raw}」暂不支持，已按 VARCHAR(255) 处理']
    if base in ('VARCHAR', 'CHAR') and not length:
        length = 255
    if base == 'DECIMAL' and length is None:
        length, scale = 10, 2
    if length is None and base in DEFAULT_LENGTH:
        length = DEFAULT_LENGTH[base]   # 对齐若依 ry_*.sql 的 bigint(20) / int(11) 写法
    return base, length, scale, warnings


def sql_type_text(base, length, scale):
    """DDL 里用的类型串（小写）。"""
    if length and scale:
        return f'{base.lower()}({length},{scale})'
    if length:
        return f'{base.lower()}({length})'
    return base.lower()


def sql_to_java(base, is_pk=False):
    if is_pk:
        return 'Long'   # 若依的 selectXxxById(Long) / deleteXxxByIds(Long[]) 约定
    return JAVA_BY_BASE.get(base, 'String')


def java_imports(java_type):
    """Java 类型需要的 import 列表。"""
    return {
        'Date': 'java.util.Date',
        'BigDecimal': 'java.math.BigDecimal',
        'byte[]': None,
    }.get(java_type)


# ---------------------------------------------------------------- 规则降级（无 AI 时的全部输出）

def translate_words(words):
    """词序列 → 中文。任一词不在词表里就返回 None（避免产出「用户Order」这种半吊子混排）。"""
    parts = []
    for w in words:
        cn = WORD_CN.get(w.lower())
        if not cn:
            return None
        parts.append(cn)
    return ''.join(parts)


def guess_table_comment(table_name):
    """表名 → 中文注释。词表全覆盖才翻译，否则退回「{表名} 表」。"""
    words = [w for w in table_name.split('_') if w]
    cn = translate_words(words)
    return f'{cn}表' if cn else f'{table_name} 表'


def guess_field_label(column_name, is_pk=False):
    """列名 → 中文标签。按模式短路匹配，保证永不为空。"""
    n = str(column_name or '').lower()
    if is_pk or n == 'id':
        return '主键'
    if n in AUDIT_LABELS:
        return AUDIT_LABELS[n]
    if n in EXACT_LABELS:
        return EXACT_LABELS[n]

    m = re.match(r'^(.+?)_id$', n)
    if m:
        cn = translate_words(m.group(1).split('_'))
        return f'{cn}编号' if cn else f'{m.group(1)} 编号'
    m = re.match(r'^(.+?)_(time|at|date)$', n)
    if m:
        cn = translate_words(m.group(1).split('_'))
        suffix = '日期' if m.group(2) == 'date' else '时间'
        return f'{cn}{suffix}' if cn else f'{m.group(1)} {suffix}'
    m = re.match(r'^(is|has)_(.+)$', n)
    if m:
        cn = translate_words(m.group(2).split('_'))
        return f'是否{cn}' if cn else f'是否 {m.group(2)}'
    if n in ('enabled', 'visible'):
        return f'是否{WORD_CN[n]}'

    # {前缀}_{属性} —— 属性在词表里才拼（如 user_name → 用户名称）
    m = re.match(r'^(.+?)_(.+)$', n)
    if m:
        head = translate_words(m.group(1).split('_'))
        tail_cn = WORD_CN.get(m.group(2))
        if head and tail_cn:
            return f'{head}{tail_cn}'
    cn = translate_words(n.split('_'))
    if cn:
        return cn
    return str(column_name)   # 兜底：原列名，绝不留空


def guess_dict_type(column_name):
    """列名 → 若依字典类型。只吐白名单值，猜不出就留空（猜错会让 dict-tag 渲染空白）。"""
    n = str(column_name or '').lower()
    if 'sex' in n or 'gender' in n:
        return 'sys_user_sex'
    if 'notice_type' in n:
        return 'sys_notice_type'
    if 'notice_status' in n:
        return 'sys_notice_status'
    if 'job_group' in n:
        return 'sys_job_group'
    if 'job_status' in n:
        return 'sys_job_status'
    if n == 'status' or n.endswith('_status'):
        return 'sys_normal_disable'
    if re.match(r'^(is|has)_', n) or n in ('enabled', 'visible'):
        return 'sys_yes_no'
    if n == 'show_hide':
        return 'sys_show_hide'
    return ''


def guess_html_type(base, dict_type):
    if dict_type:
        return 'radio' if dict_type in ('sys_user_sex', 'sys_normal_disable', 'sys_show_hide', 'sys_yes_no', 'sys_notice_type', 'sys_job_status') else 'select'
    if base in ('TEXT', 'LONGTEXT', 'MEDIUMTEXT', 'TINYTEXT', 'JSON'):
        return 'textarea'
    if base in ('DATE', 'DATETIME', 'TIMESTAMP', 'TIME'):
        return 'datetime'
    if base in ('BOOLEAN', 'BOOL', 'BIT'):
        return 'radio'
    return 'input'


def guess_query_type(base, dict_type=''):
    # 字典/布尔列走等值查询（前端是下拉/单选，用 like 永远匹配不上）
    if dict_type or base in ('BOOLEAN', 'BOOL', 'BIT'):
        return 'EQ'
    if base in ('VARCHAR', 'CHAR', 'TEXT', 'LONGTEXT', 'MEDIUMTEXT', 'TINYTEXT'):
        return 'LIKE'
    if base in ('DATE', 'DATETIME', 'TIMESTAMP'):
        return 'BETWEEN'
    return 'EQ'


def read_converter_exp(dict_type):
    """字典 → @Excel 的 readConverterExp（'0=正常,1=停用'），让导出的 Excel 显示中文。"""
    opts = DICT_OPTIONS.get(dict_type)
    if not opts:
        return ''
    return ','.join(f'{v}={l}' for v, l in opts)


def is_super_column(java_field):
    return java_field in ('createBy', 'createTime', 'updateBy', 'updateTime', 'remark')


# ---------------------------------------------------------------- schema

def _make_column(name, base, length, scale, comment, is_pk, is_fk, is_super=False,
                 required=False, list_=True, query=True, dict_type='', increment=False):
    java_type = sql_to_java(base, is_pk=is_pk)
    return {
        'column_name': name,
        'java_field': to_camel(name),
        'java_type': java_type,
        'base': base,
        'length': length,
        'scale': scale,
        'sql_type': sql_type_text(base, length, scale),
        'comment': comment,
        'is_pk': is_pk,
        'is_fk': is_fk,
        'is_super': is_super,
        'increment': increment,
        'required': required and not is_pk and not is_super,
        'list': list_,
        # 审计列不参与条件查询；主键也不当查询条件（与若依自带页面一致，如岗位页不按编号搜）
        'query': query and not is_pk and not is_super and base not in ('TEXT', 'LONGTEXT', 'MEDIUMTEXT', 'TINYTEXT', 'JSON'),
        'query_type': guess_query_type(base, dict_type),
        'html_type': guess_html_type(base, dict_type),
        'dict_type': dict_type,
        'read_converter': read_converter_exp(dict_type),
    }


def _audit_columns(existing_names):
    """补齐缺失的审计列（create_by/create_time/update_by/update_time/remark）。"""
    cols, added = [], []
    for name in SUPER_COLUMNS:
        if name in existing_names:
            continue
        base, length, _, default, comment = AUDIT_COLUMN_DEFS[name]
        # create_time 进列表展示（与若依自带页面一致），其余审计列不进
        col = _make_column(name, base, length, None, comment, False, False,
                           is_super=True, list_=(name == 'create_time'), query=False)
        col['default'] = default
        cols.append(col)
        added.append(name)
    return cols, added


def build_table_schema(entity, cfg, index=0, apply_override=False):
    """单个 ER 实体 → 若依表 schema。返回 (table_dict, warnings)。"""
    warnings = []
    raw_name = entity.get('name') or ''
    table_name, w = normalize_table_name(raw_name, index)
    warnings += w

    fields = entity.get('fields') or []
    pk_indexes = [i for i, f in enumerate(fields) if f.get('isPrimary')]

    columns = []
    seen = set()
    audit_renamed = {}
    pk_col_names = []

    for i, f in enumerate(fields):
        raw_col = f.get('name') or f'field_{i + 1}'
        col_name = to_snake(raw_col) or f'field_{i + 1}'
        if not col_name[0].isalpha():
            col_name = 'c_' + col_name
        # 审计列别名 → 统一重命名，避免 create_time / created_at 两列并存
        if col_name in AUDIT_ALIASES:
            audit_renamed[col_name] = AUDIT_ALIASES[col_name]
            col_name = AUDIT_ALIASES[col_name]
        if col_name in seen:
            warnings.append(f'表 {table_name} 的字段「{raw_col}」与前面的列重名，已跳过')
            continue
        seen.add(col_name)

        is_pk = len(pk_indexes) > 0 and i == pk_indexes[0]
        if i in pk_indexes:
            pk_col_names.append(col_name)
        base, length, scale, tw = parse_sql_type(f.get('type'))
        warnings += [f'表 {table_name}：{t}' for t in tw]

        is_fk = bool(f.get('isForeign')) or bool(re.match(r'^(.+?)_id$', col_name))
        if is_pk:
            if base != 'BIGINT':
                warnings.append(
                    f'表 {table_name} 的主键 {col_name} 原类型为「{f.get("type")}」，'
                    f'已按若依约定归一化为 BIGINT(20) / Long'
                )
            base, length, scale = 'BIGINT', DEFAULT_LENGTH['BIGINT'], None
        comment = str(f.get('description') or f.get('comment') or '').strip() or guess_field_label(col_name, is_pk)
        super_col = is_super_column(to_camel(col_name))
        col = _make_column(
            name=col_name, base=base, length=length, scale=scale, comment=comment,
            is_pk=is_pk, is_fk=is_fk, is_super=super_col,
            # 只有 create_time 进列表展示（与若依自带页面一致），TEXT/JSON 不进
            list_=(col_name == 'create_time') if super_col else base not in ('TEXT', 'LONGTEXT', 'MEDIUMTEXT', 'TINYTEXT', 'JSON'),
            dict_type=guess_dict_type(col_name), increment=is_pk,
        )
        col['_index'] = i
        columns.append(col)

    # 复合主键：第一个当业务主键，其余降级为普通列
    if len(pk_indexes) > 1:
        extra = [columns[i]['column_name'] for i in pk_indexes[1:]]
        warnings.append(
            f'表 {table_name} 是复合主键（{"、".join(extra)} 已降级为普通列）：'
            f'若依假定单主键，domain / Mapper.xml / ServiceImpl / Controller / index.vue 里的主键相关代码需手工调整'
        )
    if not pk_indexes:
        warnings.append(f'表 {table_name} 没有主键，已自动补一个自增 id')

    # 主键必须在第一列（若依 DDL 风格 + 自增列习惯）
    business = [c for c in columns if not c['is_super']]
    business.sort(key=lambda c: (0 if c['is_pk'] else 1, c.get('_index', 0)))

    for k, v in audit_renamed.items():
        warnings.append(f'表 {table_name} 的审计列「{k}」已重命名为「{v}」以贴合若依规范')

    # 审计列统一收到末尾，按若依固定顺序（create_by, create_time, update_by, update_time, remark）
    supers = {c['column_name']: c for c in columns if c['is_super']}
    missing_audit, added_audit = _audit_columns(set(supers))
    if added_audit:
        warnings.append(f'表 {table_name} 缺少审计列 {("、".join(added_audit))}，已按若依标准补齐')
    for c in missing_audit:
        supers[c['column_name']] = c
    columns = business + [supers[n] for n in SUPER_COLUMNS if n in supers]

    for c in columns:
        c.pop('_index', None)

    pk = next((c for c in columns if c['is_pk']), None)
    pk_field = pk['java_field'] if pk else 'id'
    composite_pk = len(pk_indexes) > 1

    stripped = strip_table_prefix(table_name, cfg.table_prefix)
    if apply_override and cfg.class_name:
        class_name = cfg.class_name if cfg.class_name[:1].isupper() else to_pascal(cfg.class_name)
    else:
        class_name = to_pascal(stripped) or 'Record'
    if apply_override and cfg.business_name:
        business_name = cfg.business_name if cfg.business_name[:1].islower() else to_camel(cfg.business_name)
    else:
        business_name = to_camel(class_name)

    table = {
        'table_name': table_name,
        'raw_name': raw_name,
        'class_name': class_name,
        'class_name_lower': business_name,
        'business_name': business_name,
        'module_name': cfg.module_name,
        'package_name': cfg.package_name,
        'package_path': cfg.package_path,
        'permission_prefix': f'{cfg.module_name}:{business_name}',
        'comment': guess_table_comment(stripped),
        'columns': columns,
        'pk': pk,
        'pk_field': pk_field,
        'pk_cap': pk_field[:1].upper() + pk_field[1:],
        'composite_pk': composite_pk,
        'pk_columns': pk_col_names,   # 复合主键时 DDL 用（Java 层只用第一个）
        'warnings': warnings,
        'has_create_time': any(c['column_name'] == 'create_time' for c in columns),
        'has_update_time': any(c['column_name'] == 'update_time' for c in columns),
    }
    table['function_name'] = table['comment']
    return table, warnings


def build_module_schema(er_entities, er_relations, cfg, annotation=None):
    """ER 模型 → {tables, join_tables, warnings}。annotation 为 AI 标注（可为 None）。"""
    warnings = []
    tables = []
    used = set()
    entities = er_entities or []
    apply_override = len(entities) == 1

    for i, ent in enumerate(entities):
        table, tw = build_table_schema(ent, cfg, index=i, apply_override=apply_override)
        base = table['table_name']
        k = 2
        while table['table_name'] in used:
            table['table_name'] = f'{base}_{k}'
            k += 1
            table['warnings'].append(f'表名重复，已改名为 {table["table_name"]}')
        used.add(table['table_name'])
        warnings += table['warnings']
        tables.append(table)

    if not tables:
        return {'tables': [], 'join_tables': [], 'warnings': ['模型里没有可生成的表（ER 实体为空）']}

    # 应用 AI 标注（逐字段合并：AI 优先、规则兜底）
    if annotation:
        warnings += merge_annotation(tables, annotation)

    # M:N → 中间表（若依不原生支持多对多，不为其生成 Java/前端）
    id_to_table = {}
    for ent, t in zip(entities, tables):
        raw = ent.get('id')
        if raw is not None:
            id_to_table[raw] = t['table_name']
    join_tables = []
    seen_pairs = set()
    for rel in er_relations or []:
        if rel.get('type') != 'manyToMany':
            continue
        a = id_to_table.get(rel.get('startEntity'))
        b = id_to_table.get(rel.get('endEntity'))
        if not a or not b or a == b:
            continue
        # 按关系方向拼名（若依 sys_user_role 是 user 在前，不是字母序）：start 端在前
        left, right = a, b
        pair = tuple(sorted([a, b]))
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        join_tables.append({
            'table_name': f'{left}_{right}',
            'left_table': left,
            'right_table': right,
            'left_column': f'{left}_id',
            'right_column': f'{right}_id',
            'comment': f'{left} 与 {right} 关联表',
        })
    if join_tables:
        warnings.append(
            '多对多关系已生成中间表 DDL，但若依代码生成器不生成 M:N 关联导航：'
            '两端表按普通 CRUD 生成，如需主子表请在若依「代码生成」里手工配置'
        )

    for rel in er_relations or []:
        if rel.get('type') in ('oneToMany', 'oneToOne'):
            a = id_to_table.get(rel.get('startEntity'))
            b = id_to_table.get(rel.get('endEntity'))
            if a and b:
                warnings.append(
                    f'关系 {a} → {b}（{rel.get("type")}）按若依的平铺外键惯例处理，未自动改表结构：'
                    f'如需外键列请在 ER 图里补上'
                )

    return {'tables': tables, 'join_tables': join_tables, 'warnings': warnings}


# ---------------------------------------------------------------- AI 标注

def build_annotate_batches(tables, max_tables=8, max_fields=120):
    """按「≤8 表 / ≤120 字段」切批，避免单次请求被 max_tokens 截断。"""
    batches, cur, cur_fields = [], [], 0
    for t in tables:
        n = len(t['columns'])
        if cur and (len(cur) >= max_tables or cur_fields + n > max_fields):
            batches.append(cur)
            cur, cur_fields = [], 0
        cur.append(t)
        cur_fields += n
    if cur:
        batches.append(cur)
    return batches


def build_annotate_user_text(batch):
    """把一批表序列化成标注输入文本（键必须逐字回填，所以表名/列名原样给出）。"""
    lines = ['请为下面这些数据库表生成中文注释与列标签。表名与列名必须原样作为 JSON 的键，不得改写。', '']
    for t in batch:
        lines.append(f'表：{t["table_name"]}（当前推导类名 {t["class_name"]}）')
        for c in t['columns']:
            if c['is_super']:
                continue
            marks = []
            if c['is_pk']:
                marks.append('主键')
            if c['is_fk']:
                marks.append('外键')
            mark = f'（{"、".join(marks)}）' if marks else ''
            lines.append(f'  - {c["column_name"]}: {c["sql_type"]}{mark}')
        lines.append('')
    lines.append('可用字典（dictType 只能填这些，判断不了就留空字符串）：')
    for name, opts in DICT_OPTIONS.items():
        lines.append(f'  - {name}: ' + '、'.join(f'{v}={l}' for v, l in opts))
    return '\n'.join(lines)


def merge_annotation(tables, annotation):
    """把 AI 标注逐字段合并进 schema。AI 值非空则覆盖，缺失/非法则保留规则值。"""
    warnings = []
    if not isinstance(annotation, dict):
        return ['AI 标注结果格式异常，已全部按规则降级']
    ai_tables = annotation.get('tables') if isinstance(annotation.get('tables'), dict) else {}
    ai_fields = annotation.get('fields') if isinstance(annotation.get('fields'), dict) else {}

    for t in tables:
        tname = t['table_name']
        tinfo = ai_tables.get(tname)
        applied = 0
        if isinstance(tinfo, dict):
            comment = str(tinfo.get('comment') or '').strip()
            if comment:
                t['comment'] = _safe_label(comment, limit=30)
                t['function_name'] = t['comment']
                applied += 1

        cols = ai_fields.get(tname)
        if isinstance(cols, dict):
            for c in t['columns']:
                info = cols.get(c['column_name'])
                if not isinstance(info, dict):
                    continue
                label = str(info.get('label') or '').strip()
                if label:
                    c['comment'] = _safe_label(label, limit=20)
                    applied += 1
                dict_type = str(info.get('dictType') or '').strip()
                if dict_type and dict_type in DICT_OPTIONS:
                    c['dict_type'] = dict_type
                    c['read_converter'] = read_converter_exp(dict_type)
                    c['html_type'] = guess_html_type(c['base'], dict_type)
                html_type = str(info.get('htmlType') or '').strip()
                if html_type in HTML_TYPES:
                    c['html_type'] = html_type
                qt = str(info.get('queryType') or '').strip().upper()
                if qt in QUERY_TYPES:
                    c['query_type'] = qt
                for key in ('list', 'query', 'required'):
                    if isinstance(info.get(key), bool):
                        c[key] = info[key] and not c['is_super']
        if not applied:
            warnings.append(f'AI 未给表 {tname} 提供有效标注，该表按规则生成')

    # 未知键（AI 编了不存在的表/列）→ 提示，便于排查 prompt 漂移
    known = {t['table_name']: {c['column_name'] for c in t['columns']} for t in tables}
    for k in list(ai_tables.keys()) + list(ai_fields.keys()):
        if k not in known:
            warnings.append(f'AI 返回了模型里不存在的表「{k}」，已忽略')
    for tname, cols in (ai_fields or {}).items():
        if tname not in known or not isinstance(cols, dict):
            continue
        unknown = [c for c in cols if c not in known[tname]]
        if unknown:
            warnings.append(f'AI 为表 {tname} 返回了不存在的列 {"、".join(unknown)}，已忽略')

    # 审计列的展示与查询开关必须保持规则值（AI 不该动）
    for t in tables:
        for c in t['columns']:
            if c['is_super']:
                c['list'] = c['column_name'] == 'create_time'
                c['query'] = False
                c['required'] = False
    return warnings


def _safe_label(text, limit=20):
    """标签进 Java 字符串 / XML 注释，必须去引号、换行与 XML 非法的 `--`。"""
    s = str(text or '').replace('\r', ' ').replace('\n', ' ').replace('"', '').replace("'", '')
    s = s.replace('--', '—').strip()
    return s[:limit]


# ---------------------------------------------------------------- 编排与打包

def generate_ruoyi_module(er_entities, er_relations, cfg, annotation=None):
    """ER 模型 → {'files': [...], 'meta': {...}}。骨架全部确定性渲染。"""
    import ruoyi_templates as tpl   # 延迟导入：模板只依赖数据，不反向依赖本模块

    schema = build_module_schema(er_entities, er_relations, cfg, annotation=annotation)
    files = tpl.render_module_files(schema, cfg)
    meta = {
        'tables': [
            {
                'tableName': t['table_name'],
                'className': t['class_name'],
                'businessName': t['business_name'],
                'moduleName': t['module_name'],
                'permissionPrefix': t['permission_prefix'],
                'comment': t['comment'],
                'columnCount': len([c for c in t['columns'] if not c['is_super']]),
                'compositePk': t['composite_pk'],
            }
            for t in schema['tables']
        ],
        'joinTables': [j['table_name'] for j in schema['join_tables']],
        'warnings': schema['warnings'],
        'fileCount': len(files),
    }
    return {'files': files, 'meta': meta}


def safe_zip_entry(path):
    """校验 zip 条目路径（来自客户端，必须防 Zip Slip）。非法返回 None。"""
    p = str(path or '').replace('\\', '/').strip()
    if not p or p.startswith('/') or ':' in p:
        return None
    parts = [seg for seg in p.split('/') if seg not in ('', '.')]
    if not parts or any(seg == '..' for seg in parts):
        return None
    if not re.match(r'^[A-Za-z0-9._\-/]+$', '/'.join(parts)):
        return None
    ext = parts[-1].rsplit('.', 1)[-1].lower() if '.' in parts[-1] else ''
    if ext not in FRONTEND_EXT:
        return None
    return '/'.join(parts)


def ascii_zip_name(zip_name):
    """中文/非 ASCII 文件名 → 纯 ASCII 兜底名。

    `Content-Disposition` 的 `filename` 必须是 ASCII（否则部分客户端乱码或截断），
    中文名走 RFC 5987 的 `filename*=UTF-8''`。
    """
    name = str(zip_name or '').strip()
    base = name.rsplit('.', 1)[0] if '.' in name else name
    ascii_base = re.sub(r'[^A-Za-z0-9._-]+', '-', base).strip('-')
    if not ascii_base:
        ascii_base = 'ruoyi-module'
    return f'{ascii_base}.zip'


MAX_ZIP_ENTRIES = 400
MAX_ZIP_TOTAL = 8 * 1024 * 1024
MAX_ZIP_FILE = 1024 * 1024


def build_zip(files):
    """把文件列表打成 zip 字节流。返回 (bytes, error)。条目名强制 ASCII，避免 Windows 解压乱码。"""
    items = []
    total = 0
    for f in files or []:
        name = safe_zip_entry(f.get('path'))
        if not name:
            return None, f'文件名不合法：{f.get("path")}'
        if not name.isascii():
            return None, f'zip 条目名必须是 ASCII：{name}'
        content = f.get('content') or ''
        if not isinstance(content, str):
            return None, f'文件内容必须是文本：{name}'
        raw = content.encode('utf-8')
        if len(raw) > MAX_ZIP_FILE:
            return None, f'单个文件过大（>1MB）：{name}'
        total += len(raw)
        items.append((name, raw))

    if not items:
        return None, '没有可打包的文件'
    if len(items) > MAX_ZIP_ENTRIES:
        return None, f'文件数量过多（>{MAX_ZIP_ENTRIES}）'
    if total > MAX_ZIP_TOTAL:
        return None, '打包内容过大（>8MB）'

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for name, raw in items:
            zf.writestr(name, raw)
    return buf.getvalue(), None
