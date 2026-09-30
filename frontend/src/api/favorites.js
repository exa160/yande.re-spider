import api from './index'

/**
 * 收藏夹 API 封装
 */

// 获取所有收藏夹
export function getAllFolders() {
  return api.get('/favorites')
}

// 获取收藏夹及精简预览元数据（分页 + 关键字搜索 + 预览图顺序 + 是否包含在线图）
export function getFoldersWithPreview(
  page = 1,
  pageSize = 20,
  tileSize = 'adaptive',
  keyword = '',
  previewOrder = 'random',
  includeOnline = false
) {
  const params = new URLSearchParams({
    page,
    page_size: pageSize,
    tile_size: tileSize,
    preview_order: previewOrder,
  })
  if (keyword) params.set('keyword', keyword)
  if (includeOnline) params.set('include_online', 'true')
  return api.get(`/favorites/with-preview?${params.toString()}`)
}

// 获取单个收藏夹详情
export function getFolder(folderId) {
  return api.get(`/favorites/${folderId}`)
}

// 创建收藏夹
export function createFolder(data) {
  return api.post('/favorites', data)
}

// 更新收藏夹
export function updateFolder(folderId, data) {
  return api.put(`/favorites/${folderId}`, data)
}

// 删除收藏夹
export function deleteFolder(folderId) {
  return api.delete(`/favorites/${folderId}`)
}

// 批量更新排序
export function reorderFolders(folderIds) {
  return api.post('/favorites/reorder', { folder_ids: folderIds })
}

// 预览收藏夹查询结果
export function previewFolder(folderId, limit = 6) {
  return api.get(`/favorites/${folderId}/preview?limit=${limit}`)
}

// 刷新在线数量（打 yande.re XML API 取该 tags 的全站总数）
// 后端带 TTL 保鲜：默认 600s 内的重复调用直接返回缓存，不打远端；
// 需要强制刷新时传 { force: true }（后端会忽略 TTL）。
export function refreshOnlineCount(folderId, params = {}) {
  return api.post(`/favorites/${folderId}/refresh-online`, null, { params })
}

/**
 * 重算收藏夹的本地数量（后端跑一次 tags LIKE + down_flag 的 COUNT）
 *
 * ⚠️ 开销随已下载库线性放大，不要在高频路径调用。
 * 需要「写入一个已知值」时用 setLocalCount（O(1)）；此函数保留给手动刷新按钮。
 */
export function updateLocalCount(folderId, count) {
  return api.post(`/favorites/${folderId}/refresh`)
}

/**
 * 直接写入收藏夹的本地图片数量 —— O(1)：后端一条 UPDATE by PK，不重算 COUNT。
 *
 * 用于「下载完成 → 收藏夹角标 +N」的增量修正：调用方自己累加出目标值再传进来。
 * 后端契约见 POST /api/v1/favorites/{folder_id}/local-count（count 为必填 query 参数）。
 *
 * @param {number} folderId
 * @param {number} count 目标值（不是增量）
 * @returns {Promise<{data: {count: number}}>}
 */
export function setLocalCount(folderId, count) {
  return api.post(`/favorites/${folderId}/local-count`, null, { params: { count } })
}

export function triggerFolderSchedule(folderId) {
  return api.post(`/favorites/${folderId}/schedule/trigger`)
}

export function getFolderScheduleStatus(folderId) {
  return api.get(`/favorites/${folderId}/schedule/status`)
}

// 重置 last_synced_id：value=null 清空，value=整数 设为该值
export function resetFolderSync(folderId, value = null) {
  return api.post(`/favorites/${folderId}/schedule/reset-sync`, { value })
}

export default {
  getAllFolders,
  getFoldersWithPreview,
  getFolder,
  createFolder,
  updateFolder,
  deleteFolder,
  reorderFolders,
  previewFolder,
  updateLocalCount,
  setLocalCount,
  refreshOnlineCount,
  triggerFolderSchedule,
  getFolderScheduleStatus,
  resetFolderSync,
}
