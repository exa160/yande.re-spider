/**
 * recentDownloadsApi 路径契约测试
 *
 * 后端路由由 APILoader (backend/src/api/__init__.py:48-60) 按文件路径
 * `api/v1/recent_downloads` 派生前缀 `/api/v1/recent_downloads`（下划线，不是连字符）。
 *
 * axios baseURL 已经是 `/api/v1`，所以本模块每个方法传的路径应为
 * `/recent_downloads/...`。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('./index', () => {
  const api = {
    get: vi.fn(() => Promise.resolve({ data: { images: [], count: 0 } })),
    post: vi.fn(() => Promise.resolve({ data: { deleted: 0 } })),
  }
  return { default: api }
})

import api from './index'
import { recentDownloadsApi } from './recentDownloads'

beforeEach(() => {
  vi.mocked(api.get).mockClear()
  vi.mocked(api.post).mockClear()
})

describe('recentDownloadsApi', () => {
  it('getCount() → GET /recent_downloads/count', () => {
    recentDownloadsApi.getCount()
    expect(api.get).toHaveBeenCalledWith('/recent_downloads/count')
  })

  it('getPreview(8) → GET /recent_downloads/preview?limit=8', () => {
    recentDownloadsApi.getPreview(8)
    expect(api.get).toHaveBeenCalledWith('/recent_downloads/preview', { params: { limit: 8 } })
  })

  it('getPreview() 默认 limit=8', () => {
    recentDownloadsApi.getPreview()
    expect(api.get).toHaveBeenCalledWith('/recent_downloads/preview', { params: { limit: 8 } })
  })

  it('clear({mode:"all"}) → POST /recent_downloads/clear', () => {
    recentDownloadsApi.clear({ mode: 'all' })
    expect(api.post).toHaveBeenCalledWith('/recent_downloads/clear', { mode: 'all' })
  })

  it('clear({mode:"before_days", days:30}) → 原样透传 payload', () => {
    recentDownloadsApi.clear({ mode: 'before_days', days: 30 })
    expect(api.post).toHaveBeenCalledWith('/recent_downloads/clear', { mode: 'before_days', days: 30 })
  })
})
