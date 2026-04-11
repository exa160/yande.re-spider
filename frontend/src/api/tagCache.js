import api from './index'

export const tagCacheApi = {
  refreshTags(params = {}) {
    return api.post('/tag-cache/refresh-tags', params)
  },

  refreshArtists(params = {}) {
    return api.post('/tag-cache/refresh-artists', params)
  },

  getTagsStats() {
    return api.get('/tag-cache/tags/stats')
  },

  getArtistsStats() {
    return api.get('/tag-cache/artists/stats')
  },

  searchTags(keyword, limit = 20) {
    return api.get('/tag-cache/tags/search', { params: { keyword, limit } })
  },

  searchArtists(keyword, limit = 20) {
    return api.get('/tag-cache/artists/search', { params: { keyword, limit } })
  },
}
