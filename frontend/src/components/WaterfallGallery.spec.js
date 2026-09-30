import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import api from '@/api'
import WaterfallGallery from './WaterfallGallery.vue'
import { useFavoritesConfig } from '@/composables/useFavoritesConfig'
import { useDownloadState } from '@/composables/useDownloadState'

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

// =============================================================================
// 收藏标识贴右契约（左右分栏）
// =============================================================================
// 回归：.downloaded-dot 曾带 margin-left:auto，在 flex 行里吸收全部剩余空间，
// 导致「已下载」与否决定收藏按钮位置 —— 有 dot 时 dot 被顶到最右把 heart 一起
// 带过去，无 dot 时 heart 紧贴评分靠左，同一控件位置随下载状态跳变。
//
// 修复改为左右分栏（与大图浏览 .float-header-left/.float-footer-left 同构）：
// 左组=元数据，右组=收藏，靠 space-between 分开，不再依赖 margin-left:auto。
//
// 这里刻意断言样式表文本而非 DOM：DOM 顺序断言在结构上无法发现"谁带了
// margin-left:auto"这类纯 CSS 回归，必须直接锁住样式契约。
describe('WaterfallGallery 收藏标识贴右契约', () => {
  const readStyleBlock = () => {
    const fs = require('fs')
    const path = require('path')
    return fs.readFileSync(
      path.resolve(__dirname, './WaterfallGallery.vue'),
      'utf-8'
    )
  }

  // 兼容逗号分组选择器（`.a,\n.a { ... }`）：定位到选择器后取其后的第一个 {...}
  const ruleBody = (source, selector) => {
    const sel = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/^\./, '\\.')
    const start = source.search(new RegExp(sel + '\\s*(,|\\{)'))
    if (start === -1) return null
    const open = source.indexOf('{', start)
    if (open === -1) return null
    return source.slice(open + 1, source.indexOf('}', open))
  }

  const expectNoAutoMargin = (selector) => {
    const body = ruleBody(readStyleBlock(), selector)
    expect(body, `${selector} 规则未找到`).not.toBeNull()
    expect(body).not.toMatch(/margin-left\s*:\s*auto/)
  }

  it('.downloaded-dot 不带 margin-left:auto（元数据应与 ID/尺寸/评分同在左组）', () => {
    const body = ruleBody(readStyleBlock(), '.downloaded-dot')
    expect(body).not.toBeNull()
    expect(body).not.toMatch(/margin-left\s*:\s*auto/)
  })

  it('.image-info-content 用 space-between 分开左右两组，而非靠 auto margin', () => {
    const body = ruleBody(readStyleBlock(), '.image-info-content')
    expect(body).not.toBeNull()
    expect(body).toMatch(/justify-content\s*:\s*space-between/)
    // 旧实现是靠某个子元素的 margin-left:auto 吸空间，这里必须不存在
    expectNoAutoMargin('.info-group-left')
    expectNoAutoMargin('.info-group-right')
  })

  it('元数据在 .info-group-left，HeartOverlay 在 .info-group-right', async () => {
    useFavoritesConfig().enableMyFavorites.value = true
    const wrapper = factory({
      showHeart: true,
      images: [{
        id: 1, preview_url: 'http://example.com/p1.jpg',
        width: 800, height: 600, rating: 'Safe', down_flag: true, is_favorited: false,
      }],
    })
    await wrapper.vm.$nextTick()

    const left = wrapper.find('.image-info-content .info-group-left')
    const right = wrapper.find('.image-info-content .info-group-right')
    expect(left.exists()).toBe(true)
    expect(right.exists()).toBe(true)

    // 已下载 dot 属于元数据 → 左组
    expect(left.find('.downloaded-dot').exists()).toBe(true)
    expect(left.find('.info-id').exists()).toBe(true)
    expect(left.find('.info-size').exists()).toBe(true)

    // 收藏 → 右组，且左组内不得出现
    expect(right.find('.heart-overlay').exists()).toBe(true)
    expect(left.find('.heart-overlay').exists()).toBe(false)
  })

  it('dot 的有无不改变收藏按钮所在分组（不再随 down_flag 跳变）', async () => {
    useFavoritesConfig().enableMyFavorites.value = true
    const mk = (id, downFlag) => ({
      id, preview_url: `http://example.com/p${id}.jpg`,
      width: 800, height: 600, rating: 'Safe', down_flag: downFlag, is_favorited: false,
    })
    const wrapper = factory({
      showHeart: true,
      images: [mk(1, true), mk(2, false)],
    })
    await wrapper.vm.$nextTick()

    const hearts = wrapper.findAllComponents({ name: 'HeartOverlay' })
    expect(hearts.length).toBe(2)
    for (const heart of hearts) {
      // 两种下载状态下，heart 的父级都必须是右组
      const parentClasses = heart.element.parentElement.className
      expect(parentClasses).toContain('info-group-right')
    }
    // 未下载那张没有 dot，但 heart 位置不受影响
    expect(wrapper.findAll('.downloaded-dot').length).toBe(1)
  })

  it('showHeart=false → 不渲染右组（不留空 flex item）', async () => {
    useFavoritesConfig().enableMyFavorites.value = true
    const wrapper = factory({
      showHeart: false,
      images: [{
        id: 1, preview_url: 'http://example.com/p1.jpg',
        width: 800, height: 600, rating: 'Safe', down_flag: true, is_favorited: false,
      }],
    })
    await wrapper.vm.$nextTick()
    expect(wrapper.find('.info-group-right').exists()).toBe(false)
    expect(wrapper.find('.info-group-left').exists()).toBe(true)
  })
})

// =============================================================================
// 下载态标识：下载中（转圈） vs 已下载（绿点）
// 数据源是 useDownloadState 单例（Gallery.vue 轮询 /download/tasks/states 后写入），
// 本组件只读不轮询。覆盖三个触发场景的可见结果。
// =============================================================================
describe('WaterfallGallery - 下载态标识（下载中 / 已下载）', () => {
  const { markQueued, sync, _resetForTest } = useDownloadState()

  const withState = (id, downFlag = false) => ({
    id,
    preview_url: `http://example.com/p${id}.jpg`,
    width: 800, height: 600, rating: 'Safe',
    down_flag: downFlag, is_favorited: false,
  })

  beforeEach(() => {
    _resetForTest()
  })

  it('单图/批量下载：markQueued 后立刻显示转圈指示器（不再等 DB 落 down_flag）', async () => {
    const wrapper = factory({ images: [withState(9001), withState(9002)] })
    await wrapper.vm.$nextTick()
    expect(wrapper.findAll('.info-downloading').length).toBe(0)

    markQueued([9001, 9002])
    await wrapper.vm.$nextTick()
    expect(wrapper.findAll('.info-downloading').length).toBe(2)
    // 下载中不应同时显示「已下载」绿点
    expect(wrapper.findAll('.downloaded-dot').length).toBe(0)
  })

  it('收藏自动下载：后端队列里出现任务后（前端未触发）也能显示转圈', async () => {
    api.get.mockResolvedValueOnce({
      data: { data: { active: [{ image_id: 9003, task_id: 't', status: 'downloading', progress: 0.3 }], finished: [] } },
    })
    await sync()

    const wrapper = factory({ images: [withState(9003)] })
    await wrapper.vm.$nextTick()
    expect(wrapper.findAll('.info-downloading').length).toBe(1)
  })

  it('下载完成后转圈 → 绿点（down_flag 快照仍是 false 也正确）', async () => {
    markQueued([9004])
    const wrapper = factory({ images: [withState(9004)] })
    await wrapper.vm.$nextTick()
    expect(wrapper.findAll('.info-downloading').length).toBe(1)

    api.get.mockResolvedValueOnce({
      data: { data: { active: [], finished: [{ image_id: 9004, status: 'completed' }] } },
    })
    await sync()
    await wrapper.vm.$nextTick()

    expect(wrapper.findAll('.info-downloading').length).toBe(0)
    expect(wrapper.findAll('.downloaded-dot').length).toBe(1)
  })

  it('下载失败：转圈消失且不显示绿点（回到未下载）', async () => {
    markQueued([9005])
    const wrapper = factory({ images: [withState(9005)] })
    await wrapper.vm.$nextTick()
    expect(wrapper.findAll('.info-downloading').length).toBe(1)

    api.get.mockResolvedValueOnce({
      data: { data: { active: [], finished: [{ image_id: 9005, status: 'failed' }] } },
    })
    await sync()
    await wrapper.vm.$nextTick()

    expect(wrapper.findAll('.info-downloading').length).toBe(0)
    expect(wrapper.findAll('.downloaded-dot').length).toBe(0)
  })

  it('下载态指示器与已下载 dot 同属 .info-group-left（收藏按钮位置不跳动）', async () => {
    useFavoritesConfig().enableMyFavorites.value = true
    markQueued([9006])
    const wrapper = factory({ showHeart: true, images: [withState(9006)] })
    await wrapper.vm.$nextTick()

    const left = wrapper.find('.info-group-left')
    expect(left.find('.info-downloading').exists()).toBe(true)
    expect(left.find('.heart-overlay').exists()).toBe(false)

    const heart = wrapper.findComponent({ name: 'HeartOverlay' })
    expect(heart.element.parentElement.className).toContain('info-group-right')
  })
})
