import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    name: 'Gallery',
    component: () => import('@/views/Gallery.vue'),
    meta: { title: '图库' }
  },
  {
    path: '/download',
    name: 'Download',
    component: () => import('@/views/Download.vue'),
    meta: { title: '下载管理' }
  },
  {
    path: '/config',
    name: 'Config',
    component: () => import('@/views/Config.vue'),
    meta: { title: '配置' }
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  // 三个页面（图库 / 下载管理 / 配置）共用同一个 window 滚动容器，
  // 不配置 scrollBehavior 时切页会沿用上一页的滚动偏移 → 新页面"不在最顶端"。
  // 浏览器前进/后退有保存的位置时优先恢复，否则一律回到顶部。
  scrollBehavior(to, from, savedPosition) {
    if (savedPosition) return savedPosition
    return { top: 0 }
  }
})

router.beforeEach((to, from, next) => {
  document.title = to.meta.title || 'Yande.re Spider'
  next()
})

export default router
