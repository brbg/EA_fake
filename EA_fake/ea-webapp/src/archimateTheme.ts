/**
 * ArchiMate 视觉主题与纯绘制助手。
 *
 * 为什么单独成文件：这些是**纯函数**（不碰 Vue 状态、不依赖组件实例），
 * 所以可以在浏览器里直接对它们做断言，不必渲染整页。App.vue 只负责调用。
 *
 * 三类内容：
 *   ① 主题常量（层带、配色、元素形状映射、关系样式表）
 *   ② 几何助手（矩形边界求交）
 *   ③ 绘制函数（层带 / 元素 / 连接）
 *
 * 改动注意：关系样式表 REL_STYLE 是「9 种关系各自的箭头与线型」的唯一出处，
 * 前端调色板与图例都应从它派生，不要再各写一份。
 */

// ---------------------------------------------------------------- 主题常量

/** 三层背景带的 y 范围（逻辑坐标，画布逻辑高 600，正好三等分）。
 *  必须与后端 constants.ARCHIMATE_LAYER_BANDS 一致——后端布局器按它放元素。 */
export const LAYER_BANDS: Record<string, [number, number]> = {
  business: [0, 200],
  application: [200, 400],
  technology: [400, 600],
}

export const LAYER_HEAD: Record<string, string> = {
  business: '#3498db', application: '#2ecc71', technology: '#e67e22',
}
export const LAYER_BODY: Record<string, string> = {
  business: '#ecf0f1', application: '#e8f8f5', technology: '#fef5e7',
}
export const LAYER_LABEL: Record<string, string> = {
  business: '业务层  Business',
  application: '应用层  Application',
  technology: '技术层  Technology',
}

/** 元素类型 → 形状。一个形状可被多个类型复用（technology_service 用 service 的胶囊）。 */
export const ELEMENT_SHAPE: Record<string, string> = {
  actor: 'actor',
  process: 'process',
  service: 'service',
  technology_service: 'service',
  component: 'component',
  node: 'node',
  device: 'device',
  system_software: 'software',
  communication_network: 'network',
  artifact: 'artifact',
}

export type MarkerKind =
  | 'none' | 'hollow-triangle' | 'solid-triangle' | 'open-arrow'
  | 'solid-diamond' | 'hollow-diamond' | 'filled-circle'

export interface RelStyle {
  /** 线型（setLineDash 参数）；空数组=实线 */
  dash: number[]
  /** 箭头形态 */
  marker: MarkerKind
  /** 箭头画在哪一端：源端（组合/聚合的菱形）还是目标端 */
  end: 'source' | 'target'
}

/** 9 种关系的视觉规范（对齐 ArchiMate 惯用画法）。 */
export const REL_STYLE: Record<string, RelStyle> = {
  association: { dash: [], marker: 'none', end: 'target' },
  realization: { dash: [6, 4], marker: 'hollow-triangle', end: 'target' },
  serving: { dash: [], marker: 'open-arrow', end: 'target' },
  assignment: { dash: [], marker: 'filled-circle', end: 'target' },
  composition: { dash: [], marker: 'solid-diamond', end: 'source' },
  aggregation: { dash: [], marker: 'hollow-diamond', end: 'source' },
  access: { dash: [6, 4], marker: 'open-arrow', end: 'target' },
  flow: { dash: [6, 4], marker: 'solid-triangle', end: 'target' },
  triggering: { dash: [], marker: 'solid-triangle', end: 'target' },
}

/** 未知关系类型的回落样式。**必须显式存在**：以前 drawArchimateConnection 的
 *  if/else 没有 else，未知类型会沿用上一根线的 dash 状态（状态泄漏）。 */
export const DEFAULT_REL_STYLE: RelStyle = { dash: [], marker: 'none', end: 'target' }

export const REL_LABEL: Record<string, string> = {
  association: '关联', realization: '实现', serving: '服务', assignment: '部署',
  composition: '组合', aggregation: '聚合', access: '访问', flow: '流向', triggering: '触发',
}

export const relStyleOf = (type: string): RelStyle => REL_STYLE[type] || DEFAULT_REL_STYLE

// ---------------------------------------------------------------- 几何

export interface Rect { x: number; y: number; width: number; height: number }

/**
 * 求「元素中心 → 目标点」这条射线与元素矩形边界的交点。
 *
 * 用途：连线画在**元素边界之间**而不是中心之间。此前连线画到元素中心、
 * 而箭头画在中心点，元素后画就把箭头盖住了——看起来像「没有箭头」。
 */
export function rectEdgePoint(elem: Rect, towardX: number, towardY: number): { x: number; y: number } {
  const cx = elem.x + elem.width / 2
  const cy = elem.y + elem.height / 2
  const dx = towardX - cx
  const dy = towardY - cy
  if (dx === 0 && dy === 0) return { x: cx, y: cy }
  const hw = elem.width / 2
  const hh = elem.height / 2
  const scale = Math.min(
    dx !== 0 ? hw / Math.abs(dx) : Infinity,
    dy !== 0 ? hh / Math.abs(dy) : Infinity,
  )
  return { x: cx + dx * scale, y: cy + dy * scale }
}

// ---------------------------------------------------------------- 绘制：基础

function roundRectPath(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  const rr = Math.max(0, Math.min(r, Math.min(w, h) / 2))
  ctx.beginPath()
  ctx.moveTo(x + rr, y)
  ctx.lineTo(x + w - rr, y)
  ctx.quadraticCurveTo(x + w, y, x + w, y + rr)
  ctx.lineTo(x + w, y + h - rr)
  ctx.quadraticCurveTo(x + w, y + h, x + w - rr, y + h)
  ctx.lineTo(x + rr, y + h)
  ctx.quadraticCurveTo(x, y + h, x, y + h - rr)
  ctx.lineTo(x, y + rr)
  ctx.quadraticCurveTo(x, y, x + rr, y)
  ctx.closePath()
}

/** 把名称按宽度折行（最多两行，超出加省略号）。 */
function wrapName(ctx: CanvasRenderingContext2D, name: string, maxW: number, maxLines = 2): string[] {
  const text = String(name || '')
  if (ctx.measureText(text).width <= maxW) return [text]
  const lines: string[] = []
  let cur = ''
  for (const ch of text) {
    if (ctx.measureText(cur + ch).width > maxW && cur) {
      lines.push(cur)
      cur = ch
      if (lines.length === maxLines - 1) break
    } else {
      cur += ch
    }
  }
  if (cur) lines.push(cur)
  if (lines.length === maxLines) {
    const rest = text.slice(lines.join('').length)
    if (rest && ctx.measureText(lines[maxLines - 1]).width > maxW - 12) {
      lines[maxLines - 1] = lines[maxLines - 1].slice(0, -1) + '…'
    }
  }
  return lines.slice(0, maxLines)
}

const STROKE = '#2c3e50'

// ---------------------------------------------------------------- 绘制：层带

/**
 * 三层背景带。**必须在画连线与元素之前调用**（否则会盖住它们）。
 * 纯绘制，不参与命中测试。
 */
export function drawLayerBands(ctx: CanvasRenderingContext2D, logicalW: number) {
  ctx.save()
  for (const layer of Object.keys(LAYER_BANDS)) {
    const [top, bottom] = LAYER_BANDS[layer]
    ctx.globalAlpha = 0.10
    ctx.fillStyle = LAYER_HEAD[layer]
    ctx.fillRect(0, top, logicalW, bottom - top)
    ctx.globalAlpha = 1

    // 带标签
    ctx.fillStyle = LAYER_HEAD[layer]
    ctx.font = 'bold 12px Arial'
    ctx.textAlign = 'left'
    ctx.textBaseline = 'top'
    ctx.fillText(LAYER_LABEL[layer] || layer, 8, top + 6)

    // 带间分隔线
    if (top > 0) {
      ctx.strokeStyle = 'rgba(44,62,80,.18)'
      ctx.lineWidth = 1
      ctx.beginPath()
      ctx.moveTo(0, top)
      ctx.lineTo(logicalW, top)
      ctx.stroke()
    }
  }
  ctx.restore()
}

// ---------------------------------------------------------------- 绘制：元素

/** 画一个 ArchiMate 元素（按类型分派形状）。所有形状都画在 elem 的存储尺寸内。 */
export function drawArchimateElement(ctx: CanvasRenderingContext2D, elem: any) {
  const { x, y, width: w, height: h } = elem
  const head = elem.headerColor || LAYER_HEAD[elem.layer] || '#95a5a6'
  const body = elem.color || LAYER_BODY[elem.layer] || '#ecf0f1'
  const shape = ELEMENT_SHAPE[elem.type] || 'process'
  const cx = x + w / 2

  ctx.save()
  ctx.lineWidth = 2
  ctx.strokeStyle = STROKE
  ctx.fillStyle = body

  switch (shape) {
    case 'actor': {
      // 火柴人：头 + 身 + 臂 + 腿，整体在框内居中，名称在下方
      const top = y + 6
      const headR = 7
      const hx = cx
      const hy = top + headR
      ctx.beginPath(); ctx.arc(hx, hy, headR, 0, Math.PI * 2); ctx.fill(); ctx.stroke()
      const neckY = hy + headR
      const hipY = neckY + 20
      ctx.beginPath()
      ctx.moveTo(hx, neckY); ctx.lineTo(hx, hipY)
      ctx.moveTo(hx - 11, neckY + 7); ctx.lineTo(hx + 11, neckY + 7)
      ctx.moveTo(hx, hipY); ctx.lineTo(hx - 9, hipY + 12)
      ctx.moveTo(hx, hipY); ctx.lineTo(hx + 9, hipY + 12)
      ctx.stroke()
      ctx.fillStyle = STROKE
      ctx.font = '12px Arial'
      ctx.textAlign = 'center'
      ctx.textBaseline = 'alphabetic'
      ctx.fillText(wrapName(ctx, elem.name, w - 8, 1)[0], cx, y + h - 4)
      break
    }

    case 'service': {
      // 胶囊：轮廓本身即区分
      roundRectPath(ctx, x, y, w, h, h / 2)
      ctx.fill(); ctx.stroke()
      drawHeaderLabel(ctx, elem, head, cx, y, 'pill')
      break
    }

    case 'component': {
      // 矩形 + 左侧两个凸块（规范 component 符号）
      const bw = 10, bh = h * 0.22
      ctx.fillRect(x, y, w, h)
      ctx.strokeRect(x, y, w, h)
      ctx.beginPath()
      ctx.rect(x - bw / 2, y + h * 0.18, bw, bh)
      ctx.rect(x - bw / 2, y + h * 0.60, bw, bh)
      ctx.fillStyle = body; ctx.fill(); ctx.stroke()
      drawHeaderLabel(ctx, elem, head, cx, y, 'bar')
      break
    }

    case 'node':
    case 'device': {
      // 3D 盒：正面 + 顶面 + 右侧面
      const d = Math.min(12, h * 0.22)
      ctx.fillStyle = body
      ctx.fillRect(x, y + d, w - d, h - d)
      ctx.strokeRect(x, y + d, w - d, h - d)
      // 顶面
      ctx.beginPath()
      ctx.moveTo(x, y + d); ctx.lineTo(x + d, y); ctx.lineTo(x + w, y); ctx.lineTo(x + w - d, y + d)
      ctx.closePath(); ctx.fill(); ctx.stroke()
      // 右侧面
      ctx.beginPath()
      ctx.moveTo(x + w - d, y + d); ctx.lineTo(x + w, y); ctx.lineTo(x + w, y + h - d); ctx.lineTo(x + w - d, y + h)
      ctx.closePath()
      ctx.fillStyle = head; ctx.globalAlpha = 0.45; ctx.fill(); ctx.globalAlpha = 1; ctx.stroke()
      if (shape === 'device') {
        // 机架插槽：3 条水平细线
        ctx.strokeStyle = 'rgba(44,62,80,.45)'
        ctx.lineWidth = 1
        for (let i = 1; i <= 3; i++) {
          const ly = y + d + (h - d) * (i / 4)
          ctx.beginPath(); ctx.moveTo(x + 6, ly); ctx.lineTo(x + w - d - 6, ly); ctx.stroke()
        }
        ctx.strokeStyle = STROKE; ctx.lineWidth = 2
      }
      drawHeaderLabel(ctx, elem, head, x + (w - d) / 2, y + d, 'text')
      break
    }

    case 'software': {
      // 矩形 + 顶部窄带（两个小方块）
      ctx.fillRect(x, y, w, h)
      ctx.strokeRect(x, y, w, h)
      ctx.fillStyle = head; ctx.globalAlpha = 0.35
      ctx.fillRect(x, y, w, 14)
      ctx.globalAlpha = 1
      ctx.strokeStyle = 'rgba(44,62,80,.45)'; ctx.lineWidth = 1
      ctx.strokeRect(x, y, w, 14)
      ctx.fillStyle = head
      ctx.fillRect(x + 5, y + 4, 6, 6)
      ctx.fillRect(x + 15, y + 4, 6, 6)
      ctx.strokeStyle = STROKE; ctx.lineWidth = 2
      drawHeaderLabel(ctx, elem, head, cx, y + 14, 'text')
      break
    }

    case 'network': {
      // 圆角矩形 + 内部交叉对角线（网络/网关符号）
      roundRectPath(ctx, x, y, w, h, 8)
      ctx.fill(); ctx.stroke()
      ctx.strokeStyle = 'rgba(44,62,80,.40)'
      ctx.lineWidth = 1
      ctx.beginPath()
      ctx.moveTo(x + 10, y + h - 10); ctx.lineTo(x + w - 10, y + 10)
      ctx.moveTo(x + 10, y + 10); ctx.lineTo(x + w - 10, y + h - 10)
      ctx.stroke()
      ctx.strokeStyle = STROKE; ctx.lineWidth = 2
      drawHeaderLabel(ctx, elem, head, cx, y, 'pill')
      break
    }

    case 'artifact': {
      // 矩形 + 右上折角（规范 artifact）
      const f = Math.min(16, w * 0.18, h * 0.35)
      ctx.beginPath()
      ctx.moveTo(x, y)
      ctx.lineTo(x + w - f, y)
      ctx.lineTo(x + w, y + f)
      ctx.lineTo(x + w, y + h)
      ctx.lineTo(x, y + h)
      ctx.closePath()
      ctx.fill(); ctx.stroke()
      ctx.beginPath()
      ctx.moveTo(x + w - f, y); ctx.lineTo(x + w - f, y + f); ctx.lineTo(x + w, y + f)
      ctx.stroke()
      drawHeaderLabel(ctx, elem, head, cx - f / 2, y, 'bar')
      break
    }

    default: {
      // process：圆角矩形 + 左上小实心三角（流程标记）
      roundRectPath(ctx, x, y, w, h, 12)
      ctx.fill(); ctx.stroke()
      ctx.beginPath()
      ctx.moveTo(x + 8, y + h - 16)
      ctx.lineTo(x + 20, y + h - 11)
      ctx.lineTo(x + 8, y + h - 6)
      ctx.closePath()
      ctx.fillStyle = 'rgba(44,62,80,.55)'
      ctx.fill()
      drawHeaderLabel(ctx, elem, head, cx, y, 'bar')
      break
    }
  }
  ctx.restore()
}

/** 元素顶部的类型标签。`pill` 用于胶囊/圆角形（标签内缩），`bar` 用于有头部条的，`text` 用于直接写。 */
function drawHeaderLabel(ctx: CanvasRenderingContext2D, elem: any, head: string,
                         cx: number, topY: number, mode: 'pill' | 'bar' | 'text') {
  const type = String(elem.type || '').toUpperCase()
  const inset = mode === 'pill' ? 26 : mode === 'bar' ? 0 : 0
  if (mode === 'bar') {
    // 头部色条
    ctx.save()
    ctx.fillStyle = head
    ctx.globalAlpha = 0.85
    ctx.fillRect(elem.x, elem.y, elem.width, 18)
    ctx.restore()
  }
  ctx.save()
  ctx.fillStyle = mode === 'text' ? STROKE : '#ffffff'
  ctx.font = 'bold 10px Arial'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.fillText(type, cx + inset / 2 - (inset ? inset / 2 : 0), topY + 9)
  ctx.restore()

  // 名称（居中偏下）
  ctx.save()
  ctx.fillStyle = STROKE
  ctx.font = '12px Arial'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  const maxW = elem.width - 12
  const lines = wrapName(ctx, elem.name, maxW, 2)
  const startY = elem.y + elem.height / 2 + (mode === 'text' ? 8 : 6)
  lines.forEach((ln, i) => ctx.fillText(ln, cx, startY + i * 14))
  ctx.restore()
}

// ---------------------------------------------------------------- 绘制：连接

/**
 * 画一条 ArchiMate 连接：线 + 箭头 + 标签。
 *
 * 三个必须做对的地方（都是此前实测的缺陷）：
 *   ① 入口 `setLineDash([])` + 显式 default 样式 → 修掉「未知类型沿用上一根线
 *      的 dash 状态」这个状态泄漏
 *   ② 线画在**元素边界**之间（rectEdgePoint），箭头才不会落在元素中心被盖住
 *   ③ 箭头按 REL_STYLE 分派，组合/聚合的菱形画在**源端**
 */
export function drawArchimateConnection(
  ctx: CanvasRenderingContext2D,
  startElem: Rect, endElem: Rect, conn: any, scale = 1,
) {
  const style = relStyleOf(String(conn?.type || ''))
  const scx = startElem.x + startElem.width / 2
  const scy = startElem.y + startElem.height / 2
  const ecx = endElem.x + endElem.width / 2
  const ecy = endElem.y + endElem.height / 2

  const p1 = rectEdgePoint(startElem, ecx, ecy)
  const p2 = rectEdgePoint(endElem, scx, scy)

  ctx.save()
  // ① 显式重置线型，不依赖调用方或上一条线的状态
  ctx.setLineDash(style.dash)
  ctx.strokeStyle = '#7f8c8d'
  ctx.lineWidth = 2
  ctx.beginPath()
  ctx.moveTo(p1.x, p1.y)
  ctx.lineTo(p2.x, p2.y)
  ctx.stroke()
  ctx.setLineDash([])

  // ② 箭头画在边界点上，指向它所属的元素
  if (style.marker !== 'none') {
    if (style.end === 'target') {
      drawMarker(ctx, style.marker, p2.x, p2.y, Math.atan2(p2.y - p1.y, p2.x - p1.x))
    } else {
      drawMarker(ctx, style.marker, p1.x, p1.y, Math.atan2(p1.y - p2.y, p1.x - p2.x))
    }
  }

  // ③ 关系标签（线段中点）。太短或缩得太小就不画，免得糊成一团
  const label = conn?.name || REL_LABEL[String(conn?.type || '')] || ''
  const len = Math.hypot(p2.x - p1.x, p2.y - p1.y)
  if (label && len > 56 && scale >= 0.6) {
    const mx = (p1.x + p2.x) / 2
    const my = (p1.y + p2.y) / 2
    ctx.font = '10px Arial'
    const tw = ctx.measureText(label).width
    ctx.fillStyle = 'rgba(255,255,255,.88)'
    ctx.fillRect(mx - tw / 2 - 3, my - 8, tw + 6, 14)
    ctx.fillStyle = '#5b6b7c'
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillText(label, mx, my - 1)
  }
  ctx.restore()
}

/** 箭头。tip 是箭尖坐标，angle 是箭头指向（朝向所属元素）。 */
export function drawMarker(ctx: CanvasRenderingContext2D, kind: MarkerKind,
                           tipX: number, tipY: number, angle: number) {
  const L = 12          // 长度
  const W = 6           // 半宽
  const cos = Math.cos(angle), sin = Math.sin(angle)
  // 把「沿箭头方向的局部坐标」映射到画布：u 向前（朝 tip），v 向右
  const P = (u: number, v: number) => ({
    x: tipX - u * cos + v * sin,
    y: tipY - u * sin - v * cos,
  })
  ctx.save()
  ctx.setLineDash([])
  ctx.strokeStyle = '#7f8c8d'
  ctx.fillStyle = '#7f8c8d'
  ctx.lineWidth = 2

  switch (kind) {
    case 'solid-triangle': {
      const a = P(0, 0), b = P(L, W), c = P(L, -W)
      ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.lineTo(c.x, c.y)
      ctx.closePath(); ctx.fill()
      break
    }
    case 'hollow-triangle': {
      const a = P(0, 0), b = P(L, W), c = P(L, -W)
      ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.lineTo(c.x, c.y)
      ctx.closePath()
      ctx.fillStyle = '#ffffff'; ctx.fill(); ctx.stroke()
      break
    }
    case 'open-arrow': {
      const b = P(L, W), c = P(L, -W)
      ctx.beginPath(); ctx.moveTo(b.x, b.y); ctx.lineTo(tipX, tipY); ctx.lineTo(c.x, c.y)
      ctx.stroke()
      break
    }
    case 'solid-diamond': {
      const a = P(0, 0), b = P(L / 2, W), c = P(L, 0), d = P(L / 2, -W)
      ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.lineTo(c.x, c.y); ctx.lineTo(d.x, d.y)
      ctx.closePath(); ctx.fill()
      break
    }
    case 'hollow-diamond': {
      const a = P(0, 0), b = P(L / 2, W), c = P(L, 0), d = P(L / 2, -W)
      ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.lineTo(c.x, c.y); ctx.lineTo(d.x, d.y)
      ctx.closePath()
      ctx.fillStyle = '#ffffff'; ctx.fill(); ctx.stroke()
      break
    }
    case 'filled-circle': {
      ctx.beginPath(); ctx.arc(tipX, tipY, 4.5, 0, Math.PI * 2); ctx.fill()
      break
    }
    default:
      break
  }
  ctx.restore()
}
