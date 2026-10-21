"""黄金样例集（纯数据，可 import）。

文件名刻意**不加 `test_` 前缀** —— 它会被测试脚本 import，不该被当成测试自己跑起来。

用例分两类：
- `canonical`：一次 LLM 调用的产出形状（打桩喂给 `_apply_canonical_to_model`），
  喂进去后断言「物化出来的模型」的结构不变量。不依赖真实 LLM，因此可离线复现。
- `expect`：该用例期望的结构性质，由 test_golden_regression.py 消费。

新增用例请只加数据，别在测试脚本里写逻辑分支——那是下面那种「一次写巨型测试」的老路。
"""

# ---------------------------------------------------------------- 用例 1：命名一致
FARM = {
    'id': 'farm',
    'text': '设计一个智慧农业平台：涵盖农田种植、农机调度、农产品溯源、订单销售',
    'canonical': {
        'project_name': '智慧农业平台',
        'uml': {
            'elements': [
                {'type': 'Class', 'name': 'Farmland', 'attributes': ['- id: Long', '- area: Double'],
                 'methods': ['+ plant(): void']},
                {'type': 'Class', 'name': 'Crop', 'attributes': ['- id: Long', '- name: String'],
                 'methods': ['+ grow(): void']},
                {'type': 'Class', 'name': 'Machine', 'attributes': ['- id: Long', '- model: String'],
                 'methods': ['+ schedule(): void']},
                {'type': 'Class', 'name': 'Order', 'attributes': ['- id: Long', '- amount: BigDecimal'],
                 'methods': ['+ submit(): void']},
            ],
            'relationships': [
                {'source': 'Farmland', 'target': 'Crop', 'type': 'Association'},
                {'source': 'Order', 'target': 'Crop', 'type': 'Dependency'},
                {'source': 'Machine', 'target': 'Farmland', 'type': 'Association'},
            ],
        },
        'archimate': {
            'elements': [
                {'type': 'actor', 'name': 'Farmer', 'layer': 'business'},
                {'type': 'process', 'name': 'Planting', 'layer': 'business'},
                {'type': 'service', 'name': 'FarmService', 'layer': 'application'},
                {'type': 'component', 'name': 'FarmSystem', 'layer': 'application'},
            ],
            'relationships': [
                {'source': 'Farmer', 'target': 'Planting', 'type': 'triggering'},
                {'source': 'Planting', 'target': 'FarmService', 'type': 'serving'},
                {'source': 'FarmService', 'target': 'FarmSystem', 'type': 'realization'},
            ],
        },
        'er': {
            'entities': [
                {'name': 'Farmland', 'attributes': [
                    {'name': 'id', 'data_type': 'bigint', 'is_primary_key': True},
                    {'name': 'area', 'data_type': 'decimal', 'is_primary_key': False},
                ]},
                {'name': 'Crop', 'attributes': [
                    {'name': 'id', 'data_type': 'bigint', 'is_primary_key': True},
                    {'name': 'name', 'data_type': 'string', 'is_primary_key': False},
                ]},
                {'name': 'Order', 'attributes': [
                    {'name': 'id', 'data_type': 'bigint', 'is_primary_key': True},
                    {'name': 'amount', 'data_type': 'decimal', 'is_primary_key': False},
                ]},
            ],
            'relationships': [
                {'source': 'Farmland', 'target': 'Crop', 'type': 'one_to_many'},
                {'source': 'Order', 'target': 'Crop', 'type': 'many_to_one'},
            ],
        },
    },
    'expect': {'min_uml': 4, 'min_archimate': 4, 'min_er': 3, 'min_rels': 3,
               'cross_map_renames': 0, 'cross_map_same': 3},
}

# ---------------------------------------------------------------- 用例 2：跨命名约定
# UML 用 Pascal、ER 用 snake_case —— 这是 canonical 提示词本身要求的，属设计使然：
# 既不该自动改，也不该进报告（改了会污染若依生成的表名与 DDL）。
SHOP = {
    'id': 'shop',
    'text': '做一个电商中台：商品、库存、订单、支付',
    'canonical': {
        'project_name': '电商中台',
        'uml': {
            'elements': [
                {'type': 'Class', 'name': 'Product', 'attributes': ['- id: Long'], 'methods': []},
                {'type': 'Class', 'name': 'Stock', 'attributes': ['- id: Long'], 'methods': []},
                {'type': 'Class', 'name': 'Order', 'attributes': ['- id: Long'], 'methods': []},
                {'type': 'Interface', 'name': 'Payable', 'attributes': [], 'methods': ['+ pay(): void']},
            ],
            'relationships': [
                {'source': 'Order', 'target': 'Product', 'type': 'Association'},
                {'source': 'Product', 'target': 'Stock', 'type': 'Composition'},
            ],
        },
        'archimate': {
            'elements': [
                {'type': 'actor', 'name': 'Buyer', 'layer': 'business'},
                {'type': 'service', 'name': 'OrderService', 'layer': 'application'},
                {'type': 'component', 'name': 'ShopSystem', 'layer': 'application'},
            ],
            'relationships': [
                {'source': 'Buyer', 'target': 'OrderService', 'type': 'serving'},
            ],
        },
        'er': {
            'entities': [
                {'name': 'product', 'attributes': [
                    {'name': 'id', 'data_type': 'bigint', 'is_primary_key': True},
                    {'name': 'title', 'data_type': 'string', 'is_primary_key': False},
                ]},
                {'name': 'stock', 'attributes': [
                    {'name': 'id', 'data_type': 'bigint', 'is_primary_key': True},
                ]},
                {'name': 'order', 'attributes': [
                    {'name': 'id', 'data_type': 'bigint', 'is_primary_key': True},
                ]},
            ],
            'relationships': [
                {'source': 'order', 'target': 'product', 'type': 'one_to_many'},
            ],
        },
    },
    'expect': {'min_uml': 4, 'min_archimate': 3, 'min_er': 3, 'min_rels': 2,
               'cross_map_renames': 0, 'cross_map_reports': 0},
}

# ---------------------------------------------------------------- 用例 3：只有一张图
# 覆盖度惩罚的活样本：模型不空、也没错，但缺两张图 → 必须显著低于完整用例。
PARTIAL = {
    'id': 'partial',
    'text': '只画了类图，还没来得及补数据模型和架构视图',
    'canonical': {
        'project_name': '半成品',
        'uml': {
            'elements': [
                {'type': 'Class', 'name': 'Alpha', 'attributes': ['- id: Long'], 'methods': []},
                {'type': 'Class', 'name': 'Beta', 'attributes': ['- id: Long'], 'methods': []},
            ],
            'relationships': [
                {'source': 'Alpha', 'target': 'Beta', 'type': 'Association'},
            ],
        },
        'archimate': {'elements': [], 'relationships': []},
        'er': {'entities': [], 'relationships': []},
    },
    'expect': {'min_uml': 2, 'empty_kinds': 2},
}

# ------------------------------------------------- 用例 4：LLM 产出违规（闭合口子的探针）
# 这一例专门塞进「模型可能吐出来的脏东西」：非法元素/关系/层次/字段类型、悬空关系、
# 重名元素、超范围层次。断言的不是「产出好看」，而是**这些东西进不了模型**，
# 且每一处都被如实记录在 layout_report 里。
MESSY = {
    'id': 'messy',
    'text': '（用例：LLM 产出含非法类型与重名）',
    'canonical': {
        'project_name': '脏产出',
        'uml': {
            'elements': [
                {'type': 'WeirdThing', 'name': 'Alpha', 'attributes': [], 'methods': []},
                {'type': 'Class', 'name': 'Beta', 'attributes': [], 'methods': []},
                {'type': 'Enum', 'name': 'Status', 'attributes': [], 'methods': []},
            ],
            'relationships': [
                {'source': 'Alpha', 'target': 'NoSuchElement', 'type': 'Bogus'},
                {'source': 'Alpha', 'target': 'Beta', 'type': 'Association'},
                # 端点合法但类型非法——必须单独占一条，否则「端点检查先命中就 continue」
                # 会让类型检查永远走不到（这个用例本身就是这么发现该盲点的）
                {'source': 'Beta', 'target': 'Status', 'type': 'Bogus'},
            ],
        },
        'archimate': {
            'elements': [
                {'type': 'actor', 'name': 'Actor1', 'layer': 'business'},
                {'type': 'weirdtype', 'name': 'Actor2', 'layer': 'nosuchlayer'},
                {'type': 'service', 'name': 'Actor1', 'layer': 'application'},
            ],
            'relationships': [
                {'source': 'Actor1', 'target': 'Actor2', 'type': 'bogus_rel'},
            ],
        },
        'er': {
            'entities': [
                {'name': 'Alpha', 'attributes': [
                    {'name': 'id', 'data_type': 'integer', 'is_primary_key': True},
                    {'name': 'weird', 'data_type': 'FOOBAR', 'is_primary_key': False},
                    {'name': 'blob_col', 'data_type': 'string', 'is_primary_key': False},
                ]},
            ],
            'relationships': [],
        },
    },
    # 唯一带 report_at_least 的用例：至少 6 处修正记录（详见 test_golden_regression.py）
    'expect': {'min_uml': 3, 'min_archimate': 2, 'min_er': 1, 'min_rels': 1,
               'report_at_least': 6},
}

# --------------------------------------------- 用例 5：跨图命名对齐（改一部分、报一部分）
# ER 用 `sys_` 前缀 → 高置信，自动对齐到 UML 类名 `Order`；
# ArchiMate `OrderService` 只差一个角色后缀 → 惯用写法，不报；
# ArchiMate `OrderEntry` 与 UML `Order` 是真不同的名字 → 只报告，不擅自动。
PREFIXED = {
    'id': 'prefixed',
    'text': '（用例：ER 表名带前缀，应自动对齐到 UML 类名）',
    'canonical': {
        'project_name': '前缀对齐',
        'uml': {
            'elements': [
                {'type': 'Class', 'name': 'Order', 'attributes': [], 'methods': []},
                {'type': 'Class', 'name': 'Customer', 'attributes': [], 'methods': []},
            ],
            'relationships': [
                {'source': 'Order', 'target': 'Customer', 'type': 'Association'},
            ],
        },
        'archimate': {
            'elements': [
                {'type': 'service', 'name': 'OrderService', 'layer': 'application'},
                {'type': 'component', 'name': 'OrderEntry', 'layer': 'application'},
                {'type': 'service', 'name': 'Customer', 'layer': 'application'},
            ],
            'relationships': [
                {'source': 'OrderService', 'target': 'OrderEntry', 'type': 'serving'},
            ],
        },
        'er': {
            'entities': [
                {'name': 'sys_order', 'attributes': [
                    {'name': 'id', 'data_type': 'bigint', 'is_primary_key': True}]},
                {'name': 'Customer', 'attributes': [
                    {'name': 'id', 'data_type': 'bigint', 'is_primary_key': True}]},
            ],
            'relationships': [],
        },
    },
    'expect': {'min_uml': 2, 'min_archimate': 3, 'min_er': 2, 'min_rels': 2,
               'cross_map_renames': 1,    # sys_order → Order
               # same 是「逐个名字」计的（不是按图计）：ER 的 Order、ER 的 Customer、
               # ArchiMate 的 Customer 各记一次 = 3
               'cross_map_same': 3,
               'cross_map_reports': 1},   # OrderEntry 真不同 → 只报告
}

# ------------------------------------------- 用例 6：技术层部署拓扑（4 个新技术类型）
# 这一例专测「部署视图」：技术层必须能画出服务器/数据库/缓存/网关，而不是清一色 node。
# 断言重点是**新技术类型不被降级**——布局器对未知类型有回落逻辑（技术层→node、
# 其余→service），如果常量没加对，这里会被悄悄改成 node，图就退化成清一色节点。
DEPLOY = {
    'id': 'deploy',
    'text': '（用例：技术层部署拓扑，含 device / system_software / communication_network / technology_service）',
    'canonical': {
        'project_name': '部署拓扑',
        'uml': {
            'elements': [
                {'type': 'Class', 'name': 'Order', 'attributes': ['- id: Long'], 'methods': []},
                {'type': 'Class', 'name': 'Customer', 'attributes': ['- id: Long'], 'methods': []},
            ],
            'relationships': [{'source': 'Order', 'target': 'Customer', 'type': 'Association'}],
        },
        'archimate': {
            'elements': [
                {'type': 'component', 'name': 'OrderApp', 'layer': 'application'},
                {'type': 'service', 'name': 'OrderService', 'layer': 'application'},
                {'type': 'device', 'name': 'AppServer', 'layer': 'technology'},
                {'type': 'system_software', 'name': 'MySQL', 'layer': 'technology'},
                {'type': 'system_software', 'name': 'Redis', 'layer': 'technology'},
                {'type': 'communication_network', 'name': 'NginxGateway', 'layer': 'technology'},
                {'type': 'technology_service', 'name': 'Monitoring', 'layer': 'technology'},
            ],
            'relationships': [
                # assignment = 部署关系（规范里表达「部署在…之上」）
                {'source': 'OrderApp', 'target': 'AppServer', 'type': 'assignment'},
                {'source': 'OrderService', 'target': 'MySQL', 'type': 'access'},
                {'source': 'OrderApp', 'target': 'Redis', 'type': 'access'},
                {'source': 'NginxGateway', 'target': 'OrderApp', 'type': 'serving'},
                {'source': 'AppServer', 'target': 'Monitoring', 'type': 'association'},
            ],
        },
        'er': {
            'entities': [
                {'name': 'orders', 'attributes': [
                    {'name': 'id', 'data_type': 'bigint', 'is_primary_key': True}]},
                {'name': 'customers', 'attributes': [
                    {'name': 'id', 'data_type': 'bigint', 'is_primary_key': True}]},
            ],
            'relationships': [{'source': 'orders', 'target': 'customers', 'type': 'many_to_one'}],
        },
    },
    'expect': {'min_uml': 2, 'min_archimate': 7, 'min_er': 2, 'min_rels': 2,
               # 4 个新技术类型必须原样保留（不被降级成 node/service）
               'must_keep_types': ('device', 'system_software',
                                   'communication_network', 'technology_service'),
               'must_keep_rel': 'assignment'},
}

CANONICAL_CASES = [FARM, SHOP, PARTIAL, MESSY, PREFIXED, DEPLOY]


# ------------------------------------------------------------------ 离线打分用样本
# 用于断言「打桩 chat_completion 后打分器一次 LLM 都不调」
SCORER_SAMPLES = [
    ('干净', {'uml': [], 'archimate': [], 'er': []},
     {'counts': {'uml': 4, 'archimate': 4, 'er': 3}, 'dup_names': 0, 'isolated': 0}, 100.0),
    ('一个 error', {'uml': [{'kind': 'uml', 'severity': 'error', 'type': 'naming', 'message': 'x',
                             'where': '', 'suggestion': ''}], 'archimate': [], 'er': []},
     {'counts': {'uml': 4, 'archimate': 4, 'er': 3}, 'dup_names': 0, 'isolated': 0}, 88.0),
]


# ------------------------------------------------------------------- --live 用例
# 只保留「任何合理输出都成立」的不变量，避免真实 LLM 的随机性让测试随机失败。
LIVE_CASES = [
    {'id': 'live-farm', 'text': FARM['text'], 'repeats': 3},
    {'id': 'live-shop', 'text': SHOP['text'], 'repeats': 3},
]
