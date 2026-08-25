/**
 * AdvancedQuery.vue — mode 三态 + lockFavoriteChip + favorites-filter emit
 *
 * 覆盖 spec §3.3 中的三种 AdvancedQuery.mode：
 *   - 'gallery'             → 原行为（advanced-panel trigger 可见）
 *   - 'favorites-folders'   → 隐藏 advanced-panel trigger；placeholder 文案变化；搜索 emit 'favorites-filter'
 *   - 'favorites-folder-detail' → 保留 advanced-panel + 顶部"是否展示在线内容"el-switch；folder chip 锁定
 *
 * 同时验证：
 *   - lockFavoriteChip=true 时 folder chip 的 X 关闭按钮被替换为锁图标
 *   - defineExpose 暴露 setIncludeOnline(bool) / resetAdvancedPanel()
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import AdvancedQuery from './AdvancedQuery.vue'

// mock API / 子组件 —— 与 Gallery.spec.js 保持一致
vi.mock('@/api/favorites', () => ({
  getAllFolders: vi.fn().mockResolvedValue({ data: [] }),
  createFolder: vi.fn().mockResolvedValue({ data: {} }),
  updateFolder: vi.fn().mockResolvedValue({ data: {} }),
  deleteFolder: vi.fn().mockResolvedValue({ data: {} }),
  resetFolderSync: vi.fn().mockResolvedValue({ data: {} }),
}))

vi.mock('@/api/tagCache', () => ({
  tagCacheApi: {
    getTagsWithStats: vi.fn().mockResolvedValue({ data: { tags: [] } }),
    calculateLocalStats: vi.fn().mockResolvedValue({ data: {} }),
  },
}))

// 全局桩 — Element Plus 组件统一成最小可用 DOM，避免 happy-dom 报未解析组件
const elementStubs = {
  'el-icon': { template: '<i class="el-icon-stub"><slot/></i>' },
  'el-button': {
    template: '<button class="el-button-stub" :title="title" @click="$emit(\'click\')"><slot/></button>',
    props: ['title'],
    emits: ['click'],
  },
  'el-input': {
    template: '<input class="el-input-stub" :value="modelValue" :placeholder="placeholder" @input="$emit(\'update:modelValue\', $event.target.value); $emit(\'input\', $event.target.value)" @keyup.enter="$emit(\'keyup.enter\')" />',
    props: ['modelValue', 'placeholder'],
    emits: ['update:modelValue', 'keyup.enter', 'input'],
  },
  'el-collapse-transition': {
    template: '<div class="el-collapse-transition-stub"><slot/></div>',
  },
  'el-checkbox-button': { template: '<label class="el-checkbox-button-stub"><slot/></label>' },
  'el-input-number': {
    template: '<input class="el-input-number-stub" type="number" :value="modelValue" @input="$emit(\'update:modelValue\', Number($event.target.value))" />',
    props: ['modelValue'],
    emits: ['update:modelValue'],
  },
  'el-radio-group': { template: '<div class="el-radio-group-stub"><slot/></div>' },
  'el-radio-button': { template: '<label class="el-radio-button-stub"><slot/></label>' },
  'el-select': {
    template: '<div class="el-select-stub"><slot/></div>',
    props: ['modelValue'],
    emits: ['update:modelValue'],
  },
  'el-option': { template: '<div class="el-option-stub"><slot/></div>' },
  'el-date-picker': {
    template: '<input class="el-date-picker-stub" :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />',
    props: ['modelValue'],
    emits: ['update:modelValue'],
  },
  'el-switch': {
    template: '<button class="el-switch-stub" :class="{ \'is-checked\': modelValue }" @click="$emit(\'update:modelValue\', !modelValue)">{{ modelValue ? "on" : "off" }}</button>',
    props: ['modelValue'],
    emits: ['update:modelValue'],
  },
  'el-tag': { template: '<span class="el-tag-stub"><slot/></span>' },
}

// FavoritePanel 用 stub，避免重复组件依赖
const FavoritePanelStub = {
  name: 'FavoritePanel',
  props: ['folders', 'colorOptions', 'sourceMode'],
  emits: ['select', 'longPress', 'create', 'update', 'delete', 'reset-sync', 'mode-change'],
  template: '<div class="favorite-panel-stub"><slot/></div>',
}

const factory = (props = {}) => mount(AdvancedQuery, {
  props: { sourceMode: 'local', ...props },
  global: {
    stubs: {
      ...elementStubs,
      FavoritePanel: FavoritePanelStub,
    },
  },
})

describe('AdvancedQuery.vue mode 三态', () => {
  beforeEach(() => {
    globalThis.ResizeObserver = vi.fn().mockImplementation(() => ({
      observe: vi.fn(),
      disconnect: vi.fn(),
      unobserve: vi.fn(),
    }))
  })

  it('mode=gallery（默认）显示 advanced-panel 触发器（Setting 按钮）', () => {
    const wrapper = factory({ mode: 'gallery' })
    // 默认折叠状态 — Setting 按钮应可见（当 mode === 'gallery'）
    const advancedBtn = wrapper.findAll('button').find(b => b.element.title?.includes('Setting'))
    expect(advancedBtn).toBeTruthy()
  })

  it('mode=favorites-folders 隐藏 advanced-panel 触发器（Setting 按钮）', () => {
    const wrapper = factory({ mode: 'favorites-folders' })
    // search-bar 仍可见
    expect(wrapper.find('.search-bar').exists()).toBe(true)
    // 但 Setting 按钮（advanced-panel trigger）不可见
    const advancedBtn = wrapper.findAll('button').find(b => b.element.title?.includes('Setting'))
    expect(advancedBtn).toBeFalsy()
  })

  it('mode=favorites-folders 时搜索框 placeholder 为收藏夹提示', () => {
    const wrapper = factory({ mode: 'favorites-folders' })
    const input = wrapper.find('input.el-input-stub')
    expect(input.attributes('placeholder')).toBe('搜索收藏夹名称或标签')
  })

  it('mode=gallery 时 placeholder 不变（保留原行为）', () => {
    const wrapper = factory({ mode: 'gallery' })
    const input = wrapper.find('input.el-input-stub')
    expect(input.attributes('placeholder')).not.toBe('搜索收藏夹名称或标签')
    // gallery 模式保留原有 placeholder
    expect(input.attributes('placeholder')).toContain('标签')
  })

  it('mode=favorites-folders 搜索时触发 favorites-filter emit（不带 search emit）', async () => {
    const wrapper = factory({ mode: 'favorites-folders' })
    const input = wrapper.find('input.el-input-stub')
    await input.setValue('fav-keyword')
    await flushPromises()

    // favorites-filter 应触发
    expect(wrapper.emitted('favorites-filter')).toBeTruthy()
    expect(wrapper.emitted('favorites-filter').at(-1)[0]).toBe('fav-keyword')
    // 同时**不**应触发原有 search（mode=favorites-folders 一级不走 /api/v1/gallery/load）
    expect(wrapper.emitted('search')).toBeFalsy()
  })

  it('mode=favorites-folder-detail 展开 advanced-panel 后顶部包含"展示在线内容"开关', async () => {
    const wrapper = factory({ mode: 'favorites-folder-detail' })
    // Setting 按钮应可见（advanced-panel 触发器保留）
    const advancedBtn = wrapper.findAll('button').find(b => b.element.title?.includes('Setting'))
    expect(advancedBtn).toBeTruthy()
    await advancedBtn.trigger('click')
    await flushPromises()

    // advanced-panel 应展开 + 包含"是否展示在线内容"label
    expect(wrapper.find('.advanced-panel').exists()).toBe(true)
    expect(wrapper.text()).toContain('是否展示在线内容')
    // el-switch 至少存在一个
    expect(wrapper.find('.el-switch-stub').exists()).toBe(true)
  })

  it('mode=favorites-folders 不应显示 favorite-detail 专属的"在线内容"开关 label', () => {
    const wrapper = factory({ mode: 'favorites-folders' })
    // advanced-panel 完全不展开（且没显示 switch 文案）
    expect(wrapper.text()).not.toContain('是否展示在线内容')
  })
})

describe('AdvancedQuery.vue lockFavoriteChip', () => {
  beforeEach(() => {
    globalThis.ResizeObserver = vi.fn().mockImplementation(() => ({
      observe: vi.fn(),
      disconnect: vi.fn(),
      unobserve: vi.fn(),
    }))
  })

  it('lockFavoriteChip=false 时 folder chip 显示 X 关闭按钮', async () => {
    const wrapper = factory({ mode: 'favorites-folder-detail', lockFavoriteChip: false })
    // 通过 exposed selectFavorite 模拟进入二级
    await wrapper.vm.selectFavorite({ id: 10, name: 'fav', tags: 'cat_cute' })
    await flushPromises()

    // folder chip 应存在
    expect(wrapper.find('.input-tag.favorite-tag').exists()).toBe(true)
    // X 按钮存在（input-tag-close）
    expect(wrapper.findAll('.input-tag-close').length).toBeGreaterThan(0)
    // 不应有 lock-icon
    expect(wrapper.find('.lock-icon').exists()).toBe(false)
  })

  it('lockFavoriteChip=true 时 folder chip X 替换为 🔒', async () => {
    const wrapper = factory({ mode: 'favorites-folder-detail', lockFavoriteChip: true })
    await wrapper.vm.selectFavorite({ id: 20, name: 'locked', tags: 'foo' })
    await flushPromises()

    expect(wrapper.find('.input-tag.favorite-tag').exists()).toBe(true)
    // lock-icon 应存在
    expect(wrapper.find('.lock-icon').exists()).toBe(true)
    // 应包含 🔒 字符
    expect(wrapper.find('.lock-icon').text()).toContain('🔒')
    // favorite-tag 内不应再有 .input-tag-close（因为 chip 不可关闭）
    const favTag = wrapper.find('.input-tag.favorite-tag')
    expect(favTag.find('.input-tag-close').exists()).toBe(false)
  })
})

describe('AdvancedQuery.vue defineExpose', () => {
  beforeEach(() => {
    globalThis.ResizeObserver = vi.fn().mockImplementation(() => ({
      observe: vi.fn(),
      disconnect: vi.fn(),
      unobserve: vi.fn(),
    }))
  })

  it('暴露 setIncludeOnline(bool) — 切换内部 includeOnline ref 并触发 search', async () => {
    const wrapper = factory({ mode: 'favorites-folder-detail', sourceMode: 'favorites' })
    expect(typeof wrapper.vm.setIncludeOnline).toBe('function')

    // 打开 advanced-panel 后第一次搜索（用 reset 干净状态）
    wrapper.vm.reset()
    await flushPromises()

    await wrapper.vm.setIncludeOnline(true)
    expect(wrapper.vm.includeOnline).toBe(true)

    // 应触发 search（mode=favorites-folder-detail 走 /api/v1/gallery/load with include_online）
    expect(wrapper.emitted('search')).toBeTruthy()
    const lastSearch = wrapper.emitted('search').at(-1)[0]
    expect(lastSearch.params.include_online).toBe(true)
  })

  it('暴露 resetAdvancedPanel() — 重置 queryParams 但保留 selectedFavorite 不动', async () => {
    const wrapper = factory({ mode: 'favorites-folder-detail', sourceMode: 'favorites' })
    expect(typeof wrapper.vm.resetAdvancedPanel).toBe('function')

    // 写入 queryParams 一些状态
    wrapper.vm.queryParams.author = 'foo_author'
    wrapper.vm.queryParams.minWidth = 100

    // 选中 favorite
    await wrapper.vm.selectFavorite({ id: 1, name: 'fav', tags: 'tag1' })
    await flushPromises()

    // 调用 resetAdvancedPanel
    wrapper.vm.resetAdvancedPanel()
    await flushPromises()

    // queryParams 已重置
    expect(wrapper.vm.queryParams.author).toBe('')
    expect(wrapper.vm.queryParams.minWidth).toBeNull()
    // selectedFavorite 应**保留**（resetAdvancedPanel 不动它）
    expect(wrapper.vm.selectedFavorite).toBeTruthy()
    expect(wrapper.vm.selectedFavorite.name).toBe('fav')
    // showAdvanced 应关闭
    expect(wrapper.vm.showAdvanced).toBe(false)
  })

  it('暴露 reset() — 同时清空 selectedFavorite（区别于 resetAdvancedPanel）', async () => {
    const wrapper = factory({ mode: 'favorites-folder-detail', sourceMode: 'favorites' })
    await wrapper.vm.selectFavorite({ id: 1, name: 'fav', tags: 'tag1' })
    await flushPromises()

    wrapper.vm.reset()
    await flushPromises()

    // 全清空
    expect(wrapper.vm.selectedFavorite).toBeNull()
  })
})
