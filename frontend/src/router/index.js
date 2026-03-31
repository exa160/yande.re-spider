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
  routes
})

router.beforeEach((to, from, next) => {
  document.title = to.meta.title || 'Yande.re Spider'
  next()
})

export default router
