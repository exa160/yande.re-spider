import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import api from '@/api'
import WaterfallGallery from './WaterfallGallery.vue'
import { useFavoritesConfig } from '@/composables/useFavoritesConfig'

vi.mock('@/api', () => ({
  default: {
    get: vi.fn().mockRejectedValue(new Error('mocked-fail')),
    post: vi.fn().mockResolvedValue({ data: [] })
  }
}))

vi.mock('@/api/myFavorites', () => ({
  myFavoritesApi: {
    add: vi.fn().mockResolvedValue({ data: {} }),
    remove: vi.fn().mockResolvedValue({ data: {} }),
  }
}))

vi.mock('element-plus', async (importOriginal) => {
  const mod = await importOriginal()
  return {
    ...mod,
    ElMessage: { error: vi.fn(), success: vi.fn() }
  }
})

let observerInstances
let observedTargets

beforeEach(() => {
  observerInstances = []
  observedTargets = []
  globalThis.IntersectionObserver = vi.fn().mockImplementation((cb) => {
    const instance = {
      cb,
      observe: vi.fn((el) => observedTargets.push(el)),
      disconnect: vi.fn(),
    }
    observerInstances.push(instance)
    return instance
  })
  api.get.mockClear()
  api.post.mockClear()
  localStorage.clear()
})

const triggerAllIntersecting = async () => {
  await flushPromises()
  const entries = observedTargets.map((el) => ({
    isIntersecting: true,
    target: el,
  }))
  observerInstances.forEach((o) => o.cb(entries))
  await flushPromises()
}

const mkImage = (id) => ({
  id,
  preview_url: `http://example.com/p${id}.jpg`,
  width: 800,
  height: 600,
  rating: 'Safe',
  down_flag: false
})

const factory = (props = {}) => mount(WaterfallGallery, {
  props: {
    images: [mkImage(1), mkImage(2)],
    loading: false,
    hasMore: false,
    selectable: false,
    selectedImages: [],
    sourceMode: 'local',
    saveDataMode: false,
    isLoadingMore: false,
    loadError: false,
    safeMode: false,
    ...props
  },
  global: {
    stubs: {
      ElImage: {
        name: 'ElImage',
        template: '<div class="el-image-stub"><slot name="error"/><slot name="placeholder"/></div>'
      }
    }
  }
})

const elImageAt = (wrapper, i) =>
  wrapper.findAllComponents({ name: 'ElImage' }).at(i)

describe('WaterfallGallery - 预览图加载状态机', () => {
  describe('P0 - 基础状态转换', () => {
    it('T1 入列后默认 LOADING：所有图片占位', async () => {
      const wrapper = factory()
      await wrapper.vm.$nextTick()
      await triggerAllIntersecting()
      expect(wrapper.findAll('.image-placeholder').length).toBe(2)
      expect(wrapper.findAll('.retry-button').length).toBe(0)
    })

    it('T2 @load 触发后单图进入 LOADED：当前图占位消失，waterfall-item 获得 image-loaded class', async () => {
      const wrapper = factory()
      await wrapper.vm.$nextTick()
      await triggerAllIntersecting()
      await elImageAt(wrapper, 0).vm.$emit('load')
      await wrapper.vm.$nextTick()
      expect(wrapper.findAll('.image-placeholder').length).toBe(1)
      expect(wrapper.findAll('.waterfall-item')[0].classes()).toContain('image-loaded')
    })

    it('T3 @error 触发后自动 fallback 链失败：单图进入 FAILED，retry 按钮 +1', async () => {
      const wrapper = factory()
      await wrapper.vm.$nextTick()
      await triggerAllIntersecting()
      await elImageAt(wrapper, 0).vm.$emit('error')
      await flushPromises()
      expect(wrapper.findAll('.image-placeholder').length).toBe(1)
      expect(wrapper.findAll('.retry-button').length).toBe(1)
      expect(api.get).toHaveBeenCalledWith('/gallery/cache/preview/local/1')
      expect(api.get).toHaveBeenCalledWith('/gallery/cache/preview/fetch/1')
    })
  })

  describe('P0 - bug 核心回归（30s/60s 内不显示 reload）', () => {
    it('T4 30 秒后仍未 @load：所有占位持续显示，无 reload 按钮', async () => {
      vi.useFakeTimers()
      const wrapper = factory()
      await wrapper.vm.$nextTick()
      await triggerAllIntersecting()
      vi.advanceTimersByTime(30_000)
      await wrapper.vm.$nextTick()
      expect(wrapper.findAll('.image-placeholder').length).toBe(2)
      expect(wrapper.findAll('.retry-button').length).toBe(0)
      vi.useRealTimers()
    })

    it('T5 60 秒后仍未 @load：所有占位持续显示，无 reload 按钮', async () => {
      vi.useFakeTimers()
      const wrapper = factory()
      await wrapper.vm.$nextTick()
      await triggerAllIntersecting()
      vi.advanceTimersByTime(60_000)
      await wrapper.vm.$nextTick()
      expect(wrapper.findAll('.image-placeholder').length).toBe(2)
      expect(wrapper.findAll('.retry-button').length).toBe(0)
      vi.useRealTimers()
    })
  })

  describe('P1 - retry 流程', () => {
    it('T6 用户点 reload：retry 后 loadingImages 重置，占位重新出现', async () => {
      const wrapper = factory()
      await wrapper.vm.$nextTick()
      await triggerAllIntersecting()
      await elImageAt(wrapper, 0).vm.$emit('error')
      await flushPromises()
      expect(wrapper.findAll('.retry-button').length).toBe(1)
      await wrapper.findAll('.retry-button')[0].trigger('click')
      await flushPromises()
      expect(wrapper.findAll('.image-placeholder').length).toBe(2)
    })

    it('T7 retry 失败：mock api 抛错 → 重新显示 reload 按钮', async () => {
      api.get.mockRejectedValue(new Error('network error'))
      const wrapper = factory()
      await wrapper.vm.$nextTick()
      await triggerAllIntersecting()
      await elImageAt(wrapper, 0).vm.$emit('error')
      await flushPromises()
      await wrapper.findAll('.retry-button')[0].trigger('click')
      await flushPromises()
      expect(wrapper.findAll('.retry-button').length).toBe(1)
    })
  })

  describe('P1 - 状态清理', () => {
    it('T8 props.images 清空时所有相关 DOM 元素都消失', async () => {
      const wrapper = factory()
      await wrapper.vm.$nextTick()
      await triggerAllIntersecting()
      await elImageAt(wrapper, 0).vm.$emit('error')
      await flushPromises()
      expect(wrapper.findAll('.retry-button').length).toBe(1)
      await wrapper.setProps({ images: [] })
      await wrapper.vm.$nextTick()
      expect(wrapper.findAll('.retry-button').length).toBe(0)
      expect(wrapper.findAll('.image-placeholder').length).toBe(0)
    })
  })

  describe('P2 - 自动 fallback 链成功（cache-buster 触发重载）', () => {
    it('T9 @error → fallback 链成功 → previewCacheBuster 写入 → 不显示 retry 按钮', async () => {
      api.get.mockResolvedValueOnce({ data: 'ok' })
      const wrapper = factory()
      await wrapper.vm.$nextTick()
      await triggerAllIntersecting()
      await elImageAt(wrapper, 0).vm.$emit('error')
      await flushPromises()
      expect(wrapper.findAll('.retry-button').length).toBe(0)
      expect(api.get).toHaveBeenCalledTimes(1)
      expect(api.get).toHaveBeenCalledWith('/gallery/cache/preview/local/1')
    })

    it('T10 fallback 链防重入：同 id 并发 @error 只跑一次链', async () => {
      let resolveFirst
      api.get.mockImplementationOnce(() => new Promise((r) => { resolveFirst = r }))
      const wrapper = factory()
      await wrapper.vm.$nextTick()
      await triggerAllIntersecting()
      elImageAt(wrapper, 0).vm.$emit('error')
      elImageAt(wrapper, 0).vm.$emit('error')
      expect(api.get).toHaveBeenCalledTimes(1)
      resolveFirst({ data: 'ok' })
      await flushPromises()
      expect(wrapper.findAll('.retry-button').length).toBe(0)
    })
  })
})

describe('WaterfallGallery itemType=folder', () => {
  const mkFolder = (id) => ({
    id,
    name: `f${id}`,
    local_count: 10,
    preview_images: [],
  })

  it('itemType=folder 时渲染 slot 内容', () => {
    const folders = [mkFolder(1), mkFolder(2)]
    const wrapper = mount(WaterfallGallery, {
      props: {
        images: folders,
        itemType: 'folder',
        loading: false,
        hasMore: false,
        selectable: false,
        selectedImages: [],
        sourceMode: 'local',
        saveDataMode: false,
        isLoadingMore: false,
        loadError: false,
        safeMode: false,
      },
      slots: {
        default: '<div class="test-folder-slot">{{ params.folder.name }}</div>',
      },
    })
    expect(wrapper.findAll('.test-folder-slot')).toHaveLength(2)
    expect(wrapper.text()).toContain('f1')
    expect(wrapper.text()).toContain('f2')
  })
})

// =============================================================================
// v2 我的最爱 / 随机浏览：showHeart × enableMyFavorites 双判断 + HeartOverlay 渲染
// =============================================================================
describe('WaterfallGallery v2 我的最爱 showHeart 集成', () => {
  const setEnableMyFavorites = (val) => {
    const { enableMyFavorites } = useFavoritesConfig()
    enableMyFavorites.value = val
  }

  const mkImageWithFav = (id, isFavorited = false) => ({
    id,
    preview_url: `http://example.com/p${id}.jpg`,
    width: 800,
    height: 600,
    rating: 'Safe',
    down_flag: false,
    is_favorited: isFavorited,
  })

  describe('P0 - include_favorite_status 参数注入（双判断）', () => {
    it('T1 showHeart=true 且 enableMyFavorites=true → loadNewPage 含 include_favorite_status=true', async () => {
      // given: showHeart=true 且后端开关打开
      setEnableMyFavorites(true)
      api.post.mockResolvedValue({ data: { data: [], has_more: false } })
      const wrapper = factory({ showHeart: true })

      // when: 调用智能分页加载
      await wrapper.vm.loadNewPage(1, 20, { tags: 'cat' })

      // then: include_favorite_status=true 被注入，且其它参数保留
      expect(api.post).toHaveBeenCalledWith(
        '/gallery/load',
        expect.objectContaining({ include_favorite_status: true })
      )
      const body = api.post.mock.calls[0][1]
      expect(body.page).toBe(1)
      expect(body.page_size).toBe(20)
      expect(body.tags).toBe('cat')
    })

    it('T2 showHeart=false → loadNewPage 不含 include_favorite_status（即使 enableMyFavorites=true）', async () => {
      // given: UI 入口关闭
      setEnableMyFavorites(true)
      api.post.mockResolvedValue({ data: { data: [], has_more: false } })
      const wrapper = factory({ showHeart: false })

      // when: 调用智能分页加载
      await wrapper.vm.loadNewPage(1, 20, {})

      // then: 即使后端开关打开，UI 入口关闭时也不传
      const body = api.post.mock.calls[0][1]
      expect('include_favorite_status' in body).toBe(false)
    })

    it('T3 enableMyFavorites=false → loadNewPage 不含 include_favorite_status（即使 showHeart=true）', async () => {
      // given: UI 入口打开，但后端总开关关闭
      setEnableMyFavorites(false)
      api.post.mockResolvedValue({ data: { data: [], has_more: false } })
      const wrapper = factory({ showHeart: true })

      // when: 调用智能分页加载
      await wrapper.vm.loadNewPage(1, 20, {})

      // then: 防御性 — 后端开关关闭时绝不传，避免无意义的 JOIN 开销
      const body = api.post.mock.calls[0][1]
      expect('include_favorite_status' in body).toBe(false)
    })
  })

  describe('P0 - HeartOverlay 渲染', () => {
    it('T4 showHeart=true → 每张图渲染 HeartOverlay（initial-favorited 取 is_favorited）', async () => {
      // given: showHeart=true，混合初始收藏态
      setEnableMyFavorites(true)
      const wrapper = factory({
        showHeart: true,
        images: [mkImageWithFav(1, true), mkImageWithFav(2, false)],
      })
      await wrapper.vm.$nextTick()

      // then: 两张图都渲染 HeartOverlay，prop 正确透传
      const hearts = wrapper.findAllComponents({ name: 'HeartOverlay' })
      expect(hearts.length).toBe(2)
      expect(hearts[0].props('initialFavorited')).toBe(true)
      expect(hearts[1].props('initialFavorited')).toBe(false)
      expect(hearts[0].props('imageId')).toBe(1)
      expect(hearts[1].props('imageId')).toBe(2)
    })

    it('T5 showHeart=false → 不渲染 HeartOverlay', async () => {
      // given: showHeart 默认 false
      setEnableMyFavorites(true)
      const wrapper = factory({ showHeart: false })
      await wrapper.vm.$nextTick()

      // then: 0 个 HeartOverlay 组件
      expect(wrapper.findAllComponents({ name: 'HeartOverlay' }).length).toBe(0)
    })

    it('T6 HeartOverlay @changed → 向上 emit favorite-toggled(payload)', async () => {
      // given: showHeart=true
      setEnableMyFavorites(true)
      const wrapper = factory({
        showHeart: true,
        images: [mkImageWithFav(1, false)],
      })
      await wrapper.vm.$nextTick()

      // when: HeartOverlay 抛出 changed 事件（点击切换后）
      const heart = wrapper.findComponent({ name: 'HeartOverlay' })
      heart.vm.$emit('changed', { imageId: 1, favorited: true })

      // then: 父组件重新抛出 favorite-toggled 给 Gallery.vue 用于同步本地状态
      const events = wrapper.emitted('favorite-toggled')
      expect(events).toBeTruthy()
      expect(events[0][0]).toEqual({ imageId: 1, favorited: true })
    })
  })
})
