import { describe, it, expect } from 'vitest'
import {
  getColumnCount,
  getColumnWidth,
  getEffectiveColumnCount,
  getFolderPageSizes,
  COLUMN_GAP,
  MIN_COLUMN_WIDTH,
  MIN_FOLDER_COLUMN_WIDTH,
  MAX_COLUMNS,
  MAX_FOLDER_COLUMNS,
} from './columnLayout'

describe('columnLayout - 瀑布流列数计算', () => {
  describe('P0 - 窄屏沿用原有断点（不改变手机/平板观感）', () => {
    it('T1 宽度 < 480 → 1 列', () => {
      expect(getColumnCount(320)).toBe(1)
      expect(getColumnCount(479)).toBe(1)
    })

    it('T2 480 ≤ 宽度 < 768 → 2 列', () => {
      expect(getColumnCount(480)).toBe(2)
      expect(getColumnCount(767)).toBe(2)
    })

    it('T3 768 ≤ 宽度 < 1200 → 3 列', () => {
      expect(getColumnCount(768)).toBe(3)
      expect(getColumnCount(1199)).toBe(3)
    })
  })

  describe('P0 - 宽屏按最小列宽反推', () => {
    it('T4 1200px 仍为 4 列（与改造前一致）', () => {
      expect(getColumnCount(1200)).toBe(4)
      expect(getColumnCount(1504)).toBe(4)
    })

    it('T5 逐档递增到 10 列', () => {
      expect(getColumnCount(1505)).toBe(5)
      expect(getColumnCount(1809)).toBe(6)
      expect(getColumnCount(2113)).toBe(7)
      expect(getColumnCount(2417)).toBe(8)
      expect(getColumnCount(2721)).toBe(9)
      expect(getColumnCount(3025)).toBe(10)
    })

    it('T6 4K 100% 缩放（容器 3800px）封顶 10 列', () => {
      expect(getColumnCount(3800)).toBe(MAX_COLUMNS)
      expect(getColumnCount(6000)).toBe(MAX_COLUMNS)
    })
  })

  describe('P0 - 列宽不小于最小列宽（保证磁贴不会过小）', () => {
    it('T7 任一档位下单列宽度 ≥ MIN_COLUMN_WIDTH（除 1~3 档窄屏）', () => {
      const widths = [1200, 1505, 1809, 2113, 2417, 2721, 3025, 3800]
      for (const w of widths) {
        const cols = getColumnCount(w)
        const colWidth = getColumnWidth(w, cols)
        expect(colWidth).toBeGreaterThanOrEqual(MIN_COLUMN_WIDTH - 1)
      }
    })

    it('T8 列宽随容器变宽单调不减（不会出现更宽容器反而更小列）', () => {
      const widths = [1200, 1505, 1809, 2113, 2417, 2721, 3025, 3800]
      let prev = 0
      for (const w of widths) {
        const cols = getColumnCount(w)
        const colWidth = getColumnWidth(w, cols)
        expect(colWidth).toBeGreaterThanOrEqual(prev - 1)
        prev = colWidth
      }
    })
  })

  describe('P1 - 异常输入兜底', () => {
    it('T9 非法宽度（0/负数/NaN）→ 1 列，不抛错', () => {
      expect(getColumnCount(0)).toBe(1)
      expect(getColumnCount(-100)).toBe(1)
      expect(getColumnCount(NaN)).toBe(1)
      expect(getColumnCount(undefined)).toBe(1)
    })

    it('T10 getColumnWidth 列数为 0/1 时不产生负宽度', () => {
      expect(getColumnWidth(1000, 0)).toBe(1000)
      expect(getColumnWidth(1000, 1)).toBe(1000)
    })
  })

  describe('P1 - 与 CSS gap 常量一致', () => {
    it('T11 COLUMN_GAP = 15，与 .waterfall-container 的 gap 保持同步', () => {
      expect(COLUMN_GAP).toBe(15)
    })
  })

  describe('P0 - folder 模式（收藏夹一级页磁贴）独立策略', () => {
    it('T12 folder 模式窄屏沿用 1/2/3 档断点（与 image 模式一致）', () => {
      expect(getColumnCount(320, 'folder')).toBe(1)
      expect(getColumnCount(600, 'folder')).toBe(2)
      expect(getColumnCount(1000, 'folder')).toBe(3)
      // 与 image 模式完全一致 → 手机横屏不会出现「图片 3 列、收藏夹 1 列」
      for (const w of [320, 390, 600, 800, 844, 1000]) {
        expect(getColumnCount(w, 'folder')).toBe(getColumnCount(w, 'image'))
      }
    })

    it('T13 folder 模式最小列宽 420px，比 image 模式更宽', () => {
      expect(MIN_FOLDER_COLUMN_WIDTH).toBeGreaterThan(MIN_COLUMN_WIDTH)
      expect(MIN_FOLDER_COLUMN_WIDTH).toBe(420)
    })

    it('T14 folder 模式宽屏按 420px 反推，上限 8 列', () => {
      // 1440p（容器 1880）→ 4 列
      expect(getColumnCount(1880, 'folder')).toBe(4)
      // 2560（容器 2520）→ 5 列
      expect(getColumnCount(2520, 'folder')).toBe(5)
      // 4K 100%（容器 3800）→ 封顶 8 列
      expect(getColumnCount(3800, 'folder')).toBe(MAX_FOLDER_COLUMNS)
      expect(MAX_FOLDER_COLUMNS).toBe(8)
    })

    it('T15 folder 模式任意档位单列宽度 ≥ 288px（宽屏段）', () => {
      // 宽屏段（≥1200）最少 4 列 → 单列宽 = (1200-45)/4 ≈ 288
      const widths = [1200, 2160, 2595, 3030, 3465, 3800]
      for (const w of widths) {
        const cols = getColumnCount(w, 'folder')
        const colWidth = getColumnWidth(w, cols)
        expect(colWidth).toBeGreaterThanOrEqual(288)
      }
    })

    it('T16 默认模式仍是 image（向后兼容）', () => {
      expect(getColumnCount(1880)).toBe(getColumnCount(1880, 'image'))
    })
  })

  describe('P0 - 手机 / 平板尺寸档位（窄屏统一 1/2/3）', () => {
    it('T21 手机竖屏 390 → 1 列', () => {
      expect(getColumnCount(350, 'folder')).toBe(1)
      expect(getColumnCount(350, 'image')).toBe(1)
    })

    it('T22 手机横屏 844 → 3 列（与图片一致）', () => {
      expect(getColumnCount(804, 'folder')).toBe(3)
      expect(getColumnCount(804, 'image')).toBe(3)
    })

    it('T23 平板竖屏 780 → 3 列', () => {
      expect(getColumnCount(780, 'folder')).toBe(3)
    })

    it('T24 单列时磁贴宽度 = 容器宽度，不会超出容器（无横向溢出）', () => {
      const container = 350
      const cols = getColumnCount(container, 'folder')
      expect(cols).toBe(1)
      expect(getColumnWidth(container, cols)).toBeLessThanOrEqual(container)
    })
  })

  describe('P0 - 空列折叠（磁贴数少于列数时不留空列）', () => {
    it('T17 内容数少于列数 → 实际列数 = 内容数', () => {
      expect(getEffectiveColumnCount(6, 3)).toBe(3)
      expect(getEffectiveColumnCount(10, 5)).toBe(5)
      expect(getEffectiveColumnCount(6, 6)).toBe(6)
    })

    it('T18 内容数多于列数 → 实际列数 = 列数上限', () => {
      expect(getEffectiveColumnCount(6, 20)).toBe(6)
      expect(getEffectiveColumnCount(10, 500)).toBe(10)
    })

    it('T19 内容数为 0 → 至少 1 列，不产生 0 列', () => {
      expect(getEffectiveColumnCount(6, 0)).toBe(1)
      expect(getEffectiveColumnCount(6, undefined)).toBe(1)
    })

    it('T20 折叠空列后磁贴变宽（收藏夹只有 5 个磁贴时不再被摊成 1/6）', () => {
      const width = 3800
      const cols = getColumnCount(width, 'folder')
      const before = getColumnWidth(width, cols)
      const after = getColumnWidth(width, getEffectiveColumnCount(cols, 5))
      expect(after).toBeGreaterThan(before)
      expect(after).toBeGreaterThan(600)
    })
  })

  describe('P0 - 收藏夹分页条数按列数对齐（每页填满行）', () => {
    it('T21 每页条数由列数推导（列数 × 3 行，窄屏至少 8 个）', () => {
      // 4 列 → 12；8 列 → 24；1 列 → 8（最小值）；2 列 → 8；3 列 → 9
      expect(getFolderPageSizes(4, 0)).toEqual({ block: 12, firstPage: 12, laterPage: 12 })
      expect(getFolderPageSizes(8, 0)).toEqual({ block: 24, firstPage: 24, laterPage: 24 })
      expect(getFolderPageSizes(1, 0)).toEqual({ block: 8, firstPage: 8, laterPage: 8 })
      expect(getFolderPageSizes(2, 0)).toEqual({ block: 8, firstPage: 8, laterPage: 8 })
      expect(getFolderPageSizes(3, 0)).toEqual({ block: 9, firstPage: 9, laterPage: 9 })
    })

    it('T22 第 1 页扣掉置顶的虚拟磁贴，后续页为整块', () => {
      expect(getFolderPageSizes(4, 3)).toEqual({ block: 12, firstPage: 9, laterPage: 12 })
      expect(getFolderPageSizes(6, 2)).toEqual({ block: 18, firstPage: 16, laterPage: 18 })
    })

    it('T23 累计显示总数恒为列数的整数倍（每页最后一行都填满）', () => {
      for (const cols of [1, 2, 3, 4, 5, 6, 8, 10]) {
        for (const v of [0, 1, 2, 3]) {
          const { block, firstPage, laterPage } = getFolderPageSizes(cols, v)
          expect(v + firstPage).toBe(block)
          for (const page of [2, 3, 4]) {
            const total = v + firstPage + (page - 1) * laterPage
            expect(total % cols).toBe(0)
            expect(total).toBe(page * block)
          }
        }
      }
    })

    it('T24 非法输入兜底：至少 1 个磁贴、至少 1 列', () => {
      const r = getFolderPageSizes(0, 0)
      expect(r.block).toBeGreaterThanOrEqual(1)
      expect(r.firstPage).toBeGreaterThanOrEqual(1)
      expect(r.laterPage).toBeGreaterThanOrEqual(1)
    })
  })
})
