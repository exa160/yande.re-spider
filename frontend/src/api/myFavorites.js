/**
 * 我的最爱 API 模块
 *
 * - add / remove: 加入/取消我的最爱（POST/DELETE /api/v1/my_favorites/{image_id}）
 * - list: 分页列出我的最爱
 * - count: 总数（用于收藏夹列表前端插入磁贴的角标）
 * - getPreview: 我的最爱预览图（文件夹展示页用，独立接口）
 *
 * 路径说明：后端文件名是 `backend/src/api/v1/my_favorites.py`，由 APILoader
 * (backend/src/api/__init__.py:48-60) 自动按文件路径派生 URL 前缀
 * `/api/v1/my_favorites`（下划线，不是连字符）。
 */
import api from './index'

export const myFavoritesApi = {
  /**
   * 加入我的最爱
   * @param {number} imageId
   * @returns {Promise<void>}
   */
  add(imageId) {
    return api.post(`/my_favorites/${imageId}`)
  },

  /**
   * 取消我的最爱（幂等）
   * @param {number} imageId
   * @returns {Promise<void>}
   */
  remove(imageId) {
    return api.delete(`/my_favorites/${imageId}`)
  },

  /**
   * 分页列出我的最爱
   * @param {number} page - 页码（默认 1）
   * @param {number} pageSize - 每页条数（默认 20）
   * @returns {Promise<{total: number, data: Array}>}
   */
  list(page = 1, pageSize = 20) {
    return api.get('/my_favorites', { params: { page, page_size: pageSize } })
  },

  /**
   * 我的最爱总数
   * @returns {Promise<{count: number}>}
   */
  count() {
    return api.get('/my_favorites/count')
  },

  /**
   * 我的最爱预览图（独立接口，不复用 favorites）
   * @param {number} limit - 返回预览图数（默认 20）
   * @returns {Promise<{images: Array}>}
   */
  getPreview(limit = 20) {
    return api.get('/my_favorites/preview', { params: { limit } })
  },
}