# 预览图加载 Bug 修复 — 设计文档

**状态**：Draft
**日期**：2026-07-14
**分支**：`next_dev`
**类型**：Bug 修复 + 测试引入

---

## 1. 目标

修复 `frontend/src/components/WaterfallGallery.vue` 中的两个相关 bug：

1. **症状 1（最关键）**：当 `<el-image>` 的 fetch 仍在 pending 状态时，UI 显示"重新加载"按钮。这给用户造成"加载失败"的错误印象，实际上请求还在网络栈里挂着。
2. **症状 2（次要）**：加载超过 10 秒的图片的"加载中"动画（`skeleton-shimmer`）消失，用户看到不完整的占位体验。

修复完成后：
- 任何图片在 `<el-image>` 内部仍处于 loading 状态时，仅显示 placeholder（shimmer 动画），绝不会出现 reload 按钮
- 仅当 `<el-image>` 真实触发 `@error` 事件时（即浏览器网络栈已判定失败），才显示 reload 按钮
- 状态完全由 `<el-image>` 真实事件驱动，无任何主动 `setTimeout` 干预

---

## 2. 背景：当前 Bug

### 触发场景

```text
用户首次刷新图库 → 后端为每张图预生成缩略图（首次访问 yande.re 域）
  ↓
前端 <img> 标签发起 HTTP 请求，浏览器层与后端建立 TCP，等待响应
  ↓
T+10s：硬超时触发（详见 § 3）
  ↓
UI 状态变化：
  - loadingImages.delete(id)   ← placeholder 立刻消失
  - failedImages.add(id)       ← reload 按钮立刻出现
  - <el-image> 内部 fetch 仍在浏览器 pending
  ↓
T+15s：浏览器终于拿到字节流，<el-image> 触发 @load 事件
  - handleImageLoad 把 failedImages.delete → reload 按钮消失
  - 用户体验：在 5 秒里看到 reload 图标，感觉"图片挂了"，实际它后来加载出来了
```

### 影响范围

| 场景 | 频率 | 严重度 |
|------|----|----|
| 首次访问图片（后端首次预生成缩略图） | 中（每张图首次） | 高（误导用户）|
| 跨外网拉图（在线模式 `sourceMode !== 'local'`） | 高 | 高 |
| 慢网络/弱网 | 中 | 中 |
| 本地模式（已缓存） | 低（命中缓存快） | 低 |

---

## 3. 根因分析

### 反模式 1：硬超时强制标 failed

文件：`frontend/src/components/WaterfallGallery.vue` 第 609、618-631 行

```js
const IMAGE_LOAD_TIMEOUT = 10000 // 10秒超时

const setImageTimeout = (image) => {
  clearImageTimeout(image.id)
  const timeoutId = setTimeout(() => {
    // 超时后检查：如果图片在 loadingImages 但不在 loadedImages，认为加载失败
    if (loadingImages.value.has(image.id) && !loadedImages.value.has(image.id)) {
      if (!props.saveDataMode) {
        failedImages.value.add(image.id)   // ⚠️ 把 pending 状态标成 failed
      }
    }
    loadingImages.value.delete(image.id)
    imageLoadTimeouts.value.delete(image.id)
  }, IMAGE_LOAD_TIMEOUT)
  imageLoadTimeouts.value.set(image.id, timeoutId)
}
```

**问题**：
- 第 624 行 `failedImages.value.add(image.id)` 主动将 pending 状态的图片标为失败
- 这与 `<el-image>` 内部的真实状态无关
- 即使 10s 后 `fetch` 仍在进行，UI 也立即显示 reload 按钮
- 该 `setTimeout` 不取消浏览器层请求，所以请求最终还会到，但 UI 已经先显示"失败"

### 反模式 2：placeholder 显示条件被硬超时过快地清除

文件：`frontend/src/components/WaterfallGallery.vue` 第 65-67 行、第 627 行

```vue
<template #placeholder>
  <div v-if="loadingImages.has(image.id)"
       class="image-placeholder skeleton-shimmer"></div>
</template>
```

```js
// setImageTimeout 内：
loadingImages.value.delete(image.id)  // ⚠️ 10s 后强制清掉
```

**问题**：
- placeholder 是否显示完全耦合 `loadingImages` 集合
- 一旦该 id 从 set 中删除（无论是真实 `handleImageLoad` 触发还是 10s 硬超时），placeholder div 立刻卸载
- 短时间窗口内 placeholder div 消失 → 用户看到空 div → reload 图标叠加

### 反模式 3：双状态机不一致

- `<el-image>` 内部状态：`imageLoading === true/false`（由 `<img>` 的 onload/onerror 决定）
- 自定义状态：`loadingImages` Set（由 `@load/@error` + setTimeout 决定）

两个状态机独立维护 → `<el-image>` 还在 pending，但自定义状态已经标 failed → UI 与实际状态脱钩

---

## 4. 修复策略

### 4.1 整体方向

**彻底移除硬超时机制**，让 `<el-image>` 的真实事件作为状态的唯一真相。

### 4.2 新状态机

```
                  add loadingImages
[入列] ──────────────────────────▶ [LOADING]
                                       │
                          @load事件     │     @error事件
                                       ▼             ▼
                                   [LOADED]      [FAILED]
                                                       ▲
                                                       │ retry 失败
                                                 [RETRYING]
                                                       ▲
                                                       │ retry 成功
                                                  (用户点 reload)
```

所有转换完全由 `<el-image>` 内部的 `img` 标签真实 `onload/onerror` 事件驱动。
不再有任何 `setTimeout` 干预 `loadingImages`/`failedImages`。

### 4.3 设计原则

| 原则 | 体现 |
|----|----|
| **Single source of truth** | 状态机只由 `<el-image>` 的 `@load @error` 驱动 |
| **最小改动** | 仅删除 ~30 行代码，不重构状态机迁移到 Pinia |
| **回归测试保护** | 显式覆盖"30s 后仍未 @load"→ 不显示 reload |
| **不动 CSS / 模板 v-if** | placeholder 模板条件 `<div v-if="loadingImages.has(id)">` 已正确，仅清掉导致它消失的反模式 |

### 4.4 边界处理

| 场景 | 行为 |
|----|----|
| 极慢网络（>10 分钟） | placeholder 持续显示；浏览器网络栈会自己超时（这超出前端控制）|
| 后端预生成缩略图超时 | placeholder 持续显示；用户可以滚动离开后回来由 IntersectionObserver 处理（保留现有逻辑）|
| `props.saveDataMode === true` | 新行为与旧的"省流模式不动"完全一致（因为旧省流模式也不主动标 failed）|
| `props.images` 清空（搜索切换） | 现有清理逻辑（L297-324）保留，仅删 `imageLoadTimeouts` 相关清理 |
| 用户拖拽排序 | watcher 仅处理"新增 id"，不重复 add loadingImages，行为保持 |

---

## 5. 文件改动清单

### 5.1 修改文件

| 文件 | 改动 | 行数 |
|----|----|----|
| `frontend/src/components/WaterfallGallery.vue` | 删除 `IMAGE_LOAD_TIMEOUT` 常量、删除 `setImageTimeout`、`clearImageTimeout` 函数、删除 `imageLoadTimeouts` 变量、删除相关调用 | -30 |
| `frontend/vite.config.js` | 新增 `test:` 段（happy-dom、spec 包含规则、css: false） | +10 |
| `frontend/package.json` | 新增 `vitest`、`@vue/test-utils`、`happy-dom` 到 devDependencies；新增 `test` 与 `test:watch` 脚本 | +10 |

### 5.2 新建文件

| 文件 | 内容 |
|----|----|
| `frontend/src/components/WaterfallGallery.spec.js` | 8 个组件测试（详见 § 6）|

### 5.3 不修改（明确声明）

- ❌ `frontend/src/views/Gallery.vue`（父组件）
- ❌ `frontend/src/api/*`（axios 实例、API 封装）
- ❌ `frontend/src/components/WaterfallGallery.vue` 内部其他逻辑（`handleImageLoad`、`handleImageError`、`IntersectionObserver`、reorder 算法、touch/mouse handlers）
- ❌ 所有 CSS / Scoped 样式
- ❌ 后端任何文件
- ❌ CI 配置（`.github/workflows/`）
- ❌ 项目根的 Dockerfile、docker-compose（无需）

---

## 6. 测试策略

### 6.1 测试设施引入

| 依赖 | 版本 | 用途 |
|----|----|----|
| `vitest` | `^3.2.0` | 测试 runner（项目无测试框架，本次新增）|
| `@vue/test-utils` | `^2.4.0` | `mount()`、`findComponent()`、`$emit` |
| `happy-dom` | `^15.0.0` | DOM 环境 |

**配置文件**：复用 `vite.config.js`（加 `test:` 段），不新建 `vitest.config.ts`。

### 6.2 Stub 策略

**`ElImage` stub**：
```js
ElImage: {
  name: 'ElImage',
  template: '<div class="el-image-stub"><slot name="error"/><slot name="placeholder"/></div>'
}
```
- 原因：happy-dom 中 `<img src="/test.jpg">` 会触发真实网络请求，难精确控制
- stub 后用 `wrapper.findComponent({ name: 'ElImage' }).vm.$emit('load')` 精确触发

**`api` mock**：
```js
vi.mock('@/api', () => ({
  default: { get: vi.fn().mockResolvedValue({ data: 'mocked' }) }
}))
```
- `handleImageRetry` 内部调 `api.get`，不 mock 会发真实请求

### 6.3 测试用例集（8 个）

| ID | 测试名 | 状态 | 核心验证点 |
|----|----|----|----|
| **T1** | 入列 → 默认 LOADING | P0 | `.image-placeholder` 存在，`.retry-button` 不存在 |
| **T2** | `@load` 触发 → LOADED | P0 | placeholder 消失，`.image-loaded` class 出现 |
| **T3** | `@error` 触发 → FAILED | P0 | placeholder 消失，retry 按钮出现 |
| **T4** | ⭐ **30s 后仍未 `@load` → placeholder 持续显示** | P0 | **bug 核心回归**：fake timers 30s 后 reload 按钮**仍然不存在** |
| **T5** | 60s 后仍未 `@load` 仍保持 LOADING | P0 | T4 强化版，防遗漏的延迟 timeout |
| **T6** | 用户点 reload → retrying → 重新进入 LOADING | P1 | `handleImageRetry` 主路径未被破坏 |
| **T7** | retry 失败（mock api 抛错）→ 重新显示 reload | P1 | `handleImageRetry` 失败分支 |
| **T8** | `props.images = []` → 全部状态 set 清空 | P1 | 清理路径未破坏 |

### 6.4 T4/T5 关键代码

```js
it('30s 后仍未 @load 仍保持 LOADING 状态', async () => {
  vi.useFakeTimers()
  const wrapper = factory()
  await wrapper.vm.$nextTick()
  
  // 推进 30 秒（实际上新机制下没有任何 setTimeout 被注册）
  vi.advanceTimersByTime(30_000)
  await wrapper.vm.$nextTick()
  
  // ⭐ 关键断言：reload 按钮绝不能出现
  expect(wrapper.find('.retry-button').exists()).toBe(false)
  
  vi.useRealTimers()
})
```

**价值**：未来若有人无意中加回 `setImageTimeout`，这个测试会**立即失败**。

---

## 7. 风险与回退

### 7.1 风险清单

| 风险 | 等级 | 缓解 |
|----|----|----|
| 首次 install vitest 网络问题 | 中 | 实施前 `node -v` 与 `npm ping`；如需配置 `npm config set proxy http://192.168.100.222:20171` |
| Node 版本 < 18 | 中 | 已确认环境 Node 22.23.1 ✓ |
| fake timers 干扰 element-plus | 低 | T4/T5 不触发 element-plus 内部交互 |
| 删除 nextTick 后顺序变化 | 低 | sync add loadingImages 顺序更安全 |
| `setImageTimeout` 留作 internal API | 低 | 完全删除（不留 dead code） |

### 7.2 回退方案

| 触发 | 操作 |
|----|----|
| 单测失败 | `git diff` 检查；只动 `WaterfallGallery.vue` 相关行 |
| `npm run build` 失败 | `git checkout frontend/vite.config.js frontend/package.json` |
| dev runtime 异常 | `git revert HEAD`（单 commit）|
| 需要保留 `setImageTimeout` 但不标 failed | 重新引入函数，但删第 622-625 行的 `if` 块 |

---

## 8. 验证步骤（顺序执行）

### 8.1 预备

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/frontend
node -v                                                       # 应 ≥ 18
# npm config set proxy http://192.168.100.222:20171           # 仅当 npm ping 失败时
# npm config set https-proxy http://192.168.100.222:20171
```

### 8.2 依赖安装

```bash
# 编辑 package.json 后
npm install
ls node_modules/vitest/package.json   # 确认装上
```

### 8.3 编写测试（先于 .vue 修改）

```bash
# 新建 WaterfallGallery.spec.js
npm run test                            # 期望：所有用例 FAIL（因 .vue 还没改）
```

### 8.4 修改组件代码

按 § 5.1 删除 WaterfallGallery.vue 相关行：
- 删除 L179：`imageLoadTimeouts`
- 删除 L308-309：`imageLoadTimeouts` 清理
- 修改 L319：去掉 `nextTick(() => setImageTimeout(img))`
- 删除 L609：`IMAGE_LOAD_TIMEOUT`
- 删除 L611-616：`clearImageTimeout`
- 删除 L618-631：`setImageTimeout`
- 删除 L645：在 `handleImageRetry` 内 `clearImageTimeout(image.id)`
- 删除 L668：`nextTick(() => setImageTimeout(image))`

```bash
npm run test                            # 期望：8 个用例全部 PASS
```

### 8.5 回归生产构建

```bash
npm run build                           # 应成功
git status                              # 确认只动前端
```

### 8.6 手动验证（推荐）

```bash
npm run dev                             # 启动 :3000
```

- DevTools → Network → Slow 3G
- 访问图库，观察新图片入列 → 持续 shimmer
- 等 30 秒以上，确认 **没有** reload 按钮
- 等 fetch 真正返回，确认图片正常显示

### 8.7 提交

```bash
git add frontend/
git commit -m "fix(frontend): 删除预览图硬超时机制，避免 fetch pending 时显示 reload 按钮"
```

---

## 9. 成功标准

- [ ] 8 个测试用例全部通过（其中 T4/T5 是 bug 核心回归）
- [ ] `npm run build` 成功
- [ ] `npm run dev` 正常启动且功能正常
- [ ] DevTools Slow 3G 下，30 秒+ 仍未加载的图片保持 shimmer，**无 reload 按钮**
- [ ] 真实加载失败的图片**仍然能**显示 reload 按钮（向后兼容）
- [ ] 改动文件数 ≤ 4（1 个 .vue + 1 个 vite.config.js + 1 个 package.json + 1 个新 .spec.js）
- [ ] 现有文件净改动行数（删除 + 修改）≤ 50 行（不计新建 .spec.js）

---

## 10. 范围之外（不做）

- 后端 fetch 超时配置
- IntersectionObserver 重新进入视口的 retry 行为
- Pinia store 化 `loadingImages` / `failedImages`
- 前端其他组件改动
- 任何 CSS / 样式改动
- CI 工作流新增 vitest 自动运行（可在后续 PR 添加）

---

## 11. 相关文档

- 项目规范：`/AGENTS.md`
- 设计参考：`/docs/design.md`
- 重构历史：`/docs/refactor-2026-05-17.md`（图片预览优化相关）

---

**Spec 完成。下一步**：等待用户 review 后进入实现规划（writing-plans skill）。
