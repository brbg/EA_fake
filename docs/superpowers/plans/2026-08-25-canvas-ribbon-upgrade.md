# 画布高清自适应 + Ribbon 功能区 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 三套建模画布（UML/ArchiMate/ER）高分屏清晰渲染、随容器自适应，并把工具栏改造成 Word 风格 Ribbon 功能区。

**Architecture:** 逻辑坐标系保持 1150×600 不变，新增 `canvasUtils.ts` 统一处理 DPR 缩放与 CSS→逻辑坐标换算；所有画布鼠标事件经 `toLogical()` 转回逻辑空间。Ribbon 是 App.vue 里一个按 activeTab 条件渲染的功能区，把画布卡内旧工具栏按钮上移进来。

**Tech Stack:** Vue 3 + TypeScript + Vite，原生 Canvas 2D。

**Spec:** `docs/superpowers/specs/2026-08-25-canvas-ribbon-upgrade-design.md`

## Global Constraints

- 逻辑坐标系恒为 1150×600；元素坐标、网格、命中检测全部在该空间运算，不迁移数据。
- 不引入缩放平移、不做纸张页面隐喻、不换画布库、不改后端。
- 三套画布统一处理：UML 变量名 `canvas`/`ctx`/`elements`/`connections`，ArchiMate `archimateCanvas`/`archimateElements`/`archimateConnections`，ER `erCanvas`/`erEntities`/`erRelations`。
- 验证手段：`vue-tsc --noEmit` 与 `vite build`（项目无前端单测框架），加浏览器手工验收。

---

### Task 1: 画布变换工具模块 `canvasUtils.ts`

**Files:**
- Create: `EA_fake/ea-webapp/src/canvasUtils.ts`

**Interfaces:**
- Produces: `LOGICAL_W=1150`、`LOGICAL_H=600`、`setupCanvasTransform(canvas, logicalW?, logicalH?)`、`toLogical(e, canvas, logicalW?, logicalH?)`。后续所有画布任务都依赖这四个导出。

- [ ] **Step 1: 创建文件**

```ts
// Canvas 高清 + 自适应工具：逻辑坐标恒为 1150×600，物理像素按 DPR 与容器尺寸换算
export const LOGICAL_W = 1150
export const LOGICAL_H = 600

/**
 * 按容器 CSS 尺寸 × devicePixelRatio 设置画布物理尺寸，并设置变换，
 * 使所有绘制都发生在 1150×600 逻辑空间。
 * 返回 null 表示画布不可用（未挂载/宽度为 0），调用方应跳过本次。
 */
export function setupCanvasTransform(
  canvas: HTMLCanvasElement,
  logicalW = LOGICAL_W,
  logicalH = LOGICAL_H
): { sx: number; sy: number; dpr: number; ctx: CanvasRenderingContext2D } | null {
  const rect = canvas.getBoundingClientRect()
  if (rect.width <= 0 || rect.height <= 0) return null
  const dpr = window.devicePixelRatio || 1
  canvas.width = Math.round(rect.width * dpr)
  canvas.height = Math.round(rect.height * dpr)
  const ctx = canvas.getContext('2d')
  if (!ctx) return null
  const sx = logicalW / rect.width
  const sy = logicalH / rect.height
  ctx.setTransform(dpr * sx, 0, 0, dpr * sy, 0, 0)
  return { sx, sy, dpr, ctx }
}

/**
 * 把事件坐标（CSS 像素）换算为逻辑坐标（1150×600 空间）。
 */
export function toLogical(
  e: { clientX: number; clientY: number },
  canvas: HTMLCanvasElement,
  logicalW = LOGICAL_W,
  logicalH = LOGICAL_H
): { x: number; y: number } {
  const rect = canvas.getBoundingClientRect()
  return {
    x: (e.clientX - rect.left) * (logicalW / rect.width),
    y: (e.clientY - rect.top) * (logicalH / rect.height),
  }
}
```

- [ ] **Step 2: 验证编译**

Run: `cd EA_fake/ea-webapp && ./node_modules/.bin/vue-tsc --noEmit`
Expected: PASS（无类型错误）

- [ ] **Step 3: 提交**

```bash
git add EA_fake/ea-webapp/src/canvasUtils.ts
git commit -m "feat: 新增 canvasUtils（DPR 高清 + 逻辑坐标换算）"
```

---

### Task 2: UML 画布 DPR + 自适应

**Files:**
- Modify: `EA_fake/ea-webapp/src/App.vue`

**Interfaces:**
- Consumes: Task 1 的 `setupCanvasTransform` / `toLogical` / `LOGICAL_W` / `LOGICAL_H`。
- Produces: `resizeAllCanvases()`（三画布统一 resize，Task 3/4 复用）。

- [ ] **Step 1: 引入工具并改造 init / 网格 / 钳制**

在 App.vue script 顶部（现有 import 区）加：
```ts
import { setupCanvasTransform, toLogical, LOGICAL_W, LOGICAL_H } from './canvasUtils'
```

`initCanvas`（当前 1124 行附近）改为：
```ts
const initCanvas = () => {
  canvas = document.getElementById('canvas') as HTMLCanvasElement
  if (canvas) {
    setupCanvasTransform(canvas)
    ctx = canvas.getContext('2d')
    drawGrid()
    redraw()
  }
}
```

`drawGrid`（1140-1150）把 `canvas.width` → `LOGICAL_W`、`canvas.height` → `LOGICAL_H`。

`ctx.clearRect(0, 0, canvas.width, canvas.height)`（1508 附近）→ `ctx.clearRect(0, 0, LOGICAL_W, LOGICAL_H)`。

- [ ] **Step 2: 改造所有 UML 鼠标处理器坐标**

把每个 handler 里的
```ts
const rect = canvas.getBoundingClientRect()
const x = e.clientX - rect.left
const y = e.clientY - rect.top
```
替换为
```ts
const p = toLogical(e, canvas)
const x = p.x
const y = p.y
```
涉及函数与位置：
- `handleMouseDown`（1326-1331；同时其后的钳制 `Math.min(canvas.width - 120, x)` → `Math.min(LOGICAL_W - 120, x)`、`canvas.height - 100` → `LOGICAL_H - 100`）
- `handleMouseMove`（1393-1394）
- `handleMouseMove` 拖拽分支（1428-1434：`canvas.width - selectedElement.width` → `LOGICAL_W - ...`、`canvas.height - ...` → `LOGICAL_H - ...`）
- `handleMouseUp`（1441-1442）
- `handleCanvasClick`（1481-1482）
- `handleUmlContextMenu`（1562-1563）

- [ ] **Step 3: 加 resize 监听与统一函数**

在 script 末尾（`onMounted` 附近）加：
```ts
let canvasResizeTimer: number | null = null
const resizeAllCanvases = () => {
  if (canvasResizeTimer) window.clearTimeout(canvasResizeTimer)
  canvasResizeTimer = window.setTimeout(() => {
    const c1 = document.getElementById('canvas') as HTMLCanvasElement | null
    if (c1) { setupCanvasTransform(c1); redraw() }
    const c2 = archimateCanvas.value as HTMLCanvasElement | null
    if (c2) { setupCanvasTransform(c2); redrawArchimateCanvas() }
    const c3 = erCanvas.value as HTMLCanvasElement | null
    if (c3) { setupCanvasTransform(c3); redrawErCanvas() }
  }, 150)
}
window.addEventListener('resize', resizeAllCanvases)
```
`initArchimateCanvas` / `initErCanvas`（1626 / 2091 附近）开头加 `setupCanvasTransform(...)` 后再画网格/重绘（各画布用自己的 ref）。

- [ ] **Step 4: 画布 CSS 自适应**

在 `<style>` 里 `#canvas { display:block; cursor:crosshair; }` 附近追加：
```css
#canvas, #archimateCanvas, #erCanvas {
  width: 100%;
  height: auto;
  aspect-ratio: 1150 / 600;
}
```

- [ ] **Step 5: 验证编译**

Run: `cd EA_fake/ea-webapp && ./node_modules/.bin/vue-tsc --noEmit && ./node_modules/.bin/vite build`
Expected: PASS

- [ ] **Step 6: 浏览器验证**

Run 后端后打开 http://localhost:8080，UML 画布：高分屏文字清晰；拖拽窗口宽度画布随容器等比缩放；拖拽/连线/双击/右键坐标正确。

- [ ] **Step 7: 提交**

```bash
git add EA_fake/ea-webapp/src/App.vue
git commit -m "feat: UML 画布 DPR 高清 + 容器自适应"
```

---

### Task 3: ArchiMate 画布 DPR + 自适应

**Files:**
- Modify: `EA_fake/ea-webapp/src/App.vue`

**Interfaces:**
- Consumes: `setupCanvasTransform` / `toLogical` / `LOGICAL_W` / `LOGICAL_H`；Task 2 的 `resizeAllCanvases` 已覆盖 ArchiMate。

- [ ] **Step 1: init + 坐标改造**

`initArchimateCanvas`（1626 附近）在取到 `archimateCanvas.value` 后加 `setupCanvasTransform(c)`（c 为 canvas 元素）。

把以下 ArchiMate 处理器里的 `const rect = archimateCanvas.value.getBoundingClientRect()` + `const x = e.clientX - rect.left` / `y = ...` 替换为 `const p = toLogical(e, archimateCanvas.value); const x = p.x; const y = p.y`：
- `handleArchimateMouseDown`（1802-1803）
- `handleArchimateMouseMove`（1872-1873，含 1909-1910 的拖拽分支；拖拽钳制 1830 附近 `archimateCanvas.value.width` → `LOGICAL_W`、height → `LOGICAL_H`）
- `handleArchimateMouseUp`（1922-1923）
- `handleArchimateClick`（1955-1956）
- `handleArchimateContextMenu`（2028-2029）

- [ ] **Step 2: 验证编译**

Run: `cd EA_fake/ea-webapp && ./node_modules/.bin/vue-tsc --noEmit && ./node_modules/.bin/vite build`
Expected: PASS

- [ ] **Step 3: 浏览器验证**

ArchiMate 画布：清晰、自适应、拖拽/连线/双击/右键坐标正确。

- [ ] **Step 4: 提交**

```bash
git add EA_fake/ea-webapp/src/App.vue
git commit -m "feat: ArchiMate 画布 DPR 高清 + 容器自适应"
```

---

### Task 4: ER 画布 DPR + 自适应

**Files:**
- Modify: `EA_fake/ea-webapp/src/App.vue`

**Interfaces:**
- Consumes: `setupCanvasTransform` / `toLogical` / `LOGICAL_W` / `LOGICAL_H`；Task 2 的 `resizeAllCanvases` 已覆盖 ER。

- [ ] **Step 1: init + 坐标改造**

`initErCanvas`（2091 附近）取到 `erCanvas.value` 后加 `setupCanvasTransform(c)`。

替换以下 ER 处理器的坐标计算（`const rect = erCanvas.value.getBoundingClientRect()` + clientX/clientY）为 `const p = toLogical(e, erCanvas.value); const x = p.x; const y = p.y`：
- `handleErMouseDown`（2317-2318）
- `handleErMouseMove`（2366-2367；拖拽钳制 2323 附近 `erCanvas.value.width` → `LOGICAL_W`、height → `LOGICAL_H`）
- `handleErMouseUp`（2403-2404）
- `handleErClick`（2416 附近）
- `handleErContextMenu`（其余 clientX/clientY 出现处）

- [ ] **Step 2: 验证编译**

Run: `cd EA_fake/ea-webapp && ./node_modules/.bin/vue-tsc --noEmit && ./node_modules/.bin/vite build`
Expected: PASS

- [ ] **Step 3: 浏览器验证**

ER 画布：清晰、自适应、拖拽/连线/双击/右键坐标正确。

- [ ] **Step 4: 提交**

```bash
git add EA_fake/ea-webapp/src/App.vue
git commit -m "feat: ER 画布 DPR 高清 + 容器自适应"
```

---

### Task 5: Ribbon 骨架 + UML 组

**Files:**
- Modify: `EA_fake/ea-webapp/src/App.vue`

**Interfaces:**
- Produces: `.ribbon` 结构（Task 6 加 ArchiMate/ER 组，Task 7 加样式）。复用现有 `tools`、`selectedTool`、`undoUml` 等变量/函数。

- [ ] **Step 1: 在 `.nav-tabs` 之后插入 Ribbon 容器 + UML 组**

在模板 `.nav-tabs` 的 `</div>` 之后、`<div v-if="activeTab === 'dashboard'">` 之前插入：
```html
<div class="ribbon" v-if="activeTab === 'uml' || activeTab === 'archimate' || activeTab === 'data'">
  <template v-if="activeTab === 'uml'">
    <div class="ribbon-group">
      <div class="ribbon-group-label">建模工具</div>
      <button v-for="tool in tools" :key="tool.id"
        :class="['toolbar-btn', { active: selectedTool === tool.id }]"
        @click="selectedTool = tool.id" :title="tool.name">
        <i :class="tool.icon"></i> {{ tool.name }}
      </button>
    </div>
    <div class="ribbon-group">
      <div class="ribbon-group-label">编辑</div>
      <button class="toolbar-btn" @click="undoUml" title="撤销 (Ctrl+Z)"><i class="fas fa-undo"></i> 撤销</button>
      <button class="toolbar-btn" @click="redoUml" title="重做 (Ctrl+Y)"><i class="fas fa-redo"></i> 重做</button>
      <button class="toolbar-btn" @click="saveModel"><i class="fas fa-save"></i> 保存</button>
      <button class="toolbar-btn" @click="clearCanvas"><i class="fas fa-trash"></i> 清空</button>
    </div>
    <div class="ribbon-group">
      <div class="ribbon-group-label">AI</div>
      <div style="position:relative; display:inline-block;">
        <button class="toolbar-btn" @click="toggleAiMenu('uml')" :class="{ active: openAiMenu === 'uml' }" title="AI 功能">
          <i class="fas fa-robot"></i> AI <i class="fas fa-chevron-down" style="font-size:10px;"></i>
        </button>
        <div v-if="openAiMenu === 'uml'" class="ai-dropdown">
          <div class="ai-dropdown-title">UML 模型</div>
          <button class="ai-dropdown-item" @click="runAiAction('uml', 'validate')" :disabled="validating">
            <i class="fas fa-magnifying-glass-chart"></i> {{ validating ? '校验中...' : 'AI校验整个模型' }}
          </button>
          <button class="ai-dropdown-item" @click="runAiAction('uml', 'analyze')" :disabled="analyzing">
            <i class="fas fa-wand-magic-sparkles"></i> {{ analyzing ? '分析中...' : 'AI分析选中元素' }}
          </button>
          <button class="ai-dropdown-item" @click="runAiAction('uml', 'edit')">
            <i class="fas fa-comment-dots"></i> AI对话式编辑
          </button>
        </div>
      </div>
    </div>
    <div class="ribbon-group">
      <div class="ribbon-group-label">导出</div>
      <button class="toolbar-btn" @click="exportImage"><i class="fas fa-download"></i> 导出图片</button>
    </div>
  </template>
</div>
```

- [ ] **Step 2: 移除 UML 画布卡内的旧工具栏**

删除 UML canvas card 里的整个 `<div class="canvas-toolbar">...</div>`（即当前含 `tools` 循环 + AI 下拉 + 撤销/保存/导出/清空按钮的那段），画布卡只留 `<canvas>` + 底部提示。

- [ ] **Step 3: 验证编译**

Run: `cd EA_fake/ea-webapp && ./node_modules/.bin/vue-tsc --noEmit`
Expected: PASS（Ribbon 里引用的 `selectedTool`/`undoUml` 等均已存在）

- [ ] **Step 4: 提交**

```bash
git add EA_fake/ea-webapp/src/App.vue
git commit -m "feat: Ribbon 骨架 + UML 建模/编辑/AI/导出 组"
```

---

### Task 6: Ribbon ArchiMate + ER 组

**Files:**
- Modify: `EA_fake/ea-webapp/src/App.vue`

**Interfaces:**
- Consumes: Task 5 的 `.ribbon` 容器与 `.ribbon-group` 结构；现有 `archimateTools`、`archimateLayer`、`erTools` 等。

- [ ] **Step 1: 在 Task 5 的 UML `<template>` 后追加 ArchiMate 组**

在 `<template v-if="activeTab === 'uml'">...</template>` 之后追加：
```html
<template v-if="activeTab === 'archimate'">
  <div class="ribbon-group">
    <div class="ribbon-group-label">建模工具</div>
    <button v-for="tool in archimateTools" :key="tool.id"
      :class="['toolbar-btn', { active: selectedArchimateTool === tool.id }]"
      @click="selectedArchimateTool = tool.id" :title="tool.name">
      <i :class="tool.icon"></i> {{ tool.name }}
    </button>
  </div>
  <div class="ribbon-group">
    <div class="ribbon-group-label">层次</div>
    <label style="display:flex;align-items:center;cursor:pointer;gap:4px;">
      <input type="radio" v-model="archimateLayer" value="business" /> 业务层
    </label>
    <label style="display:flex;align-items:center;cursor:pointer;gap:4px;">
      <input type="radio" v-model="archimateLayer" value="application" /> 应用层
    </label>
    <label style="display:flex;align-items:center;cursor:pointer;gap:4px;">
      <input type="radio" v-model="archimateLayer" value="technology" /> 技术层
    </label>
  </div>
  <div class="ribbon-group">
    <div class="ribbon-group-label">编辑</div>
    <button class="toolbar-btn" @click="undoArchimate"><i class="fas fa-undo"></i> 撤销</button>
    <button class="toolbar-btn" @click="redoArchimate"><i class="fas fa-redo"></i> 重做</button>
    <button class="toolbar-btn" @click="saveArchimateModel"><i class="fas fa-save"></i> 保存</button>
    <button class="toolbar-btn" @click="clearArchimateCanvas"><i class="fas fa-trash"></i> 清空</button>
  </div>
  <div class="ribbon-group">
    <div class="ribbon-group-label">AI</div>
    <div style="position:relative; display:inline-block;">
      <button class="toolbar-btn" @click="toggleAiMenu('archimate')" :class="{ active: openAiMenu === 'archimate' }">
        <i class="fas fa-robot"></i> AI <i class="fas fa-chevron-down" style="font-size:10px;"></i>
      </button>
      <div v-if="openAiMenu === 'archimate'" class="ai-dropdown">
        <div class="ai-dropdown-title">ArchiMate 架构</div>
        <button class="ai-dropdown-item" @click="runAiAction('archimate', 'review')" :disabled="reviewing">
          <i class="fas fa-magnifying-glass-chart"></i> {{ reviewing ? '评审中...' : 'AI架构评审' }}
        </button>
        <button class="ai-dropdown-item" @click="runAiAction('archimate', 'analyze')" :disabled="analyzing">
          <i class="fas fa-wand-magic-sparkles"></i> {{ analyzing ? '分析中...' : 'AI分析选中元素' }}
        </button>
        <button class="ai-dropdown-item" @click="runAiAction('archimate', 'edit')">
          <i class="fas fa-comment-dots"></i> AI对话式编辑
        </button>
      </div>
    </div>
  </div>
  <div class="ribbon-group">
    <div class="ribbon-group-label">导出</div>
    <button class="toolbar-btn" @click="exportArchimateImage"><i class="fas fa-download"></i> 导出图片</button>
  </div>
</template>
```

- [ ] **Step 2: 追加 ER 组**

在 ArchiMate `<template>` 之后追加：
```html
<template v-if="activeTab === 'data'">
  <div class="ribbon-group">
    <div class="ribbon-group-label">建模工具</div>
    <button v-for="tool in erTools" :key="tool.id"
      :class="['toolbar-btn', { active: selectedErTool === tool.id }]"
      @click="selectedErTool = tool.id" :title="tool.name">
      <i :class="tool.icon"></i> {{ tool.name }}
    </button>
  </div>
  <div class="ribbon-group">
    <div class="ribbon-group-label">编辑</div>
    <button class="toolbar-btn" @click="undoEr"><i class="fas fa-undo"></i> 撤销</button>
    <button class="toolbar-btn" @click="redoEr"><i class="fas fa-redo"></i> 重做</button>
    <button class="toolbar-btn" @click="generateErSql"><i class="fas fa-database"></i> 生成SQL</button>
    <button class="toolbar-btn" @click="saveErModel"><i class="fas fa-save"></i> 保存</button>
    <button class="toolbar-btn" @click="clearErCanvas"><i class="fas fa-trash"></i> 清空</button>
  </div>
  <div class="ribbon-group">
    <div class="ribbon-group-label">AI</div>
    <div style="position:relative; display:inline-block;">
      <button class="toolbar-btn" @click="toggleAiMenu('er')" :class="{ active: openAiMenu === 'er' }">
        <i class="fas fa-robot"></i> AI <i class="fas fa-chevron-down" style="font-size:10px;"></i>
      </button>
      <div v-if="openAiMenu === 'er'" class="ai-dropdown">
        <div class="ai-dropdown-title">数据模型</div>
        <button class="ai-dropdown-item" @click="runAiAction('er', 'analyze')" :disabled="analyzing">
          <i class="fas fa-wand-magic-sparkles"></i> {{ analyzing ? '分析中...' : 'AI分析选中表' }}
        </button>
        <button class="ai-dropdown-item" @click="runAiAction('er', 'edit')">
          <i class="fas fa-comment-dots"></i> AI对话式编辑
        </button>
      </div>
    </div>
  </div>
  <div class="ribbon-group">
    <div class="ribbon-group-label">导出</div>
    <button class="toolbar-btn" @click="exportErImage"><i class="fas fa-download"></i> 导出图片</button>
  </div>
</template>
```

- [ ] **Step 3: 移除 ArchiMate 与 ER 画布卡内的旧工具栏**

删除 ArchiMate 与 ER canvas card 里的整个 `<div class="canvas-toolbar">...</div>`。

- [ ] **Step 4: 验证编译**

Run: `cd EA_fake/ea-webapp && ./node_modules/.bin/vue-tsc --noEmit && ./node_modules/.bin/vite build`
Expected: PASS

- [ ] **Step 5: 浏览器验证**

三个画布 tab 均显示 Ribbon 对应分组；工具互斥高亮正常；AI 下拉可展开触发。

- [ ] **Step 6: 提交**

```bash
git add EA_fake/ea-webapp/src/App.vue
git commit -m "feat: Ribbon ArchiMate/ER 分组，移除旧画布工具栏"
```

---

### Task 7: Ribbon 样式（Word 风格）

**Files:**
- Modify: `EA_fake/ea-webapp/src/App.vue`

**Interfaces:**
- Consumes: Task 5/6 的 `.ribbon` / `.ribbon-group` / `.ribbon-group-label` 结构。

- [ ] **Step 1: 追加 Ribbon CSS**

在 `<style>` 里 `.nav-tabs` 样式之后追加：
```css
.ribbon {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 12px;
  background: #f7f8fa;
  border: 1px solid #e8ecf0;
  border-radius: 8px;
  margin: 8px 0;
  flex-wrap: wrap;
  overflow-x: auto;
}
.ribbon-group {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
}
.ribbon-group + .ribbon-group {
  border-left: 1px solid #dfe3ea;
}
.ribbon-group-label {
  font-size: 11px;
  color: #94a3b8;
  margin-right: 2px;
  white-space: nowrap;
}
.ribbon .toolbar-btn {
  padding: 6px 10px;
  white-space: nowrap;
}
```

- [ ] **Step 2: 验证编译**

Run: `cd EA_fake/ea-webapp && ./node_modules/.bin/vue-tsc --noEmit && ./node_modules/.bin/vite build`
Expected: PASS

- [ ] **Step 3: 浏览器验证**

Ribbon 显示为浅色功能区，分组间有竖线分隔、组标题小字；整体观感接近 Word 功能区分栏。

- [ ] **Step 4: 提交**

```bash
git add EA_fake/ea-webapp/src/App.vue
git commit -m "style: Ribbon 功能区 Word 风格样式"
```

---

## Self-Review

- **Spec 覆盖**：Part A（DPR/自适应/坐标换算/resize）→ Task 1-4；Part B（Ribbon 结构/分组/样式/移除旧工具栏）→ Task 5-7。全部覆盖。
- **占位符**：无 TBD/TODO；每个 task 有具体代码与验证步骤。
- **类型一致性**：`setupCanvasTransform` / `toLogical` / `LOGICAL_W` / `LOGICAL_H` 在 Task 1 定义、Task 2-4 引用，签名一致；`resizeAllCanvases` 在 Task 2 定义、Task 3/4 复用。
