# AI 生成质量保障（设计）

日期：2026-09-22

## Context

平台的 AI 生成链路此前只有「调大模型 + 散落的兜底」：布局/ID/命名是确定性的，每个布局器有白名单改写与丢弃守卫，若依骨架完全不调 LLM。但缺最关键的一层——**校验器只把问题报给用户看，从不回喂模型**，于是同一个错误每次生成都会重犯。

另有三处可观测性缺口：

- `applied_ops` 报的是 LLM **声称**的步数，被丢弃的操作也算成功，用户以为改上了；
- 三条生成路径**没有截断信号**，内容超 max_tokens 时静默降级成关键词解析，用户只看到「图很糙」；
- 跨图命名一致性全靠提示词自觉，无代码级保障。

本次补齐 7 项，全部是**不依赖更强模型**的工程手段。

## 三个先决发现（改变了设计）

1. **`validate_uml_model` / `review_archimate_model` 不是纯校验器** —— 它们内部会调 LLM 做语义评审（`uml_ai.py:585`、`app.py` 的 `_ai_review_archimate_semantics`）。若打分器直接吃 model 对象，一次 best-of-N 会静默产生 3×2 次额外调用、结果不可复现、离线测试必然随机失败。故：**打分函数永不接受 model**，只接受 issue 列表 + 结构统计量；两个校验器加 `use_ai=False` 开关作第二道防线。
2. **`_apply_er_edits` 有浅拷贝别名缺陷** —— `[dict(e) for e in erEntities]` 是浅拷贝，`e['fields']` 与入参共享同一个 list，而 `add_field` 走 `target['fields'].append(...)` → **原地修改调用方的模型**。这让「报告说 0 步生效、模型其实已被改」成为可能，直接摧毁第 7 项的语义。只有 ER 的 add_field 有此问题（UML / ArchiMate 都是重新赋值）。
3. **`counts` 结构不可污染** —— `_run_architect_agent` 里有 `any(v[0] > 0 for v in counts.values())`，按下标消费。往 `counts` 塞任何标量都会 `TypeError`。新增计数一律走 `report` 返回。

## 产品决策

| 决策 | 选择 | 理由 |
|---|---|---|
| 修复循环触发 | 一键生成后**自动跑一轮** | 用户不必理解「校验」为何物；质量默认就高 |
| 跨图命名 | 高置信自动改，其余只报告 | 不擅自改用户数据，又消掉确定性的机器噪音 |
| Best-of-N | **默认开，3 次采样** | 在一次性关键路径上把长尾烂输出挡在门外 |
| 跨命名约定（`Order` ↔ `orders`） | 既不自动改也不报告 | canonical 提示词本身就要求 ER 表名 snake_case，强行统一会污染若依产物与 DDL 表名 |

## 模块边界

```
code_lint.py   (纯 stdlib)  java_lint / vue_lint / _TagBalancer / lint_generated_files
      ↑ tests/test_ruoyi_gen.py（改为 import，测试从此锁生产实现而非自己的副本）
      ↑ app.py:ruoyi_code_generate_v1（路由层调用，并入 meta['lint'] 与 meta['warnings']）

ai_quality.py  (纯函数，不 import app)
      ↑ app.py（模块级 import）
      ↑ tests/test_ai_quality.py、tests/test_golden_regression.py
```

**硬约束：`ai_quality.py` 不能 import `app`。** `run.bat` 用 `python app.py` 启动时 app.py 的模块名是 `__main__`，任何 `from app import ...` 都会二次导入整个 Flask 应用（重复 app 对象、重复内存缓存、重复 `db.init_db()`）。需要 app 侧的东西一律由调用方注入——与既有 `agent.py` 的「实现由调用方注入」风格一致。

## 实现要点

### 1. 校验-回喂修复循环
`_quality_issues_for_model(model)` 把三套结构校验归一成统一 issue（UML / ArchiMate 走 `use_ai=False`；ER 走四个 `check_*` + `er_view_shim` 适配）。`_auto_repair_once(model, model_id)` 按 kind 分组回喂——不把 UML 的问题发给 ER/ArchiMate，省两次调用也免了误改。

`applied` 的判据是「**有没有真的改动**」而非「模型有没有提出」：全被丢弃时如实说「未自动改动」。

**已知边界**：ops 是按**名字**寻址的，所以「未命名元素」「悬空关系」这类错误反而修不了——坏掉的东西没有合法名字。修复循环对可表达于 ops 词汇的错误有效（如 ER 缺主键 → `add_field`）。

### 2. 确定性打分器
```
基础 100
一、逐条扣分：error 12 / warning 4.5 / minor 1.5 / suggestion 0.5 / 未知 4
    （4.5 而非 4：让 3 error(36) 与 9 warning(40.5) 不打平，消除 12/4 的整除歧义）
二、覆盖度：三个 kind 各要求 ≥1 元素/实体，每缺一个扣 40（防空模型拿满分）
三、结构：同 kind 重名每个扣 8；孤立元素每个扣 1 封顶 10
clamp 到 [0, 100]
```
三张图量纲不同，但**严重度语义共享**（error=模型坏了 / warning=有风险 / minor=建议），只在 severity 这一维归一，其余用与图种类无关的结构量补齐。best-of-N 只需**单调排序**，不需绝对准确。

排除两类条目：`type=='semantic'`（LLM 来源，不可复现）与 `type=='empty'`（覆盖度惩罚已单独扣过，避免双倍惩罚）。

### 3. Best-of-N
一次大 JSON 调用（max_tokens 8192）采 N 次，**用上面的确定性打分器择优选**。顺序是「给所有原始候选打分 → 择优 → 物化 → 修复」：修复要花 LLM 调用，只该修赢家。

两个早退：第 1 次就失败 → 立刻走既有降级，不空耗；某个候选 100 分 → 不再采样。

### 4. 闭合 fail-open 口子
- `_normalize_uml_type` 未知类型改为回落默认 + 记 report（原是 `capitalize()` 直接放行）。`constants.ELEMENT_TYPES['uml']` 补 `'Enum'`——编辑提示词把它列为合法类型，白名单里却没有，不补会引入「合法 Enum 被降级成 Class」的新 bug。
- ER 字段类型新增 `ER_FIELD_TYPES` 闭合词表 + `normalize_er_field_type`（原 `str(x or 'string').upper()` 既不校验、默认值 `'STRING'` 本身也不在词表里）。canonical 的逻辑类型映射到画布惯用写法：`string → VARCHAR(255)`、`integer → INT`、`decimal → DECIMAL(10,2)`。
- ArchiMate 布局器补同名去重（原 `by_name[name] = eid` 直接覆盖，导致引用该名字的关系全指向最后一个同名元素，第一个变成孤立元素）。照搬兄弟布局器的现成守卫。

### 5. 产物自检提到生产侧
`java_lint` / `vue_lint` / `_TagBalancer` 原只活在测试里，测试实际是「测自己的副本」。搬到 `code_lint.py` 后测试改为 import → 变成对生产实现的回归锁。自检在**路由层**调用（不插在纯函数 `generate_ruoyi_module` 内，那个函数被测试直接调用且 fixture 故意构造降级输出）。

自检**只收集告警、永不 raise**，异常降级为一条 `自检未完成（...）` 而非静默当成没问题。

### 6. 跨图命名对齐
判定按序短路：key 相等 → `same`（跨约定算设计使然）；剥表名前缀/后缀后相等 → `high`；仅末位 token 为同义词 → `high`；其余 `different`（只报告）。

安全阀：中文名与英文名绝不互改；key 过短/纯数字不判定；同一名字匹配到多个候选 → 降级为只报告。

报告时抑制「角色后缀」噪音：`OrderService` ↔ `Order` 是三图之间的惯用对应，报出来只会淹没真正该看的问题。

「只报告」的着陆点是健康度 issues（前端弹窗已在渲染字符串列表，**零新增 UI 管线**）；规则版 `perform_health_check` 也接了一份，这样没配 API 密钥的演示环境同样能看到。

### 7. 诚实计数
`EditReport` 以**可选累加器**（`report=None`）的方式贯穿三个 `_apply_*_edits`：9 处调用点一行不改即可工作，向后兼容是构造性的；一个 report 能跨 kind 贯穿（返回三元组就得手工合并三份）；与 `ruoyi_gen.build_module_schema` 的显式 `warnings: list` 风格一致。

计数语义：`applied` = 真正改动了模型的 op 数；「合法但无效果」（`delete_field` 指向不存在字段）计入 `discarded`。每个静默 `continue` 都换成了 `report.skip(op, reason)`，循环末尾补 `else: unknown_op`。

`ai_edit_model_v1` 保留 `applied_ops` 键名（前端已读）但值改成真实生效数，另加 `claimed_ops` / `discarded`。

## 验证

```
D:/python/python.exe backend/tests/test_ruoyi_gen.py
D:/python/python.exe backend/tests/test_ruoyi_api.py
D:/python/python.exe backend/tests/test_ai_quality.py
D:/python/python.exe backend/tests/test_golden_regression.py
D:/python/python.exe backend/tests/test_golden_regression.py --live   # 可选，需 API 密钥
cd ea-webapp && npm run build
```

四套测试均离线（打桩 `AIService.chat_completion`、强制 `enabled=False`），共 526 条断言。黄金回归集覆盖 5 个 canonical 用例（命名一致 / 跨命名约定 / 只有一张图 / 违规产出 / 带表名前缀）+ 整条 7 步编排链路。

**离线必须显式强制关掉 AI**：`core.py` 在 **import 时**就读数据库里的 ai_config，开发机存过 key 的话 `enabled` 会是 True，「离线」测试就会真的联网并随机失败。

## 风险与已知缺口

- **ER 在降级路径无确定性兜底**：`_agent_apply_fallback` 直接调 `_ai_generate_er_data`，拿不到就记 `[0,0]`；而 ER 单图路由走 `ai_generate_er_model`，那里会退到 `extract_entities_from_requirements` 关键词解析。**同一个 AI 关闭场景，单图路由能出 ER、智能体降级路径不能**。已写进黄金测试的 `[已知缺口]` 提示，未修。
- **`finish_reason` 只迁了两条路径**（canonical 与编辑）。其余约 8 个 LLM 辅助函数仍「截断 → 半截 JSON 被 `_ai_parse_json_response` 救回」。半截被救回比直接 None 更危险（模型被建了一半、看起来却成功），但不动它们以保持 diff 可审。
- **best-of-N 的墙钟时间**：生成器 + 同步 requests，N=3 串行会把最慢一步变 3 倍。早退缓解平均成本，最坏情况仍在；v2 可考虑 `ThreadPoolExecutor` 并发。
- **修复循环的边界**：见上文「ops 按名字寻址」。
- **ER 单图路由不做自动修复**：依赖方向会成环（er_routes → ai_quality → er_routes）。
