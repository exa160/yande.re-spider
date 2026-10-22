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
          RefreshRight: { template: '<i></i>' },
          MoreFilled: { template: '<i></i>' },
          Warning: { template: '<i></i>' },
          Delete: { template: '<i></i>' },
          Search: { template: '<i></i>' },
          ArrowDown: { template: '<i></i>' },
          CaretBottom: { template: '<i></i>' },
          ElAlert: { template: '<div><slot/></div>' },
          ElDropdown: { template: '<div><slot/><slot name="dropdown"/></div>' },
          ElDropdownMenu: { template: '<div><slot/></div>' },
          ElDropdownItem: { template: '<div><slot/></div>' },
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

  it('不渲染刷新按钮；窗口聚焦 / 恢复可见时自动刷新（1s 去重）', async () => {
    const wrapper = factory()
    await flushPromises()
    await new Promise((r) => setTimeout(r, 50))

    expect(wrapper.findAll('button').some((b) => b.text() === '刷新')).toBe(false)

    vi.mocked(api.get).mockClear()

    window.dispatchEvent(new Event('focus'))
    await flushPromises()

    expect(api.get).toHaveBeenCalledWith('/download/tasks', expect.anything())
    expect(api.get).toHaveBeenCalledWith('/download/tasks/count')

    // 同一时刻的 visibilitychange（切换标签页时与 focus 双触发）应被去重
    vi.mocked(api.get).mockClear()
    document.dispatchEvent(new Event('visibilitychange'))
    await flushPromises()
    expect(api.get).not.toHaveBeenCalled()

    // 超过去重窗口后再恢复可见 → 重新刷新
    const realNow = Date.now()
    vi.spyOn(Date, 'now').mockReturnValue(realNow + 2000)
    document.dispatchEvent(new Event('visibilitychange'))
    await flushPromises()
    expect(api.get).toHaveBeenCalledWith('/download/tasks', expect.anything())

    wrapper.unmount()
  })
})

/**
 * 清除下载记录 —— 工具栏常驻按钮 + 标准对话框
 *
 * 设计（2026-10-22 重做）：
 *   - 「清除记录」与「全部重试」同排常驻，不再藏进更多菜单
 *   - 对话框按范围显示后端预览的精确删除条数
 *   - 一次明确确认即可，不再有「点两次 + 5 秒回弹」
 */
describe('Download.vue 清除记录对话框', () => {
  const EMPTY = { data: { data: [], total: 0 } }

  const countsWith = ({ completed = 0, failed = 0 } = {}) => ({
    data: {
      data: {
        pending: 0, downloading: 0, paused: 0,
        completed, failed, cancelled: 0,
      },
    },
  })

  const PREVIEW = {
    all: 18581,
    before_days: { 7: 12, 30: 138, 90: 521 },
  }

  const factory = ({ completed = 5, failed = 0 } = {}) => {
    vi.spyOn(api, 'get').mockImplementation((url) => {
      if (url === '/download/tasks/count') {
        return Promise.resolve(countsWith({ completed, failed }))
      }
      if (url === '/download/tasks/clear-preview') {
        return Promise.resolve({ data: { data: PREVIEW } })
      }
      return Promise.resolve(EMPTY)
    })
    vi.spyOn(api, 'post').mockImplementation(() => Promise.resolve(EMPTY))
    vi.spyOn(api, 'delete').mockImplementation(() => Promise.resolve(EMPTY))
    vi.spyOn(recentDownloadsApi, 'clear').mockImplementation(() =>
      Promise.resolve({ data: { deleted: 138 } })
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
          ElDialog: {
            name: 'ElDialog',
            props: ['modelValue', 'title'],
            template:
              '<div v-if="modelValue" class="dialog-stub">' +
              '<div class="dialog-title">{{ title }}</div>' +
              '<slot/><slot name="footer"/>' +
              '</div>',
          },
          ElAlert: { template: '<div class="alert-stub"><slot/></div>' },
          ElDropdown: {
            name: 'ElDropdown',
            template:
              '<div class="dropdown-stub"><slot/><slot name="dropdown"/></div>',
          },
          ElDropdownMenu: { template: '<div><slot/></div>' },
          ElDropdownItem: { template: '<div class="dropdown-item"><slot/></div>' },
          Refresh: { template: '<i></i>' },
          RefreshRight: { template: '<i></i>' },
          MoreFilled: { template: '<i></i>' },
          Warning: { template: '<i></i>' },
        },
      },
    })
  }

  afterEach(() => {
    vi.restoreAllMocks()
  })

  const gotoAllTab = async (wrapper, tab = 'all') => {
    wrapper.vm.activeTab = tab
    await flushPromises()
  }

  it('工具栏「清除记录」只在全部/已完成页签出现', async () => {
    const wrapper = factory({ failed: 3, completed: 5 })
    await flushPromises()

    for (const tab of ['all', 'completed']) {
      wrapper.vm.activeTab = tab
      await flushPromises()
      expect(wrapper.find('.toolbar-clear').exists(), `tab=${tab}`).toBe(true)
    }
    for (const tab of ['active', 'failed', 'cancelled']) {
      wrapper.vm.activeTab = tab
      await flushPromises()
      expect(wrapper.find('.toolbar-clear').exists(), `tab=${tab}`).toBe(false)
    }

    // 错误页签只保留「全部重试」
    wrapper.vm.activeTab = 'failed'
    await flushPromises()
    const actions = wrapper.findAll('.toolbar-action').map((b) => b.text())
    expect(actions.some((t) => t.includes('全部重试 (3)'))).toBe(true)
    expect(actions.some((t) => t.includes('清除记录'))).toBe(false)
  })

  it('打开对话框时拉取预览，并逐项显示将删除条数', async () => {
    const wrapper = factory()
    await flushPromises()
    await gotoAllTab(wrapper)

    await wrapper.vm.openClearDialog()
    await flushPromises()

    expect(wrapper.vm.clearDialogVisible).toBe(true)
    expect(api.get).toHaveBeenCalledWith('/download/tasks/clear-preview')
    expect(wrapper.vm.clearOptions.map((o) => o.count)).toEqual([
      12, 138, 521, 18581,
    ])
    const optionTexts = wrapper.findAll('.clear-option').map((el) => el.text())
    expect(optionTexts.some((t) => t.includes('将删除 138 条'))).toBe(true)
  })

  it('默认选中 30 天；清除时发送 before_days 请求', async () => {
    const wrapper = factory()
    await flushPromises()

    await wrapper.vm.openClearDialog()
    await flushPromises()

    expect(wrapper.vm.clearScope).toBe(30)
    expect(wrapper.vm.selectedClearCount).toBe(138)

    await wrapper.vm.onClearConfirm()
    await flushPromises()

    expect(recentDownloadsApi.clear).toHaveBeenCalledWith({
      mode: 'before_days',
      days: 30,
    })
    expect(wrapper.vm.clearDialogVisible).toBe(false)
  })

  it('默认范围无可删记录时回退到第一个非空范围（避免主按钮一打开就禁用）', async () => {
    const wrapper = factory()
    await flushPromises()
    vi.mocked(api.get).mockImplementation((url) => {
      if (url === '/download/tasks/count') {
        return Promise.resolve(countsWith({ completed: 23 }))
      }
      if (url === '/download/tasks/clear-preview') {
        return Promise.resolve({
          data: {
            data: { all: 23, before_days: { 7: 20, 30: 0, 90: 0 } },
          },
        })
      }
      return Promise.resolve(EMPTY)
    })

    await wrapper.vm.openClearDialog()
    await flushPromises()

    expect(wrapper.vm.clearScope).toBe(7)
    expect(wrapper.vm.selectedClearCount).toBe(20)
  })

  it('选「全部已完成记录」→ 发 {mode:"all"}', async () => {
    const wrapper = factory()
    await flushPromises()
    await wrapper.vm.openClearDialog()
    await flushPromises()

    await wrapper.findAll('.clear-option')[3].trigger('click')
    expect(wrapper.vm.clearScope).toBe(0)
    expect(wrapper.vm.selectedClearCount).toBe(18581)

    await wrapper.vm.onClearConfirm()
    await flushPromises()
    expect(recentDownloadsApi.clear).toHaveBeenCalledWith({ mode: 'all' })
  })

  it('completed=0 → 已完成页签清除按钮禁用、不打开对话框、不发预览请求', async () => {
    const wrapper = factory({ completed: 0 })
    await flushPromises()
    wrapper.vm.activeTab = 'completed'
    await flushPromises()

    const clearButton = wrapper.find('.toolbar-clear')
    expect(clearButton.exists()).toBe(true)
    expect(clearButton.attributes('disabled')).toBeDefined()

    await wrapper.vm.openClearDialog()
    await flushPromises()

    expect(wrapper.vm.clearDialogVisible).toBe(false)
    expect(api.get).not.toHaveBeenCalledWith('/download/tasks/clear-preview')
  })

  it('预览加载失败 → 关闭对话框并提示错误', async () => {
    const wrapper = factory()
    await flushPromises()
    vi.mocked(api.get).mockImplementation((url) => {
      if (url === '/download/tasks/clear-preview') {
        return Promise.reject(new Error('preview down'))
      }
      return Promise.resolve(EMPTY)
    })
    const err = vi.spyOn(ElMessage, 'error').mockImplementation(() => {})

    await wrapper.vm.openClearDialog()
    await flushPromises()

    expect(wrapper.vm.clearDialogVisible).toBe(false)
    expect(err).toHaveBeenCalled()
  })

  it('清除失败 → 提示错误、loading 复位、对话框保持打开', async () => {
    const wrapper = factory()
    await flushPromises()
    await wrapper.vm.openClearDialog()
    await flushPromises()

    vi.spyOn(recentDownloadsApi, 'clear').mockRejectedValue(new Error('API 500'))
    const err = vi.spyOn(ElMessage, 'error').mockImplementation(() => {})

    await wrapper.vm.onClearConfirm()
    await flushPromises()

    expect(err).toHaveBeenCalled()
    expect(wrapper.vm.clearingRecords).toBe(false)
    expect(wrapper.vm.clearDialogVisible).toBe(true)
  })

  it('错误页签：全部重试按钮显示失败数，确认后调用批量接口', async () => {
    const wrapper = factory({ failed: 3 })
    await flushPromises()
    wrapper.vm.activeTab = 'failed'
    await flushPromises()

    expect(wrapper.text()).toContain('全部重试 (3)')

    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm')
    vi.spyOn(ElMessage, 'success').mockImplementation(() => {})
    const post = vi.spyOn(api, 'post').mockResolvedValue({
      data: { data: { requested: 3, started: 2, skipped: 1 } },
    })

    await wrapper.vm.onRetryAllFailed()
    await flushPromises()

    expect(post).toHaveBeenCalledWith('/download/tasks/retry-failed')
    expect(ElMessage.success).toHaveBeenCalledWith('已重试 2 个任务，跳过 1 个')
  })
})

/**
 * 取消下载中任务
 *
 * 此前 worker 没有停止信号，取消会被收尾逻辑覆盖成 completed，
 * 因此按钮被硬禁用。后端补齐协作式取消后，前端恢复入口。
 */
describe('Download.vue 取消下载中任务', () => {
  const DOWNLOADING_TASK = {
    task_id: 'task-cancel-1',
    image_id: 42,
    file_name: '42.png',
    status: 'downloading',
    progress: 0.3,
    downloaded_size: 300,
    file_size: 1000,
    speed: 10,
    error_message: null,
    created_at: '2026-10-22T10:00:00',
    completed_at: null,
  }

  const factory = () => {
    vi.spyOn(api, 'get').mockImplementation((url) => {
      if (url === '/download/tasks/count') {
        return Promise.resolve({
          data: {
            data: {
              pending: 0, downloading: 1, paused: 0,
              completed: 0, failed: 0, cancelled: 0,
            },
          },
        })
      }
      if (url === '/download/tasks') {
        return Promise.resolve({
          data: { data: [{ ...DOWNLOADING_TASK }], total: 1 },
        })
      }
      return Promise.resolve(EMPTY_RESPONSE)
    })
    vi.spyOn(api, 'delete').mockImplementation(HANG_FOREVER)
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
          ElPopover: { template: '<div><slot/><slot name="reference"/></div>' },
          ElSelect: { template: '<div><slot/></div>' },
          ElOption: { template: '<div><slot/></div>' },
          Refresh: { template: '<i></i>' },
          RefreshRight: { template: '<i></i>' },
          MoreFilled: { template: '<i></i>' },
          Warning: { template: '<i></i>' },
          Delete: { template: '<i></i>' },
          ElAlert: { template: '<div><slot/></div>' },
          ElDropdown: { template: '<div><slot/><slot name="dropdown"/></div>' },
          ElDropdownMenu: { template: '<div><slot/></div>' },
          ElDropdownItem: { template: '<div><slot/></div>' },
        },
      },
    })
  }

  beforeEach(() => {
    // 渲染移动端卡片视图（表格视图的操作列被 ElTableColumn stub 吞掉）
    vi.stubGlobal('innerWidth', 500)
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  const findCancelButton = (wrapper) =>
    wrapper.findAll('button').find((b) => b.text() === '取消')

  it('下载中任务展示可点击的取消按钮（不再禁用）', async () => {
    const wrapper = factory()
    await flushPromises()

    const cancel = findCancelButton(wrapper)
    expect(cancel).toBeTruthy()
    expect(cancel.attributes('disabled')).toBeUndefined()

    wrapper.unmount()
  })

  it('点击取消 → 确认后调用 cancel 接口', async () => {
    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm')
    vi.spyOn(ElMessage, 'success').mockImplementation(() => {})
    const post = vi.spyOn(api, 'post').mockResolvedValue({})

    const wrapper = factory()
    await flushPromises()

    await findCancelButton(wrapper).trigger('click')
    await flushPromises()

    expect(ElMessageBox.confirm).toHaveBeenCalled()
    expect(post).toHaveBeenCalledWith('/download/task/task-cancel-1/cancel')
    expect(ElMessage.success).toHaveBeenCalledWith('任务已取消')

    wrapper.unmount()
  })
})
