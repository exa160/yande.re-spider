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
          props: ['modelValue'],
          emits: ['update:modelValue'],
          template: '<div class="radio-group-stub"><slot/></div>',
        },
        'el-radio-button': {
          props: ['label'],
          template: '<button class="radio-button-stub" :data-label="label"><slot/></button>',
        },
        'el-button': { template: '<button><slot/></button>' },
        'el-input': { template: '<input>' },
        'el-input-number': { template: '<input type="number">' },
        'el-segmented': { template: '<div><slot/></div>' },
        'el-switch': { template: '<input type="checkbox">' },
        'el-alert': { template: '<div><slot/></div>' },
      },
    },
  })

describe('Config.vue 收藏夹 section（高级功能 tab）', () => {
  it('切到高级功能 tab → 渲染收藏夹 section + 缓存更新 section', async () => {
    const wrapper = factory()
    await flushPromises()

    // 默认 activeMenu='api'，两个 section 都不可见（v-show）
    expect(wrapper.findAll('.advanced-section').length).toBeGreaterThanOrEqual(2)

    // 切到 advanced tab
    const advancedMenuItem = wrapper.findAll('.menu-item').find((el) => el.text() === '高级功能')
    expect(advancedMenuItem).toBeDefined()
    advancedMenuItem.trigger('click')
    await flushPromises()

    // 至少有两个 .advanced-section：收藏夹 + 缓存更新
    const sections = wrapper.findAll('.advanced-section')
    expect(sections.length).toBeGreaterThanOrEqual(2)

    // 收藏夹 section 包含 "收藏夹" 标题
    const hasFavoritesTitle = sections.some((s) => s.text().includes('收藏夹'))
    expect(hasFavoritesTitle).toBe(true)
  })

  it('收藏夹 section 包含两组 radio（buttonMode + tileSize）', async () => {
    const wrapper = factory()
    await flushPromises()
    wrapper.findAll('.menu-item').find((el) => el.text() === '高级功能').trigger('click')
    await flushPromises()

    const radioGroups = wrapper.findAll('.radio-group-stub')
    // buttonMode + tileSize 两组
    expect(radioGroups.length).toBeGreaterThanOrEqual(2)
  })

  it('radio buttonMode 选项：hidden / shown / default', async () => {
    const wrapper = factory()
    await flushPromises()
    wrapper.findAll('.menu-item').find((el) => el.text() === '高级功能').trigger('click')
    await flushPromises()

    const labels = wrapper.findAll('.radio-button-stub').map((b) => b.attributes('data-label'))
    expect(labels).toContain('hidden')
    expect(labels).toContain('shown')
    expect(labels).toContain('default')
  })

  it('radio tileSize 选项：adaptive / 4 / 6 / 8', async () => {
    const wrapper = factory()
    await flushPromises()
    wrapper.findAll('.menu-item').find((el) => el.text() === '高级功能').trigger('click')
    await flushPromises()

    const labels = wrapper.findAll('.radio-button-stub').map((b) => b.attributes('data-label'))
    expect(labels).toContain('adaptive')
    expect(labels).toContain('4')
    expect(labels).toContain('6')
    expect(labels).toContain('8')
  })

  it('favoritesForm 初值 = composable 初始值（默认 shown / adaptive）', async () => {
    const wrapper = factory()
    await flushPromises()
    wrapper.findAll('.menu-item').find((el) => el.text() === '高级功能').trigger('click')
    await flushPromises()

    expect(wrapper.vm.favoritesForm.buttonMode).toBe('shown')
    expect(wrapper.vm.favoritesForm.tileSize).toBe('adaptive')
  })

  it('favoritesForm 初值 = composable 持久化值（hidden / 8）', async () => {
    localStorage.setItem('gallery_favorites_button_mode', 'hidden')
    localStorage.setItem('gallery_favorites_tile_size', '8')

    const wrapper = factory()
    await flushPromises()
    wrapper.findAll('.menu-item').find((el) => el.text() === '高级功能').trigger('click')
    await flushPromises()

    expect(wrapper.vm.favoritesForm.buttonMode).toBe('hidden')
    expect(wrapper.vm.favoritesForm.tileSize).toBe('8')
  })

  it('favoritesForm 修改 → 写入 composable（composable 单一来源）', async () => {
    const wrapper = factory()
    await flushPromises()
    wrapper.findAll('.menu-item').find((el) => el.text() === '高级功能').trigger('click')
    await flushPromises()

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
})
