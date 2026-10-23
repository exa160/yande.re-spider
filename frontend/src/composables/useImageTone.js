import { ref } from 'vue'

/**
 * 大图 header/footer 的明暗 tone：
 * - 亮图 → 'light'（浅色 band + 深色文字/图标）
 * - 暗图 → 'dark'（暗色 band + 白色文字/图标）
 *
 * 只取图片顶部/底部条带的平均亮度，因为 header/footer 就压在这两块上。
 * 这不是对比度保证（band 本身已经足够不透明），而是让 chrome 的明暗
 * 跟随图片，避免亮图上出现深色横条、暗图上出现白色横条。
 */

export const IMAGE_TONE_THRESHOLD = 0.42

const SAMPLE_SIZE = 32
const BAND_ROWS = 6

function srgbToLinear(channel) {
  const v = channel / 255
  return v <= 0.04045 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4)
}

function relativeLuminance(r, g, b) {
  return 0.2126 * srgbToLinear(r) + 0.7152 * srgbToLinear(g) + 0.0722 * srgbToLinear(b)
}

/**
 * 从 32×32 的采样图判断 tone。
 * 透明像素按大图包装层的近黑底（rgba(0,0,0,.9)）合成。
 *
 * @param {{data: Uint8ClampedArray|Uint8Array|number[], width: number, height: number}} imgData
 * @returns {'light'|'dark'}
 */
export function imageToneFromImageData(imgData) {
  const { data, width, height } = imgData
  if (!width || !height || !data) return 'dark'

  const rows = Math.min(BAND_ROWS, Math.floor(height / 2))
  let sum = 0
  let count = 0

  for (let y = 0; y < height; y++) {
    if (y >= rows && y < height - rows) continue
    for (let x = 0; x < width; x++) {
      const i = (y * width + x) * 4
      const alpha = data[i + 3] / 255
      const r = data[i] * alpha
      const g = data[i + 1] * alpha
      const b = data[i + 2] * alpha
      sum += relativeLuminance(r, g, b)
      count += 1
    }
  }

  if (!count) return 'dark'
  return sum / count >= IMAGE_TONE_THRESHOLD ? 'light' : 'dark'
}

/**
 * @param {'light'|'dark'} [fallback] 采样不可用时的兜底 tone
 * @returns {{
 *   tone: import('vue').Ref<'light'|'dark'>,
 *   analyze: (imgEl: HTMLImageElement, nextFallback?: 'light'|'dark') => void,
 *   reset: (next?: 'light'|'dark') => void,
 * }}
 */
export function useImageTone(fallback = 'light') {
  const tone = ref(fallback)
  let canvas = null

  const reset = (next = fallback) => {
    tone.value = next
  }

  const analyze = (imgEl, nextFallback = fallback) => {
    try {
      if (!imgEl || !imgEl.naturalWidth || !imgEl.naturalHeight) {
        reset(nextFallback)
        return
      }
      if (typeof document === 'undefined') {
        reset(nextFallback)
        return
      }
      if (!canvas) canvas = document.createElement('canvas')
      canvas.width = SAMPLE_SIZE
      canvas.height = SAMPLE_SIZE
      const ctx = canvas.getContext('2d')
      if (!ctx) {
        reset(nextFallback)
        return
      }
      ctx.clearRect(0, 0, SAMPLE_SIZE, SAMPLE_SIZE)
      ctx.drawImage(imgEl, 0, 0, SAMPLE_SIZE, SAMPLE_SIZE)
      tone.value = imageToneFromImageData(ctx.getImageData(0, 0, SAMPLE_SIZE, SAMPLE_SIZE))
    } catch {
      reset(nextFallback)
    }
  }

  return { tone, analyze, reset }
}
