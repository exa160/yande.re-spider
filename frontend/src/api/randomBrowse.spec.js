/**
 * randomBrowseApi 路径契约测试
 *
 * 后端路由由 APILoader (backend/src/api/__init__.py:48-60) 按文件路径
 * `api/v1/random_browse` 派生前缀 `/api/v1/random_browse`（下划线，不是连字符）。
 *
 * axios baseURL 已经是 `/api/v1`，所以本模块每个方法传的路径应为
 * `/random_browse/...`。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('./index', () => {
  const api = {
    get: vi.fn(() => Promise.resolve({ data: { images: [], count: 0 } })),
  }
  return { default: api }
})

import api from './index'
import { randomBrowseApi } from './randomBrowse'

beforeEach(() => {
  vi.mocked(api.get).mockClear()
})

describe('randomBrowseApi', () => {
  it('getCount() → GET /random_browse/count', () => {
    randomBrowseApi.getCount()
    expect(api.get).toHaveBeenCalledWith('/random_browse/count')
  })
  it('getPreview(8) → GET /random_browse/preview?limit=8', () => {
    randomBrowseApi.getPreview(8)
    expect(api.get).toHaveBeenCalledWith('/random_browse/preview', { params: { limit: 8 } })
  })

  it('getPreview() 默认 limit=8', () => {
    randomBrowseApi.getPreview()
    expect(api.get).toHaveBeenCalledWith('/random_browse/preview', { params: { limit: 8 } })
  })

  it('getPreview(20) → GET /random_browse/preview?limit=20', () => {
    randomBrowseApi.getPreview(20)
    expect(api.get).toHaveBeenCalledWith('/random_browse/preview', { params: { limit: 20 } })
  })
})