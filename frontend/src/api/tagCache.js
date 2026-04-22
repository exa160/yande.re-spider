import api from './index'

export const tagCacheApi = {
  refreshTags(params = {}) {
    return api.post('/tag_cache/refresh-tags', params)
  },

  refreshArtists(params = {}) {
    return api.post('/tag_cache/refresh-artists', params)
  },

  getTagsStats() {
    return api.get('/tag_cache/tags/stats')
  },

  getArtistsStats() {
    return api.get('/tag_cache/artists/stats')
  },

  searchTags(keyword, limit = 20) {
    return api.get('/tag_cache/tags/search', { params: { keyword, limit } })
  },

  searchArtists(keyword, limit = 20) {
    return api.get('/tag_cache/artists/search', { params: { keyword, limit } })
  },

  calculateLocalStats() {
    return api.post('/tag_cache/tags/calculate-local-stats')
  },

  getTagsWithStats(params = {}) {
    return api.get('/tag_cache/tags/with-stats', { params })
  },
}
