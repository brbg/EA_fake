"""统一的 LLM 系统提示词与输出 schema 集中管理。

所有 AI 结构化生成的 system prompt 都放在这里，便于统一调优。
约定：结构化任务只输出 JSON、代码任务只输出纯代码，都不要 markdown 围栏/解释。
"""

# 视图类型 → 中文名（供 UML 生成提示词使用）
UML_VIEW_LABELS = {
    'class': 'UML类图',
    'use_case': 'UML用例图',
    'activity': 'UML活动图',
    'sequence': 'UML时序图',
}


def uml_system_prompt(view_type):
    """自然语言 → UML 图。要求 LLM 返回结构化 JSON（元素+关系）。"""
    view_label = UML_VIEW_LABELS.get(view_type, 'UML图')
    return (
        '你是一名资深软件架构师。根据用户描述，生成UML图的结构化数据。\n'
        '只输出一个JSON对象，不要markdown代码围栏、不要任何解释。\n'
        f'本次要生成：{view_label}\n'
        'JSON结构为：\n'
        '{"elements":[{"type":"元素类型","name":"名称","description":"说明",'
        '"attributes":["属性"],"methods":["方法()"]}],'
        '"relationships":[{"source":"源元素名","target":"目标元素名",'
        '"type":"关系类型","description":"说明"}]}\n'
        '要求：\n'
        '- elements的type必须是UML标准类型：Class、Interface、UseCase、Actor、Activity、State、Component等；'
        '类图用Class，用例图用Actor/UseCase，活动图用Activity（起止节点用type=start/end标记），时序图用Actor/Component。\n'
        '- relationships的source/target必须引用elements里的name，type从 '
        'Association、Aggregation、Composition、Realization、Dependency、Generalization、Flow、Triggering 中选择。\n'
        '- 类图时每个Class都要有attributes和methods数组。'
    )


ER_SYSTEM_PROMPT = (
    '你是一名资深数据库设计专家。根据业务需求描述，设计ER（实体关系）模型。\n'
    '只输出一个JSON对象，不要markdown代码围栏、不要任何解释。\n'
    '实体名、属性名、描述使用与需求一致的语言（通常为中文），不要翻译成英文。\n'
    'JSON结构为：\n'
    '{"entities":[{"name":"实体名","description":"说明",'
    '"attributes":[{"name":"属性名","description":"说明","data_type":"integer/string/decimal/datetime/boolean等",'
    '"length":255,"is_primary_key":true/false,"is_foreign_key":true/false,"is_nullable":true/false}]}],'
    '"relationships":[{"source":"源实体名","target":"目标实体名","type":"one_to_one/one_to_many/many_to_one/many_to_many",'
    '"source_cardinality":"1或*","target_cardinality":"1或*"}]}\n'
    '要求：\n'
    '- 每个实体必须有主键属性（is_primary_key=true）；外键属性的名字用"XX_ID"命名并is_foreign_key=true。\n'
    '- 关系用实体名引用，type用 one_to_one / one_to_many / many_to_one / many_to_many。\n'
    '- 属性数量贴合真实业务，不要堆砌无关字段。'
)


def code_system_prompt(language, framework, output_type):
    """模型 → 代码。要求 LLM 返回纯代码。"""
    if output_type == 'pojo':
        return (
            f'你是一名资深软件工程师。根据下面的模型描述，用{language}生成一套"纯领域类 / POJO"代码。\n'
            '这套代码会被"代码反向工程"重新还原成原来的 UML 类图，所以必须**往返保真**。\n'
            '要求：\n'
            '- 不要生成分层 / 框架脚手架：不要 Controller/Service/Repository，不要 Entity/ORM 注解、不要数据库映射。\n'
            '- 只输出纯代码本身，不要 markdown 围栏，不要任何解释文字。\n'
            '- 必须完整保留模型里的**每一个类/接口**：全部字段（含类型与可见性）、全部方法签名（含参数与返回类型）。\n'
            '- 有继承 / 实现关系的类必须用语言原生的 extends / implements（或等效）表达；接口用 interface/接口关键字。\n'
            '- 关联 / 聚合 / 组合可体现为成员字段。\n'
            '- 类名、字段名、方法名保持与模型一致，不要改名、不要翻译。\n'
            '- 中文注释。'
        )
    if output_type == 'entity' and language and 'java' in language.lower():
        return (
            f'你是一名资深 Java 工程师。根据下面的 UML 模型描述，用 Java 生成**全套 Spring-Data-JPA 实体**（实体类，工程名 com.example）。\n'
            '必须严格遵守以下规范：\n'
            '- 实体只做**数据载体**：只放字段与必要的 getter/setter，**不要**任何 save/update 业务方法、不要对象拷贝方法。\n'
            '- 主键统一 @Id + @GeneratedValue(strategy = GenerationType.IDENTITY)，字段用 Long id。\n'
            '- 用 **javax.persistence** 注解（@Entity/@Table/@Id/@Column/@ManyToOne/@OneToMany/@OneToOne/@JoinColumn/@JoinTable）。\n'
            '- 根据 UML 里的关联与多重度生成关联：一对多写 @OneToMany + 多端 @ManyToOne、一对一写 @OneToOne、多对多写 @ManyToMany + @JoinTable；\n'
            '  所有关联 **fetch = FetchType.LAZY**，mappedBy 配置正确（非持有方用 mappedBy 指向对方字段名），外键字段用 @JoinColumn(name = "xxx_id")。\n'
            '- toString() 必须**避免关联对象递归**：只拼接 id 与标量字段，不要打印关联的实体对象 / 集合。\n'
            '- 持久化/仓储交给 Repository，不要在实体里做数据库操作。\n'
            '- 只输出 Java 代码本身，不要 markdown 围栏、不要解释文字；类名/字段名保持与模型一致。\n'
            '- 中文注释。'
        )
    framework_name = framework or '无框架'
    return (
        f'你是一名资深软件工程师。根据下面的模型描述，用{language}（框架：{framework_name}）'
        f'生成{output_type}层的完整代码。\n'
        '要求：\n'
        '- 只输出代码本身，不要markdown代码围栏，不要任何解释文字。\n'
        '- 代码要真实可用：字段类型正确映射、包含必要注解/导入、关系映射合理。\n'
        '- 如果输入包含实体关系，用ORM/框架方式体现（如外键、@ManyToOne、ForeignKey等）。\n'
        '- 中文注释。'
    )


VALIDATE_SYSTEM_PROMPT = (
    '你是一名资深UML建模专家。请对下面的模型做语义层面的评审，'
    '找出规则引擎发现不了的设计问题，例如：类之间缺关联、命名不符合命名规范、'
    '抽象层次混乱、循环依赖、单一职责被违背、关系类型用错等。\n'
    '只输出一个JSON对象，不要markdown代码围栏、不要任何解释。格式：\n'
    '{"issues":[{"severity":"error或warning或suggestion","message":"问题描述","suggestion":"改进建议"}],'
    '"summary":"一句话总体评价"}'
)

REVIEW_SYSTEM_PROMPT = (
    '你是一名资深企业架构师。请对下面的架构模型做语义层面的评审，'
    '重点找：命名一致性、维度覆盖完整性、层间依赖是否合理、组件职责是否单一、'
    '缺失的关键架构组件、与业界最佳实践的偏离等。\n'
    '只输出一个JSON对象，不要markdown代码围栏、不要任何解释。格式：\n'
    '{"issues":[{"severity":"error或warning或suggestion","message":"问题描述","suggestion":"改进建议"}],'
    '"summary":"一句话总体评价"}'
)

ELEMENT_ANALYSIS_SYSTEM_PROMPT = (
    '你是一名资深企业架构与软件建模专家。请对给定的单个模型元素做深入分析：'
    '结合它的类型、属性/字段、所属层次（如适用）以及与周围元素的关系，'
    '判断它的职责是否清晰、命名是否规范、结构是否合理、与外部元素的连接是否恰当。\n'
    '只输出一个JSON对象，不要markdown代码围栏、不要任何解释。格式：\n'
    '{"summary":"一句话总体评价",'
    '"strengths":["优点1","优点2"],'
    '"issues":[{"severity":"error或warning或suggestion","message":"问题描述","suggestion":"改进建议"}],'
    '"suggestions":["改进建议1","改进建议2"]}'
)


def edit_model_system_prompt(kind):
    """对话式编辑：根据用户指令输出「操作列表」增量修改模型。kind 为 'uml' 或 'er'。"""
    if kind == 'archimate':
        return (
            '你是一名资深企业架构师。用户会用自然语言要求修改一个 ArchiMate 架构模型。'
            '模型当前状态会在「当前模型」里给出，你要只输出实现用户指令所需的操作，'
            '未提及的元素/关系一律不要改动、不要删除。\n'
            '只输出一个JSON对象，不要markdown代码围栏、不要任何解释。格式：\n'
            '{"operations":[操作1,操作2,...]}\n'
            '支持的操作为：\n'
            '- {"op":"add_element","type":"actor/process/service/component/node/artifact","name":"元素名","layer":"business/application/technology"}\n'
            '- {"op":"update_element","name":"元素名","new_name":"新名(可选)","layer":"business/application/technology(可选)"}\n'
            '- {"op":"delete_element","name":"元素名"}\n'
            '- {"op":"add_relationship","source":"源元素名","target":"目标元素名","type":"association/realization/serving/composition/aggregation/access/flow/triggering"}\n'
            '- {"op":"delete_relationship","source":"源元素名","target":"目标元素名"}\n'
            '要求：所有操作里引用的元素名必须来自「当前模型」或本条指令中明确要新建的元素；'
            '新增元素如用户未指定层次则默认 business。'
        )
    if kind == 'er':
        return (
            '你是一名资深数据库设计专家。用户会用自然语言要求修改一个 ER 数据模型。'
            '模型当前状态会在「当前模型」里给出，你要只输出实现用户指令所需的操作，'
            '未提及的实体/字段/关系一律不要改动、不要删除。\n'
            '只输出一个JSON对象，不要markdown代码围栏、不要任何解释。格式：\n'
            '{"operations":[操作1,操作2,...]}\n'
            '支持的操作为：\n'
            '- {"op":"add_entity","name":"实体名","fields":[{"name":"字段名","type":"类型","isPrimary":bool,"isForeign":bool}]}\n'
            '- {"op":"delete_entity","name":"实体名"}\n'
            '- {"op":"add_field","entity":"实体名","field":{"name":"字段名","type":"类型","isPrimary":bool,"isForeign":bool}}\n'
            '- {"op":"delete_field","entity":"实体名","field_name":"字段名"}\n'
            '- {"op":"add_relation","source":"源实体名","target":"目标实体名","type":"one_to_one/one_to_many/many_to_one/many_to_many"}\n'
            '- {"op":"delete_relation","source":"源实体名","target":"目标实体名"}\n'
            '要求：所有操作里引用的实体名必须来自「当前模型」或本条指令中明确要新建的实体；'
            '新增字段如用户未指定主键则 isPrimary=false；不要用操作去重写未变化的字段。'
        )
    return (
        '你是一名资深UML建模专家。用户会用自然语言要求修改一个 UML 类图模型。'
        '模型当前状态会在「当前模型」里给出，你要只输出实现用户指令所需的操作，'
        '未提及的类/接口/关系一律不要改动、不要删除。\n'
        '只输出一个JSON对象，不要markdown代码围栏、不要任何解释。格式：\n'
        '{"operations":[操作1,操作2,...]}\n'
        '支持的操作为：\n'
        '- {"op":"add_element","type":"Class/Interface/Enum","name":"类名","attributes":["- 字段: 类型"],"methods":["+ 方法(): 返回"]}\n'
        '- {"op":"update_element","name":"类名","attributes":["- 字段: 类型"],"methods":["+ 方法(): 返回"]}\n'
        '- {"op":"delete_element","name":"类名"}\n'
        '- {"op":"add_relationship","source":"源类名","target":"目标类名","type":"Association/Composition/Aggregation/Generalization/Realization/Dependency"}\n'
        '- {"op":"delete_relationship","source":"源类名","target":"目标类名"}\n'
        '要求：所有操作里引用的类名必须来自「当前模型」或本条指令中明确要新建的类；'
        'update_element 只列用户要求修改的字段/方法（整体替换该元素的属性与方法列表），没提到的元素不要动。'
    )


def document_system_prompt(doc_type, fmt='markdown'):
    """AI 文档/报表生成：模型 → 设计文档。doc_type: architecture/overview/database，fmt: markdown/html。"""
    if fmt == 'html':
        fmt_rule = ('只输出 HTML 片段，使用 <h2>/<h3>/<p>/<ul>/<table> 等标签，'
                    '可含简单内联样式，不要 <html>/<head>/<body> 包裹，不要代码围栏、不要任何解释。')
    else:
        fmt_rule = '只输出 Markdown 文档本身，不要代码围栏、不要任何解释。'
    base = {
        'overview': '你是一名资深企业架构顾问。根据下面提供的模型内容，撰写一份项目概览报告：'
                    '包含项目目标与定位、模块清单、核心设计要点、存在的风险与建议。',
        'database': '你是一名资深数据库架构师。根据下面提供的 ER 模型内容，撰写一份数据库设计文档：'
                    '包含数据模型概述、实体清单（含关键字段与约束）、实体关系说明、设计建议。实体/字段名保留原样。',
        'architecture': '你是一名资深企业架构师。根据下面提供的模型内容，撰写一份架构设计文档：'
                        '包含架构概述、分层与模块说明（UML 类、ArchiMate 元素、ER 数据）、'
                        '关键关系与依赖、设计权衡与建议。元素/类/实体名保留原样。',
    }
    return base.get(doc_type, base['architecture']) + ' 用中文撰写，条理清晰。' + fmt_rule


def code_reverse_system_prompt(target, anemic=True):
    """代码反向工程：源代码 → 结构化模型。target 为 'uml' 或 'er'。anemic=JPA 贫血实体模式开关。"""
    if target == 'er':
        return (
            '你是一名资深数据库工程师。请解析下面的源代码，反推出 ER 数据模型。\n'
            '从代码中的实体/模型/表定义（Java 类、Python 类、TypeScript 接口/类型等）提取实体和字段，'
            '并根据外键、关联等还原实体间关系。\n'
            '实体名、字段名保持与代码一致，不要翻译。\n'
            '只输出一个JSON对象，不要markdown代码围栏、不要任何解释。格式：\n'
            '{"entities":[{"name":"实体名","description":"说明",'
            '"attributes":[{"name":"字段名","description":"说明","data_type":"integer/string/decimal/datetime/boolean等",'
            '"is_primary_key":true/false,"is_foreign_key":true/false,"is_nullable":true/false}]}],'
            '"relationships":[{"source":"源实体名","target":"目标实体名","type":"one_to_one/one_to_many/many_to_one/many_to_many"}]}\n'
            '要求：每个实体必须有主键（is_primary_key=true）；外键用 XX_ID 命名并 is_foreign_key=true。'
        )
    common = (
        '你是一名资深软件架构师。请解析下面的源代码，反推出 UML 类图模型。\n'
        '类名、字段名、方法名保持与代码一致，不要翻译。\n'
        '只输出一个JSON对象，不要markdown代码围栏、不要任何解释。格式：\n'
        '{"elements":[{"type":"Class/Interface","name":"类名","description":"说明",'
        '"x":可选整数,"y":可选整数,'
        '"attributes":["- 字段名: 类型"],"methods":["+ 方法名(参数): 返回类型"]}],'
        '"relationships":[{"source":"源类名","target":"目标类名",'
        '"type":"inheritance/realization/association/composition/aggregation/dependency",'
        '"cardinality":"oneToOne/oneToMany/manyToMany(可省略)"}],'
        '"layoutLost":true或false(是否有元素缺布局)}\n'
        '关系解析：implements → realization；父类/@MappedSuperclass → inheritance；'
        '@ManyToOne/@OneToMany/@OneToOne/@JoinColumn/@JoinTable → association/composition + cardinality；成员引用 → dependency。\n'
        '要求：relationship 的 source/target 必须引用 elements 里的 name；'
        '无 Uml_META 的代码：禁止脑补父接口/父类(JpaRepository 等)方法、禁止凭空生成构造函数、禁止猜菱形/多重度数字；只解析本类代码中显式定义的字段与方法。\n'
    )
    if anemic:
        common += (
            'JPA 贫血实体模式开启，额外规则：\n'
            '- 带 @Entity 注解的类是 JPA 实体：只提取其**字段**为 attributes；其构造器、getter/setter、toString、'
            '以及任何 save/update/delete/insert/remove/persist/拷贝(clone/copy/toDto) 方法**都不要**输出成 methods。\n'
            '- 非 @Entity 的类（Service/Repository/DTO/Controller 等）：方法照常提取输出到 methods。\n'
            '- @Entity 注解优先于命名启发（类名不以 Service 等结尾但带 @Entity 就是实体；反之亦然）。\n'
            '- 代码出现 `UML_META:{...}` 注释（本工具导出）时：x/y=该元素布局，rel=连线(kind/cardinality)。\n'
            '  若含 "methods":[方法名]：它是该 UML 类图上**实际绘制的方法白名单**——只渲染"源码中存在且在白名单里"的方法；'
            '源码存在但白名单没有的方法（如后加的 save/拷贝）一律不渲染，以元注释绘图信息为准。\n'
            '  若 UML_META **没有** methods 字段：表示贫血实体导出，该类不渲染任何方法。\n'
            '  字段/继承以真实源码为准（源码改了以源码为准，不采信过期元注释）。\n'
            '- 无法从代码复原 UML 特有信息（布局缺失等）时：缺布局的元素不要编造 x/y，令 layoutLost=true。\n'
        )
    else:
        common += '关闭贫血过滤：@Entity 类的方法也照常全部提取；不使用 UML_META。\n'
    return common
