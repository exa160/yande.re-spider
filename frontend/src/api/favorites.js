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

// 更新在线数量
export function updateOnlineCount(folderId, count) {
  return api.post(`/favorites/${folderId}/online-count?count=${count}`)
}

// 更新本地数量
export function updateLocalCount(folderId, count) {
  return api.post(`/favorites/${folderId}/refresh`)
}

// 从 yande API 刷新在线数量
export function refreshOnlineCount(folderId) {
  return api.post(`/favorites/${folderId}/refresh-online`)
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
  updateOnlineCount,
  updateLocalCount,
  refreshOnlineCount,
  triggerFolderSchedule,
  getFolderScheduleStatus,
  resetFolderSync,
}
