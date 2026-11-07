import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import './styles/viewer.css'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'

import App from './App.vue'
import router from './router'

const app = createApp(App)

// 关闭浏览器原生的滚动位置恢复：刷新页面时浏览器会自己把 scrollY 恢复回去，
// 表现为"刷新后停在页面中间"、进入新页面时位置随机。
// 页面内的位置记忆统一由 Gallery.vue 的滚动策略负责。
if ('scrollRestoration' in window.history) {
  window.history.scrollRestoration = 'manual'
}

// 注册Element Plus图标
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

app.use(createPinia())
app.use(router)
app.use(ElementPlus)

app.mount('#app')
