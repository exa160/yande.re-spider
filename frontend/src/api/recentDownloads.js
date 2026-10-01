/**
 * 最近下载 API 模块
 *
 * - getCount: 已完成下载任务涉及的去重图片数（磁贴角标，COUNT(DISTINCT image_id)）
 * - getPreview: 最近下载磁贴的预览图元数据（文件夹展示页用，独立接口）
 * - clear: 清除下载完成记录（按天数 / 全清），只删任务日志，不删图片文件
 *
 * 路径说明：后端文件是 `backend/src/api/v1/recent_downloads.py`，由 APILoader
 * (backend/src/api/__init__.py:48-60) 自动按文件路径派生 URL 前缀
 * `/api/v1/recent_downloads`（下划线，不是连字符）。
 *
 * 响应结构对齐 `/api/v1/random_browse/preview`（MyFavoritePreviewResponse）：
 * { code, message, data: { images: [...] } }，前端 useFavoriteFoldersList
 * 可复用同一套解析逻辑，FolderTile 也可直接复用渲染。
 */
import api from './index'

export const recentDownloadsApi = {
  /**
   * 最近下载去重图片数（已完成任务 GROUP BY image_id 取 MAX(completed_at)）
   * @returns {Promise<{count: number}>}
   */
  getCount() {
    return api.get('/recent_downloads/count')
  },

  /**
   * 最近下载预览图（按 MAX(completed_at) DESC 取前 N 张）
   * @param {number} limit - 返回预览图数（默认 8）
   * @returns {Promise<{images: Array}>}
   */
  getPreview(limit = 8) {
    return api.get('/recent_downloads/preview', { params: { limit } })
  },

  /**
   * 清除已完成下载记录
   * @param {{mode: 'before_days'|'all', days?: number}} payload -
   *        mode='before_days' 时 days 必填（清除 N 天前的记录）；mode='all' 清空全部
   * @returns {Promise<{deleted: number}>}
   */
  clear(payload) {
    return api.post('/recent_downloads/clear', payload)
  },
}

export default recentDownloadsApi
