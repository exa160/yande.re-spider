/**
 * useDownloadState 单例 composable 测试
 *
 * 覆盖三处「下载标识不更新」的修复点：
 * 1. 单图下载：markQueued → 立即「下载中」，不再乐观写 down_flag
 * 2. 批量下载：markQueued([...]) 批量打标记
 * 3. 收藏自动下载：前端未参与触发，靠 sync() 对账后端队列发现
 * 以及对账收敛：completed → 已下载、failed/cancelled → 复位未下载
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

const { apiMock } = vi.hoisted(() => ({
  apiMock: {
    get: vi.fn().mockResolvedValue({ data: { data: { active: [], finished: [] } } }),
    post: vi.fn(),
  },
}))
vi.mock('@/api', () => ({ default: apiMock }))

import { useDownloadState } from './useDownloadState'

const { sync, markQueued, reset, downStateOf, start, stop, _resetForTest } = useDownloadState()

/** 构造后端 /download/tasks/states 的响应体（axios 拦截器已剥出 response.data） */
const statesResponse = ({ active = [], finished = [] }) => ({
  data: { code: '0000', message: 'OK.', data: { active, finished } },
})

beforeEach(() => {
  _resetForTest()
  apiMock.get.mockReset()
  apiMock.get.mockResolvedValue(statesResponse({}))
  vi.useFakeTimers()
})

afterEach(() => {
  _resetForTest()
  vi.useRealTimers()
})

describe('useDownloadState — 本地乐观标记', () => {
  it('markQueued 后 downStateOf 立即为 downloading（无需等网络）', () => {
    markQueued([100])
    expect(downStateOf({ id: 100, down_flag: false })).toBe('downloading')
  })

  it('批量 markQueued 一次标记多张（批量下载场景）', () => {
    markQueued([1, 2, 3])
    expect(downStateOf({ id: 1 })).toBe('downloading')
    expect(downStateOf({ id: 2 })).toBe('downloading')
    expect(downStateOf({ id: 3 })).toBe('downloading')
    expect(downStateOf({ id: 4 })).toBe('none')
  })

  it('未标记且 down_flag=false → none（未下载）', () => {
    expect(downStateOf({ id: 200, down_flag: false })).toBe('none')
  })

  it('down_flag=true（DB 权威）→ downloaded', () => {
    expect(downStateOf({ id: 201, down_flag: true })).toBe('downloaded')
  })

  it('markQueued 无条件覆盖 downloaded（重新下载已下载的图片也要转「下载中」）', () => {
    // 先由 sync 标记为 downloaded，再次乐观标记应转为 queued
    apiMock.get.mockResolvedValueOnce(
      statesResponse({ finished: [{ image_id: 300, status: 'completed' }] })
    )
    return sync().then(() => {
      expect(downStateOf({ id: 300 })).toBe('downloaded')
      markQueued([300])
      expect(downStateOf({ id: 300 })).toBe('downloading')
    })
  })
})

describe('useDownloadState — 与后端队列对账', () => {
  it('sync 发现后端活跃任务 → downloading（收藏自动下载场景）', async () => {
    apiMock.get.mockResolvedValueOnce(
      statesResponse({
        active: [{ image_id: 400, task_id: 't1', status: 'downloading', progress: 0.42 }],
      })
    )
    await sync()
    expect(downStateOf({ id: 400, down_flag: false })).toBe('downloading')
  })

  it('sync 覆盖本地乐观标记 queued → 后端真实状态', async () => {
    markQueued([401])
    apiMock.get.mockResolvedValueOnce(
      statesResponse({
        active: [{ image_id: 401, task_id: 't2', status: 'downloading', progress: 0.1 }],
      })
    )
    await sync()
    expect(useDownloadState().states[401]).toBe('downloading')
  })

  it('sync 收到 completed → 收敛为 downloaded（DB 快照仍为 false 也能变绿点）', async () => {
    markQueued([402])
    apiMock.get.mockResolvedValueOnce(
      statesResponse({ finished: [{ image_id: 402, status: 'completed' }] })
    )
    await sync()
    expect(downStateOf({ id: 402, down_flag: false })).toBe('downloaded')
  })

  it('sync 收到 failed → 复位为 none（不会留下永久「下载中」）', async () => {
    markQueued([403])
    apiMock.get.mockResolvedValueOnce(
      statesResponse({ finished: [{ image_id: 403, status: 'failed' }] })
    )
    await sync()
    expect(downStateOf({ id: 403, down_flag: false })).toBe('none')
  })

  it('sync 收到 cancelled → 复位为 none', async () => {
    markQueued([404])
    apiMock.get.mockResolvedValueOnce(
      statesResponse({ finished: [{ image_id: 404, status: 'cancelled' }] })
    )
    await sync()
    expect(downStateOf({ id: 404 })).toBe('none')
  })

  it('paused 状态既不是 downloading 也不是 downloaded', async () => {
    apiMock.get.mockResolvedValueOnce(
      statesResponse({
        active: [{ image_id: 405, task_id: 't5', status: 'paused', progress: 0.5 }],
      })
    )
    await sync()
    expect(downStateOf({ id: 405 })).toBe('paused')
  })

  it('响应体缺字段 / 结构异常时不抛错（降级为空快照）', async () => {
    apiMock.get.mockResolvedValueOnce({ data: {} })
    await expect(sync()).resolves.toBe(true)
    apiMock.get.mockResolvedValueOnce({ data: { data: null } })
    await expect(sync()).resolves.toBe(true)
  })

  it('网络异常时静默失败，保留本地标记等待下一轮', async () => {
    markQueued([406])
    apiMock.get.mockRejectedValueOnce(new Error('network down'))
    await expect(sync()).resolves.toBe(false)
    expect(downStateOf({ id: 406 })).toBe('downloading')
  })

  it('请求带终态回看窗口 finished_window=300（大于最长可能的隐藏时间）', async () => {
    await sync()
    expect(apiMock.get).toHaveBeenCalledWith('/download/tasks/states', {
      params: { finished_window: 300 },
    })
  })

  it('兜底回收：后端长期不再上报且无终态记录 → 解除「下载中」，不会永久卡住', async () => {
    vi.setSystemTime(new Date('2026-01-01T00:00:00Z'))
    markQueued([407])
    // 后端队列与终态窗口都查不到它（模拟页面长时间隐藏期间任务已结束）
    apiMock.get.mockResolvedValue(statesResponse({}))
    await sync()
    expect(downStateOf({ id: 407 })).toBe('downloading') // 刚标记，还没到阈值

    vi.setSystemTime(new Date('2026-01-01T00:03:00Z')) // 3 分钟 > STALE_MS
    await sync()
    expect(downStateOf({ id: 407 })).toBe('none')
  })

  it('后端持续上报活跃任务时不触发兜底回收（长图下载不会被误判）', async () => {
    vi.setSystemTime(new Date('2026-01-01T00:00:00Z'))
    markQueued([408])
    apiMock.get.mockResolvedValue(
      statesResponse({
        active: [{ image_id: 408, task_id: 't', status: 'downloading', progress: 0.1 }],
      })
    )
    vi.setSystemTime(new Date('2026-01-01T00:10:00Z'))
    await sync()
    expect(downStateOf({ id: 408 })).toBe('downloading')
  })

  it('paused 任务在下载页被删除后同样会被兜底回收（不会永久停在「已暂停」）', async () => {
    vi.setSystemTime(new Date('2026-01-01T00:00:00Z'))
    apiMock.get.mockResolvedValueOnce(
      statesResponse({
        active: [{ image_id: 409, task_id: 't', status: 'paused', progress: 0.3 }],
      })
    )
    await sync()
    expect(downStateOf({ id: 409 })).toBe('paused')

    vi.setSystemTime(new Date('2026-01-01T00:05:00Z'))
    apiMock.get.mockResolvedValue(statesResponse({}))
    await sync()
    expect(downStateOf({ id: 409 })).toBe('none')
  })
})

// =============================================================================
// 下载完成订阅：收藏夹角标按「新增张数」增量修正（不走 /favorites/{id}/refresh 的 COUNT）
// =============================================================================
describe('useDownloadState — 下载完成订阅（收藏夹角标增量用）', () => {
  const { onCompleted, sync, markQueued, _resetForTest } = useDownloadState()

  beforeEach(() => {
    _resetForTest()
  })

  it('queued → completed 触发一次 onCompleted([id])', async () => {
    const handler = vi.fn()
    onCompleted(handler)
    markQueued([410])
    apiMock.get.mockResolvedValueOnce(
      statesResponse({ finished: [{ image_id: 410, status: 'completed' }] })
    )
    await sync()
    expect(handler).toHaveBeenCalledTimes(1)
    expect(handler).toHaveBeenCalledWith([410])
  })

  it('终态回看窗口内重复回放同一条 completed → 不重复通知（否则角标会多加）', async () => {
    const handler = vi.fn()
    onCompleted(handler)
    apiMock.get.mockResolvedValue(
      statesResponse({ finished: [{ image_id: 411, status: 'completed' }] })
    )
    await sync()
    await sync()
    await sync()
    expect(handler).toHaveBeenCalledTimes(1)
  })

  it('一轮内多张完成 → 一次通知带全部 id（failed 不在其中）', async () => {
    const handler = vi.fn()
    onCompleted(handler)
    apiMock.get.mockResolvedValueOnce(
      statesResponse({
        finished: [
          { image_id: 412, status: 'completed' },
          { image_id: 413, status: 'completed' },
          { image_id: 414, status: 'failed' },
        ],
      })
    )
    await sync()
    expect(handler).toHaveBeenCalledTimes(1)
    expect(handler).toHaveBeenCalledWith([412, 413])
  })

  it('退订后不再收到通知', async () => {
    const handler = vi.fn()
    const off = onCompleted(handler)
    off()
    apiMock.get.mockResolvedValueOnce(
      statesResponse({ finished: [{ image_id: 415, status: 'completed' }] })
    )
    await sync()
    expect(handler).not.toHaveBeenCalled()
  })

  it('订阅者抛错不影响轮询（sync 仍返回 true 且状态已更新）', async () => {
    onCompleted(() => {
      throw new Error('handler boom')
    })
    apiMock.get.mockResolvedValueOnce(
      statesResponse({ finished: [{ image_id: 416, status: 'completed' }] })
    )
    await expect(sync()).resolves.toBe(true)
    expect(downStateOf({ id: 416 })).toBe('downloaded')
  })
})

describe('useDownloadState — 轮询生命周期', () => {
  it('start 立即对账一次并按 2s 轮询（有进行中任务）', async () => {
    markQueued([500])
    start()
    expect(apiMock.get).toHaveBeenCalledTimes(1)

    await vi.advanceTimersByTimeAsync(1999)
    expect(apiMock.get).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(1)
    expect(apiMock.get).toHaveBeenCalledTimes(2)
    stop()
  })

  it('空闲时轮询节奏放慢到 5s', async () => {
    start()
    expect(apiMock.get).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(2000)
    expect(apiMock.get).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(3000)
    expect(apiMock.get).toHaveBeenCalledTimes(2)
    stop()
  })

  it('引用计数：多个组件 start 只建一个定时器，全部 stop 后才清理', async () => {
    start()
    start()
    await vi.advanceTimersByTimeAsync(5000)
    // 两次 start 只触发一次立即对账 + 一个定时器
    expect(apiMock.get).toHaveBeenCalledTimes(2)

    // 引用计数仍为 1（另一个消费者未卸载）→ 继续轮询
    stop()
    await vi.advanceTimersByTimeAsync(5000)
    expect(apiMock.get).toHaveBeenCalledTimes(3)

    // 归零 → 定时器清理，之后不再请求
    stop()
    await vi.advanceTimersByTimeAsync(10000)
    expect(apiMock.get).toHaveBeenCalledTimes(3)
  })

  it('reset 清掉本地标记（回到未下载）', () => {
    markQueued([600])
    reset([600])
    expect(downStateOf({ id: 600 })).toBe('none')
  })
})
