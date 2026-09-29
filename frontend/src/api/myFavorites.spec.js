/**
 * myFavoritesApi 路径契约测试
 *
 * 后端路由由 APILoader (backend/src/api/__init__.py:48-60) 按文件路径
 * `api/v1/my_favorites` 派生前缀 `/api/v1/my_favorites`（下划线）。
 *
 * axios baseURL 已经是 `/api/v1`，所以本模块每个方法传的路径应为
 * `/my_favorites/...`（不要带连字符，否则 404）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('./index', () => {
  const api = {
    post: vi.fn(() => Promise.resolve({ data: { message: 'ok' } })),
    delete: vi.fn(() => Promise.resolve({ data: { message: 'ok' } })),
    get: vi.fn(() => Promise.resolve({ data: { total: 0, count: 0, images: [] } })),
  }
  return { default: api }
})

import api from './index'
import { myFavoritesApi } from './myFavorites'

beforeEach(() => {
  vi.mocked(api.post).mockClear()
  vi.mocked(api.delete).mockClear()
  vi.mocked(api.get).mockClear()
})

describe('myFavoritesApi', () => {
  it('add(42) posts to /my_favorites/42 (underscore, matching APILoader)', () => {
    myFavoritesApi.add(42)
    expect(api.post).toHaveBeenCalledWith('/my_favorites/42')
  })

  it('remove(1265019) deletes /my_favorites/1265019 (regression: hotfix-2 404)', () => {
    myFavoritesApi.remove(1265019)
    expect(api.delete).toHaveBeenCalledWith('/my_favorites/1265019')
  })

  it('list() gets /my_favorites with page params', () => {
    myFavoritesApi.list(2, 30)
    expect(api.get).toHaveBeenCalledWith('/my_favorites', { params: { page: 2, page_size: 30 } })
  })

  it('count() gets /my_favorites/count', () => {
    myFavoritesApi.count()
    expect(api.get).toHaveBeenCalledWith('/my_favorites/count')
  })

  it('getPreview(20) gets /my_favorites/preview?limit=20', () => {
    myFavoritesApi.getPreview(20)
    expect(api.get).toHaveBeenCalledWith('/my_favorites/preview', { params: { limit: 20 } })
  })

  it('regression: no path uses hyphen /my-favorites (would 404 against APILoader)', () => {
    const allCalls = [
      ...vi.mocked(api.post).mock.calls,
      ...vi.mocked(api.delete).mock.calls,
      ...vi.mocked(api.get).mock.calls,
    ]
    const urls = allCalls.map(c => c[0])
    urls.forEach(url => {
      expect(url).not.toMatch(/^\/my-favorites/)
    })
  })
})