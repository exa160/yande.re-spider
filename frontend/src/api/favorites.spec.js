/**
 * favorites API 路径契约测试
 *
 * 重点是「贵/便宜」分界与已删除的接口：
 * - setLocalCount → /local-count（O(1)：一条 UPDATE by PK）
 * - updateLocalCount → /refresh（重跑 tags LIKE + COUNT，昂贵，仅留给手动刷新）
 * - refreshOnlineCount → /refresh-online（打 yande.re，后端带 600s TTL 兜底）
 * - updateOnlineCount → /online-count **已删除**（零调用点，避免有人手写一个陈旧值覆盖真实计数）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('./index', () => {
  const api = {
    get: vi.fn(() => Promise.resolve({ data: {} })),
    post: vi.fn(() => Promise.resolve({ data: { count: 0 } })),
  }
  return { default: api }
})

import api from './index'
import * as favoritesApi from './favorites'
import { setLocalCount, updateLocalCount, refreshOnlineCount } from './favorites'

beforeEach(() => {
  vi.mocked(api.post).mockClear()
})

describe('favorites API — 本地数量写入', () => {
  it('setLocalCount(7, 123) → POST /favorites/7/local-count?count=123（O(1) 增量路径）', () => {
    setLocalCount(7, 123)
    expect(api.post).toHaveBeenCalledWith('/favorites/7/local-count', null, {
      params: { count: 123 },
    })
  })

  it('setLocalCount 不打 /refresh（那会触发全表 COUNT）', () => {
    setLocalCount(7, 0)
    expect(api.post.mock.calls[0][0]).not.toContain('/refresh')
  })

  it('updateLocalCount 仍走 /refresh（重算 COUNT，仅供手动刷新使用）', () => {
    updateLocalCount(7, 999)
    expect(api.post).toHaveBeenCalledWith('/favorites/7/refresh')
  })
})

describe('favorites API — 在线数量刷新', () => {
  it('refreshOnlineCount(7) → POST /favorites/7/refresh-online（不带参数由后端吃默认 TTL）', () => {
    refreshOnlineCount(7)
    expect(api.post).toHaveBeenCalledWith('/favorites/7/refresh-online', null, { params: {} })
  })

  it('refreshOnlineCount(7, { force: true }) → 透传 force 以跳过 TTL', () => {
    refreshOnlineCount(7, { force: true })
    expect(api.post).toHaveBeenCalledWith('/favorites/7/refresh-online', null, {
      params: { force: true },
    })
  })
})

describe('favorites API — 已删除的死接口', () => {
  it('updateOnlineCount 不再导出（后端 /online-count 端点已删除）', () => {
    expect(favoritesApi.updateOnlineCount).toBeUndefined()
    expect(favoritesApi.default.updateOnlineCount).toBeUndefined()
  })
})
