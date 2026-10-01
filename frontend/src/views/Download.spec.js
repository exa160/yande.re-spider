import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '@/api'
import { recentDownloadsApi } from '@/api/recentDownloads'
import Download from './Download.vue'

/**
 * Download.vue 轮询生命周期：**按需启停**
 *
 * 2026-10-01 起不再「进 active/all 页签就无条件 2s 轮询整页任务列表」。
 * 现在由 counts.running（pending + downloading，**不含 paused**）决定：
 *   - 有正在跑的任务 → 每 2s
 *   - 0 个 → 定时器完全停掉，0 请求
 *
 * 覆盖两个方向：0 任务挂载不起定时器 / 有任务挂载起定时器且 counts 归零后被清掉。
 */

const HANG_FOREVER = () => new Promise(() => {})
const EMPTY_RESPONSE = { data: { data: [], total: 0 } }

const TABLE_NOOP = {
  name: 'ElTableColumn',
  template: '<div></div>',
}

/** 构造 /download/tasks/count 的响应（running 决定轮询开关） */
const countsResponse = ({ pending = 0, downloading = 0, paused = 0 } = {}) => ({
  data: {
    data: {
      pending, downloading, paused,
      completed: 0, failed: 0, cancelled: 0,
    },
  },
})

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

    vi.spyOn(api, 'get').mockImplementation((url) => {
      if (url === '/download/tasks/count') return Promise.resolve(countsResponse())
      return Promise.resolve(EMPTY_RESPONSE)
    })
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
          // 清除入口默认不在 active 页签渲染，但组件名仍会被解析，补 stub 免得刷警告
          ElPopover: {
            name: 'ElPopover',
            template: '<div class="popover-stub"><slot/><slot name="reference"/></div>',
          },
          ElSelect: { template: '<div class="el-select-stub"><slot/></div>' },
          ElOption: {
            props: ['label', 'value'],
            template: '<div class="el-option-stub" :data-value="value">{{ label }}</div>',
          },
          Refresh: { template: '<i></i>' },
          Delete: { template: '<i></i>' },
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

  it('counts.running=0 → 挂载后完全不起定时器（空闲零请求）', async () => {
    const wrapper = factory()
    await flushPromises()
    await new Promise((r) => setTimeout(r, 50))

    expect(activeIntervalCount()).toBe(0)
    wrapper.unmount()
  })

  it('counts.running>0 → 定时器启动', async () => {
    vi.mocked(api.get).mockImplementation((url) => {
      if (url === '/download/tasks/count') {
        return Promise.resolve(countsResponse({ downloading: 1 }))
      }
      return Promise.resolve(EMPTY_RESPONSE)
    })

    const wrapper = factory()
    await flushPromises()
    await new Promise((r) => setTimeout(r, 50))

    expect(activeIntervalCount()).toBe(1)
    wrapper.unmount()
  })

  it('仅有 paused 任务不算 running → 不起定时器（进度不会动）', async () => {
    vi.mocked(api.get).mockImplementation((url) => {
      if (url === '/download/tasks/count') {
        return Promise.resolve(countsResponse({ paused: 3 }))
      }
      return Promise.resolve(EMPTY_RESPONSE)
    })

    const wrapper = factory()
    await flushPromises()
    await new Promise((r) => setTimeout(r, 50))

    expect(activeIntervalCount()).toBe(0)
    wrapper.unmount()
  })

  it('运行中 → 全部完成后定时器被清掉', async () => {
    vi.mocked(api.get).mockImplementation((url) => {
      if (url === '/download/tasks/count') {
        return Promise.resolve(countsResponse({ downloading: 1 }))
      }
      return Promise.resolve(EMPTY_RESPONSE)
    })

    const wrapper = factory()
    await flushPromises()
    await new Promise((r) => setTimeout(r, 50))
    expect(activeIntervalCount()).toBe(1)

    // 任务跑完，counts 归零 → loadCounts 的 finally 里 syncPolling 停掉定时器
    vi.mocked(api.get).mockImplementation((url) => {
      if (url === '/download/tasks/count') return Promise.resolve(countsResponse())
      return Promise.resolve(EMPTY_RESPONSE)
    })
    await wrapper.vm.loadCounts()
    await flushPromises()

    expect(activeIntervalCount()).toBe(0)
    wrapper.unmount()
  })

  it('卸载后 loadCounts 迟到 → 不得再 setInterval（孤儿定时器回归测试）', async () => {
    // 复现：挂载时 tasks/count 请求在途 → 用户立刻关掉 dialog →
    // onUnmounted 的 stopPolling 跑完 → 请求才 resolve → finally 里 syncPolling
    // 若没有卸载闸门，就会 setInterval 出一个永远没人清的定时器
    let releaseCounts
    vi.mocked(api.get).mockImplementation((url) => {
      if (url === '/download/tasks/count') {
        return new Promise((resolve) => {
          releaseCounts = () => resolve(countsResponse({ downloading: 1 }))
        })
      }
      return Promise.resolve(EMPTY_RESPONSE)
    })

    const wrapper = factory()
    await wrapper.vm.$nextTick()

    wrapper.unmount()
    expect(activeIntervalCount()).toBe(0)

    // 请求现在才回来，且此时 counts.running=1（满足轮询条件）
    releaseCounts()
    await flushPromises()
    await new Promise((r) => setTimeout(r, 50))

    expect(activeIntervalCount()).toBe(0)
  })

  it('loadCounts 失败 → 不拿陈旧 counts 重新裁决（避免误停轮询后卡死）', async () => {
    // 先以 running=1 建立「正在轮询」的状态
    vi.mocked(api.get).mockImplementation((url) => {
      if (url === '/download/tasks/count') {
        return Promise.resolve(countsResponse({ downloading: 1 }))
      }
      return Promise.resolve(EMPTY_RESPONSE)
    })
    const wrapper = factory()
    await flushPromises()
    await new Promise((r) => setTimeout(r, 50))
    expect(activeIntervalCount()).toBe(1)

    // 断网：此时 counts 里 running 仍是旧的 1。若用旧值重新裁决没问题，
    // 但真正危险的是反向——旧值 0 而实际在跑。这里验证「失败不裁决」这个契约
    vi.mocked(api.get).mockImplementation((url) => {
      if (url === '/download/tasks/count') return Promise.reject(new Error('net down'))
      return Promise.resolve(EMPTY_RESPONSE)
    })
    await wrapper.vm.loadCounts()
    await flushPromises()

    // 保守维持：定时器没被误停
    expect(activeIntervalCount()).toBe(1)
    wrapper.unmount()
  })
})

/**
 * 清除下载完成记录 —— 图标按钮 + 小弹窗 + 弹窗内二次点击确认
 *
 * 设计（2026-10-01 重做）：
 *   - 入口收成刷新按钮旁边的一个图标按钮，不再平铺下拉 + 两个大按钮
 *   - 点开是 el-popover 小弹窗，选范围（7/30/90 天前 · 全部）后点「清除」
 *   - **第一次点「清除」只进入待确认态，不发请求**；5 秒内第二次点击才执行
 *   - 入口只在「全部 / 已完成」两个页签出现，且 completed=0 时禁用
 */
describe('Download.vue 清除记录弹窗', () => {
  const EMPTY = { data: { data: [], total: 0 } }

  const countsWith = (completed) => ({
    data: {
      data: {
        pending: 0, downloading: 0, paused: 0,
        completed, failed: 0, cancelled: 0,
      },
    },
  })

  const factory = (completed = 5) => {
    vi.spyOn(api, 'get').mockImplementation((url) => {
      if (url === '/download/tasks/count') return Promise.resolve(countsWith(completed))
      return Promise.resolve(EMPTY)
    })
    vi.spyOn(api, 'post').mockImplementation(() => Promise.resolve(EMPTY))
    vi.spyOn(api, 'delete').mockImplementation(() => Promise.resolve(EMPTY))
    vi.spyOn(recentDownloadsApi, 'clear').mockImplementation(() =>
      Promise.resolve({ data: { deleted: 3 } })
    )
    vi.spyOn(recentDownloadsApi, 'getCount').mockImplementation(() =>
      Promise.resolve({ data: { count: 0 } })
    )
    return mount(Download, {
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
          ElEmpty: { template: '<div></div>' },
          ElDialog: { template: '<div><slot/></div>' },
          // popover 始终渲染内容，便于直接断言弹窗内元素
          ElPopover: {
            name: 'ElPopover',
            template: '<div class="popover-stub"><slot/><slot name="reference"/></div>',
          },
          ElSelect: { name: 'ElSelect', template: '<div class="el-select-stub"><slot/></div>' },
          ElOption: {
            props: ['label', 'value'],
            template: '<div class="el-option-stub" :data-value="value">{{ label }}</div>',
          },
          Refresh: { template: '<i></i>' },
          Delete: { template: '<i></i>' },
        },
      },
    })
  }

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  /** 切到能看见清除入口的页签（默认 active 页签不显示该入口） */
  const gotoAllTab = async (wrapper, tab = 'all') => {
    wrapper.vm.activeTab = tab
    await flushPromises()
  }

  it('工具栏只留一个清除图标按钮（不再是下拉 + 两个大按钮）', async () => {
    const wrapper = factory()
    await flushPromises()
    await gotoAllTab(wrapper)

    expect(wrapper.find('.clear-trigger').exists()).toBe(true)
    expect(wrapper.find('.clear-pop').exists()).toBe(true)
    // 旧实现的两个平铺按钮文案应已消失
    expect(wrapper.find('.toolbar-actions').text()).not.toContain('清除 30 前记录')
    expect(wrapper.find('.toolbar-actions').text()).not.toContain('清空已完成记录')
  })

  it('清除范围下拉为 7/30/90 天前 + 全部', async () => {
    const wrapper = factory()
    await flushPromises()
    await gotoAllTab(wrapper)

    const values = wrapper.findAll('.clear-scope .el-option-stub')
      .map((o) => o.attributes('data-value'))
    expect(values).toEqual(['7', '30', '90', '0'])
    expect(wrapper.find('.clear-scope').text()).toContain('全部已完成记录')
  })

  it('弹窗内明示「不删除本地图片文件」', async () => {
    const wrapper = factory()
    await flushPromises()
    await gotoAllTab(wrapper)

    expect(wrapper.find('.clear-pop-hint').text()).toContain('不会删除本地图片文件')
  })

  it('第一次点「清除」只进入待确认态，不发请求', async () => {
    const wrapper = factory()
    await flushPromises()
    await gotoAllTab(wrapper)

    await wrapper.vm.onClearClick()
    await flushPromises()

    expect(wrapper.vm.clearArmed).toBe(true)
    expect(recentDownloadsApi.clear).not.toHaveBeenCalled()
    expect(wrapper.find('.clear-confirm').text()).toContain('再次点击确认清除')
  })

  it('待确认态 5 秒后自动回弹', async () => {
    vi.useFakeTimers()
    const wrapper = factory()
    await flushPromises()

    await wrapper.vm.onClearClick()
    expect(wrapper.vm.clearArmed).toBe(true)

    vi.advanceTimersByTime(5000)
    expect(wrapper.vm.clearArmed).toBe(false)
    expect(recentDownloadsApi.clear).not.toHaveBeenCalled()
  })

  it('第二次点击才真正发请求（按天数：before_days）', async () => {
    const wrapper = factory()
    await flushPromises()

    wrapper.vm.clearScope = 90
    await wrapper.vm.onClearClick()
    await wrapper.vm.onClearClick()
    await flushPromises()

    expect(recentDownloadsApi.clear).toHaveBeenCalledWith({
      mode: 'before_days',
      days: 90,
    })
    expect(wrapper.vm.clearArmed).toBe(false)
  })

  it('选「全部已完成记录」→ 发 {mode:"all"}', async () => {
    const wrapper = factory()
    await flushPromises()

    wrapper.vm.clearScope = 0
    await wrapper.vm.onClearClick()
    await wrapper.vm.onClearClick()
    await flushPromises()

    expect(recentDownloadsApi.clear).toHaveBeenCalledWith({ mode: 'all' })
  })

  it('切换清除范围会重置待确认态（防止「选了 30 天却按 90 天执行」）', async () => {
    const wrapper = factory()
    await flushPromises()
    await gotoAllTab(wrapper)

    await wrapper.vm.onClearClick()
    expect(wrapper.vm.clearArmed).toBe(true)

    wrapper.vm.clearScope = 7
    await wrapper.findComponent({ name: 'ElSelect' }).vm.$emit('change', 7)
    await flushPromises()

    expect(wrapper.vm.clearArmed).toBe(false)
  })

  it('关闭弹窗重置待确认态', async () => {
    const wrapper = factory()
    await flushPromises()
    await gotoAllTab(wrapper)

    await wrapper.vm.onClearClick()
    expect(wrapper.vm.clearArmed).toBe(true)

    wrapper.findComponent({ name: 'ElPopover' }).vm.$emit('hide')
    await flushPromises()

    expect(wrapper.vm.clearArmed).toBe(false)
  })

  it('completed=0 → 入口禁用且点了也不发请求', async () => {
    const wrapper = factory(0)
    await flushPromises()
    await gotoAllTab(wrapper)

    expect(wrapper.find('.clear-trigger').attributes('disabled')).toBeDefined()

    await wrapper.vm.onClearClick()
    await wrapper.vm.onClearClick()
    await flushPromises()

    expect(recentDownloadsApi.clear).not.toHaveBeenCalled()
  })

  it('清除失败 → 提示错误且不崩溃', async () => {
    const wrapper = factory()
    await flushPromises()

    vi.spyOn(recentDownloadsApi, 'clear').mockRejectedValue(new Error('API 500'))
    const errMock = vi.spyOn(ElMessage, 'error').mockImplementation(() => {})

    await wrapper.vm.onClearClick()
    await wrapper.vm.onClearClick()
    await flushPromises()

    expect(errMock).toHaveBeenCalled()
    expect(wrapper.vm.clearingRecords).toBe(false)
    expect(wrapper.vm.clearArmed).toBe(false)
  })

  it('入口只在「全部 / 已完成」页签出现', async () => {
    const wrapper = factory()
    await flushPromises()

    for (const tab of ['all', 'completed']) {
      wrapper.vm.activeTab = tab
      await flushPromises()
      expect(wrapper.find('.clear-trigger').exists(), `tab=${tab}`).toBe(true)
    }
    for (const tab of ['active', 'failed', 'cancelled']) {
      wrapper.vm.activeTab = tab
      await flushPromises()
      expect(wrapper.find('.clear-trigger').exists(), `tab=${tab}`).toBe(false)
    }
  })

  it('卸载时清理待确认态定时器（不留悬挂 setTimeout）', async () => {
    vi.useFakeTimers()
    const wrapper = factory()
    await flushPromises()

    await wrapper.vm.onClearClick()
    expect(wrapper.vm.clearArmed).toBe(true)

    wrapper.unmount()
    // 卸载后再推进 5s：不应抛错（定时器已 clearTimeout）
    expect(() => vi.advanceTimersByTime(10000)).not.toThrow()
  })
})
