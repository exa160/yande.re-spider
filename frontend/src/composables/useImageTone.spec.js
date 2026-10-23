import { describe, it, expect } from 'vitest'
import {
  IMAGE_TONE_THRESHOLD,
  imageToneFromImageData,
  useImageTone,
} from './useImageTone'

function makeImgData(width, height, fill) {
  const data = new Uint8ClampedArray(width * height * 4)
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const [r, g, b, a = 255] = fill(x, y)
      const i = (y * width + x) * 4
      data[i] = r
      data[i + 1] = g
      data[i + 2] = b
      data[i + 3] = a
    }
  }
  return { data, width, height }
}

describe('useImageTone — 图片明暗判断', () => {
  it('纯白 → light，纯黑 → dark', () => {
    expect(imageToneFromImageData(makeImgData(32, 32, () => [255, 255, 255]))).toBe('light')
    expect(imageToneFromImageData(makeImgData(32, 32, () => [0, 0, 0]))).toBe('dark')
  })

  it('只看顶部/底部条带：中间亮不影响上下暗的图', () => {
    const data = makeImgData(32, 32, (_x, y) => (
      y >= 6 && y < 26 ? [255, 255, 255] : [0, 0, 0]
    ))
    expect(imageToneFromImageData(data)).toBe('dark')
  })

  it('上下亮、中间暗 → light', () => {
    const data = makeImgData(32, 32, (_x, y) => (
      y < 6 || y >= 26 ? [255, 255, 255] : [0, 0, 0]
    ))
    expect(imageToneFromImageData(data)).toBe('light')
  })

  it('透明像素按近黑底合成 → dark', () => {
    const data = makeImgData(32, 32, () => [255, 255, 255, 0])
    expect(imageToneFromImageData(data)).toBe('dark')
  })

  it('阈值两侧的中性灰分别判为 dark / light', () => {
    expect(imageToneFromImageData(makeImgData(32, 32, () => [150, 150, 150]))).toBe('dark')
    expect(imageToneFromImageData(makeImgData(32, 32, () => [180, 180, 180]))).toBe('light')
    expect(IMAGE_TONE_THRESHOLD).toBeGreaterThan(0)
    expect(IMAGE_TONE_THRESHOLD).toBeLessThan(1)
  })

  it('空数据回退 dark', () => {
    expect(imageToneFromImageData({ data: new Uint8ClampedArray(0), width: 0, height: 0 })).toBe('dark')
  })
})

describe('useImageTone — composable 兜底', () => {
  it('初始 tone 使用 fallback；reset 可指定新值', () => {
    const { tone, reset } = useImageTone('dark')
    expect(tone.value).toBe('dark')
    reset('light')
    expect(tone.value).toBe('light')
  })

  it('图片不可用时回退到传入的 fallback', () => {
    const { tone, analyze } = useImageTone('light')
    analyze(null, 'dark')
    expect(tone.value).toBe('dark')
    analyze({ naturalWidth: 0, naturalHeight: 0 }, 'light')
    expect(tone.value).toBe('light')
  })
})
