/**
 * 随机浏览 API 模块
 *
 * - getCount: 随机浏览候选池总数（本地已下载图片数，磁贴角标）
 * - getPreview: 随机浏览磁贴的预览图元数据（文件夹展示页用，独立接口）
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

export const randomBrowseApi = {
  /**
   * 随机浏览候选池总数（down_flag=True 的本地图片数）
   * @returns {Promise<{count: number}>}
   */
  getCount() {
    return api.get('/random_browse/count')
  },

  /**
   * 随机浏览预览图（每次返回不同随机序列；无 seed）
   * @param {number} limit - 返回预览图数（默认 8）
   * @returns {Promise<{images: Array}>}
   */
  getPreview(limit = 8) {
    return api.get('/random_browse/preview', { params: { limit } })
  },
}

export default randomBrowseApi