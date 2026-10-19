/**
 * useOverlayScrim —— 大图浏览页三块浮层（`.float-header` / `.float-footer` /
 * `.float-detail-panel`）的背景遮罩求解。
 *
 * ## 要解决的问题
 *
 * 旧实现在 `Gallery.vue` 内联（`analyzeImageColor` + `overlayColorScheme` + 两档
 * `overlay-light` / `overlay-dark` class），有四个致命缺陷：
 *
 * 1. **多半根本不跑**。入口要求 `img.preview_url` 非空，而该字段是
 *    `/gallery/load` 响应序列化那一刻 `check_local_file()` 的结果 —— 只有当时
 *    `downloads/previews/{id}.jpg` 已存在才非空。瀑布流是懒加载时**现场生成**
 *    预览图的且不回写，所以新会话首次浏览时恒为 `null` → 静默降级为 `dark`。
 * 2. **采样源与显示源不是同一张图**。采样用的是 150×150 中心裁切缩略图，
 *    显示用的是整图（`getDetailUrl`），构图根本无关。
 * 3. **采样区域与文字区域不一致**。判定用整图均值，遮罩却贴在顶部/底部 5%。
 * 4. **两档都够不着 4.5:1**。`dark` 档遮罩只有 6% 白（亮度 180 的图上白字
 *    1.91:1）；`light` 档 0.45 黑（纯白上 tertiary 文字 2.20:1）。
 *
 * ## 现在的做法（三层防御）
 *
 * | 层 | 手段                              | 失效后果              |
 * |---|-----------------------------------|-----------------------|
 * | L1 | CSS 写死 `rgba(0,0,0,0.62)`        | 无（纯 CSS）          |
 * | L2 | 本模块采样 → 求解 → **只往下调**   | 落回 L1，仍达标       |
 * | L3 | `blur(10px)` + `text-shadow`       | 观感下降，不影响达标  |
 *
 * **核心不变量：`solveScrimAlpha` 的返回值永远 ≤ `SCRIM_FLOOR_ALPHA`。**
 * 自适应只能让浮层更通透，永远不可能让对比度掉到 4.5:1 以下。因此本模块的
 * **任何**失败路径（canvas 不可用 / 图 404 / taint / 抛异常）都只是 `reset()`
 * （把 `scrims` 置回 `null`），由 CSS 的 `var()` 兜底接管 —— 降级的是观感，
 * 不是可用性。单测 T8/T9/T10 从三个侧面锁死这一点。
 *
 * ## 采样源：直接用 DOM 里那张已解码的 `<img>`
 *
 * 旧代码另起 `new Image()` 去请求预览图，既多一次网络往返 + 一次 JPEG 解码，
 * 又受 CORS 顾虑（`img.crossOrigin = 'Anonymous'`）。而 `el-image` 早就把图
 * 加载好画在屏幕上了，`@load` 事件的 `e.target` 就是它：
 *
 * - 零网络请求、零额外解码（画 canvas 用的是已解码的位图）；
 * - `getDetailUrl()` **永远返回同源相对路径**（`/api/v1/gallery/cache/original/...`
 *   或 `/api/v1/gallery/cache/preview/fetch/...`，后端都是 `FileResponse` 从本地
 *   吐文件），canvas 不会被 taint；
 * - 换 `src` 时浏览器 abort 旧请求，旧 `load` 事件不会再触发 → 天然不会写错图，
 *   不需要 requestId 之类的令牌（旧实现就有这个竞态）。
 *
 * 设计文档：docs/superpowers/specs/2026-10-01-image-overlay-readability-design.md
 */
import { ref } from 'vue'

// ---------------------------------------------------------------------------
// 常量
// ---------------------------------------------------------------------------

/**
 * L1 保底 alpha —— **必须与 Gallery.vue 中 `var()` 的 fallback 字面量一致**。
 * 推导：`rgba(0,0,0,0.62)` 叠在纯白上得 `#616161`，白字 tertiary@0.78 恰好
 * 4.53:1（刚过 4.5 线）。这是整套方案里唯一硬编码的对比度数字，其余全部由
 * 公式推导。单测 T9 断言两者相等，防止改一边忘另一边。
 */
export const SCRIM_FLOOR_ALPHA = 0.62

/** 求解目标：最弱一档文字的 alpha（§4.5 的 tertiary） */
export const TARGET_TEXT_ALPHA = 0.78

/** WCAG AA 正文线 */
export const MIN_CONTRAST = 4.5

/** 遮罩 alpha 的搜索步进（0.02 在视觉上不可分辨，却让结果可精确断言） */
export const ALPHA_STEP = 0.02

/** 取条带的亮度分位数。0.9 = 「文字底下最亮的那 10% 区域」 */
export const BAND_QUANTILE = 0.9

/**
 * 透明像素的合成底色 = `.float-image-wrapper` 的 `rgba(0,0,0,0.9)` 叠在
 * 浅色页面背景上 ≈ `#1a1a1a`。取最坏情况（浅色模式）。
 */
const TRANSPARENT_BASE = [26, 26, 26]

/** 浮层各部件的实际 CSS 高度（用于把 CSS 像素换算成自然像素条带） */
const HEADER_CSS_PX = 56   // padding 12*2 + 32 按钮 + 余量
const FOOTER_CSS_PX = 72   // padding 10*2 + 按钮 32 + 余量
/** `.float-detail-panel` 的 max-height 是 35vh */
const PANEL_MAX_VH = 0.35

/** 采样画布尺寸（很小：getImageData 回读 ≤ 64*48*4 = 12KB） */
const BAND_W = 64
const TOP_BAND_H = 16
const PANEL_BAND_H = 48

// ---------------------------------------------------------------------------
// WCAG 对比度数学
// ---------------------------------------------------------------------------

/** sRGB 8bit 通道 → 线性化 */
function srgbToLinear(c) {
  const v = c / 255
  return v <= 0.04045 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4)
}

/**
 * WCAG 2.x 相对亮度。
 *
 * 旧实现用的是 `0.299R + 0.587G + 0.114B` —— 那是在 **gamma 编码值** 上算 luma，
 * 不是相对亮度；再配一个拍脑袋的阈值 180，随机颜色里有近 49% 会判错档。
 *
 * @param {number} r 0-255
 * @param {number} g 0-255
 * @param {number} b 0-255
 * @returns {number} 0-1
 */
export function relativeLuminance(r, g, b) {
  return 0.2126 * srgbToLinear(r) + 0.7152 * srgbToLinear(g) + 0.0722 * srgbToLinear(b)
}

/**
 * WCAG 2.x 对比度。
 *
 * @param {number} l1 亮度值 1
 * @param {number} l2 亮度值 2
 * @returns {number} 1-21
 */
export function contrastRatio(l1, l2) {
  const hi = Math.max(l1, l2)
  const lo = Math.min(l1, l2)
  return (hi + 0.05) / (lo + 0.05)
}

/** 三元组的相对亮度 */
function luminanceOf(pixel) {
  return relativeLuminance(pixel[0], pixel[1], pixel[2])
}

/** `rgba(0, 0, 0, alpha)` 合成到 pixel 上（逐通道乘 (1-alpha)） */
function applyScrim(pixel, alpha) {
  const k = 1 - alpha
  return [pixel[0] * k, pixel[1] * k, pixel[2] * k]
}

/** `rgba(255, 255, 255, alpha)` 合成到 pixel 上 */
function applyWhiteText(pixel, alpha) {
  return [
    alpha * 255 + (1 - alpha) * pixel[0],
    alpha * 255 + (1 - alpha) * pixel[1],
    alpha * 255 + (1 - alpha) * pixel[2],
  ]
}

// ---------------------------------------------------------------------------
// 条带取样
// ---------------------------------------------------------------------------

/**
 * 从一段像素里取第 `q` 分位（由暗到亮排序）的代表像素。
 *
 * 为什么用分位数而不是均值/最大值：
 * - 均值无抗离群能力（§P2-6）：大面积留白把均值拉高、整体暗但顶部有亮边的图
 *   又把均值拉低；
 * - 最大值会被单个镜面高光带偏（一颗亮点不该把整条 header 压黑）；
 * - p90 = 「文字底下最亮的那 10% 区域」，既保守又不会被孤立亮点误伤。
 *
 * 透明像素按 `TRANSPARENT_BASE`（包装层实际渲染出来的颜色）合成，而不是跳过 ——
 * 透明 PNG 的 lineart 区域渲染出来就是接近黑的，采样必须反映这一点。
 *
 * @param {{data: Uint8ClampedArray|Uint8Array|number[], width: number, height: number}} imgData
 * @param {{rowFrom?: number, rowTo?: number, q?: number}} [opt]
 * @returns {[number, number, number]} 代表像素 RGB（0-255）
 */
export function quantilePixel(imgData, opt = {}) {
  const { data, width, height } = imgData
  const q = opt.q === undefined ? BAND_QUANTILE : opt.q
  const from = Math.max(0, Math.min(height, Math.floor(opt.rowFrom === undefined ? 0 : opt.rowFrom)))
  const to = Math.max(from, Math.min(height, Math.ceil(opt.rowTo === undefined ? height : opt.rowTo)))

  /** @type {number[][]} [亮度, r, g, b] */
  const samples = []
  for (let y = from; y < to; y++) {
    for (let x = 0; x < width; x++) {
      const i = (y * width + x) * 4
      const a = data[i + 3] / 255
      // 透明像素合成到包装层底色（a=1 时退化为原值，不引入误差）
      const r = data[i] * a + TRANSPARENT_BASE[0] * (1 - a)
      const g = data[i + 1] * a + TRANSPARENT_BASE[1] * (1 - a)
      const b = data[i + 2] * a + TRANSPARENT_BASE[2] * (1 - a)
      samples.push([relativeLuminance(r, g, b), r, g, b])
    }
  }

  if (samples.length === 0) return [...TRANSPARENT_BASE]
  samples.sort((p, r) => p[0] - r[0])
  const idx = Math.min(samples.length - 1, Math.max(0, Math.round(q * (samples.length - 1))))
  return [samples[idx][1], samples[idx][2], samples[idx][3]]
}

// ---------------------------------------------------------------------------
// 求解
// ---------------------------------------------------------------------------

/**
 * 给定代表像素，求让 `white@targetAlpha` 文字达到 `minContrast` 所需的
 * **最小**遮罩 alpha。
 *
 * 逐档试，取第一个达标的 → 背景越暗求出的 alpha 越小（暗图得到 0，保持
 * 「不压黑」的观感）。`maxAlpha` 默认即 L1 保底，所以**返回值永远 ≤ 0.62**，
 * 这是方案 C 的核心不变量（单测 T8 全域验证）。
 *
 * @param {[number, number, number]|number[]} pixel 背景代表像素 RGB（0-255）
 * @param {{targetAlpha?: number, minContrast?: number, maxAlpha?: number, step?: number}} [opt]
 * @returns {number} alpha，取值 0 ~ SCRIM_FLOOR_ALPHA
 */
export function solveScrimAlpha(pixel, opt = {}) {
  const targetAlpha = opt.targetAlpha === undefined ? TARGET_TEXT_ALPHA : opt.targetAlpha
  const minContrast = opt.minContrast === undefined ? MIN_CONTRAST : opt.minContrast
  const maxAlpha = opt.maxAlpha === undefined ? SCRIM_FLOOR_ALPHA : opt.maxAlpha
  const step = opt.step === undefined ? ALPHA_STEP : opt.step

  const steps = Math.floor(maxAlpha / step + 1e-9)
  for (let i = 0; i <= steps; i++) {
    const alpha = Math.min(i * step, maxAlpha)
    const panel = applyScrim(pixel, alpha)
    const text = applyWhiteText(panel, targetAlpha)
    if (contrastRatio(luminanceOf(text), luminanceOf(panel)) >= minContrast) {
      return Math.round(alpha * 1000) / 1000
    }
  }
  // 循环上界就是 maxAlpha，数学上第 maxAlpha 档必达标；走到这里只可能是
  // 浮点误差，兜底返回保底值（与 CSS 兜底一致）。
  return maxAlpha
}

/** alpha → `rgba(0, 0, 0, a)` 字符串（0.60 → "0.6"，0 → "0"） */
function scrimToCss(alpha) {
  return `rgba(0, 0, 0, ${alpha})`
}

/**
 * 组合成两个 CSS 颜色值。
 *
 * - `bar` 供 `.float-header` + `.float-footer` 共用，取顶/底条带里**较亮**的那个
 *   （较亮的一侧需要更重的遮罩，两块共享时必须按它算）；
 * - `panel` 供 `.float-detail-panel` 单独使用。面板最多占 35vh，若并进 `bar`，
 *   「上暗下亮」的常见人像图 header 会被下半张的亮部无谓压黑。
 *
 * @param {{top: number[], bottom: number[], panel: number[]}} bands
 * @returns {{bar: string, panel: string}}
 */
export function buildScrims({ top, bottom, panel }) {
  const brighter = luminanceOf(top) >= luminanceOf(bottom) ? top : bottom
  return {
    bar: scrimToCss(solveScrimAlpha(brighter)),
    panel: scrimToCss(solveScrimAlpha(panel)),
  }
}

// ---------------------------------------------------------------------------
// DOM 取样（薄封装：决策逻辑全在上面，这里只负责把像素取出来）
// ---------------------------------------------------------------------------

let _canvas = null

function getCanvas() {
  if (typeof document === 'undefined') return null
  if (!_canvas) _canvas = document.createElement('canvas')
  return _canvas
}

/** 把条带画进固定尺寸画布并读回 ImageData */
function readBand(ctx, imgEl, srcTop, srcRows, dstH) {
  // 改 width/height 会清空画布，所以每次都显式设置
  _canvas.width = BAND_W
  _canvas.height = dstH
  ctx.clearRect(0, 0, BAND_W, dstH)
  ctx.drawImage(imgEl, 0, srcTop, imgEl.naturalWidth, srcRows, 0, 0, BAND_W, dstH)
  return ctx.getImageData(0, 0, BAND_W, dstH)
}

/**
 * 采样三条带的代表像素。
 *
 * 采样区域按**文字实际压住的像素**划，而不是固定比例 —— 浮层的宽高比是按
 * 图片自身比例算出来的（`calculatePreviewSize`），所以用「CSS 像素高度 ×
 * 缩放系数」反推自然像素行区间最准；短图（显示尺寸小于浮层高度）用比例会
 * 采不准。`rect.height` 取不到时 `scale = 1` 退化为按自然像素的固定条带。
 *
 * @param {HTMLImageElement} imgEl
 * @returns {{top: number[], bottom: number[], panel: number[]}|null}
 */
function sampleBands(imgEl) {
  const canvas = getCanvas()
  if (!canvas) return null
  const ctx = canvas.getContext('2d')
  if (!ctx) return null

  const nw = imgEl.naturalWidth
  const nh = imgEl.naturalHeight
  if (!nw || !nh) return null

  const rect = typeof imgEl.getBoundingClientRect === 'function' ? imgEl.getBoundingClientRect() : null
  const scale = rect && rect.height > 0 ? nh / rect.height : 1
  const rows = (cssPx, min, max) => Math.max(min, Math.min(max, Math.ceil(cssPx)))

  const topRows = rows(HEADER_CSS_PX * scale, 1, Math.floor(nh * 0.5))
  const bottomRows = rows(FOOTER_CSS_PX * scale, 1, Math.floor(nh * 0.5))
  // min=bottomRows 保证面板条带至少覆盖 footer 条带（面板就在 footer 上方展开）；
  // 极短图时 max 可能小于 min，此时 rows() 返回 min，仍是合法行数。
  const panelRows = rows(
    (FOOTER_CSS_PX + (typeof window !== 'undefined' ? window.innerHeight : 0) * PANEL_MAX_VH) * scale,
    bottomRows,
    Math.floor(nh * 0.9)
  )

  // 底条带 ⊂ 面板条带，一次 draw 同时读出两组行区间
  const bottomData = readBand(ctx, imgEl, nh - panelRows, panelRows, PANEL_BAND_H)
  const topData = readBand(ctx, imgEl, 0, topRows, TOP_BAND_H)

  const footerRowFrom = PANEL_BAND_H - Math.max(1, Math.ceil((bottomRows / panelRows) * PANEL_BAND_H))

  return {
    top: quantilePixel(topData),
    bottom: quantilePixel(bottomData, { rowFrom: footerRowFrom, rowTo: PANEL_BAND_H }),
    panel: quantilePixel(bottomData),
  }
}

/**
 * 大图浮层遮罩 composable。
 *
 * `scrims` 初始为 `null` —— 调用方（Gallery.vue）据此**不写** CSS 变量，
 * `var()` 自然回落到 CSS 里的 L1 保底值。JS 少写一个键就是一层降级，
 * 不需要在 JS 里重复实现「保底」。
 *
 * @returns {{scrims: import('vue').Ref<{bar: string, panel: string}|null>,
 *            analyzeFromImageEl: (imgEl: HTMLImageElement) => void,
 *            reset: () => void}}
 */
export function useOverlayScrim() {
  const scrims = ref(null)

  /** 回到保底：置 null，而不是置成某个具体值 */
  const reset = () => {
    scrims.value = null
  }

  /**
   * 从「屏幕上那张 `<img>`」求解遮罩。**任何失败都只是 reset()**，
   * 绝不写入比保底更轻的值。
   *
   * @param {HTMLImageElement} imgEl `el-image` 的 `@load` 事件 target
   */
  const analyzeFromImageEl = (imgEl) => {
    try {
      if (!imgEl || !imgEl.naturalWidth || !imgEl.naturalHeight) {
        reset()
        return
      }
      const bands = sampleBands(imgEl)
      if (!bands) {
        reset()
        return
      }
      scrims.value = buildScrims(bands)
    } catch {
      // canvas 被 taint / getImageData 抛 SecurityError / 任何意外 —— 同源
      // 理论不会 taint，但兜底必须是「无害」而非「报错」
      reset()
    }
  }

  return { scrims, analyzeFromImageEl, reset }
}
