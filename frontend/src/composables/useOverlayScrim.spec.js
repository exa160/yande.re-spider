import { describe, it, expect } from 'vitest'
import {
  SCRIM_FLOOR_ALPHA,
  TARGET_TEXT_ALPHA,
  MIN_CONTRAST,
  BAND_QUANTILE,
  relativeLuminance,
  contrastRatio,
  quantilePixel,
  solveScrimAlpha,
  buildScrims,
  useOverlayScrim,
} from './useOverlayScrim'

// 参照实现的 WCAG 公式（与被测代码独立写一遍，避免同源错误自我掩盖）
function refLum(r, g, b) {
  const f = (c) => {
    const v = c / 255
    return v <= 0.04045 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4)
  }
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)
}
function refCr(l1, l2) {
  const hi = Math.max(l1, l2)
  const lo = Math.min(l1, l2)
  return (hi + 0.05) / (lo + 0.05)
}
/** 某个 alpha 的黑纱罩叠上去之后，白字@textAlpha 与面板的对比度 */
function contrastAt(pixel, alpha, textAlpha) {
  const k = 1 - alpha
  const panel = [pixel[0] * k, pixel[1] * k, pixel[2] * k]
  const text = panel.map((c) => textAlpha * 255 + (1 - textAlpha) * c)
  return refCr(refLum(...text), refLum(...panel))
}

/** 造一个 width×height 的 ImageData 替身，fill 决定每像素颜色 */
function makeImgData(width, height, fill) {
  const data = new Uint8ClampedArray(width * height * 4)
  for (let i = 0; i < width * height; i++) {
    const [r, g, b, a] = fill(i)
    data[i * 4] = r
    data[i * 4 + 1] = g
    data[i * 4 + 2] = b
    data[i * 4 + 3] = a === undefined ? 255 : a
  }
  return { data, width, height }
}

describe('useOverlayScrim — WCAG 数学（T1–T2）', () => {
  it('T1 relativeLuminance: 黑=0 白=1，红=0.2126', () => {
    expect(relativeLuminance(0, 0, 0)).toBe(0)
    expect(relativeLuminance(255, 255, 255)).toBeCloseTo(1, 10)
    expect(relativeLuminance(255, 0, 0)).toBeCloseTo(0.2126, 5)
    expect(relativeLuminance(0, 255, 0)).toBeCloseTo(0.7152, 5)
    expect(relativeLuminance(0, 0, 255)).toBeCloseTo(0.0722, 5)
  })

  it('T1b relativeLuminance 与参照实现在 200 组随机色上一致', () => {
    let seed = 42
    const rnd = () => ((seed = (seed * 1103515245 + 12345) & 0x7fffffff) % 256)
    for (let i = 0; i < 200; i++) {
      const c = [rnd(), rnd(), rnd()]
      expect(relativeLuminance(...c)).toBeCloseTo(refLum(...c), 10)
    }
  })

  it('T2 contrastRatio: 白黑=21，对称', () => {
    expect(contrastRatio(1, 0)).toBeCloseTo(21, 10)
    expect(contrastRatio(0, 1)).toBeCloseTo(21, 10)
    expect(contrastRatio(0.5, 0.5)).toBeCloseTo(1, 10)
  })
})

describe('useOverlayScrim — 求解器（T3–T10）', () => {
  it('T3 solveScrimAlpha(纯白) = 保底 0.62，且恰好达标', () => {
    const a = solveScrimAlpha([255, 255, 255])
    expect(a).toBeCloseTo(0.62, 3)
    expect(contrastAt([255, 255, 255], a, TARGET_TEXT_ALPHA)).toBeGreaterThanOrEqual(MIN_CONTRAST)
  })

  it('T4 solveScrimAlpha 深色 = 0（不压黑，保持观感）', () => {
    expect(solveScrimAlpha([0, 0, 0])).toBe(0)
    expect(solveScrimAlpha([25, 40, 90])).toBe(0)
    expect(solveScrimAlpha([40, 40, 40])).toBe(0)
  })

  it('T5 solveScrimAlpha 亮黄 = 0.58', () => {
    const a = solveScrimAlpha([255, 230, 0])
    expect(a).toBeCloseTo(0.58, 3)
    expect(contrastAt([255, 230, 0], a, TARGET_TEXT_ALPHA)).toBeGreaterThanOrEqual(MIN_CONTRAST)
  })

  it('T6 亮度越高，alpha 单调不减（0→255 步进 25）', () => {
    const alphas = []
    for (let v = 0; v <= 255; v += 25) alphas.push(solveScrimAlpha([v, v, v]))
    for (let i = 1; i < alphas.length; i++) {
      expect(alphas[i]).toBeGreaterThanOrEqual(alphas[i - 1])
    }
    expect(alphas[0]).toBe(0)
    expect(alphas[alphas.length - 1]).toBeCloseTo(0.62, 3)
  })

  it('T7 4096 组随机色：求解结果全部满足 >= 4.5:1', () => {
    let seed = 20261001
    const rnd = () => ((seed = (seed * 1103515245 + 12345) & 0x7fffffff) % 256)
    for (let i = 0; i < 4096; i++) {
      const px = [rnd(), rnd(), rnd()]
      const a = solveScrimAlpha(px)
      expect(contrastAt(px, a, TARGET_TEXT_ALPHA), `rgb(${px}) alpha=${a}`).toBeGreaterThanOrEqual(MIN_CONTRAST)
    }
  })

  it('T8 核心不变量：4096 组随机色下 alpha 永远 <= 保底 0.62', () => {
    let seed = 777
    const rnd = () => ((seed = (seed * 1103515245 + 12345) & 0x7fffffff) % 256)
    for (let i = 0; i < 4096; i++) {
      expect(solveScrimAlpha([rnd(), rnd(), rnd()])).toBeLessThanOrEqual(SCRIM_FLOOR_ALPHA)
    }
  })

  it('T9 SCRIM_FLOOR_ALPHA 与 Gallery.vue 的 var() fallback 字面量一致', async () => {
    const { readFileSync } = await import('node:fs')
    const { fileURLToPath } = await import('node:url')
    const path = await import('node:path')
    const file = path.join(path.dirname(fileURLToPath(import.meta.url)), '../views/Gallery.vue')
    const css = readFileSync(file, 'utf-8')
    // 两处 var() 的 fallback 都必须等于 SCRIM_FLOOR_ALPHA
    const literals = [...css.matchAll(/var\(--overlay-scrim(?:-panel)?,\s*rgba\(0,\s*0,\s*0,\s*([\d.]+)\)\)/g)]
      .map((m) => Number(m[1]))
    expect(literals.length).toBeGreaterThanOrEqual(2)
    for (const lit of literals) expect(lit).toBe(SCRIM_FLOOR_ALPHA)
  })

  it('T10 L1 保底 0.62 在纯白上：tertiary 文字 >= 4.5:1（把推导固化成测试）', () => {
    expect(contrastAt([255, 255, 255], SCRIM_FLOOR_ALPHA, TARGET_TEXT_ALPHA))
      .toBeGreaterThanOrEqual(MIN_CONTRAST)
    // 三档文字在保底下同时达标
    for (const a of [0.95, 0.82, TARGET_TEXT_ALPHA]) {
      expect(contrastAt([255, 255, 255], SCRIM_FLOOR_ALPHA, a), `textAlpha=${a}`)
        .toBeGreaterThanOrEqual(MIN_CONTRAST)
    }
  })
})

describe('useOverlayScrim — 分位数取样（T11–T14）', () => {
  it('T11 全同色条带：返回该色', () => {
    const img = makeImgData(64, 16, () => [200, 100, 50])
    const px = quantilePixel(img)
    expect(px[0]).toBeCloseTo(200, 0)
    expect(px[1]).toBeCloseTo(100, 0)
    expect(px[2]).toBeCloseTo(50, 0)
  })

  it('T12 80% 黑 + 20% 白，q=0.9 落在白侧（确实取到「最亮那 10% 区域」）', () => {
    const n = 64 * 16
    const img = makeImgData(64, 16, (i) => (i >= n * 0.8 ? [255, 255, 255] : [0, 0, 0]))
    const px = quantilePixel(img)
    expect(px[0]).toBeGreaterThan(200)
  })

  it('T13 孤立高光（1/1024）不移动 q=0.9（抗离群）', () => {
    const n = 64 * 16
    const img = makeImgData(64, 16, (i) => (i === n - 1 ? [255, 255, 255] : [0, 0, 0]))
    const px = quantilePixel(img)
    expect(px[0]).toBeLessThan(20)
  })

  it('T14 透明像素按包装层底色 #1a1a1a 合成（不是跳过、也不是取原值）', () => {
    const img = makeImgData(64, 16, () => [255, 255, 255, 0])
    const px = quantilePixel(img)
    expect(px).toEqual([26, 26, 26])
  })

  it('T14b 半透明像素按 alpha 混合', () => {
    const img = makeImgData(64, 16, () => [255, 255, 255, 128])
    const px = quantilePixel(img)
    expect(px[0]).toBeCloseTo(255 * 0.5 + 26 * 0.5, 0)
  })

  it('T14c rowFrom/rowTo 限定行区间', () => {
    // 上半全白、下半全黑
    const img = makeImgData(64, 16, (i) => (i < 64 * 8 ? [255, 255, 255] : [0, 0, 0]))
    expect(quantilePixel(img, { rowFrom: 0, rowTo: 8 })[0]).toBeGreaterThan(200)
    expect(quantilePixel(img, { rowFrom: 8, rowTo: 16 })[0]).toBeLessThan(20)
  })
})

describe('useOverlayScrim — 组合（T15–T16）', () => {
  it('T15 buildScrims: bar 取顶/底中较亮的一侧，panel 独立', () => {
    const dark = [20, 20, 20]
    const light = [255, 255, 255]
    const r = buildScrims({ top: light, bottom: dark, panel: dark })
    // bar 取了较亮的 top → 必须是满额
    expect(r.bar).toBe(`rgba(0, 0, 0, ${SCRIM_FLOOR_ALPHA})`)
    // panel 是暗色 → 0
    expect(r.panel).toBe('rgba(0, 0, 0, 0)')

    const r2 = buildScrims({ top: dark, bottom: light, panel: light })
    expect(r2.bar).toBe(r.bar)   // 底更亮时结果一致（取较亮者）
  })

  it('T16 buildScrims 返回合法 rgba() 字符串', () => {
    const r = buildScrims({ top: [128, 128, 128], bottom: [90, 90, 90], panel: [200, 200, 200] })
    for (const v of [r.bar, r.panel]) {
      expect(v).toMatch(/^rgba\(0, 0, 0, [\d.]+\)$/)
      const alpha = Number(v.match(/([\d.]+)\)$/)[1])
      expect(alpha).toBeGreaterThanOrEqual(0)
      expect(alpha).toBeLessThanOrEqual(SCRIM_FLOOR_ALPHA)
    }
  })

  it('T16b 浮点不累积：结果落在步进网格上', () => {
    for (const v of [0, 33, 90, 135, 180, 200, 230, 255]) {
      const a = solveScrimAlpha([v, v, v])
      expect(Math.abs(a / 0.02 - Math.round(a / 0.02))).toBeLessThan(1e-6)
    }
  })
})

describe('useOverlayScrim — composable（T20/T22）', () => {
  it('T20 初始 scrims 为 null（Gallery 据此不写 CSS 变量，走 L1 兜底）', () => {
    const { scrims } = useOverlayScrim()
    expect(scrims.value).toBeNull()
  })

  it('T22 分析失败一律回到 null，绝不写入比保底更轻的值', () => {
    const { scrims, analyzeFromImageEl, reset } = useOverlayScrim()

    // 1. null 入参
    analyzeFromImageEl(null)
    expect(scrims.value).toBeNull()

    // 2. naturalWidth = 0
    analyzeFromImageEl({ naturalWidth: 0, naturalHeight: 0 })
    expect(scrims.value).toBeNull()

    // 3. getContext 返回 null（happy-dom 就是这样）
    const broken = {
      naturalWidth: 800,
      naturalHeight: 600,
      getBoundingClientRect: () => ({ width: 800, height: 600 }),
    }
    analyzeFromImageEl(broken)
    expect(scrims.value).toBeNull()

    // 4. drawImage 抛异常
    const throwing = {
      naturalWidth: 800,
      naturalHeight: 600,
      getBoundingClientRect: () => ({ width: 800, height: 600 }),
    }
    Object.defineProperty(throwing, 'naturalWidth', {
      get() { throw new Error('boom') },
    })
    analyzeFromImageEl(throwing)
    expect(scrims.value).toBeNull()

    reset()
    expect(scrims.value).toBeNull()
  })

  it('T22b 兜底后 scrims 仍为 null → CSS var() 拿不到定义 → 落到 0.62', () => {
    const { scrims, analyzeFromImageEl } = useOverlayScrim()
    analyzeFromImageEl({ naturalWidth: 0, naturalHeight: 0 })
    // Gallery 的 wrapperStyle 只在 scrims 非 null 时写 --overlay-scrim-*
    // scrims 为 null ⇒ style 对象里没有这两个 key
    const style = { ...(scrims.value && { '--overlay-scrim': scrims.value.bar }) }
    expect(Object.keys(style)).not.toContain('--overlay-scrim')
  })

  it('BAND_QUANTILE 取 0.9', () => {
    expect(BAND_QUANTILE).toBe(0.9)
  })
})
