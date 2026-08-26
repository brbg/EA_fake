# 研发管理模块（需求/测试用例/缺陷/任务）设计

日期：2026-08-26
状态：已获用户批准（brainstorming 完成）

## 背景

后端已存在四类实体的类定义与 CRUD 路由，但处于"半成品"状态：

1. **无 owner 隔离**：requirement/testcase/defect/task 全部路由只做登录检查（`session_id in sessions_cache`），未校验项目归属——任何登录用户可跨项目读写他人数据。
2. **纯内存不落库**：数据只存 `requirements_cache` / `test_cases_cache` / `defects_cache` / `tasks_cache`，后端重启即丢。
3. **前端零接线**：`src/` 下无任何对 requirement/testcase/defect/task 接口的引用，用户在界面无法使用这些模块。

## 目标

- 四类实体（需求 / 测试用例 / 缺陷 / 任务）在界面上可用：增删改查 + AI 生成。
- 数据按项目持久化（SQLite），重启不丢。
- 按用户隔离（跨用户访问 404）。
- 沿用现有实体类的字段，不推倒重来。

## 非目标

- 不做工作流引擎/审批流转。
- 不做跨项目的全局视图。
- 不改动模型/画布相关逻辑。

## 后端改造

### Owner 隔离

所有相关路由统一改用 `_require_user_id()` + `load_model_from_cache(project_id)` + `_model_owned_by()` 校验：

```python
user_id = _require_user_id()
if user_id is None:
    return jsonify({'error': '未登录'}), 401
model = load_model_from_cache(project_id)
if not _model_owned_by(model, user_id):
    return jsonify({'error': '模型不存在'}), 404
```

覆盖路由（app.py 约 10198-10610 行）：
- `POST /api/v1/project/<pid>/requirement/ai/generate`
- `GET|POST|PUT|DELETE /api/v1/project/<pid>/requirement`
- `GET /api/v1/project/<pid>/requirement/list`
- `POST /api/v1/project/<pid>/testcase/ai/generate`
- `GET|POST|PUT|DELETE /api/v1/project/<pid>/testcase`
- `GET /api/v1/project/<pid>/testcase/list`
- `GET|POST|PUT|DELETE /api/v1/project/<pid>/defect`
- `POST /api/v1/project/<pid>/task/ai/plan`
- `GET|POST|PUT|DELETE /api/v1/project/<pid>/task`
- `GET /api/v1/project/<pid>/task/list`

### 持久化

- 数据写入 SQLite（`db.py` 的 `get/set/keys`），每类一个 key：
  - `req:<project_id>` → `{'entries': [requirement dict...]}`
  - `tc:<project_id>` → `{'entries': [testcase dict...]}`
  - `def:<project_id>` → `{'entries': [defect dict...]}`
  - `task:<project_id>` → `{'entries': [task dict...]}`
- 新增辅助函数（与 `_get_memories` 同模式）：
  - `_load_requirements(project_id)` / `_save_requirements(project_id, entries)`
  - `_load_test_cases(project_id)` / `_save_test_cases(...)`
  - `_load_defects(project_id)` / `_save_defects(...)`
  - `_load_tasks(project_id)` / `_save_tasks(...)`
- 各路由读写改为「先读库 → 操作 → 写库」，替换原纯内存缓存访问。`*_cache` 改为启动时从库预载或直接读库（直接读库最简，避免双写）。
- 列表/详情/更新/删除全部基于库里当前状态。

### 数据字段（沿用现有类）

- **Requirement**：id / project_id / name / description / type(feature,function,etc.) / priority(high,medium,low) / status(draft,confirmed,implemented,etc.) / assignee_id / user_id / created_at
- **TestCase**：id / project_id / req_id(关联需求) / name / steps / expected_result / priority / status / created_at
- **Defect**：id / project_id / title / description / severity(critical,major,minor) / status(open,fixed,closed) / assignee_id / created_at
- **Task**：id / project_id / name / description / priority / status / assignee_id / dependencies / created_at

## 前端

### 入口

导航 tabs 新增一项：`{ id: 'dev', name: '研发管理' }`（放在「AI助手」之前）。

### 页面结构

`activeTab === 'dev'` 时渲染一个卡片，顶部 4 个页签（tab 按钮）：需求 / 测试用例 / 缺陷 / 任务。页签内为各实体管理列表。

**公共列表结构**：工具栏（新增按钮 + 可能的 AI 生成按钮 + 刷新）+ 表格/卡片列表（每条含名称、关键字段、编辑/删除按钮）+ 新增/编辑弹窗。

**各页签功能**：

| 页签 | 列表字段 | 操作 | AI 能力 |
|---|---|---|---|
| 需求 | 名称/类型/优先级/状态 | 新增/编辑/删除 | 「AI 生成」：textarea 粘贴业务描述 → POST ai/generate → 批量添加 |
| 测试用例 | 名称/关联需求/优先级/状态 | 新增/编辑/删除 | 「AI 生成」：选一条需求 → POST ai/generate → 生成用例 |
| 缺陷 | 标题/严重度/状态/指派人 | 新增/编辑/删除 | 无 |
| 任务 | 名称/优先级/状态/指派人 | 新增/编辑/删除 | 「AI 计划」：选需求 → POST ai/plan → 生成任务 |

### 弹窗

- 通用新增/编辑弹窗：按实体字段渲染表单（复用现有 `.modal-overlay` / `.modal-content` 模式）。
- AI 生成弹窗：textarea（或需求选择）+ 生成按钮 + 结果确认。

## 错误处理

- 未登录 → 401；项目不存在/非本人 → 404；缺参 → 400。
- AI 未启用/失败 → 明确错误提示（沿用 `error` 字段 + 前端红字展示）。

## 测试 / 验收

1. **Owner 隔离**：用户 A 建数据，用户 B 访问 → 404；未登录 → 401。
2. **持久化**：新增/修改后重启后端，数据仍在。
3. **CRUD**：四类增删改查端到端可用。
4. **AI 生成**：需求/测试用例/任务三类 AI 生成返回真实数据并入库。
5. **前端**：`vue-tsc` + `vite build` 通过；研发管理 tab 四个页签可用。
6. **回归**：既有建模/AI 功能不受影响。

## 改动文件

- `EA_fake/ea-webapp/backend/app.py`（路由改造 + 持久化辅助）
- `EA_fake/ea-webapp/src/App.vue`（新 tab + 四个子页 UI + 弹窗）
- 文档：本 spec
