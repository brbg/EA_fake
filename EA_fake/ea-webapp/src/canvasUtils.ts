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
  ctx.setTransform(dpr / sx, 0, 0, dpr / sy, 0, 0)
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
