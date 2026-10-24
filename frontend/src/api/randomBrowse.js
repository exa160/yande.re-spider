/**
 * 随机浏览 API 模块
 *
 * - getCount: 随机浏览候选池总数（本地已下载图片数，磁贴角标）
 * - getPreview: 随机浏览磁贴的预览图元数据（文件夹展示页用，独立接口）
 * - createRandomSeed: 生成预览/瀑布流共享的随机种子
 *
 * 路径说明：后端文件是 `backend/src/api/v1/random_browse.py`，由 APILoader
 * (backend/src/api/__init__.py:48-60) 自动按文件路径派生 URL 前缀
 * `/api/v1/random_browse`（下划线，不是连字符）。
 *
 * 响应结构对齐 `/api/v1/my_favorites/preview`（MyFavoritePreviewResponse）：
 * { code, message, data: { images: [...] } }，前端 useFavoriteFoldersList
 * 可复用同一套解析逻辑。
 */
import api from './index'

// 后端 random_seed 的范围是 [0, 2^31-1)
const RANDOM_SEED_MAX = 2147483647

/**
 * 生成随机浏览 seed。
 *
 * 磁贴预览和瀑布流共用同一个 seed，后端据此做确定性排序，
 * 保证「预览里的 N 张图 = 瀑布流顺序的前 N 张」。
 * @returns {number} 0 ~ 2147483646 的整数
 */
export function createRandomSeed() {
  return Math.floor(Math.random() * RANDOM_SEED_MAX)
}

export const randomBrowseApi = {
  /**
   * 随机浏览候选池总数（down_flag=True 的本地图片数）
   * @returns {Promise<{count: number}>}
   */
  getCount() {
    return api.get('/random_browse/count')
  },

  /**
   * 随机浏览预览图
   *
   * 传 seed 时按确定性顺序返回；不传则每次随机（兼容旧调用方）。
   * @param {number} limit - 返回预览图数（默认 8）
   * @param {number} [seed] - 与瀑布流 random_seed 共享的随机种子
   * @returns {Promise<{images: Array}>}
   */
  getPreview(limit = 8, seed) {
    const params = { limit }
    if (seed !== undefined && seed !== null) {
      params.seed = seed
    }
    return api.get('/random_browse/preview', { params })
  },
}

export default randomBrowseApi