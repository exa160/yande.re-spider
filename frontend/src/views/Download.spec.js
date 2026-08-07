import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import api from '@/api'
import Download from './Download.vue'

/**
 * Bug 2: Download.vue 轮询关闭后又启动
 *
 * 给定 onMounted 是 async + 用户快速打开→关闭 dialog 时：
 *   1. onMounted 启动 → await loadTasks（永远不 resolve）
 *   2. 关闭 dialog → onUnmounted → stopPolling（pollTimer=null）
 *   3. await 永不完成，但若改成 sync 后 startPolling 应在 mount 阶段被调
 *   → 验证修复后 unmount 不留孤儿 setInterval
 */

const HANG_FOREVER = () => new Promise(() => {})
const EMPTY_RESPONSE = { data: { data: [], total: 0 } }

const TABLE_NOOP = {
  name: 'ElTableColumn',
  template: '<div></div>',
}

describe('Download.vue 轮询生命周期', () => {
  let intervalRegistry

  beforeEach(() => {
    intervalRegistry = new Map()
    let nextId = 0
    vi.spyOn(globalThis, 'setInterval').mockImplementation((fn) => {
      const id = ++nextId
      intervalRegistry.set(id, { fn, cleared: false })
      return id
    })
    vi.spyOn(globalThis, 'clearInterval').mockImplementation((id) => {
      const entry = intervalRegistry.get(id)
      if (entry) entry.cleared = true
    })

    vi.spyOn(api, 'get').mockImplementation(() => Promise.resolve(EMPTY_RESPONSE))
    vi.spyOn(api, 'post').mockImplementation(HANG_FOREVER)
    vi.spyOn(api, 'delete').mockImplementation(HANG_FOREVER)
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  const activeIntervalCount = () =>
    Array.from(intervalRegistry.values()).filter((i) => !i.cleared).length

  const factory = () =>
    mount(Download, {
      global: {
        directives: { loading: () => {} },
        stubs: {
          ElTable: { template: '<div><slot/></div>' },
          ElTableColumn: TABLE_NOOP,
          ElTabs: { template: '<div><slot/></div>' },
          ElTabPane: { template: '<div><slot/></div>' },
          ElBadge: { template: '<span><slot/></span>' },
          ElButton: { template: '<button><slot/></button>' },
          ElIcon: { template: '<i></i>' },
          ElTag: { template: '<span><slot/></span>' },
          ElProgress: { template: '<div></div>' },
          ElPagination: { template: '<div></div>' },
          ElEmpty: { template: '<div><slot/></div>' },
          ElDialog: { template: '<div><slot/></div>' },
          Refresh: { template: '<i></i>' },
          Search: { template: '<i></i>' },
          ArrowDown: { template: '<i></i>' },
          CaretBottom: { template: '<i></i>' },
        },
      },
    })

  it('mount 后立即 unmount 不应留下孤儿 setInterval', async () => {
    const wrapper = factory()
    await wrapper.vm.$nextTick()

    wrapper.unmount()
    await flushPromises()
    await new Promise((r) => setTimeout(r, 50))

    expect(activeIntervalCount()).toBe(0)
  })

  it('onMounted 同步阶段必须启动轮询，不依赖 loadTasks 完成', async () => {
    const wrapper = factory()
    await wrapper.vm.$nextTick()
    await new Promise((r) => setTimeout(r, 10))

    expect(activeIntervalCount()).toBe(1)
  })
})