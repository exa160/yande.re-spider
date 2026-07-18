# 预览图加载 Bug 修复 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 `WaterfallGallery.vue` 预览图加载 bug，引入 Vitest 测试基础设施

**Architecture:** 彻底移除组件内的 10s 硬超时机制，状态完全由 `<el-image>` 真实 `@load/@error` 事件驱动；引入 Vitest + happy-dom 做组件级单元测试覆盖状态转换，特别是 30s 后仍未加载时的回归保护。

**Tech Stack:** Vue 3.4、Element Plus 2.5、Vitest 3.x、@vue/test-utils 2.x、happy-dom 15.x

**前置阅读：**
- Spec：`docs/superpowers/specs/2026-07-14-preview-image-loading-fix-design.md`
- 项目规范：`AGENTS.md`
- 全局规则：`~/.config/opencode/AGENTS.md`（中文回复 / 网络代理 `http://192.168.100.222:20171` / 不创建 PR 只到 push）

---

## Task 1：环境预备（node / npm 代理）

**Files:**
- 仅环境检查，不修改任何文件

- [ ] **Step 1: 确认 Node 版本**

```bash
node -v
```

预期输出：`v22.x.x` 或 `v20.x.x` 或 `>=v18.0.0`
若低于 v18：升级 Node 或固定 vitest 2.x 版本（**停止**，询问用户）

- [ ] **Step 2: 探测 npm 仓库连通性**

```bash
npm ping
```

预期：请求成功（带 200 / OK 回复）

- [ ] **Step 3: 失败时配置代理**

若 `npm ping` 失败或超时：

```bash
npm config set proxy http://192.168.100.222:20171
npm config set https-proxy http://192.168.100.222:20171
```

完成后再次 `npm ping` 验证

- [ ] **Step 4: 记录操作**

在最后 commit 时不需要提交任何东西，仅作备忘

---

## Task 2：更新 package.json（添加 devDependencies 与 test 脚本）

**Files:**
- Modify: `frontend/package.json`

- [ ] **Step 1: 读取当前文件**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/frontend
cat package.json
```

- [ ] **Step 2: 修改 devDependencies 与 scripts**

将 `package.json` 修改为：

```json
{
  "name": "yande-re-spider-frontend",
  "version": "1.1.5",
  "description": "Picture Manager Frontend - Vue.js 3 + Element Plus",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview",
    "test": "vitest run",
    "test:watch": "vitest"
  },
  "dependencies": {
    "vue": "^3.4.0",
    "vue-router": "^4.2.0",
    "pinia": "^2.1.0",
    "element-plus": "^2.5.0",
    "axios": "^1.6.0",
    "@element-plus/icons-vue": "^2.3.0"
  },
  "devDependencies": {
    "@vitejs/plugin-vue": "^5.0.0",
    "@vue/test-utils": "^2.4.6",
    "happy-dom": "^15.11.0",
    "vite": "^5.0.0",
    "vitest": "^3.2.0",
    "typescript": "^5.3.0",
    "vue-tsc": "^1.8.0"
  }
}
```

- [ ] **Step 3: 安装新依赖**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/frontend
npm install
```

预期：安装 vitest、@vue/test-utils、happy-dom 等；可能修改 package-lock.json

- [ ] **Step 4: 验证依赖安装**

```bash
ls node_modules/vitest/package.json node_modules/@vue/test-utils/package.json node_modules/happy-dom/package.json
```

预期：3 个文件都存在

- [ ] **Step 5: 提交**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev
git add frontend/package.json frontend/package-lock.json
git commit -m "build(frontend): 引入 vitest 测试依赖"
```

---

## Task 3：配置 vite.config.js 的 test 段

**Files:**
- Modify: `frontend/vite.config.js`

- [ ] **Step 1: 修改 vite.config.js 添加 test 配置**

将文件内容替换为：

```js
/// <reference types="vitest" />
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'
import { readFileSync } from 'fs'

// 编译时从 package.json 读取 version，注入到 bundle
// Config.vue 等组件用 __APP_VERSION__ 引用，build 后变成字面量字符串
const packageJson = JSON.parse(readFileSync(resolve(__dirname, 'package.json'), 'utf-8'))

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src')
    }
  },
  define: {
    __APP_VERSION__: JSON.stringify(packageJson.version)
  },
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true
      }
    }
  },
  build: {
    outDir: 'dist',
    assetsDir: 'assets'
  },
  test: {
    environment: 'happy-dom',
    globals: false,
    include: ['src/**/*.spec.js'],
    css: false
  }
})
```

- [ ] **Step 2: 验证 vitest 可启动**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/frontend
npx vitest --version
```

预期：输出类似 `vitest@3.x.x`

- [ ] **Step 3: 提交**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev
git add frontend/vite.config.js
git commit -m "build(frontend): vite 配置 vitest 测试段"
```

---

## Task 4：写 WaterfallGallery.spec.js（TDD 红阶段 — 期望全失败）

**Files:**
- Create: `frontend/src/components/WaterfallGallery.spec.js`

- [ ] **Step 1: 新建测试文件**

完整写入以下内容：

```js
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import WaterfallGallery from './WaterfallGallery.vue'

// Mock api：handleImageRetry 会调用，避免真实网络
vi.mock('@/api', () => ({
  default: {
    get: vi.fn().mockResolvedValue({ data: 'mocked' })
  }
}))

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
    it('T1 入列后默认 LOADING：显示 placeholder，不显示 reload 按钮', async () => {
      const wrapper = factory()
      await wrapper.vm.$nextTick()
      expect(wrapper.find('.image-placeholder').exists()).toBe(true)
      expect(wrapper.find('.retry-button').exists()).toBe(false)
    })

    it('T2 @load 触发后进入 LOADED：placeholder 消失，waterfall-item 获得 image-loaded class', async () => {
      const wrapper = factory()
      await wrapper.vm.$nextTick()
      await elImageAt(wrapper, 0).vm.$emit('load')
      await wrapper.vm.$nextTick()
      expect(wrapper.findAll('.image-placeholder').length).toBe(0)
      expect(wrapper.findAll('.waterfall-item')[0].classes()).toContain('image-loaded')
    })

    it('T3 @error 触发后进入 FAILED：不显示 placeholder，显示 reload 按钮', async () => {
      const wrapper = factory()
      await wrapper.vm.$nextTick()
      await elImageAt(wrapper, 0).vm.$emit('error')
      await wrapper.vm.$nextTick()
      expect(wrapper.find('.image-placeholder').exists()).toBe(false)
      expect(wrapper.find('.retry-button').exists()).toBe(true)
    })
  })

  describe('P0 - bug 核心回归（30s/60s 内不显示 reload）', () => {
    it('T4 30 秒后仍未 @load：仍显示 placeholder，不显示 reload 按钮', async () => {
      vi.useFakeTimers()
      const wrapper = factory()
      await wrapper.vm.$nextTick()
      vi.advanceTimersByTime(30_000)
      await wrapper.vm.$nextTick()
      expect(wrapper.find('.image-placeholder').exists()).toBe(true)
      expect(wrapper.find('.retry-button').exists()).toBe(false)
      vi.useRealTimers()
    })

    it('T5 60 秒后仍未 @load：仍显示 placeholder，不显示 reload 按钮', async () => {
      vi.useFakeTimers()
      const wrapper = factory()
      await wrapper.vm.$nextTick()
      vi.advanceTimersByTime(60_000)
      await wrapper.vm.$nextTick()
      expect(wrapper.find('.image-placeholder').exists()).toBe(true)
      expect(wrapper.find('.retry-button').exists()).toBe(false)
      vi.useRealTimers()
    })
  })

  describe('P1 - retry 流程', () => {
    it('T6 用户点 reload：retrying 状态切换 → 重新进入 LOADING', async () => {
      const wrapper = factory()
      await wrapper.vm.$nextTick()
      await elImageAt(wrapper, 0).vm.$emit('error')
      await wrapper.vm.$nextTick()
      const retryBtn = wrapper.find('.retry-button')
      expect(retryBtn.exists()).toBe(true)
      await retryBtn.trigger('click')
      await wrapper.vm.$nextTick()
      // retry 中：add loadingImages → placeholder 应重新出现
      expect(wrapper.find('.image-placeholder').exists()).toBe(true)
    })

    it('T7 retry 失败：mock api 抛错 → 重新显示 reload 按钮', async () => {
      const api = (await import('@/api')).default
      api.get.mockRejectedValueOnce(new Error('network error'))
      const wrapper = factory()
      await wrapper.vm.$nextTick()
      await elImageAt(wrapper, 0).vm.$emit('error')
      await wrapper.vm.$nextTick()
      await wrapper.find('.retry-button').trigger('click')
      // 等异步完成
      await new Promise((r) => setTimeout(r, 50))
      await wrapper.vm.$nextTick()
      expect(wrapper.find('.retry-button').exists()).toBe(true)
    })
  })

  describe('P1 - 状态清理', () => {
    it('T8 props.images 清空时所有内部 set 与 map 都被清空', async () => {
      const wrapper = factory()
      await wrapper.vm.$nextTick()
      await elImageAt(wrapper, 0).vm.$emit('error')
      await wrapper.vm.$nextTick()
      expect(wrapper.find('.retry-button').exists()).toBe(true)
      await wrapper.setProps({ images: [] })
      await wrapper.vm.$nextTick()
      expect(wrapper.find('.retry-button').exists()).toBe(false)
      expect(wrapper.find('.image-placeholder').exists()).toBe(false)
    })
  })
})
```

- [ ] **Step 2: 跑测试验证全部 FAIL（TDD 红）**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/frontend
npm run test
```

预期结果：8 个测试用例全部 FAIL（因为 `.vue` 还没改，hard timeout 仍在，会导致 T4/T5 失败、T6/T8 也有副作用）
具体表现：vitest 报告「8 failed」

- [ ] **Step 3: 暂存测试文件但**不**提交**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev
git add frontend/src/components/WaterfallGallery.spec.js
# 此时不要 commit，等待 Task 5 实施代码后一并 commit
```

---

## Task 5：删除 WaterfallGallery.vue 中的硬超时机制（TDD 绿阶段）

**Files:**
- Modify: `frontend/src/components/WaterfallGallery.vue`

> **重要：** 本任务包含 6 处删除/修改。一次性完成后再统一验证测试。

- [ ] **Step 1: 删除 imageLoadTimeouts 变量（L179）**

把：
```js
const imageLoadTimeouts = ref(new Map()) // 跟踪图片加载超时
```

改为：
```js
（整行删除，并在前面变量块的尾部保留一个空行）
```

如变量顺序变动了，整段保持原顺序（仅删目标行）

- [ ] **Step 2: 修改 watcher 中的清理逻辑（L297-324）**

把：
```js
watch(() => props.images.length, () => {
  const newImages = props.images
  if (newImages.length === 0) {
    displayedImages.value = []
    visibleImages.value.clear()
    failedImages.value.clear()
    loadingImages.value.clear()
    loadedImages.value.clear()
    retryingImages.value.clear()
    retrySuccessImages.value.clear()
    // 清除所有超时
    imageLoadTimeouts.value.forEach(t => clearTimeout(t))
    imageLoadTimeouts.value.clear()
    return
  }
  const existingIds = new Set(displayedImages.value.map(img => img.id))
  const newItems = newImages.filter(img => !existingIds.has(img.id))
  if (newItems.length > 0) {
    displayedImages.value = [...displayedImages.value, ...newItems]
    // 新图片加入后标记为正在加载
    newItems.forEach(img => {
      loadingImages.value.add(img.id)
      nextTick(() => setImageTimeout(img))
    })
  }
  // 新图片加入后，重新观察
  nextTick(() => observeNewImages())
}, { immediate: true })
```

改为：
```js
watch(() => props.images.length, () => {
  const newImages = props.images
  if (newImages.length === 0) {
    displayedImages.value = []
    visibleImages.value.clear()
    failedImages.value.clear()
    loadingImages.value.clear()
    loadedImages.value.clear()
    retryingImages.value.clear()
    retrySuccessImages.value.clear()
    return
  }
  const existingIds = new Set(displayedImages.value.map(img => img.id))
  const newItems = newImages.filter(img => !existingIds.has(img.id))
  if (newItems.length > 0) {
    displayedImages.value = [...displayedImages.value, ...newItems]
    // 新图片加入后标记为正在加载（状态完全由 el-image 的 @load/@error 事件驱动退出）
    newItems.forEach(img => {
      loadingImages.value.add(img.id)
    })
  }
  // 新图片加入后，重新观察
  nextTick(() => observeNewImages())
}, { immediate: true })
```

- [ ] **Step 3: 删除 IMAGE_LOAD_TIMEOUT 与两个函数（L609-631）**

把：
```js
// 超时检测图片加载失败
const IMAGE_LOAD_TIMEOUT = 10000 // 10秒超时

const clearImageTimeout = (imageId) => {
  if (imageLoadTimeouts.value.has(imageId)) {
    clearTimeout(imageLoadTimeouts.value.get(imageId))
    imageLoadTimeouts.value.delete(imageId)
  }
}

const setImageTimeout = (image) => {
  clearImageTimeout(image.id)
  const timeoutId = setTimeout(() => {
    // 超时后检查：如果图片在 loadingImages 但不在 loadedImages，认为加载失败
    if (loadingImages.value.has(image.id) && !loadedImages.value.has(image.id)) {
      if (!props.saveDataMode) {
        failedImages.value.add(image.id)
      }
    }
    loadingImages.value.delete(image.id)
    imageLoadTimeouts.value.delete(image.id)
  }, IMAGE_LOAD_TIMEOUT)
  imageLoadTimeouts.value.set(image.id, timeoutId)
}
```

整段替换为：
```js
（整段删除，前后各保留 1 个空行）
```

- [ ] **Step 4: 修改 handleImageRetry（L637-671）**

把：
```js
const handleImageRetry = async (image, event) => {
  if (event) {
    event.stopPropagation()
  }

  retryingImages.value.add(image.id)
  failedImages.value.delete(image.id)
  loadingImages.value.add(image.id)
  clearImageTimeout(image.id)

  let apiSuccess = false
  if (props.sourceMode === 'local') {
    try {
      await api.get(`/gallery/cache/preview/local/${image.id}`)
      apiSuccess = true
    } catch (e) {
      ElMessage.error('生成缩略图失败')
    }
  } else {
    try {
      await api.get(`/gallery/cache/preview/fetch/${image.id}`)
      apiSuccess = true
    } catch (e) {
      ElMessage.error('缓存预览图失败')
    }
  }

  retryingImages.value.delete(image.id)

  if (!apiSuccess) {
    failedImages.value.add(image.id)
    nextTick(() => setImageTimeout(image))
  }
  // 如果 API 成功，等待 el-image 的 load/error 事件处理状态
}
```

改为：
```js
const handleImageRetry = async (image, event) => {
  if (event) {
    event.stopPropagation()
  }

  retryingImages.value.add(image.id)
  failedImages.value.delete(image.id)
  loadingImages.value.add(image.id)

  let apiSuccess = false
  if (props.sourceMode === 'local') {
    try {
      await api.get(`/gallery/cache/preview/local/${image.id}`)
      apiSuccess = true
    } catch (e) {
      ElMessage.error('生成缩略图失败')
    }
  } else {
    try {
      await api.get(`/gallery/cache/preview/fetch/${image.id}`)
      apiSuccess = true
    } catch (e) {
      ElMessage.error('缓存预览图失败')
    }
  }

  retryingImages.value.delete(image.id)

  if (!apiSuccess) {
    failedImages.value.add(image.id)
  }
  // 如果 API 成功，等待 el-image 的 load/error 事件处理状态
}
```

- [ ] **Step 5: 跑测试验证全部 PASS（TDD 绿）**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/frontend
npm run test
```

预期结果：vitest 报告「8 passed」
若失败：阅读报错，对照 spec § 6 检查 stub/mock 实现，**不要**继续往下走

- [ ] **Step 6: 验证剩余代码无残留引用**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev
grep -nE "IMAGE_LOAD_TIMEOUT|setImageTimeout|clearImageTimeout|imageLoadTimeouts" frontend/src/components/WaterfallGallery.vue
```

预期：**没有**任何输出（grep 无匹配）
若输出仍有残留：回头检查 Step 1-4 是否漏改

- [ ] **Step 7: 提交**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev
git add frontend/src/components/WaterfallGallery.vue frontend/src/components/WaterfallGallery.spec.js
git commit -m "fix(frontend): 删除预览图硬超时机制，避免 fetch pending 时显示 reload 按钮"
```

---

## Task 6：验证生产构建

**Files:** 不修改

- [ ] **Step 1: 跑 vite build**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/frontend
npm run build
```

预期：构建成功，输出 `dist/index.html` 与 `dist/assets/*`

- [ ] **Step 2: 确认改动范围**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev
git status
git log --oneline -3
```

预期：
- `git status` 中无变更（已 commit）或仅显示 Task 2-5 的 commit
- `git log` 显示前 3 个 commit：
  1. fix(frontend): 删除预览图硬超时机制...
  2. build(frontend): vite 配置 vitest 测试段
  3. build(frontend): 引入 vitest 测试依赖

---

## Task 7：手动验证（Slow Network）

**Files:** 不修改（仅使用浏览器）

- [ ] **Step 1: 启动 dev server**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/frontend
npm run dev &
DEV_PID=$!
sleep 3
```

预期：dev server 在 :3000 启动

- [ ] **Step 2: 在浏览器打开并限制网络**

- 浏览器打开 `http://localhost:3000`
- DevTools → Network → Throttling: **Slow 3G**
- 触发一次新搜索/刷新图库

- [ ] **Step 3: 观察行为**

观察窗：
- ☐ 新图片入列 → 看到 shimmer 动画 ✓
- ☐ 等 30 秒+ → 仍然 shimmer，**没有** reload 按钮 ⭐
- ☐ 等真实 fetch 完成 → 图片正常显示 ✓
- ☐ 触发一张图真实失败（手动 reject / 改后端）→ reload 按钮正确显示 ✓

- [ ] **Step 4: 关闭 dev server**

```bash
kill $DEV_PID 2>/dev/null
```

---

## Task 8：推送（**不**创建 PR）

**Files:** 不修改

- [ ] **Step 1: 查看远程与当前分支**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev
git branch --show-current
git remote -v
```

- [ ] **Step 2: push 到当前分支**

```bash
git push origin $(git branch --show-current)
```

预期：`To <remote>.git\n   <hash>..<hash>  <branch> -> <branch>`

- [ ] **Step 3: 验证 push 成功**

```bash
git status
```

预期：`Your branch is up to date with 'origin/<branch>'`

⛔ **不要**运行 `gh pr create` / `gh release create` / 任何 PR 创建命令

- [ ] **Step 4: 输出完成摘要**

在最终汇报中说明：
- 4 个 commit hash（按顺序）
- 测试 pass 数（应为 8）
- push 到的远程分支名
- 提示用户：「下一步如需 MR，请人工到 GitLab/GitHub 创建（按用户要求未自动创建）」

---

## 实施完成后的最终验证清单

- [ ] 8 个测试用例全部 pass（含 T4/T5 bug 回归）
- [ ] `npm run build` 成功
- [ ] dev server 在 Slow 3G 下，30s+ 仍未加载的图片保持 shimmer，无 reload 按钮
- [ ] 真实加载失败时仍能显示 reload 按钮
- [ ] 总共 4 个 commit，全部在 `frontend/` 目录
- [ ] 已 push 到远程分支（**未**创建 PR）
