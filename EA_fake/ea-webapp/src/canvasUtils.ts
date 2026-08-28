// Canvas 高清 + 自适应工具：逻辑坐标恒为 1150×600，物理像素按 DPR 与容器尺寸换算
export const LOGICAL_W = 1150
export const LOGICAL_H = 600

export interface CanvasView { x: number; y: number; scale: number }
export const DEFAULT_VIEW: CanvasView = { x: 0, y: 0, scale: 1 }

// 每个画布独立的视图（平移/缩放），用 WeakMap 关联，toLogical/setupCanvasTransform 自动读取
const canvasViews = new WeakMap<HTMLCanvasElement, CanvasView>()

export function setCanvasView(canvas: HTMLCanvasElement, view: CanvasView): void {
  canvasViews.set(canvas, view)
}

function getView(canvas: HTMLCanvasElement): CanvasView {
  return canvasViews.get(canvas) || DEFAULT_VIEW
}

/**
 * 按容器 CSS 尺寸 × devicePixelRatio 设置画布物理尺寸，并设置变换（含视图平移/缩放），
 * 使所有绘制都发生在 1150×600 逻辑空间内、随视图移动缩放。
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
  const view = getView(canvas)
  const sx = logicalW / rect.width
  const sy = logicalH / rect.height
  const kx = (dpr / sx) * view.scale
  const ky = (dpr / sy) * view.scale
  ctx.setTransform(kx, 0, 0, ky, -view.x * kx, -view.y * ky)
  return { sx, sy, dpr, ctx }
}

/**
 * 把事件坐标（CSS 像素）换算为逻辑坐标（1150×600 空间，含视图平移/缩放）。
 */
export function toLogical(
  e: { clientX: number; clientY: number },
  canvas: HTMLCanvasElement,
  logicalW = LOGICAL_W,
  logicalH = LOGICAL_H
): { x: number; y: number } {
  const rect = canvas.getBoundingClientRect()
  const view = getView(canvas)
  const px = (e.clientX - rect.left) * (logicalW / rect.width)
  const py = (e.clientY - rect.top) * (logicalH / rect.height)
  return { x: view.x + px / view.scale, y: view.y + py / view.scale }
}
