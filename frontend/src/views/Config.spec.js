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
        'el-input': { template: '<input>' },
        'el-input-number': { template: '<input type="number">' },
        'el-segmented': { template: '<div><slot/></div>' },
        'el-switch': {
          props: ['modelValue', 'disabled'],
          template: '<input type="checkbox" class="switch-stub" :disabled="disabled || undefined">',
          emits: ['update:modelValue'],
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
// 标签面板「/ yande M」的数据源是 yande_tags.count，此前只能手动刷新；
// 这里锁定开关 + cron + 每页条数能读写，以及保存走对端点。
// =============================================================================
describe('Config.vue 标签缓存定时更新', () => {
  const tagCacheResp = {
    enable_daily_refresh: true,
    refresh_cron: '30 5 * * *',
    batch_limit: 250,
  }

  it('切到高级功能 → GET /config/tag-cache 拉回配置', async () => {
    const api = (await import('@/api')).default
    api.get.mockClear()
    api.get.mockImplementation((url) => {
      if (url === '/config/tag-cache') return Promise.resolve({ data: tagCacheResp })
      return Promise.resolve({ data: {} })
    })

    const wrapper = factory()
    await flushPromises()
    await clickMenuItem(wrapper, '高级功能')

    expect(api.get).toHaveBeenCalledWith('/config/tag-cache')
    expect(wrapper.vm.tagCacheForm.enableDailyRefresh).toBe(true)
    expect(wrapper.vm.tagCacheForm.refreshCron).toBe('30 5 * * *')
    expect(wrapper.vm.tagCacheForm.batchLimit).toBe(250)
  })

  it('保存 → PUT /config/tag-cache 带 enable_daily_refresh / refresh_cron / batch_limit', async () => {
    const api = (await import('@/api')).default
    api.put.mockClear()

    const wrapper = factory()
    await flushPromises()
    await clickMenuItem(wrapper, '高级功能')

    wrapper.vm.tagCacheForm.enableDailyRefresh = false
    wrapper.vm.tagCacheForm.refreshCron = '  0 6 * * *  '
    wrapper.vm.tagCacheForm.batchLimit = 300
    await wrapper.vm.saveTagCache()

    expect(api.put).toHaveBeenCalledWith('/config/tag-cache', {
      enable_daily_refresh: false,
      refresh_cron: '0 6 * * *', // 去空格后提交
      batch_limit: 300,
    })
  })

  it('开关关闭时不显示 cron / 每页条数输入（避免误改无效项）', async () => {
    const wrapper = factory()
    await flushPromises()
    await clickMenuItem(wrapper, '高级功能')

    wrapper.vm.tagCacheForm.enableDailyRefresh = true
    await flushPromises()
    const onHtml = wrapper.find('.tag-cache-cron-input').exists()
    wrapper.vm.tagCacheForm.enableDailyRefresh = false
    await flushPromises()
    const offHtml = wrapper.find('.tag-cache-cron-input').exists()

    expect(onHtml).toBe(true)
    expect(offHtml).toBe(false)
  })
})
