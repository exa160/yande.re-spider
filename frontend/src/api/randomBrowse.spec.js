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
import { createRandomSeed, randomBrowseApi } from './randomBrowse'

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

  it('getPreview(8, seed) → 带上 seed（与瀑布流 random_seed 共享）', () => {
    randomBrowseApi.getPreview(8, 123456)
    expect(api.get).toHaveBeenCalledWith('/random_browse/preview', {
      params: { limit: 8, seed: 123456 },
    })
  })

  it('getPreview(8, 0) → seed=0 也必须透传（不是 falsy 判断）', () => {
    randomBrowseApi.getPreview(8, 0)
    expect(api.get).toHaveBeenCalledWith('/random_browse/preview', {
      params: { limit: 8, seed: 0 },
    })
  })
})

describe('createRandomSeed', () => {
  it('返回 [0, 2^31-1) 内的整数', () => {
    for (let i = 0; i < 20; i++) {
      const seed = createRandomSeed()
      expect(Number.isInteger(seed)).toBe(true)
      expect(seed).toBeGreaterThanOrEqual(0)
      expect(seed).toBeLessThan(2147483647)
    }
  })
})