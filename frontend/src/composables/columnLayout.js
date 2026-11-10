/**
 * 瀑布流 / 网格的列数布局计算（纯函数，无 Vue 依赖，便于单测）
 *
 * 设计约束：
 * 1. 判据是「容器 CSS 宽度」，不是视口宽度，也不是设备物理像素。
 *    → 浏览器缩放 / 系统 DPI 缩放会自动缩小 CSS 视口，列数随之减少，
 *      磁贴在屏幕上的相对比例保持不变（不会因高分屏而变小）。
 * 2. **窄屏统一档位**：<480→1 列、<768→2 列、<1200→3 列。
 *    image 模式（图片瀑布流）与 folder 模式（收藏夹磁贴网格）共用同一套档位，
 *    手机横屏下两者列数一致（都是 3 列），不会出现「图片 3 列、收藏夹 1 列」。
 * 3. **宽屏（≥1200）按最小列宽反推**：两种模式各自一个最小列宽与上限，
 *    保证磁贴宽度不小于该模式的密度下限。
 */

// 列间距（CSS px），需与 WaterfallGallery.vue / FolderGrid.vue 的 gap 保持一致
export const COLUMN_GAP = 15

// image 模式：最小列宽（CSS px）
export const MIN_COLUMN_WIDTH = 289

// image 模式：最大列数（4K 100% 缩放时约 10 列）
export const MAX_COLUMNS = 10

// folder 模式：最小列宽（CSS px）—— 比 image 模式更宽，保证磁贴内预览格清晰可辨
export const MIN_FOLDER_COLUMN_WIDTH = 420

// folder 模式：最大列数
export const MAX_FOLDER_COLUMNS = 8

/**
 * 根据容器宽度计算列数
 *
 * 窄屏（< 1200px）：统一 1 / 2 / 3 档断点
 *   <480 → 1 | <768 → 2 | <1200 → 3
 *
 * 宽屏（≥ 1200px）：按最小列宽反推
 *   image : n 列需要 width >= n * (289 + 15) - 15 → 4→1201 … 10→3025
 *   folder: n 列需要 width >= n * (420 + 15) - 15 → 4→1201 … 8→3465
 *
 * @param {number} width 容器 CSS 宽度（px）
 * @param {'image'|'folder'} [mode='image'] 渲染模式
 * @returns {number} 列数
 */
export const getColumnCount = (width, mode = 'image') => {
  if (!Number.isFinite(width) || width <= 0) return 1

  // 窄屏统一档位（两种模式一致）
  if (width < 480) return 1
  if (width < 768) return 2
  if (width < 1200) return 3

  if (mode === 'folder') {
    const cols = Math.floor(
      (width + COLUMN_GAP) / (MIN_FOLDER_COLUMN_WIDTH + COLUMN_GAP)
    )
    return Math.min(MAX_FOLDER_COLUMNS, Math.max(4, cols))
  }

  const cols = Math.floor((width + COLUMN_GAP) / (MIN_COLUMN_WIDTH + COLUMN_GAP))
  return Math.min(MAX_COLUMNS, Math.max(4, cols))
}

/**
 * 计算指定列数下的单列宽度（CSS px）
 *
 * @param {number} width 容器 CSS 宽度（px）
 * @param {number} cols 列数
 * @returns {number} 单列宽度（px）
 */
export const getColumnWidth = (width, cols) => {
  if (!cols || cols < 1) return width
  return (width - COLUMN_GAP * (cols - 1)) / cols
}

/**
 * 实际渲染列数：列数上限受「内容数量」约束。
 *
 * 磁贴数少于列数时不再保留空列 —— 空列同样是 flex: 1 1 0 的项目，会占掉 1/N 宽度，
 * 导致磁贴被摊薄（收藏夹一级页只有 8/12/20 个磁贴时最明显）+ 右侧留大片空白。
 *
 * @param {number} cols 宽度推导出的列数
 * @param {number} itemCount 当前内容条数
 * @returns {number} 实际渲染列数
 */
export const getEffectiveColumnCount = (cols, itemCount) =>
  Math.max(1, Math.min(cols, itemCount || 1))

/**
 * 收藏夹一级页的分页切片尺寸：让「每页磁贴总数」永远是列数的整数倍。
 *
 * 背景：收藏夹磁贴高度固定（预览区 4:3 + 固定信息栏），瀑布流的「最短列优先」
 * 退化为严格轮流分配 → 只要总数不是列数的整数倍，就一定会出现「最后一行缺几块」。
 * 分页条数与列数（宽度推导）如果各自独立，就必然对不齐 → 每翻一页都缺几块。
 *
 * 现在每页条数完全由列数推导（列数 × FOLDER_PAGE_ROWS 行），**不再有用户可调的
 * 「每页个数」**：屏幕越宽列数越多，每页自动带更多行，且始终填满。
 *
 * 只有整个列表真正取完时（最后一页不满）才会缺，属于必然结果。
 */
export const FOLDER_PAGE_ROWS = 3
export const FOLDER_PAGE_MIN = 8

/**
 * 收藏夹一级页分页切片尺寸
 *
 * @param {number} cols 当前列数
 * @param {number} virtualCount 虚拟磁贴数量（0~3）
 * @returns {{block: number, firstPage: number, laterPage: number}}
 *   block     —— 每页磁贴总数（列数整数倍）
 *   firstPage —— 第 1 页真实收藏夹条数（block 扣掉置顶的虚拟磁贴）
 *   laterPage —— 第 2 页起每页真实收藏夹条数
 */
export const getFolderPageSizes = (cols, virtualCount) => {
  const c = Math.max(1, cols || 1)
  // 每页 = 列数 × 3 行；窄屏（1~2 列）时至少 8 个，避免每次滚动只加两三个
  const block = Math.max(c * FOLDER_PAGE_ROWS, FOLDER_PAGE_MIN)
  const aligned = Math.ceil(block / c) * c // 对齐到列数整数倍 → 每行都填满
  const firstPage = Math.max(1, aligned - (virtualCount || 0))
  return { block: aligned, firstPage, laterPage: aligned }
}

/**
 * 收藏夹一级页独立网格（FolderGrid）的参数。
 *
 * 收藏夹一级页不再走瀑布流（磁贴等高，瀑布流的错落高度没有收益），
 * 改为等宽 CSS Grid。列数由 JS 显式下发（grid-template-columns: repeat(N, 1fr)），
 * 而不是 CSS auto-fill —— 后者有「最小列宽硬下限」的问题：
 * 窄屏时轨道宽会超出容器（内容被裁），且列数与 JS 推算值可能不一致。
 */
export const FOLDER_GRID_GAP = COLUMN_GAP
