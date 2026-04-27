import api from './index'

export const tagCacheApi = {
  // 标签刷新
  refreshTags(params = {}) {
    return api.post('/tag-cache/refresh-tags', params)
  },

  // 艺术家刷新
  refreshArtists(params = {}) {
    return api.post('/tag-cache/refresh-artists', params)
  },

  // 标签统计
  getTagsStats() {
    return api.get('/tag-cache/tags/stats')
  },

  // 艺术家统计
  getArtistsStats() {
    return api.get('/tag-cache/artists/stats')
  },

  // 搜索标签
  searchTags(keyword, limit = 20) {
    return api.get('/tag-cache/tags/search', { params: { keyword, limit } })
  },

  // 搜索艺术家
  searchArtists(keyword, limit = 20) {
    return api.get('/tag-cache/artists/search', { params: { keyword, limit } })
  },

  // 计算本地标签统计
  calculateLocalStats() {
    return api.post('/tag-cache/tags/calculate-local-stats')
  },

  // 获取标签列表（带本地统计）
  getTagsWithStats(params = {}) {
    return api.get('/tag-cache/tags/with-stats', { params })
  },

  // 根据名称批量获取标签类型
  getTagsByNames(names) {
    return api.get('/tag-cache/tags/by-names', { params: { names } })
  },
}