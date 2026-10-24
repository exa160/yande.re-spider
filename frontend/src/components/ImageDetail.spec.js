import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ImageDetail from './ImageDetail.vue'

const sections = [
  {
    label: '文件',
    fields: [
      { label: '大小', value: '15.61 MB' },
      { label: 'MD5', value: 'abc123', mono: true, wide: true },
      { label: '时间', value: '2026-01-01T00:00:00' },
    ],
  },
  {
    label: '来源',
    fields: [
      { label: '来源', value: 'pixiv', href: 'https://www.pixiv.net/artworks/1', wide: true },
      { label: '作者', value: 'jenmin12' },
      { label: '上传用户', value: 'VigorousMMM' },
    ],
  },
]

const tags = [
  { text: 'ass', dot: 'rgb(1, 2, 3)', bg: 'rgba(1, 2, 3, 0.1)', border: 'rgb(1, 2, 3)' },
  { text: 'heels', dot: 'rgba(255, 255, 255, 0.45)', bg: '', border: '' },
]

const factory = (props = {}) => mount(ImageDetail, {
  props: {
    layout: 'rail',
    title: '详情',
    subtitle: '#100 · 1080 × 1920',
    rating: 'Safe',
    sections,
    tags,
    height: '600px',
    ambientSrc: '/api/v1/gallery/cache/preview/100',
    postUrl: 'https://yande.re/post/show/100',
    ...props,
  },
  global: {
    stubs: {
      'el-icon': { template: '<i><slot /></i>' },
    },
  },
})

describe('ImageDetail — 桌面 rail', () => {
  it('渲染分区、字段、链接和标签', () => {
    const wrapper = factory()

    expect(wrapper.attributes('data-layout')).toBe('rail')
    expect(wrapper.find('.detail-title').text()).toBe('详情')
    expect(wrapper.find('.detail-subtitle').text()).toBe('#100 · 1080 × 1920')
    expect(wrapper.findAll('.detail-section-label').map((el) => el.text())).toEqual([
      '文件',
      '来源',
      '标签 (2)',
    ])
    expect(wrapper.findAll('.detail-row')).toHaveLength(6)
    expect(wrapper.find('.detail-value--mono').text()).toBe('abc123')

    const link = wrapper.find('.detail-link')
    expect(link.text()).toContain('pixiv')
    expect(link.attributes('href')).toBe('https://www.pixiv.net/artworks/1')
    expect(link.attributes('title')).toBe('https://www.pixiv.net/artworks/1')

    expect(wrapper.findAll('.detail-tag')).toHaveLength(2)
    expect(wrapper.findAll('.detail-tag')[0].text()).toBe('ass')
    expect(wrapper.findAll('.detail-tag')[0].find('.detail-tag-dot').attributes('style'))
      .toContain('rgb(1, 2, 3)')
    expect(wrapper.findAll('.detail-tag')[0].attributes('style'))
      .toContain('rgba(1, 2, 3, 0.1)')
  })

  it('rail 应用高度与环境色变量', () => {
    const wrapper = factory()
    const style = wrapper.attributes('style') || ''
    expect(style).toContain('height: 600px')
    expect(style).toContain('--detail-ambient: url("/api/v1/gallery/cache/preview/100")')
  })

  it('评级按 Safe / Questionable / Explicit / 其他映射色调', () => {
    expect(factory({ rating: 'Safe' }).find('.detail-rating').classes()).toContain('detail-rating--safe')
    expect(factory({ rating: 'Questionable' }).find('.detail-rating').classes()).toContain('detail-rating--warn')
    expect(factory({ rating: 'Explicit' }).find('.detail-rating').classes()).toContain('detail-rating--danger')
    expect(factory({ rating: 'Unknown' }).find('.detail-rating').classes()).toContain('detail-rating--neutral')
  })
})

describe('ImageDetail — 窄屏 dock', () => {
  it('拍平成两列网格，MD5/来源跨两列，不渲染分区标题', () => {
    const wrapper = factory({ layout: 'dock' })

    expect(wrapper.attributes('data-layout')).toBe('dock')
    expect(wrapper.find('.detail-grid').exists()).toBe(true)
    expect(wrapper.findAll('.detail-field')).toHaveLength(6)
    expect(wrapper.findAll('.detail-field--wide')).toHaveLength(2)
    // 唯一的分区标题是标签区
    expect(wrapper.findAll('.detail-section-label').map((el) => el.text())).toEqual(['标签 (2)'])
    expect(wrapper.attributes('style') || '').not.toContain('height')
  })
})

describe('ImageDetail — 交互', () => {
  it('canRefreshTags=false 时「更新标签」置灰，原帖/复制链接仍可用', async () => {
    const wrapper = factory()
    const btn = wrapper.find('.detail-refresh')
    expect(btn.exists()).toBe(true)
    expect(btn.attributes('disabled')).toBeDefined()
    expect(wrapper.findAll('.detail-action')).toHaveLength(2)

    await btn.trigger('click')
    expect(wrapper.emitted('refresh-tags')).toBeUndefined()
  })

  it('canRefreshTags=true 时点击 emit refresh-tags', async () => {
    const wrapper = factory({ canRefreshTags: true })
    const btn = wrapper.find('.detail-refresh')
    expect(btn.text()).toBe('更新标签')
    expect(btn.attributes('disabled')).toBeUndefined()

    await btn.trigger('click')
    expect(wrapper.emitted('refresh-tags')).toHaveLength(1)
  })

  it('refreshingTags=true 时按钮禁用并显示更新中', () => {
    const wrapper = factory({ canRefreshTags: true, refreshingTags: true })
    const btn = wrapper.find('.detail-refresh')
    expect(btn.attributes('disabled')).toBeDefined()
    expect(btn.text()).toContain('更新中')
  })

  it('原帖是外链，复制链接 emit copy-link(url)', async () => {
    const wrapper = factory()
    const link = wrapper.find('a.detail-action')
    expect(link.attributes('href')).toBe('https://yande.re/post/show/100')
    expect(link.attributes('target')).toBe('_blank')
    expect(link.attributes('rel')).toContain('noopener')

    const copyBtn = wrapper.findAll('button.detail-action')[0]
    await copyBtn.trigger('click')
    expect(wrapper.emitted('copy-link')).toEqual([
      ['https://yande.re/post/show/100'],
    ])
  })

  it('关闭按钮 emit close', async () => {
    const wrapper = factory()
    await wrapper.find('.detail-icon').trigger('click')
    expect(wrapper.emitted('close')).toHaveLength(1)
  })

  it('没有 rating 时不渲染评级 chip', () => {
    const wrapper = factory({ rating: '' })
    expect(wrapper.find('.detail-rating').exists()).toBe(false)
  })
})
