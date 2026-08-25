# 夜间模式适配方案

> 记录本项目（Vue 3 + Element Plus 2.13 + Vite）夜间模式（dark mode）的适配原理、现有规则、调试方法与新增适配指引。
> 本文档源于 v1.1.8 / v1.1.9 配置页/下载页夜间模式修复的实战经验（见 [release.md](release.md)）。

---

## 1. 核心机制

### 1.1 dark-mode 类如何挂载

`frontend/src/App.vue`：

```vue
<template>
  <div id="app" :class="{ 'dark-mode': isDarkMode }">
    <router-view />
  </div>
</template>
```

```js
const isDarkMode = ref(localStorage.getItem('dark_mode') === 'true')

watch(isDarkMode, (val) => {
  localStorage.setItem('dark_mode', val ? 'true' : 'false')
  document.documentElement.classList.toggle('dark-mode', val)  // 同步到 <html>
})

onMounted(() => {
  document.documentElement.classList.toggle('dark-mode', isDarkMode.value)
})
```

- `.dark-mode` 同时挂在 `<div id="app">`（模板绑定）和 `<html>`（JS 手动）
- 所有暗色规则以 `.dark-mode` 为前缀，集中写在 `App.vue` 的**全局 `<style>`**（非 scoped）

### 1.2 主题变量（`:root` vs `:root.dark-mode`）

| 变量 | 浅色（`:root`） | 深色（`:root.dark-mode`） |
|------|----------------|--------------------------|
| `--bg-primary` | `#f5f7fa` | `#1a1a1a` |
| `--bg-secondary` | `#ffffff` | `#2d2d2d` |
| `--bg-tertiary` | `#ffffff` | `#3d3d3d` |
| `--text-primary` | `#303133` | `#e0e0e0` |
| `--text-secondary` | `#606266` | `#a0a0a0` |
| `--text-muted` | `#909399` | `#707070` |
| `--border-color` | `#e4e7ed` | `#404040` |
| `--hover-bg` | `#f5f7fa` | `#3d3d3d` |

> ⚠️ **关键认知**：这些是**项目自定义变量**，与 Element Plus 的 `--el-*` 变量体系完全独立。

---

## 2. ⚠️ 三大历史坑（必须先知道）

### 坑 1：Element Plus 实际版本是 2.13，不是 2.5

- `package.json` 写的是 `^2.5.0`，但 npm 实际安装 **2.13.6**
- **EP 2.13 不再生成 `.el-button--default` class**！
  - `<el-button>`（无 type）只渲染 `class="el-button"`（不带 `--default`）
  - `type` 默认为空字符串 `""`（见 `use-button.mjs` L24）
  - 因此旧代码 `.dark-mode .el-button.el-button--default` **永远不会命中任何按钮**
- **版本核对方法**：
  ```bash
  cat frontend/node_modules/element-plus/package.json | grep '"version"'
  ```

### 坑 2：EP 自家暗色主题（`dark/css-vars.css`）从未导入

- `frontend/src/main.js` 只导入 `import 'element-plus/dist/index.css'`
- **未导入** `element-plus/theme-chalk/dark/css-vars.css`
- 后果：`--el-color-primary-light-3` 等 EP 派生变量**永远是浅色值**（如 `#66b1ff`），在暗色模式下也不会变深
- 因此：
  - 不能依赖 `var(--el-color-primary-light-3)` 做暗色 hover（浅蓝变浅蓝，视觉无变化）
  - 暗色规则要用**绝对色值**（如 `#1d4ed8`）或项目自定义变量
- 备选方案（未采用）：导入 `dark/css-vars.css` 并让 `<html>` 挂 `.dark` 类，会启用 EP 完整暗色体系，但需迁移全部现有 `.dark-mode` 规则，风险大

### 坑 3：Vue 3 scoped 样式无法向上穿透

- `:deep(.dark-mode)` 只能**向下**穿透到子组件，**不能向上**选中祖先元素上的 `.dark-mode` 类
- Config.vue 曾写过 `:deep(.dark-mode) .menu-item.active` —— 永远不命中
- **规则**：涉及全局 `.dark-mode` 前缀的暗色规则，一律放 `App.vue` 的全局 `<style>`，不要放组件的 `<style scoped>`

---

## 3. 适配策略总览

| 组件类型 | 策略 | 说明 |
|---------|------|------|
| **纯 EP 组件**（按钮/分页/标签等） | 覆盖 CSS 变量 + `!important` 覆盖属性 | EP 2.13 用 CSS 变量驱动，变量覆盖通常够用，但对写死的属性需 `!important` |
| **自定义组件**（Config.vue 侧边栏等） | 在 `App.vue` 全局样式按 class 覆盖 | 不能依赖 `:deep()` 向上穿透 |
| **页面局部**（Download.vue 错误卡片） | 组件 `<style scoped>` 内直接加 `.dark-mode` 前缀 | 注意选择器作用域，若类在父级需移全局 |

---

## 4. 已适配组件清单（现状快照）

> 以下规则全部位于 `frontend/src/App.vue` 全局 `<style>`（约 450 行）。

### 4.1 el-button（L249-311）

**纯按钮（无 type）** —— 用 `:not()` 排除有专用规则的语义类型：

```css
.dark-mode .el-button:not(.el-button--primary):not(.el-button--danger):not(.el-button--text),
.dark-mode .el-button.el-button--success,
.dark-mode .el-button.el-button--warning,
.dark-mode .el-button.el-button--info {
  background-color: var(--bg-tertiary) !important;
  border-color: var(--border-color) !important;
  color: var(--text-primary) !important;
}
```

> ⚠️ **不要用 `:not([class*="el-button--"])`** —— `size="small"` 会渲染 `el-button--small` class，被字符串匹配误伤！

**primary / danger** —— 用绝对色值覆盖基底 + hover + active：

```css
.dark-mode .el-button.el-button--primary {
  background-color: #2563eb !important;  /* 基底 */
  color: #e0e0e0 !important;
}
.dark-mode .el-button.el-button--primary:hover {
  background-color: #1d4ed8 !important;  /* hover */
  color: #fff !important;
}
.dark-mode .el-button.el-button--primary:active {
  background-color: #1e40af !important;  /* active */
  color: #fff !important;
}
```

| 状态 | primary | danger |
|------|---------|--------|
| 基底 | `#2563eb` | `#dc2626` |
| hover | `#1d4ed8` | `#b91c1c` |
| active | `#1e40af` | `#991b1b` |

### 4.2 el-segmented（L313-346）

**关键认知**：EP 的选中背景不在 `.is-selected` 元素上，而在独立的**滑动滑块** `.el-segmented__item-selected` 上，读取变量 `--el-segmented-item-selected-bg-color`：

```css
.dark-mode .el-segmented {
  --el-segmented-item-color: var(--text-primary);
  --el-segmented-item-hover-color: var(--text-primary);   /* ⚠️ 文字色，不是背景色！ */
  --el-segmented-item-selected-bg-color: #2563eb;          /* 滑块背景 */
  background-color: var(--bg-tertiary);
}
```

> ⚠️ `--el-segmented-item-hover-color` 是 **hover 文字色**，曾被误设为 `var(--hover-bg)`（深灰背景色）导致 hover 时字与背景同色不可见！

**移动端垂直堆叠**（Config.vue）：
- 复用 EP 内置 `direction="vertical"` prop，无需自定义 DOM
- 断点 `<540px`，`window.matchMedia` 监听（Safari < 14 fallback `addListener`）
- `onUnmounted` 清理监听器

```js
const SEGMENTED_VERTICAL_BREAKPOINT = 540
const segmentedDirection = ref('horizontal')
const mqlSegmented = window.matchMedia(`(max-width: ${SEGMENTED_VERTICAL_BREAKPOINT - 1}px)`)
const updateSegmentedDirection = (e) => {
  segmentedDirection.value = e.matches ? 'vertical' : 'horizontal'
}
updateSegmentedDirection(mqlSegmented)
mqlSegmented.addEventListener('change', updateSegmentedDirection)
```

```css
@media screen and (max-width: 539px) {
  .proxy-mode-segmented {
    min-width: 0;   /* 取消水平模式下的 320px 约束 */
    width: 100%;
  }
}
```

### 4.3 el-pagination（L155-194）

EP 分页的背景变量默认指向 `--el-fill-color-blank`（白色），`dark/css-vars.css` 未导入所以不变：

```css
.dark-mode .el-pagination {
  --el-pagination-bg-color: var(--bg-tertiary);
  --el-pagination-button-disabled-bg-color: var(--bg-secondary);
  --el-pagination-button-color: var(--text-secondary);
  --el-pagination-button-disabled-color: var(--text-muted);
}
.dark-mode .el-pagination .btn-prev,
.dark-mode .el-pagination .btn-next { background: var(--bg-tertiary); }
.dark-mode .el-pager li { background: var(--bg-tertiary); }
.dark-mode .el-pager li.active { background: var(--el-color-primary); color: #fff; }
.dark-mode .el-pagination__sizes .el-select .el-input__wrapper { background: var(--bg-tertiary); }
```

### 4.4 el-table（L106-145）

EP 表格**多层元素各自有白底**，需逐层覆盖：

```css
.dark-mode .el-table td.el-table__cell { background: var(--bg-secondary); }
.dark-mode .el-table__body-wrapper { background: var(--bg-secondary); }
.dark-mode .el-table__empty-block { background: var(--bg-secondary); }
.dark-mode .el-table__fixed-right-patch { background: var(--bg-secondary) !important; }  /* EP 写死 #fff */
.dark-mode .el-table--striped .el-table__body tr.el-table__row--striped td.el-table__cell { background: var(--bg-tertiary); }
.dark-mode .el-table__body tr:hover > td.el-table__cell { background: var(--hover-bg); }
```

### 4.5 el-tag（L348-384）

按 6 种 type 各给深色版（深底浅字，语义色保持一致）：

```css
.dark-mode .el-tag.el-tag--primary { background-color: #1a3a6b; color: #93c5fd; }
.dark-mode .el-tag.el-tag--success { background-color: #1a3d2e; color: #86efac; }
.dark-mode .el-tag.el-tag--warning { background-color: #3d2e1a; color: #fde68a; }
.dark-mode .el-tag.el-tag--danger  { background-color: #3d1a1a; color: #fca5a5; }
.dark-mode .el-tag.el-tag--info    { background-color: #2d2d3d; color: #d1d5db; }
```

### 4.6 el-radio-button（L417-444）

**关键认知**：EP 的单选按钮组（多联开关，如收藏夹配置页 `buttonMode`）的 `.el-radio-button__inner` 默认背景是 `--el-fill-color-blank`（白色，EP 2.13 静态值），暗色模式下不自动适配，会显示**白色方块**。

**驱动变量**：
- `--el-fill-color-blank`（背景，EP 2.13 静态白色）
- `--el-text-color-regular`（文字，EP 2.13 静态深色）

**EP 选中态选择器**（来自 `node_modules/element-plus/theme-chalk/src/radio-button.scss` L72-95）：

```css
.el-radio-button.is-active .el-radio-button__original-radio:not(:disabled)+.el-radio-button__inner {
  color: var(--el-radio-button-checked-text-color, var(--el-color-white));
  background-color: var(--el-radio-button-checked-bg-color, var(--el-color-primary));
  border-color: var(--el-radio-button-checked-border-color, var(--el-color-primary));
  box-shadow: -1px 0 0 0 var(--el-radio-button-checked-border-color, var(--el-color-primary));
}
```

特异性 **(0,5,0)**，**无 `!important`**。

**修复**（App.vue 全局样式，3 条规则）：

```css
/* 未选基底：加 :not(.is-active) 限定，避免覆盖 EP 选中态蓝色 */
.dark-mode .el-radio-button:not(.is-active) .el-radio-button__inner {
  background: var(--bg-tertiary);
  color: var(--text-primary);
  border-color: var(--border-color);
  outline-color: var(--border-color);  /* EP 用 outline 而非 border 描边 */
}
/* 首尾按钮圆角重置（EP 自带 first/last 圆角，深色下保持一致） */
.dark-mode .el-radio-button:not(.is-active):first-child .el-radio-button__inner,
.dark-mode .el-radio-button:not(.is-active):last-child .el-radio-button__inner {
  border-radius: 0;
}
/* hover：未选 hover 文字变蓝 + 背景变深灰（与 el-segmented 一致） */
.dark-mode .el-radio-button:not(.is-active) .el-radio-button__inner:hover {
  color: var(--el-color-primary);
  background: #4a4a4a;
  outline-color: var(--border-color);
}
```

**关键修复点**：去掉所有 `!important` + 加 `:not(.is-active)` 限定未选基底。

| 状态 | 规则 | 特异性 | 胜出 | 视觉效果 |
|------|------|--------|------|----------|
| 未选基底 | App.vue `:not(.is-active)` 覆盖 | (0,4,0) | ✅ App.vue | 深灰底 + 浅字 |
| **选中态** | EP `.is-active ... + .__inner` | (0,5,0) | ✅ EP | **蓝色底 + 白字** |
| 未选 hover | App.vue `:not(.is-active):hover` | (0,5,0) | ✅ App.vue | 深灰底 + 蓝字 |

**为什么不能用 `!important`**：`!important` 优先级 > 无 `!important`，无论特异性高低。
若给未选基底的覆盖加 `!important`，会吞掉 EP 选中态（无 `!important`）的蓝色 → 选中态变深灰，无法区分。

**参考实现差异**：
- `el-segmented`（§4.2）选中态由 CSS 变量 `--el-segmented-item-selected-bg-color` 驱动，覆盖变量不会冲突 → 不需要 `:not(.is-selected)` 限定
- `el-radio-button` 选中态由类名选择器驱动，覆盖属性会被 `!important` 吞掉 → 必须 `:not(.is-active)` 限定

**适配日期**：
- 2026-08-22（v1.1.10）：初版，仅覆盖未选基底
- 2026-08-25（v1.1.11）：修复选中态蓝色丢失 + hover 加背景反馈

### 4.7 其他组件

| 组件 | 规则 |
|------|------|
| el-switch | `--el-switch-off-color` / `--el-switch-on-color: #1e6fd9` + 圆点 `#c0c4cc` |
| el-input / el-input-number | `--bg-secondary` 底 + `#409EFF` focus 描边 |
| el-textarea | `--bg-secondary` 底 + `--border-color` 边框 |
| el-dialog / el-card | `background: var(--bg-secondary)` |
| el-form-item__label | `color: var(--text-secondary)` |
| el-alert | `background-color: var(--bg-tertiary)` + `--text-primary` |
| el-checkbox / el-radio label | `color: var(--text-primary)` |
| el-radio-button | 见 §4.6 |
| el-tooltip（light） | `--bg-secondary` + `--border-color` + 阴影 |
| Config.vue 侧边栏 active | `.dark-mode .config-menu .menu-item.active` → `#1a1a2e` + 柔蓝描边 |

### 4.8 页面局部适配

**Download.vue 错误卡片**（组件 scoped 内可直接加）：

```css
.card-error { background: #fef0f0; }        /* 浅色 */
.dark-mode .card-error { background: #3d1f1f; }  /* 深色 */
```

---

## 5. 新增组件 / 新增页面的适配流程

1. **确认 EP 实际版本**（坑 1），确认目标组件的 DOM 结构：
   ```bash
   cat frontend/node_modules/element-plus/package.json | grep '"version"'
   ```
2. **检查 EP 是否内置暗色支持**：
   - 搜索组件 `*.mjs` 源码中是否有 `dark` 相关分支或 CSS 变量
   - 确认目标元素实际由哪个变量驱动（如 segmented 选中色在独立滑块元素上）
3. **优先覆盖 CSS 变量**，其次 `!important` 覆盖属性：
   - 变量覆盖：`--el-xxx-color`（若 EP 未导入 dark 主题，派生变量值是浅色的，需绝对色值）
   - 属性覆盖：EP 直接写死 background/color 的属性需 `!important`
4. **暗色规则放对位置**：
   - 全局组件规则 → `App.vue` 全局 `<style>`，前缀 `.dark-mode`
   - 页面内 class → 组件 scoped 内直接加 `.dark-mode` 前缀（若该 class 存在于组件自身 DOM）
   - ❌ 不要用 `:deep(.dark-mode)` 试图向上穿透
5. **验证**：
   ```bash
   cd frontend && npm run build   # 必须 exit 0
   # 检查构建产物含新规则
   grep -o "\.dark-mode.*<目标>" dist/assets/index-*.css
   ```
6. **浏览器验证**（dev server）：
   - 切换暗色模式，逐组件检查基底态 / hover / active / focus 四态
   - 窄屏（<540px）检查移动端布局

---

## 6. 常见故障速查表

| 症状 | 根因 | 修复 |
|------|------|------|
| 按钮不变暗 | `:not([class*="el-button--"])` 误伤 `el-button--small` | 改用 `:not(.el-button--primary):not(.el-button--danger):not(.el-button--text)` |
| 纯按钮不变暗 | EP 2.13 无 `--default` class | 用 `:not()` 排除语义类型后匹配 |
| hover 无视觉变化 | `--el-color-primary-light-3` 是浅色值 | 用绝对色值（`#1d4ed8`）覆盖 hover |
| hover 字与背景同色 | `--el-segmented-item-hover-color` 误设为背景色 | 设为文字色 `var(--text-primary)` |
| segmented 选中滑块颜色不变 | 未设 `--el-segmented-item-selected-bg-color`（只设了 `-active-`） | 补设 `-selected-` 变量 |
| **el-radio-button 选中态丢失蓝色** | **覆盖规则用 `!important`，吞掉 EP `.is-active` 选择器（无 `!important`，特异性 0,5,0）的蓝色背景** | **去掉 `!important` + 加 `:not(.is-active)` 限定未选基底** |
| el-radio-button hover 无视觉反馈 | 只改 `color`，未改 `background` | hover 加 `background: #4a4a4a`（与 el-segmented 一致） |
| 表格局部白色 | 只覆盖了 `.el-table`，漏了 cell/body/fixed-patch | 逐层覆盖（见 §4.4） |
| 分页白色 | 只改 `color`，未改 `--el-pagination-bg-color` | 覆盖变量 + btn/pager 元素 |
| 标签白色 | 无 `.el-tag` 暗色规则 | 按 type 各配深色版 |
| scoped 组件内 `:deep(.dark-mode)` 不生效 | Vue3 `:deep()` 无法向上穿透 | 移到 App.vue 全局样式 |
| `filter: brightness()` 无效 | 对蓝色按钮肉眼不可察 | 改用绝对色值覆盖颜色 |

---

## 7. 相关文件

| 文件 | 内容 |
|------|------|
| `frontend/src/App.vue` | 全局暗色规则（L106-450）+ `.dark-mode` 挂载逻辑（L2-19）|
| `frontend/src/views/Config.vue` | segmented 移动端垂直堆叠逻辑（L368-372）+ 响应式 CSS（L1054-1062）|
| `frontend/src/views/Download.vue` | card-error 深色适配（L657）|
| `docs/superpowers/specs/2026-08-05-config-popup-dark-mode-fix-design.md` | 初始设计稿 |

---

*最后更新：v1.1.11 el-radio-button 选中态蓝色丢失修复（2026-08-25，去掉 `!important` + 加 `:not(.is-active)` 限定 + hover 加背景反馈，更新 §4.6 与 §6）*
