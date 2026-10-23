import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import Config from './Config.vue'

// localStorage 清空 + module 重置（composable 是 singleton）
// vi.resetModules() 是异步的，必须 await 才能真正清空 Vite module cache
beforeEach(async () => {
  await vi.resetModules()
  localStorage.clear()
  // Config.vue 顶层用 window.matchMedia
  globalThis.matchMedia = globalThis.matchMedia || vi.fn().mockImplementation((query) => ({
    matches: false,
    media: query,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }))
})

// api mock：避免 Config loadConfig() 真实请求
vi.mock('@/api', () => ({
  default: {
    get: vi.fn().mockResolvedValue({
      data: {
        yande_api: { retry: 3, timeout: 30, proxy_enable: null, proxies: { http: '' }, headers: {} },
        downloader: { thread_num: 4, max_concurrent_tasks: 3, chunk_size: 10240, split_size: 209715200, retry_times: 3 },
        database: { enable: false, host: 'localhost', port: 3306, user: 'root', password: '', schema_name: 'Pictures' },
      },
    }),
    put: vi.fn().mockResolvedValue({ data: {} }),
    post: vi.fn().mockResolvedValue({ data: { success: true } }),
  },
}))

vi.mock('@/api/tagCache', () => ({
  tagCacheApi: {
    getTagsStats: vi.fn().mockResolvedValue({ data: { total: 0, max_id: 0 } }),
    getArtistsStats: vi.fn().mockResolvedValue({ data: { total: 0 } }),
    refreshTags: vi.fn().mockResolvedValue({ data: { total_updated: 0, last_id: 0 } }),
    refreshArtists: vi.fn().mockResolvedValue({ data: null, message: 'started' }),
  },
}))

// 最近下载：开启「最近下载」后 saveFavoritesConfig 会拉角标（独立封装模块，必须 mock）
vi.mock('@/api/recentDownloads', () => ({
  recentDownloadsApi: {
    getCount: vi.fn().mockResolvedValue({ data: { count: 0 } }),
    getPreview: vi.fn().mockResolvedValue({ data: { images: [] } }),
    clear: vi.fn().mockResolvedValue({ data: { deleted: 0 } }),
  },
}))

const factory = () =>
  mount(Config, {
    global: {
      stubs: {
        // 子对话框组件
        PreviewCleanupDialog: { template: '<div></div>' },
        HeadersEditorDialog: { template: '<div></div>' },
        // Element Plus 通用桩
        'el-form': { template: '<form><slot/></form>' },
        'el-form-item': {
          props: ['label'],
          template: '<div class="el-form-item-stub"><label>{{ label }}</label><slot/></div>',
        },
        'el-radio-group': {
          props: ['modelValue', 'disabled'],
          emits: ['update:modelValue'],
          template: '<div class="radio-group-stub" :data-disabled="String(disabled ?? false)"><slot/></div>',
        },
        'el-radio-button': {
          props: ['label', 'value'],
          template: '<button class="radio-button-stub" :data-label="String(label ?? value)"><slot/></button>',
        },
        'el-button': { template: '<button><slot/></button>' },
        'el-input': {
          props: ['modelValue'],
          emits: ['update:modelValue'],
          template: '<input class="input-stub" :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)">',
        },
        'el-input-number': { template: '<input type="number">' },
        'el-segmented': { template: '<div><slot/></div>' },
        'el-switch': {
          name: 'ElSwitch',
          props: ['modelValue', 'disabled'],
          template: '<input type="checkbox" class="switch-stub" :checked="!!modelValue" :disabled="disabled || undefined" @change="$emit(\'update:modelValue\', $event.target.checked); $emit(\'change\', $event.target.checked)">',
          emits: ['update:modelValue', 'change'],
        },
        'el-time-picker': {
          name: 'ElTimePicker',
          props: ['modelValue'],
          emits: ['update:modelValue', 'change'],
          template: '<input class="time-picker-stub" :value="modelValue">',
        },
        'el-checkbox-group': {
          name: 'ElCheckboxGroup',
          emits: ['update:modelValue', 'change'],
          template: '<div class="checkbox-group-stub"><slot/></div>',
        },
        'el-checkbox': {
          props: ['value', 'label'],
          template: '<span class="checkbox-stub" :data-value="String(value ?? label)"><slot/></span>',
        },
        'el-divider': { template: '<hr class="divider-stub" />' },
        'el-alert': { template: '<div><slot/></div>' },
      },
    },
  })

// 找到菜单项的 helper：避免重复写 wrapper.findAll...find 文本
const clickMenuItem = async (wrapper, label) => {
  const item = wrapper.findAll('.menu-item').find((el) => el.text() === label)
  expect(item).toBeDefined()
  item.trigger('click')
  await flushPromises()
}

// =============================================================================
// Task 19 重构：Config.vue 左侧菜单新增「收藏夹」分页（位于「高级功能」之上）
// 高级功能 tab 现在只剩「缓存更新」section，3 个新开关 + 5 个迁移偏好全部
// 移到独立的「收藏夹」tab。
// =============================================================================
describe('Config.vue 菜单结构 — 收藏夹分页位于高级之上', () => {
  it('左菜单顺序：API / 下载器 / 数据库 / 收藏夹配置 / 高级功能 / 关于', async () => {
    const wrapper = factory()
    await flushPromises()

    const labels = wrapper.findAll('.menu-item').map((el) => el.text().trim())
    // 顺序：API配置 → 下载器配置 → 数据库配置 → 收藏夹配置 → 高级功能 → 关于
    //   收藏夹配置在「高级功能」之上是核心契约，确保用户能直接定位
    expect(labels.indexOf('收藏夹配置')).toBeGreaterThan(-1)
    expect(labels.indexOf('高级功能')).toBeGreaterThan(-1)
    expect(labels.indexOf('收藏夹配置')).toBeLessThan(labels.indexOf('高级功能'))
  })

  it('点击「收藏夹」菜单 → 看到 .favorites-section 独立分页', async () => {
    const wrapper = factory()
    await flushPromises()

    await clickMenuItem(wrapper, '收藏夹配置')

    const favSection = wrapper.find('.favorites-section')
    expect(favSection.exists()).toBe(true)
    expect(favSection.isVisible()).toBe(true)
  })

  it('点击「高级功能」菜单 → 只有「缓存更新」section，无任何收藏夹字段', async () => {
    const wrapper = factory()
    await flushPromises()

    await clickMenuItem(wrapper, '高级功能')

    // 高级功能下只剩「缓存更新」section（限定在 .advanced-section 内，避免 v-show=false 的 element 混入）
    const advancedSections = wrapper.findAll('.advanced-section')
    expect(advancedSections.length).toBe(1)
    const advancedDom = advancedSections[0]
    const text = advancedDom.text()
    expect(text).toContain('缓存更新')
    expect(text).not.toContain('主页显示收藏夹')
    expect(text).not.toContain('收藏夹大小')
    expect(text).not.toContain('收藏夹预览图顺序')
    expect(text).not.toContain('收藏夹预览包含未下载图片')
    expect(text).not.toContain('每页收藏夹个数')
    expect(text).not.toContain('我的最爱')
    expect(text).not.toContain('随机浏览')
    expect(text).not.toContain('在线图片收藏自动下载')
    const hasSaveFavoritesBtn = advancedDom.findAll('button').some((b) => b.text().includes('保存收藏夹配置'))
    expect(hasSaveFavoritesBtn).toBe(false)
  })
})

describe('Config.vue 收藏夹分页（3 个新开关 + saveFavoritesConfig）', () => {
  const findFavoritesSection = (wrapper) => {
    return wrapper.find('.favorites-section').element
      ? wrapper.find('.favorites-section')
      : null
  }

  it('收藏夹分页渲染 3 个新开关（radio-group 风格）：我的最爱 / 在线图片收藏自动下载 / 随机浏览', async () => {
    const wrapper = factory()
    await flushPromises()
    await clickMenuItem(wrapper, '收藏夹配置')

    const favSection = wrapper.find('.favorites-section')
    expect(favSection.exists()).toBe(true)

    const text = favSection.text()
    expect(text).toContain('我的最爱')
    expect(text).toContain('在线图片收藏自动下载')
    expect(text).toContain('随机浏览')
    // 「收藏夹展示」已移除，冗余于「主页显示收藏夹」
    expect(text).not.toContain('收藏夹展示')
    // 3 个新开关已统一为 radio-group，不再有裸 el-switch
    expect(favSection.findAll('input.switch-stub').length).toBe(0)
    // buttonMode + 我的最爱 + 自动下载 + 随机浏览 + 其余 4 个 = 8 个 radio group
    expect(favSection.findAll('.radio-group-stub').length).toBeGreaterThanOrEqual(8)
  })

  it('收藏夹分页渲染 5 个迁移偏好 radio 组 + 保存按钮', async () => {
    const wrapper = factory()
    await flushPromises()
    await clickMenuItem(wrapper, '收藏夹配置')

    const favSection = wrapper.find('.favorites-section')
    expect(favSection.exists()).toBe(true)

    const text = favSection.text()
    expect(text).toContain('主页显示收藏夹')        // buttonMode
    expect(text).toContain('收藏夹大小')              // tileSize
    expect(text).toContain('收藏夹预览图顺序')        // previewOrder
    expect(text).toContain('收藏夹预览包含未下载图片') // includeOnline
    expect(text).toContain('每页收藏夹个数')          // folderPageSize

    // 5 个 radio group
    const radioGroups = favSection.findAll('.radio-group-stub')
    // buttonMode + tileSize + previewOrder + includeOnline + folderPageSize = 5
    expect(radioGroups.length).toBeGreaterThanOrEqual(5)

    // 保存按钮
    const buttons = favSection.findAll('button')
    const hasSaveBtn = buttons.some((b) => b.text().includes('保存收藏夹配置'))
    expect(hasSaveBtn).toBe(true)
  })

  it('enableMyFavorites=false 时 autodownload switch 被禁用；翻转为 true 后解除禁用', async () => {
    const wrapper = factory()
    await flushPromises()
    await clickMenuItem(wrapper, '收藏夹配置')

    const favSection = wrapper.find('.favorites-section')
    // radio-group 顺序：主页显示收藏夹(0) / 我的最爱(1) / 在线图片收藏自动下载(2) / 随机浏览(3)
    const groups = favSection.findAll('.radio-group-stub')
    expect(groups[2].attributes('data-disabled')).toBe('true')

    wrapper.vm.favoritesForm.enableMyFavorites = true
    await flushPromises()
    expect(groups[2].attributes('data-disabled')).toBe('false')
  })

  it('点击「保存收藏夹配置」→ PUT /config/favorites 带 8 个 snake_case 字段（不含 enable_favorite_folder）', async () => {
    const { default: api } = await import('@/api')
    const wrapper = factory()
    await flushPromises()
    await clickMenuItem(wrapper, '收藏夹配置')

    wrapper.vm.favoritesForm.enableMyFavorites = true
    wrapper.vm.favoritesForm.tileSize = '8'
    await flushPromises()

    const saveBtn = wrapper.findAll('button').find((b) => b.text().includes('保存收藏夹配置'))
    expect(saveBtn).toBeDefined()
    saveBtn.trigger('click')
    await flushPromises()

    expect(api.put).toHaveBeenCalledWith('/config/favorites', expect.objectContaining({
      enable_my_favorites: true,
      enable_random_browse: expect.any(Boolean),
      enable_favorite_autodownload: expect.any(Boolean),
      button_mode: expect.any(String),
      tile_size: '8',
      preview_order: expect.any(String),
      include_online: expect.any(Boolean),
      folder_page_size: expect.any(Number),
    }))
    // 冗余字段 enable_favorite_folder 不再随保存发送
    const sent = api.put.mock.calls.find((c) => c[0] === '/config/favorites')?.[1]
    expect(sent).not.toHaveProperty('enable_favorite_folder')
  })

  it('收藏夹分页渲染「最近下载」开关，且位于「随机浏览」之后（设计文档 §4.6）', async () => {
    const wrapper = factory()
    await flushPromises()
    await clickMenuItem(wrapper, '收藏夹配置')

    const favSection = wrapper.find('.favorites-section')
    const text = favSection.text()
    expect(text).toContain('随机浏览')
    expect(text).toContain('最近下载')
    // 最近下载是独立功能（数据源是 download_task），不随「我的最爱」联动禁用
    const groups = favSection.findAll('.radio-group-stub')
    // radio-group 顺序：主页显示收藏夹(0) / 我的最爱(1) / 自动下载(2) / 随机浏览(3) / 最近下载(4)
    expect(groups[4].attributes('data-disabled')).toBe('false')
  })

  it('保存收藏夹配置 → PUT 带 enable_recent_downloads，并同步回 composable', async () => {
    const { default: api } = await import('@/api')
    const { recentDownloadsApi } = await import('@/api/recentDownloads')
    recentDownloadsApi.getCount.mockResolvedValue({ data: { count: 42 } })

    const wrapper = factory()
    await flushPromises()
    await clickMenuItem(wrapper, '收藏夹配置')

    wrapper.vm.favoritesForm.enableRecentDownloads = true
    await flushPromises()

    const saveBtn = wrapper.findAll('button').find((b) => b.text().includes('保存收藏夹配置'))
    saveBtn.trigger('click')
    await flushPromises()

    expect(api.put).toHaveBeenCalledWith('/config/favorites', expect.objectContaining({
      enable_recent_downloads: true,
    }))
    // 刚开启 → 立即拉角标
    expect(recentDownloadsApi.getCount).toHaveBeenCalled()
  })
})

describe('Config.vue 收藏夹分页 — favoritesForm / composable 同步契约', () => {
  it('favoritesForm 初值 = composable 初始值（默认 shown / adaptive）', async () => {
    const wrapper = factory()
    await flushPromises()
    await clickMenuItem(wrapper, '收藏夹配置')

    expect(wrapper.vm.favoritesForm.buttonMode).toBe('shown')
    expect(wrapper.vm.favoritesForm.tileSize).toBe('adaptive')
  })

  it('favoritesForm 初值 = composable 持久化值（hidden / 8）', async () => {
    localStorage.setItem('gallery_favorites_button_mode', 'hidden')
    localStorage.setItem('gallery_favorites_tile_size', '8')

    const wrapper = factory()
    await flushPromises()
    await clickMenuItem(wrapper, '收藏夹配置')

    expect(wrapper.vm.favoritesForm.buttonMode).toBe('hidden')
    expect(wrapper.vm.favoritesForm.tileSize).toBe('8')
  })

  it('favoritesForm 修改 → 写入 composable（composable 单一来源）', async () => {
    const wrapper = factory()
    await flushPromises()
    await clickMenuItem(wrapper, '收藏夹配置')

    // 直接改 form 值模拟 radio click（已绑 v-model）
    wrapper.vm.favoritesForm.buttonMode = 'default'
    wrapper.vm.favoritesForm.tileSize = '6'
    await flushPromises()

    // composable 同步更新
    const { useFavoritesConfig } = await import('@/composables/useFavoritesConfig')
    const { buttonMode, tileSize } = useFavoritesConfig()
    expect(buttonMode.value).toBe('default')
    expect(tileSize.value).toBe('6')

    // localStorage 持久化
    expect(localStorage.getItem('gallery_favorites_button_mode')).toBe('default')
    expect(localStorage.getItem('gallery_favorites_tile_size')).toBe('6')
  })

  it('includeOnline 是二联开关（关闭/开启）而非 el-switch', async () => {
    const wrapper = factory()
    await flushPromises()
    await clickMenuItem(wrapper, '收藏夹配置')

    // includeOnline 二联开关：false / true 两个 radio-button（在收藏夹分页里）
    const favSection = wrapper.find('.favorites-section')
    const labels = favSection.findAll('.radio-button-stub').map((b) => b.attributes('data-label'))
    expect(labels).toContain('false')
    expect(labels).toContain('true')
  })

  it('includeOnline 修改 → 写入 composable 与 localStorage', async () => {
    const wrapper = factory()
    await flushPromises()
    await clickMenuItem(wrapper, '收藏夹配置')

    wrapper.vm.favoritesForm.includeOnline = true
    await flushPromises()

    const { useFavoritesConfig } = await import('@/composables/useFavoritesConfig')
    const { includeOnline } = useFavoritesConfig()
    expect(includeOnline.value).toBe(true)
    expect(localStorage.getItem('gallery_favorites_include_online')).toBe('true')
  })
})

// =============================================================================
// 收藏夹分页 — 所有 radio 选项完整性（5 个迁移偏好的合法选项契约）
// =============================================================================
describe('Config.vue 收藏夹分页 — radio 选项完整性', () => {
  it('buttonMode 选项：hidden / shown / default', async () => {
    const wrapper = factory()
    await flushPromises()
    await clickMenuItem(wrapper, '收藏夹配置')

    const favSection = wrapper.find('.favorites-section')
    const labels = favSection.findAll('.radio-button-stub').map((b) => b.attributes('data-label'))
    expect(labels).toContain('hidden')
    expect(labels).toContain('shown')
    expect(labels).toContain('default')
  })

  it('tileSize 选项：adaptive / 4 / 6 / 8', async () => {
    const wrapper = factory()
    await flushPromises()
    await clickMenuItem(wrapper, '收藏夹配置')

    const favSection = wrapper.find('.favorites-section')
    const labels = favSection.findAll('.radio-button-stub').map((b) => b.attributes('data-label'))
    expect(labels).toContain('adaptive')
    expect(labels).toContain('4')
    expect(labels).toContain('6')
    expect(labels).toContain('8')
  })

  it('previewOrder 选项：random / desc / asc', async () => {
    const wrapper = factory()
    await flushPromises()
    await clickMenuItem(wrapper, '收藏夹配置')

    const favSection = wrapper.find('.favorites-section')
    const labels = favSection.findAll('.radio-button-stub').map((b) => b.attributes('data-label'))
    expect(labels).toContain('random')
    expect(labels).toContain('desc')
    expect(labels).toContain('asc')
  })

  it('folderPageSize 选项：8 / 12 / 20', async () => {
    const wrapper = factory()
    await flushPromises()
    await clickMenuItem(wrapper, '收藏夹配置')

    const favSection = wrapper.find('.favorites-section')
    const labels = favSection.findAll('.radio-button-stub').map((b) => b.attributes('data-label'))
    expect(labels).toContain('8')
    expect(labels).toContain('12')
    expect(labels).toContain('20')
  })
})

// =============================================================================
// 标签缓存定时更新（PUT /config/tag-cache）
// 标签面板「/ yande M」的数据源是 yande_tags.count，此前只能手动刷新。
// 本组锁定「选择即保存」的新交互：cron ↔ 预设互转 + 各控件 change 自动 PUT，
// 以及 batch_limit 已从前后端彻底移除。
// =============================================================================
describe('Config.vue 标签缓存定时更新', () => {
  const mockTagCacheGet = async (data) => {
    const api = (await import('@/api')).default
    api.get.mockClear()
    api.get.mockImplementation((url) => {
      if (url === '/config/tag-cache') return Promise.resolve({ data })
      return Promise.resolve({ data: {} })
    })
    return api
  }

  // 打开「高级功能」页并返回已挂好假数据的 wrapper
  const openAdvanced = async (data) => {
    const api = await mockTagCacheGet(data)
    api.put.mockClear()
    const wrapper = factory()
    await flushPromises()
    await clickMenuItem(wrapper, '高级功能')
    return { wrapper, api }
  }

  const dailyResp = { enable_daily_refresh: true, refresh_cron: '30 5 * * *' }

  it('加载后把 cron 反解成预设（30 5 * * * → 每天 05:30）', async () => {
    const { wrapper, api } = await openAdvanced(dailyResp)

    expect(api.get).toHaveBeenCalledWith('/config/tag-cache')
    expect(wrapper.vm.tagCacheForm.freq).toBe('daily')
    expect(wrapper.vm.tagCacheForm.time).toBe('05:30')
    expect(wrapper.vm.tagCacheForm.enableDailyRefresh).toBe(true)
    // 短摘要跟着设置走
    expect(wrapper.find('.tag-cache-summary').text()).toBe('每天 05:30')
  })

  it('每周形态的 cron 反解成「每周」+ 星期多选（顺序按 一二三四五六日）', async () => {
    const { wrapper } = await openAdvanced({
      enable_daily_refresh: true,
      refresh_cron: '30 5 * * 0,1,3',
    })

    expect(wrapper.vm.tagCacheForm.freq).toBe('weekly')
    expect(wrapper.vm.tagCacheForm.time).toBe('05:30')
    // 0=周日 会被排到末尾
    expect(wrapper.vm.tagCacheForm.weekdays).toEqual([1, 3, 0])
    expect(wrapper.find('.tag-cache-summary').text()).toBe('每周一、三、日 05:30')
  })

  it('无法解析成预设的 cron 回退「自定义」并原样展示（0 */2 * * *）', async () => {
    const { wrapper } = await openAdvanced({
      enable_daily_refresh: true,
      refresh_cron: '0 */2 * * *',
    })

    expect(wrapper.vm.tagCacheForm.freq).toBe('custom')
    expect(wrapper.vm.tagCacheForm.refreshCron).toBe('0 */2 * * *')
    // 回退到自定义时不能顺手把 cron 改成预设形态
    expect(wrapper.find('.tag-cache-cron-input').element.value).toBe('0 */2 * * *')
    // 自定义态显示 cron 输入框 + crontab.guru 链接；摘要是短 cron 文本
    expect(wrapper.find('.tag-cache-summary').text()).toBe('自定义 0 */2 * * *')
    expect(wrapper.find('a.tag-cache-cron-link').attributes('href')).toBe('https://crontab.guru/')
  })

  it.each([
    ['每天但带区间', '30 5 * * 1-5'],
    ['每月', '30 5 1 * *'],
    ['小时级', '0 */2 * * *'],
    ['六段带秒', '0 30 5 * * *'],
  ])('cron「%s」不被误判成预设', async (_label, cron) => {
    const { wrapper } = await openAdvanced({ enable_daily_refresh: true, refresh_cron: cron })

    expect(wrapper.vm.tagCacheForm.freq).toBe('custom')
    expect(wrapper.vm.tagCacheForm.refreshCron).toBe(cron)
  })

  it('切开关 → 自动 PUT，且 payload 不含 batch_limit', async () => {
    const { wrapper, api } = await openAdvanced(dailyResp)

    wrapper.vm.tagCacheForm.enableDailyRefresh = false
    await wrapper.find('.tag-cache-enable').trigger('change')

    expect(api.put).toHaveBeenCalledWith('/config/tag-cache', {
      enable_daily_refresh: false,
      refresh_cron: '30 5 * * *',
    })
    const payload = api.put.mock.calls[0][1]
    expect(payload).not.toHaveProperty('batch_limit')
  })

  it('关闭后摘要显示「已关闭」，且频率控件整体隐藏', async () => {
    const { wrapper } = await openAdvanced({ enable_daily_refresh: false, refresh_cron: '30 5 * * *' })

    // 摘要和单选在同一行，且单选是行的最后一个元素（靠右）
    const toggleRow = wrapper.find('.tag-cache-toggle')
    expect(toggleRow.find('.tag-cache-summary').text()).toBe('已关闭')
    expect(toggleRow.element.lastElementChild.classList.contains('tag-cache-enable')).toBe(true)
    expect(wrapper.find('.tag-cache-fields').exists()).toBe(false)

    wrapper.vm.tagCacheForm.enableDailyRefresh = true
    await wrapper.find('.tag-cache-enable').trigger('change')
    await flushPromises()
    expect(wrapper.find('.tag-cache-fields').exists()).toBe(true)
  })

  it('改时间 → 自动 PUT（time-picker 的 change，不是实时输入）', async () => {
    const { wrapper, api } = await openAdvanced(dailyResp)

    const picker = wrapper.findComponent({ name: 'ElTimePicker' })
    await picker.vm.$emit('change', '06:45')

    expect(wrapper.vm.tagCacheForm.refreshCron).toBe('45 6 * * *')
    expect(api.put).toHaveBeenCalledWith('/config/tag-cache', {
      enable_daily_refresh: true,
      refresh_cron: '45 6 * * *',
    })
  })

  it('频率选「每周」→ 星期选择器出现；选回「每天」→ 隐藏', async () => {
    const { wrapper } = await openAdvanced(dailyResp)

    // 默认「每天」：没有星期选择器
    expect(wrapper.find('.checkbox-group-stub').exists()).toBe(false)

    wrapper.vm.tagCacheForm.freq = 'weekly'
    await wrapper.find('.tag-cache-fields .radio-group-stub').trigger('change')
    expect(wrapper.find('.checkbox-group-stub').exists()).toBe(true)
    // 一…日 七个
    expect(wrapper.findAll('.checkbox-stub').length).toBe(7)
    // 无星期的默认 cron 被切成了周一
    expect(wrapper.vm.tagCacheForm.refreshCron).toBe('30 5 * * 1')

    wrapper.vm.tagCacheForm.freq = 'daily'
    await wrapper.find('.tag-cache-fields .radio-group-stub').trigger('change')
    expect(wrapper.find('.checkbox-group-stub').exists()).toBe(false)
    expect(wrapper.vm.tagCacheForm.refreshCron).toBe('30 5 * * *')
  })

  it('星期选择变化 → 自动 PUT（周日 0 排在最后）', async () => {
    const { wrapper, api } = await openAdvanced({
      enable_daily_refresh: true,
      refresh_cron: '30 5 * * 1,3',
    })
    api.put.mockClear()

    wrapper.vm.tagCacheForm.weekdays = [0, 2]
    await wrapper.findComponent({ name: 'ElCheckboxGroup' }).vm.$emit('change', [0, 2])

    expect(wrapper.vm.tagCacheForm.refreshCron).toBe('30 5 * * 2,0')
    expect(api.put).toHaveBeenLastCalledWith('/config/tag-cache', {
      enable_daily_refresh: true,
      refresh_cron: '30 5 * * 2,0',
    })
  })

  it('自定义 cron 输入框：敲键盘不触发 PUT，blur 才触发', async () => {
    const { wrapper, api } = await openAdvanced({
      enable_daily_refresh: true,
      refresh_cron: '0 */2 * * *',
    })
    api.put.mockClear()

    const input = wrapper.find('.tag-cache-cron-input')
    // 逐字符输入（半截 cron 会让后端 validator 直接 422）
    for (const value of ['0', '0 ', '0 5', '0 5 ', '0 5 *', '0 5 * *', '0 5 * * ']) {
      await input.setValue(value)
    }
    expect(api.put).not.toHaveBeenCalled()

    // 回车同样提交（value-format 为空时取当前绑定值）
    await input.trigger('blur')
    expect(api.put).toHaveBeenCalledTimes(1)
    expect(api.put).toHaveBeenCalledWith('/config/tag-cache', {
      enable_daily_refresh: true,
      refresh_cron: '0 5 * *',
    })
    // 提交时仍停留在「自定义」，不会自动翻回预设
    expect(wrapper.vm.tagCacheForm.freq).toBe('custom')
  })

  it('自定义 cron 回车也触发保存', async () => {
    const { wrapper, api } = await openAdvanced({
      enable_daily_refresh: true,
      refresh_cron: '0 */2 * * *',
    })
    api.put.mockClear()

    await wrapper.find('.tag-cache-cron-input').setValue('15 3 * * *')
    await wrapper.find('.tag-cache-cron-input').trigger('keydown.enter')

    expect(api.put).toHaveBeenCalledWith('/config/tag-cache', {
      enable_daily_refresh: true,
      refresh_cron: '15 3 * * *',
    })
  })

  it('保存失败 → 回滚到保存前的快照并弹错误', async () => {
    const { wrapper, api } = await openAdvanced(dailyResp)
    api.put.mockClear()
    api.put.mockRejectedValueOnce(new Error('cron 表达式非法'))

    wrapper.vm.tagCacheForm.time = '07:00'
    await wrapper.vm.saveTagCache()
    await flushPromises()

    // 界面回到保存前的 cron / 频率，避免「看着改了其实没存上」
    expect(wrapper.vm.tagCacheForm.refreshCron).toBe('30 5 * * *')
    expect(wrapper.vm.tagCacheForm.time).toBe('05:30')
  })

  it('快速连续操作（同一 tick 内）合并成一次 PUT，且带的是最终状态', async () => {
    const { wrapper, api } = await openAdvanced(dailyResp)
    api.put.mockClear()

    wrapper.vm.tagCacheForm.freq = 'weekly'
    wrapper.vm.onTagCacheFreqChange() // 内含 saveTagCache
    wrapper.vm.onTagCacheTimeChange('09:00') // 同一 tick 内再次改动
    await flushPromises()

    // 中间态不落盘：只发一次，且是合并后的最终 cron
    expect(api.put).toHaveBeenCalledTimes(1)
    expect(api.put).toHaveBeenCalledWith('/config/tag-cache', {
      enable_daily_refresh: true,
      refresh_cron: '0 9 * * 1',
    })
  })

  it('请求在飞时的再次改动不丢：串行发出第二次 PUT', async () => {
    const { wrapper, api } = await openAdvanced(dailyResp)
    api.put.mockClear()
    let release
    api.put.mockImplementationOnce(() => new Promise((resolve) => { release = resolve }))

    wrapper.vm.onTagCacheTimeChange('07:00')
    await flushPromises() // 第一次 PUT 已挂起
    wrapper.vm.onTagCacheTimeChange('08:00') // 在飞时的新改动
    release({ data: {} })
    await flushPromises()

    expect(api.put).toHaveBeenCalledTimes(2)
    expect(api.put).toHaveBeenNthCalledWith(2, '/config/tag-cache', {
      enable_daily_refresh: true,
      refresh_cron: '0 8 * * *',
    })
  })

  it('不再有「保存」按钮，也没有条/页输入', async () => {
    const { wrapper } = await openAdvanced({
      enable_daily_refresh: true,
      refresh_cron: '30 5 * * *',
    })

    const card = wrapper.find('.refresh-item--tag-refresh')
    expect(card.findAll('button').some((b) => b.text().includes('保存'))).toBe(false)
    expect(card.text()).not.toContain('条/页')
    expect(wrapper.vm.tagCacheForm.batchLimit).toBeUndefined()
  })

  it('定时更新并入「更新标签」框；更新艺术家 / 预览图清理仍是横排', async () => {
    const { wrapper } = await openAdvanced(dailyResp)

    const advanced = wrapper.find('.advanced-section')
    const stacked = advanced.findAll('.refresh-item--stacked')
    expect(stacked.length).toBe(1)
    expect(stacked[0].classes()).toContain('refresh-item--tag-refresh')
    expect(stacked[0].text()).toContain('更新标签')
    expect(stacked[0].text()).toContain('定时更新')
    expect(stacked[0].text()).not.toContain('标签缓存定时更新')
    expect(stacked[0].find('.tag-cache-toggle .tag-cache-label').text()).toBe('定时更新')
    // 与收藏夹配置一致：布尔项用「关闭 / 开启」单选按钮，不用 el-switch
    const enableLabels = stacked[0]
      .findAll('.tag-cache-enable .radio-button-stub')
      .map((el) => el.text())
    expect(enableLabels).toEqual(['关闭', '开启'])
    expect(stacked[0].find('.tag-cache-switch').exists()).toBe(false)

    // 更新标签已是 stacked；另外两项保持横排
    const plain = advanced
      .findAll('.refresh-item')
      .filter((el) => !el.classes().includes('refresh-item--stacked'))
    expect(plain.length).toBe(2)
    const texts = plain.map((el) => el.text())
    expect(texts.some((t) => t.includes('更新艺术家'))).toBe(true)
    expect(texts.some((t) => t.includes('预览图清理'))).toBe(true)
    expect(texts.some((t) => t.includes('更新标签'))).toBe(false)
  })
})
