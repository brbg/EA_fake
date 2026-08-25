# 画布高清自适应 + Word 风格 Ribbon 设计

日期：2026-08-25
状态：已获用户批准（brainstorming 完成）

## 背景

三套建模画布（UML / ArchiMate / ER）当前存在两个体验硬伤：

1. **高分屏模糊**：画布元素是固定 `width="1150" height="600"`，未做 `devicePixelRatio` 缩放，高分屏下文字与图形发虚。
2. **不随窗口自适应**：画布固定尺寸，窗口缩放时不会跟着变宽，体验不"专业"。

同时，用户希望把工具栏改成 **Word 风格的 Ribbon 功能区**，让整体界面更专业。

## 目标

- 三套画布在高分屏（HiDPI）下清晰渲染。
- 画布宽度随容器自适应，高度按比例保持。
- 引入 Word 风格的 Ribbon 功能区（分组工具栏），按当前画布显示上下文工具。
- 保持 1150×600 逻辑坐标系不变，元素数据零迁移。

## 非目标

- 不做交互式缩放平移（滚轮缩放 / 拖拽平移）——用户已确认本轮不包含。
- 不做纸张页面画布隐喻——用户确认画布保持无边网格。
- 不重构画布为独立组件/第三方库（tldraw/fabric）——那是后续方向，本轮不做。
- 不改后端。

## Part A — 画布高清 + 自适应

### 方案（方案 A：逻辑坐标不变 + DPR 物理缩放）

保持逻辑坐标系 1150×600，元素坐标、网格、命中检测都在该空间运算；渲染时按当前容器 CSS 尺寸与 devicePixelRatio 换算物理像素。

**核心工具**（新增 `src/canvasUtils.ts`）：

```ts
// 返回画布在逻辑空间里需要的转换参数
export function setupCanvasTransform(canvas: HTMLCanvasElement, logicalW: number, logicalH: number) {
  const rect = canvas.getBoundingClientRect()          // CSS 像素尺寸
  const dpr = window.devicePixelRatio || 1
  canvas.width = Math.round(rect.width * dpr)
  canvas.height = Math.round(rect.height * dpr)
  const ctx = canvas.getContext('2d')!
  const sx = logicalW / rect.width                     // 逻辑→CSS 缩放
  const sy = logicalH / rect.height
  ctx.setTransform(dpr / sx, 0, 0, dpr / sy, 0, 0)     // 一次搞定 DPR + 自适应（dpr/sx = 设备像素/逻辑单位）
  return { sx, sy, dpr }
}

// CSS 像素坐标 → 逻辑坐标
export function toLogical(e: { clientX: number; clientY: number },
                          canvas: HTMLCanvasElement,
                          logicalW: number, logicalH: number) {
  const rect = canvas.getBoundingClientRect()
  return {
    x: (e.clientX - rect.left) * (logicalW / rect.width),
    y: (e.clientY - rect.top) * (logicalH / rect.height),
  }
}
```

**应用点（三套画布统一处理）**：

1. **初始化**：`initCanvas` / `initArchimateCanvas` / `initErCanvas` 改为调用 `setupCanvasTransform` 后再画网格/重绘。
2. **窗口 resize**：新增统一 `window.addEventListener('resize', resizeAllCanvases)`，对三个 canvas 重新 `setupCanvasTransform` + 对应重绘函数（`redraw` / `redrawArchimateCanvas` / `redrawErCanvas`）。用防抖（~150ms）避免频繁重绘。
3. **鼠标坐标**：`handleMouseDown` / `handleMouseMove` / `handleMouseUp` / `handleCanvasClick` / `handleDoubleClick` / 三个 `handle*ContextMenu` 中，把 `e.clientX - rect.left` 改为 `toLogical(e, canvas, 1150, 600)`。ArchiMate 与 ER 同理（逻辑尺寸同为 1150×600）。
4. **网格与钳制**：
   - `drawGrid` 改用逻辑尺寸（1150/600）而非 `canvas.width/height`（物理值）。
   - 拖拽钳制 `Math.min(canvas.width - ...)` 改为逻辑宽度常量。
   - 其他所有读取 `canvas.width / canvas.height` 作为坐标上限的地方，改为逻辑尺寸。
5. **CSS**：三个 canvas 元素加 `width:100%; height:auto;`（配合 `aspect-ratio: 1150/600` 或由 setup 计算高度）。逻辑上保持 1150×600 不变。

### 风险与对策

- **坐标换算遗漏**：三套画布所有鼠标处理函数都要过 `toLogical`。对策：逐一 grep `clientX`/`clientY`/`getBoundingClientRect` 全部替换，并在验收时逐项手测拖拽/连线/双击/右键。
- **文字缩放**：逻辑字号随容器等比缩放。小窗口时文字会变小但保持清晰（DPR≥1），可接受；后续可加最小字号。
- **resize 触发时机**：tab 切换时 canvas 被 v-if 重建，需在 init 时重新 setup（现有 init 已覆盖）。

## Part B — Ribbon 功能区

### 结构

在 `.nav-tabs` 下方、画布内容区上方，新增 `<div class="ribbon">`，按 `activeTab` 显示对应分组。`stats-row` 保留在 header 下方、nav-tabs 上方（不动）。

### 分组定义

| 画布 | 组 | 按钮 |
|---|---|---|
| **UML** | `建模工具` | 选择/类/接口/关联/继承/实现/依赖/组合/聚合（现有 `tools`，互斥高亮） |
| | `编辑` | 撤销 / 重做 / 保存 / 清空 |
| | `AI` | AI 下拉（校验整个模型 / 分析选中元素 / 对话式编辑） |
| | `导出` | 导出图片 |
| **ArchiMate** | `建模工具` | 选择/角色/流程/服务/组件/节点/制品 + 关联/实现/服务（现有 `archimateTools`） |
| | `层次` | 业务层 / 应用层 / 技术层（radio，复用 `archimateLayer`） |
| | `编辑` | 撤销 / 重做 / 保存 / 清空 |
| | `AI` | AI 下拉（架构评审 / 分析选中元素 / 对话式编辑） |
| | `导出` | 导出图片 |
| **ER** | `建模工具` | 选择/实体/1:1/1:N/M:N（现有 `erTools`） |
| | `编辑` | 撤销 / 重做 / 生成SQL / 保存 / 清空 |
| | `AI` | AI 下拉（分析选中表 / 对话式编辑） |
| | `导出` | 导出图片 |

### 实现

- 模板：在 `.nav-tabs` 之后加 `.ribbon`，内含 `v-if="activeTab==='uml'"` / `'archimate'` / `'data'` 三块，每块把对应画布卡内现有的工具栏按钮搬进来，用 `.ribbon-group` 包裹。
- 移除三个画布卡内的 `<div class="canvas-toolbar">`（按钮已上移），画布卡只留 `<canvas>` + 底部操作提示。
- `openAiMenu` 下拉遮罩逻辑不变，下拉随 Ribbon 的 AI 组展示。
- 样式：浅色背景（`#f7f8fa`）、每组有竖线分隔、组标题小字（11px 灰色）、按钮图标+文字、激活态品牌色。复用现有 `.toolbar-btn` 并微调。

### 数据流 / 交互

- Ribbon 按钮直接调用现有函数（`selectedTool` / `selectedArchimateTool` / `selectedErTool` / `undoUml` / `saveModel` / `aiValidateModel` / `runAiAction` 等），不改逻辑。
- 工具互斥高亮沿用现有 `:class="{ active: ... }"`。

## 错误处理

- 画布 getContext 失败（极罕见）：维持现状，init 里已有 null 保护。
- resize 时 canvas 尚未挂载（tab 切换竞态）：`setupCanvasTransform` 内对 rect.width=0 做防御，跳过本次。
- 全部为前端改动，无网络/持久化错误路径。

## 测试 / 验收

1. **构建**：`vue-tsc --noEmit` + `vite build` 通过。
2. **高清**：在 devicePixelRatio>1 的屏幕上（Windows 缩放 150% 以上）确认画布文字/线条清晰。
3. **自适应**：拖拽窗口宽度变化，三画布随容器变宽、内容等比缩放，元素仍在画布内。
4. **坐标正确**：缩放后拖拽元素、创建连接、双击编辑、右键删除，命中与位置准确（重点验证 1150 逻辑宽与实际 CSS 宽的换算）。
5. **Ribbon**：三个画布 tab 各自显示对应分组；AI 下拉可展开并触发功能；工具互斥高亮正常。
6. **回归**：保存/加载、撤销/重做、AI 校验/评审/分析/编辑在改造后仍工作。

## 改动文件

- 新增：`EA_fake/ea-webapp/src/canvasUtils.ts`
- 修改：`EA_fake/ea-webapp/src/App.vue`（模板 + script + style）
- 文档：本 spec
