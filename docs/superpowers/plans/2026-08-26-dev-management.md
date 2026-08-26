# 研发管理模块（需求/测试/缺陷/任务）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把后端已有的 Requirement/TestCase/Defect/Task 四类实体从"半成品"变成可用的研发管理模块：owner 隔离 + SQLite 持久化 + 前端「研发管理」页。

**Architecture:** 后端统一改造模式——每个路由加 `_require_user_id` + `_model_owned_by` 归属校验，并把内存缓存访问换成 `db.get/set` 持久化辅助函数（`<kind>:<project_id>` key）。前端用「配置驱动的通用 CRUD 页」：一个 active 实体配置决定列表/表单/AI 生成，避免四套重复代码。

**Tech Stack:** Flask（backend/app.py）+ Vue 3 + TypeScript（src/App.vue），SQLite 经 db.py。

**Spec:** `docs/superpowers/specs/2026-08-26-dev-management-design.md`

## Global Constraints

- 归属校验沿用现有模式：`_require_user_id()` → None 返回 401「未登录」；`load_model_from_cache(project_id)` + `_model_owned_by(model, user_id)` → 非本人返回 404「模型不存在」。
- 持久化 key：`req:<project_id>` / `tc:<project_id>` / `def:<project_id>` / `task:<project_id>`，值结构 `{'entries': [dict...]}`。
- 实体字段沿用现有类（app.py 9668-9900）：Requirement(name/description/type/priority/status/assignee_id)、TestCase(name/description/level/req_id/assignee_id/priority/status)、Defect(name/description/level/case_id/req_id/assignee_id/reproduce_step/actual_result/expected_result)、Task(name/description/type/req_id/assignee_id/priority/status/work_hours/plan_start_time/plan_end_time)。
- 前端验证：`vue-tsc --noEmit` + `vite build`；后端 `python -m py_compile backend/app.py`。

---

### Task 1: 后端持久化辅助函数 + 需求路由改造（样板）

**Files:**
- Modify: `EA_fake/ea-webapp/backend/app.py`（`ai_generate_code_from_model` 之前、`manage_requirements` 附近）

**Interfaces:**
- Produces: `_load_dev_entries(kind, project_id) -> list`、`_save_dev_entries(kind, project_id, entries) -> None`（Task 2-4 复用）。

- [ ] **Step 1: 新增持久化辅助函数**

在 `def ai_generate_requirements_api` 之前插入：
```python
def _load_dev_entries(kind, project_id):
    """读取项目某类研发条目（kind: req/tc/def/task）。"""
    data = db.get(f'{kind}:{project_id}', {}) or {}
    entries = data.get('entries')
    return entries if isinstance(entries, list) else []


def _save_dev_entries(kind, project_id, entries):
    """保存项目某类研发条目。"""
    db.set(f'{kind}:{project_id}', {'entries': entries})
```

- [ ] **Step 2: 重写 requirement 路由（`manage_requirements`，当前 10221 行附近）**

给 `GET|POST|PUT|DELETE /api/v1/project/<project_id>/requirement` 的 handler 开头插入归属校验，并把对 `requirements_cache` 的读写全部换成 `_load_dev_entries('req', project_id)` / `_save_dev_entries('req', project_id, entries)`：
- GET：`entries = _load_dev_entries('req', project_id)` → 返回 `{'requirements': [e.to_dict() for e in entries]}`（entries 存 Requirement 对象；载入时需重建对象或用 dict）。**约定：存 dict，读时 `Requirement.from_dict(dict)` 重建对象**（检查 Requirement 类是否已有 `from_dict`；没有则用 `to_dict` 存、`Requirement(project_id, d['name'], ...)` 方式重建）。
- POST：校验后 `entry = req.to_dict(); entries.append(entry); _save_dev_entries('req', project_id, entries)`。
- PUT：找到对应 id 的 entry dict，更新字段后写回。
- DELETE：过滤掉对应 id，写回。
- `requirement/list`（10287）与 `requirement/ai/generate`（10198）同样加归属校验 + 持久化读写。

- [ ] **Step 3: 验证编译**

Run: `cd EA_fake/ea-webapp && /d/python/python.exe -m py_compile backend/app.py`
Expected: PASS

- [ ] **Step 4: 提交**

```bash
git add EA_fake/ea-webapp/backend/app.py
git commit -m "feat: 研发模块持久化辅助 + 需求路由归属隔离"
```

---

### Task 2: testcase 路由改造

**Files:**
- Modify: `EA_fake/ea-webapp/backend/app.py`（`manage_test_cases` 10338、`testcase/list` 10401、`testcase/ai/generate` 10314）

**Interfaces:**
- Consumes: `_load_dev_entries` / `_save_dev_entries`；归属校验模式。
- Produces: testcase 数据持久化到 `tc:<project_id>`。

- [ ] **Step 1: 重写 testcase 路由**

与 Task 1 相同模式：三个 handler 开头加归属校验；`test_cases_cache` 读写换成 `_load_dev_entries('tc', project_id)` / `_save_dev_entries('tc', project_id, entries)`；存 dict。字段沿用现有 TestCase 类（name/description/level/req_id/assignee_id/priority/status）。

- [ ] **Step 2: 验证编译**

Run: `cd EA_fake/ea-webapp && /d/python/python.exe -m py_compile backend/app.py`
Expected: PASS

- [ ] **Step 3: 提交**

```bash
git add EA_fake/ea-webapp/backend/app.py
git commit -m "feat: testcase 路由归属隔离 + 持久化"
```

---

### Task 3: defect 路由改造

**Files:**
- Modify: `EA_fake/ea-webapp/backend/app.py`（`manage_defects` 10428）

**Interfaces:**
- Consumes: `_load_dev_entries` / `_save_dev_entries`。
- Produces: defect 数据持久化到 `def:<project_id>`。

- [ ] **Step 1: 重写 defect 路由**

`manage_defects`（GET/POST/PUT/DELETE）开头加归属校验；`defects_cache` 读写换成 `_load_dev_entries('def', project_id)` / `_save_dev_entries('def', project_id, entries)`；存 dict。字段沿用现有 Defect 类（name/description/level/case_id/req_id/assignee_id/reproduce_step/actual_result/expected_result）。

- [ ] **Step 2: 验证编译**

Run: `cd EA_fake/ea-webapp && /d/python/python.exe -m py_compile backend/app.py`
Expected: PASS

- [ ] **Step 3: 提交**

```bash
git add EA_fake/ea-webapp/backend/app.py
git commit -m "feat: defect 路由归属隔离 + 持久化"
```

---

### Task 4: task 路由改造（含 ai/plan）

**Files:**
- Modify: `EA_fake/ea-webapp/backend/app.py`（`manage_tasks` 10524、`task/list` 10594、`task/ai/plan` 10497）

**Interfaces:**
- Consumes: `_load_dev_entries` / `_save_dev_entries`。
- Produces: task 数据持久化到 `task:<project_id>`。

- [ ] **Step 1: 重写 task 路由**

`manage_tasks`、`task/list`、`task/ai/plan` 开头加归属校验；`tasks_cache` 读写换成 `_load_dev_entries('task', project_id)` / `_save_dev_entries('task', project_id, entries)`；存 dict。字段沿用现有 Task 类（name/description/type/req_id/assignee_id/priority/status/work_hours/plan_start_time/plan_end_time）。

- [ ] **Step 2: 验证编译**

Run: `cd EA_fake/ea-webapp && /d/python/python.exe -m py_compile backend/app.py`
Expected: PASS

- [ ] **Step 3: 提交**

```bash
git add EA_fake/ea-webapp/backend/app.py
git commit -m "feat: task 路由归属隔离 + 持久化"
```

---

### Task 5: 前端「研发管理」页骨架 + 通用 CRUD（配置驱动）

**Files:**
- Modify: `EA_fake/ea-webapp/src/App.vue`

**Interfaces:**
- Consumes: 后端 Task 1-4 的接口（`/api/v1/project/<pid>/requirement|testcase|defect|task`）。
- Produces: `DEV_ENTITIES` 配置、`activeDevTab`、列表渲染、表单弹窗、CRUD 函数（Task 6 复用）。

- [ ] **Step 1: 导航加「研发管理」tab**

`const tabs = [...]` 数组在 `{ id: 'ai', name: 'AI助手' }` 前插入 `{ id: 'dev', name: '研发管理' }`。

- [ ] **Step 2: script 加状态与配置**

```ts
// === 研发管理（需求/测试/缺陷/任务） ===
type DevKind = 'requirement' | 'testcase' | 'defect' | 'task'
const devTabs: Array<{ id: DevKind; name: string; icon: string }> = [
  { id: 'requirement', name: '需求', icon: 'fas fa-list-check' },
  { id: 'testcase', name: '测试用例', icon: 'fas fa-vial' },
  { id: 'defect', name: '缺陷', icon: 'fas fa-bug' },
  { id: 'task', name: '任务', icon: 'fas fa-tasks' },
]
const activeDevTab = ref<DevKind>('requirement')
const devList = ref<any[]>([])
const devLoading = ref(false)
const devError = ref('')
const showDevModal = ref(false)
const editingDev = ref<any>(null)
const devForm = ref<Record<string, string>>({})

// 每个实体的字段配置（label → 表单键）
const DEV_FIELDS: Record<DevKind, Array<{ key: string; label: string }>> = {
  requirement: [
    { key: 'name', label: '名称' },
    { key: 'description', label: '描述' },
    { key: 'type', label: '类型' },
    { key: 'priority', label: '优先级' },
    { key: 'status', label: '状态' },
    { key: 'assignee_id', label: '指派人' },
  ],
  testcase: [
    { key: 'name', label: '名称' },
    { key: 'description', label: '描述' },
    { key: 'level', label: '级别' },
    { key: 'req_id', label: '关联需求' },
    { key: 'assignee_id', label: '指派人' },
    { key: 'status', label: '状态' },
  ],
  defect: [
    { key: 'name', label: '标题' },
    { key: 'description', label: '描述' },
    { key: 'level', label: '严重度' },
    { key: 'assignee_id', label: '指派人' },
    { key: 'status', label: '状态' },
  ],
  task: [
    { key: 'name', label: '名称' },
    { key: 'description', label: '描述' },
    { key: 'type', label: '类型' },
    { key: 'priority', label: '优先级' },
    { key: 'assignee_id', label: '指派人' },
    { key: 'status', label: '状态' },
    { key: 'work_hours', label: '工时' },
  ],
}
const devApi = (k: DevKind) => `/api/v1/project/${currentModelId.value}/${k}`

const loadDevList = async () => {
  const k = activeDevTab.value
  if (!currentModelId.value) { devList.value = []; return }
  devLoading.value = true
  devError.value = ''
  try {
    const res = await fetch(devApi(k), {
      headers: { 'X-Session-Id': sessionStorage.getItem('sessionId') || '' }
    })
    const data = await res.json()
    if (!res.ok || data.error) { devError.value = data.error || '加载失败'; return }
    const key = k === 'requirement' ? 'requirements' : k === 'testcase' ? 'test_cases' : k === 'defect' ? 'defects' : 'tasks'
    devList.value = data[key] || []
  } catch (e: any) {
    devError.value = e?.message || '加载失败'
  } finally { devLoading.value = false }
}

const openDevModal = (item: any | null) => {
  editingDev.value = item
  devForm.value = item ? { ...item } : {}
  showDevModal.value = true
}
const saveDev = async () => {
  const k = activeDevTab.value
  const body = editingDev.value ? { ...devForm.value, id: editingDev.value.id } : devForm.value
  try {
    const res = await fetch(devApi(k), {
      method: editingDev.value ? 'PUT' : 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Session-Id': sessionStorage.getItem('sessionId') || '' },
      body: JSON.stringify(body)
    })
    const data = await res.json()
    if (!res.ok || data.error) { devError.value = data.error || '保存失败'; return }
    showDevModal.value = false
    loadDevList()
  } catch (e: any) { devError.value = e?.message || '保存失败' }
}
const removeDev = async (item: any) => {
  const k = activeDevTab.value
  if (!confirm(`确定删除「${item.name || item.id}」？`)) return
  try {
    await fetch(devApi(k), {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json', 'X-Session-Id': sessionStorage.getItem('sessionId') || '' },
      body: JSON.stringify({ id: item.id })
    })
    loadDevList()
  } catch (e) { /* ignore */ }
}
```

- [ ] **Step 3: 模板加页面**

在 `activeTab === 'ai'` 卡片之前插入：
```html
<div v-if="activeTab === 'dev'" class="card">
  <h3 class="card-title"><i class="fas fa-tasks" style="color:#1f5eff;"></i> 研发管理</h3>
  <p class="card-desc">管理项目的需求、测试用例、缺陷与任务</p>
  <div style="display:flex; gap:8px; flex-wrap:wrap; margin-bottom:16px;">
    <button v-for="t in devTabs" :key="t.id"
      :class="['toolbar-btn', { active: activeDevTab === t.id }]"
      @click="activeDevTab = t.id; loadDevList()">
      <i :class="t.icon"></i> {{ t.name }}
    </button>
    <div style="flex:1;"></div>
    <button class="btn btn-primary" @click="openDevModal(null)"><i class="fas fa-plus"></i> 新增</button>
  </div>

  <div v-if="devError" style="color:#d33; background:#fdf0f0; padding:10px; border-radius:8px; margin-bottom:12px;">
    <i class="fas fa-exclamation-triangle"></i> {{ devError }}
  </div>

  <table class="table" v-if="devList.length">
    <thead>
      <tr>
        <th v-for="f in DEV_FIELDS[activeDevTab]" :key="f.key">{{ f.label }}</th>
        <th style="width:100px;">操作</th>
      </tr>
    </thead>
    <tbody>
      <tr v-for="item in devList" :key="item.id">
        <td v-for="f in DEV_FIELDS[activeDevTab]" :key="f.key">{{ item[f.key] || '-' }}</td>
        <td>
          <button class="btn btn-outline" style="padding:4px 8px; font-size:12px; margin-right:4px;" @click="openDevModal(item)">编辑</button>
          <button class="btn-delete" @click="removeDev(item)"><i class="fas fa-trash"></i></button>
        </td>
      </tr>
    </tbody>
  </table>
  <p v-else style="color:#999;">暂无{{ devTabs.find(t => t.id === activeDevTab)?.name }}数据，点「新增」或「AI 生成」创建。</p>
</div>
```

- [ ] **Step 4: 加表单弹窗**

在既有弹窗区（任意 modal 之后）加：
```html
<div v-if="showDevModal" class="modal-overlay" @click.self="showDevModal = false">
  <div class="modal-content">
    <span class="modal-close" @click="showDevModal = false">&times;</span>
    <h3 style="margin-bottom:16px;">{{ editingDev ? '编辑' : '新增' }}{{ devTabs.find(t => t.id === activeDevTab)?.name }}</h3>
    <div class="form-group" v-for="f in DEV_FIELDS[activeDevTab]" :key="f.key">
      <label>{{ f.label }}</label>
      <input v-model="devForm[f.key]" :placeholder="f.label" />
    </div>
    <div style="display:flex; justify-content:flex-end; gap:10px; margin-top:16px;">
      <button class="btn btn-outline" @click="showDevModal = false">取消</button>
      <button class="btn btn-primary" @click="saveDev">保存</button>
    </div>
  </div>
</div>
```

- [ ] **Step 5: 验证编译**

Run: `cd EA_fake/ea-webapp && ./node_modules/.bin/vue-tsc --noEmit && ./node_modules/.bin/vite build`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add EA_fake/ea-webapp/src/App.vue
git commit -m "feat: 研发管理页（配置驱动 CRUD：需求/测试/缺陷/任务）"
```

---

### Task 6: 前端 AI 生成（需求/测试/任务）

**Files:**
- Modify: `EA_fake/ea-webapp/src/App.vue`

**Interfaces:**
- Consumes: Task 5 的 `devList`/`loadDevList`/`devApi`/`activeDevTab`。
- Produces: `showDevAiModal`、`devAiText`、`devAiGenerating`、`generateDevAi()`。

- [ ] **Step 1: script 加 AI 生成状态与函数**

```ts
const showDevAiModal = ref(false)
const devAiText = ref('')
const devAiGenerating = ref(false)

const openDevAi = () => { devAiText.value = ''; showDevAiModal.value = true }
const generateDevAi = async () => {
  const k = activeDevTab.value
  const api = k === 'requirement'
    ? `/api/v1/project/${currentModelId.value}/requirement/ai/generate`
    : k === 'testcase'
      ? `/api/v1/project/${currentModelId.value}/testcase/ai/generate`
      : `/api/v1/project/${currentModelId.value}/task/ai/plan`
  devAiGenerating.value = true
  devError.value = ''
  try {
    const res = await fetch(api, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Session-Id': sessionStorage.getItem('sessionId') || '' },
      body: JSON.stringify({ text: devAiText.value })
    })
    const data = await res.json()
    if (!res.ok || data.error) { devError.value = data.error || '生成失败'; return }
    showDevAiModal.value = false
    loadDevList()
  } catch (e: any) { devError.value = e?.message || '生成失败' }
  finally { devAiGenerating.value = false }
}
```

- [ ] **Step 2: 模板加 AI 生成按钮与弹窗**

在研发管理页工具栏「新增」旁加：
```html
<button v-if="activeDevTab !== 'defect'" class="btn btn-outline" @click="openDevAi">
  <i class="fas fa-wand-magic-sparkles"></i> AI 生成
</button>
```
在表单弹窗后加：
```html
<div v-if="showDevAiModal" class="modal-overlay" @click.self="showDevAiModal = false">
  <div class="modal-content">
    <span class="modal-close" @click="showDevAiModal = false">&times;</span>
    <h3 style="margin-bottom:12px;"><i class="fas fa-wand-magic-sparkles"></i> AI 生成{{ devTabs.find(t => t.id === activeDevTab)?.name }}</h3>
    <textarea v-model="devAiText" rows="6" placeholder="输入业务描述 / 需求内容，AI 将拆分生成条目…"
      style="width:100%; padding:12px; border:1px solid #ddd; border-radius:8px; font-size:14px; resize:vertical; font-family:inherit;"></textarea>
    <div style="display:flex; justify-content:flex-end; gap:10px; margin-top:16px;">
      <button class="btn btn-outline" @click="showDevAiModal = false">取消</button>
      <button class="btn btn-primary" @click="generateDevAi" :disabled="devAiGenerating || !devAiText.trim()">
        <i v-if="devAiGenerating" class="fas fa-spinner fa-spin"></i> {{ devAiGenerating ? '生成中...' : '生成' }}
      </button>
    </div>
  </div>
</div>
```

- [ ] **Step 3: 验证编译**

Run: `cd EA_fake/ea-webapp && ./node_modules/.bin/vue-tsc --noEmit && ./node_modules/.bin/vite build`
Expected: PASS

- [ ] **Step 4: 提交**

```bash
git add EA_fake/ea-webapp/src/App.vue
git commit -m "feat: 研发管理 AI 生成（需求/测试/任务）"
```

---

### Task 7: 端到端验证

**Files:**
- 验证脚本（临时，不入库）

- [ ] **Step 1: 重启后端 + 写验证脚本**

重启后端（带 DeepSeek env）。写临时 Python 脚本验证：
- 登录 → 建模型 → 新增需求/测试/缺陷/任务各 1 → GET 列表各含 1 条 → PUT 改需求名 → DELETE 删除
- owner 隔离：第二个账号访问该模型 → 404
- 持久化：重启后端后再 GET → 数据仍在
- AI 生成：`requirement/ai/generate` 传 text → 返回生成条目

- [ ] **Step 2: 前端构建 + 浏览器**

`vue-tsc` + `vite build` 通过；8080 刷新后研发管理 tab 四个页签可用。

- [ ] **Step 3: 清理测试数据 + 报告**

清理测试账号/模型；把结果写回本次实现计划摘要。

---

## Self-Review

- **Spec 覆盖**：owner 隔离 → Task 1-4（每类路由）；持久化 → Task 1-4（`_load_dev_entries`/`_save_dev_entries`）；前端 tab + 4 子页 → Task 5；AI 生成（需求/测试/任务）→ Task 6；缺陷无 AI（设计如此）。验收项 → Task 7。全部覆盖。
- **占位符**：无 TBD/TODO；关键代码已给出。
- **类型一致性**：`_load_dev_entries(kind, project_id)` / `_save_dev_entries(kind, project_id, entries)` 在 Task 1 定义、Task 2-4 复用；前端 `DEV_FIELDS`/`devApi`/`loadDevList`/`openDevModal`/`saveDev`/`removeDev`/`openDevAi`/`generateDevAi` 在 Task 5-6 定义一致。
- **说明**：现有路由用内存缓存（`requirements_cache` 等），Task 1-4 统一替换为 db 持久化；实体重建用 `Requirement(project_id, ...)` 等构造（存 dict，读时重建）。若现有类有 `from_dict` 则优先用。
