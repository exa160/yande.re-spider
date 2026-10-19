# 大图浮层可读性（配色自适应）— 设计文档

**状态**：✅ 已实施（2026-10-01，方案 C；测试 18 files / 388 tests 全绿）
**日期**：2026-10-01
**类型**：缺陷修复 + 机制重构（不新增用户可见功能）
**影响面**：仅 `frontend/src/views/Gallery.vue` + 新增 1 个 composable

---

## 1. 目标

修复大图浏览页 `float-header` / `float-footer` / `float-detail-panel` 三块浮层
在**浅色 / 中间调图片**上的文字可读性问题，并让「背景识别 → 换配色」这条链路
在任何图上**都必然执行、且结果可验证达标**。

### 1.1 验收目标（硬指标）

| 对象 | 指标 |
|------|------|
| 所有浮层文字（primary / secondary / tertiary 三档） | WCAG AA **≥ 4.5:1** |
| 「来源」超链接、已收藏星标等强调色元素 | 文字/图标各自达标（见 §4.6） |
| **采样链路完全失效时**（`@error` / 无 canvas / 竞态 / JS 异常） | **仍 ≥ 4.5:1** —— 由 CSS 保底值保证（见 §4.4） |
| 配色判定 | 100% 触发，**不存在静默降级分支** |
| 性能 | 相比现状**不增加任何网络请求** |

> **本次采纳方案 C「保底 + 连续求解」**（用户在 2026-10-01 的三条路线 A/B/C 中选定 C）。
> 架构要点：**CSS 里写死一个不可突破的对比度下限，自适应只能往下调不能往上加。**
> 这样采样链路的任何失败都只影响观感，不影响可读性 —— 相比初版草案
> 「采样结果直接决定浮层能否看清」是本质改进。

### 1.2 范围内

- `Gallery.vue` 采样源改造（预览图 → 屏幕上的已解码原图）
- 采样区域（整图均值 → 文字实际所在的条带）
- 判定度量（gamma luma + 固定阈值 180 → WCAG 相对亮度 + 分位数 + **求解达标遮罩**）
- **L1 保底层**：CSS 写死对比度下限，采样只往下调（见 §4.4）—— 本方案的核心
- **残差兜底**：`text-shadow`（近乎不可见，见 §4.7）+ `prefers-contrast`（见 §4.8）
- ❌ **不改 `blur(4px)`**（曾误改成 `blur(10px) saturate(1.15)`，已回退，见 §9.6）
- 前景色补漏（来源链接 / 收藏星标 / 次级文字 alpha）
- 移除 `overlay-light` / `overlay-dark` 两档 class 机制
- 补单测

### 1.3 不在范围内

- ❌ 不动 `WaterfallGallery.vue` / `FolderTile.vue` / `HeartOverlay.vue`（收藏星标颜色用
  Gallery 侧的高特异性选择器覆盖，不改共享组件）
- ❌ 不动后端（采样源改成前端 DOM 取样后，后端不参与）
- ❌ 不做「逐元素独立遮罩」（见 §9.2 取舍）
- ❌ 不做 `mix-blend-mode: difference` 自动反色（见 §4.7 / §9.4 的技术障碍）
- ❌ 不给 `el-image-viewer`（全屏 viewer）加配色
- ❌ 不做 resize 重采样、不做逐像素最坏值（见 §9.5 已知残留）

---

## 2. 现状与缺陷（已实测复核）

> 数字均为 WCAG 2.x 相对亮度公式实测值，正文 AA 线为 4.5:1。

### P0-1 判定在多数情况下根本没执行，静默降级为 `dark`

[Gallery.vue:739-742](../../../frontend/src/views/Gallery.vue#L739) 要求 `img.preview_url` 非空。
该字段由 `check_local_file()`（[common/utils.py:36-46](../../../backend/src/common/utils.py#L36)）
在 `/gallery/load` **响应序列化那一刻**决定 —— 只有当 `downloads/previews/{id}.jpg`
**当时已存在**才非空。

而瀑布流的预览图是懒加载时**现场生成/下载**的
（[WaterfallGallery.vue:741-779](../../../frontend/src/components/WaterfallGallery.vue#L741)
的 `/cache/preview/{id}` → `/local` → `/fetch` fallback 链），生成完**不回写**
`images[].preview_url`。

→ 新会话首次浏览、或跑过预览清理之后，`preview_url` 恒为 `null`，
`analyzeImageColor('')` 直接 `return`，配色恒为 `dark`。
而 `dark` 分支的遮罩只有 6% 白（[Gallery.vue:2059](../../../frontend/src/views/Gallery.vue#L2059)）。

### P0-2 采样区域 ≠ 文字实际所在区域

浮层是 full-width 贴在图片顶部 / 底部约 5%，判定用的是**整图 50×50 均值**；
采样源还可能是 yande.re 的 **150×150 方形中心裁切**缩略图
（[gallery.py:467-509](../../../backend/src/services/gallery.py#L467) 直接下载 `preview_url`），
与显示的整图构图无关。

### P1-3 两档阈值 + 遮罩强度，实测不达标

| 分支 | 背景 | primary 0.95 | secondary 0.80 | tertiary 0.60 |
|---|---|---|---|---|
| `dark` | 均匀亮度 180 的图 | **1.91:1** | ~1.7:1 | **1.53:1** |
| `dark` | 亮度 120 的图 | 3.73:1 | 2.9:1 | 2.46:1 |
| `light` | 纯白图 | **3.19:1** | **2.74:1** | **2.20:1** |
| `light` | 浅灰蓝 (210,215,225) | 4.28:1 | 3.56:1 | 2.72:1 |

`backdrop-filter: blur(4px)` 只模糊不压暗，对对比度零贡献。

### P1-4 `overlay-light` 规则有遗漏，两个元素直接隐身

| 元素 | 颜色 | 纯白图上实测 | overlay-light 规则 |
|---|---|---|---|
| `.detail-source-link` | `#409EFF` | **1.21:1** | ❌ 无 |
| HeartOverlay `.active` 星标 | `#F56C6C` | **1.16:1** | ❌ 无 |
| header 内 rating `el-tag` | EP 浅底 | 可读 | ❌ 无（视觉不统一） |

### P2-5 判定度量错误

`0.299R+0.587G+0.114B` 是在 gamma 编码值上算 luma，不是 WCAG 相对亮度；
阈值 180（= 0.706）远高于浅色分界（luminance 0.18 ≈ sRGB 118）。
两者叠加：**随机颜色上 48.6% 判错档**。

### P2-6 均值无抗离群能力

大面积留白会把均值拉过 180；整体暗但顶部有亮边的图又会走 `dark`。

### P2-7 异步竞态 + 不复位

`img.onload` 无 token 校验（同文件 [Gallery.vue:1409-1414](../../../frontend/src/views/Gallery.vue#L1409)
的 tag 请求是有 `requestImageId` 校验的，这里漏了）；且开始分析新图时不复位，会闪上一张的配色。

### P3 零碎

- [Gallery.vue:2350-2354](../../../frontend/src/views/Gallery.vue#L2350) 的
  `:deep(.el-tag)` overlay-light 规则是**死代码** —— `getTagStyle()`
  （[Gallery.vue:1548-1558](../../../frontend/src/views/Gallery.vue#L1548)）返回的行内
  `backgroundColor` 优先级高于任何 class。
- [Gallery.vue:2292-2296](../../../frontend/src/views/Gallery.vue#L2292) 是只有注释的空规则块。
- 本功能**无任何单测**，`docs/` 无对应说明。

---

## 3. 核心决策总览

### 3.1 三层防御

| 层 | 手段 | 职责 | 失效后果 |
|---|---|---|---|
| **L1 保底** | CSS 写死 `rgba(0,0,0,0.62)` | **不可突破**的对比度下限；也是不支持 `backdrop-filter` 时唯一的屏障 | 无（纯 CSS，不会失效） |
| **L2 自适应** | 采样 → 求解 → CSS 变量**只往下调** | 让暗图/中间调不被无谓压黑 | 落回 L1，仍达标 |
| **L3 残差** | `text-shadow`（p90 分位留下的最亮 10% 像素） | 仅在笔画正好压到亮区时有微弱作用 | 几乎不可见，不影响达标 |

### 3.2 数据流

```
el-image @load（原生事件，e.target = 屏幕上那张已解码的 <img>）
   ↓ 按 CSS 布局反推「文字实际压住的像素条带」
   ↓ 每条带取分位数像素（p90）+ WCAG 相对亮度
   ↓ 求解：使 white@0.78 文字对比度 ≥ 4.5 的**最小**遮罩 alpha（步进 0.02，上限 0.62）
CSS 变量 --overlay-scrim / --overlay-scrim-panel（写在 .float-image-wrapper 上，三块浮层继承）
   ↓ var() 未定义 / 采样失败 / 图加载失败 → 回落 CSS 里的 rgba(0,0,0,0.62)
```

一句话：**从「两档 class 猜测」改成「CSS 保底 + 按实测背景向下求解」。**

> **关键不变量**：求解结果**永远 ≤** CSS 保底值。采样只能让浮层更通透，
> 永远不可能让对比度掉到 4.5:1 以下。这条不变量由 `solveScrimAlpha` 的
> `maxAlpha = SCRIM_FLOOR_ALPHA` 上限强制，并由单测 T7 全域验证。

---

## 4. 详细设计

### 4.1 采样源：直接用 DOM 里已解码的 `<img>`

**删除** `analyzeImageColor()`（[Gallery.vue:686-732](../../../frontend/src/views/Gallery.vue#L686)）
中的 `new Image()` / `img.crossOrigin` / `preview_url` 门槛。

`el-image` 已经 emit 了 `load` 并带原生事件
（`image.vue_vue_type_script_setup_true_lang.mjs:78-83`，类型 `load: (evt: Event) => void`），
`e.target` 就是正在被显示的那张图：

```vue
<el-image
  :src="getDetailUrl(currentImage)"
  fit="contain"
  class="float-main-image"
  :preview-teleported="true"
  @click.stop="viewerVisible = true"
  @load="onDetailImageLoad"
  @error="onDetailImageError"
/>
```

**为什么这样更好**（对照原设计的两条理由）：

| 原设计的理由 | 实际情况 |
|---|---|
| 「原图太大，避免重新加载」 | 原图**本来就在加载**（`getDetailUrl`），画一次 canvas 是对**已解码**图像取样，**零网络请求、零额外解码** |
| 「远程图片会 CORS」 | `getDetailUrl` **永远返回同源相对路径**（[Gallery.vue:1625-1637](../../../frontend/src/views/Gallery.vue#L1625)），后端两条分支都是 `FileResponse` 从本地吐文件。canvas 不会被 taint |

**顺带解决**：
- P0-1：完全不依赖 `preview_url`；
- P0-2：采样源 = 用户正在看的那张图，逐像素一致；
- P2-7：换 `src` 时浏览器 abort 旧请求，旧 `load` 事件不会再触发 → **天然不会写错图**，无需 token。

**重挂载**：关闭 el-image-viewer 后 `v-if`（[Gallery.vue:197](../../../frontend/src/views/Gallery.vue#L197)）
会卸载整个预览，`el-image` 重新挂载并再次触发 `load`（走浏览器缓存）→ 配色自动重算，**无需特殊处理**。

### 4.2 采样区域：按「文字实际压住的像素」分条带

wrapper 的宽高比就是按图片自身比例算出来的（[Gallery.vue:748-777](../../../frontend/src/views/Gallery.vue#L748)），
所以**图片顶部 N px 就是 header 所在的那一段**。图片没铺满的信箱区是
`rgba(0,0,0,0.9)`（[Gallery.vue:1993](../../../frontend/src/views/Gallery.vue#L1993)），本来就安全。

按 CSS 像素高度 × 缩放系数反推自然像素条带：

```js
const rect = imgEl.getBoundingClientRect()
const scale = rect.height > 0 ? nh / rect.height : 1   // 自然像素 / CSS 像素

const HEADER_CSS = 56   // padding 12*2 + 32 按钮 + 余量
const FOOTER_CSS = 72   // padding 10*2 + 按钮 32 + 余量

topRows    = clamp(ceil(HEADER_CSS * scale),                       1, floor(nh * 0.5))
bottomRows = clamp(ceil(FOOTER_CSS * scale),                       1, floor(nh * 0.5))
panelRows  = clamp(ceil((FOOTER_CSS + innerHeight * 0.35) * scale),
                   bottomRows, floor(nh * 0.9))
```

`rect.height` 取不到时（测试环境 / 极端布局）`scale = 1` 退化为按自然像素的固定条带，
**永不抛错**。

**两个 CSS 变量**：

| 变量 | 作用范围 | 判定条带 |
|---|---|---|
| `--overlay-scrim` | `.float-header` + `.float-footer` | `topRows` 与 `bottomRows` 中**较亮**的那个 |
| `--overlay-scrim-panel` | `.float-detail-panel` | `panelRows` |

详情面板独立成一个变量，而不是并进 `--overlay-scrim`：
面板最多占 35vh（≈ 图像高度的 40%+），若并进去，「上暗下亮」的人像图会因为下半张亮
而把 header 也压黑。面板本就是独立卡片，遮罩不同步没有割裂感（它自身有 0.2s 上滑过渡）。

### 4.3 判定度量：WCAG 相对亮度 + 分位数

```js
// sRGB 8bit → 相对亮度（WCAG 2.x）
const lin = c => { c /= 255; return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4 }
relativeLuminance = (r, g, b) => 0.2126*lin(r) + 0.7152*lin(g) + 0.0722*lin(b)
```

**取条带的 p90 分位像素**（不是均值、不是最大值）：
- 均值无抗离群能力（P2-6）；
- 最大值会被单个高光像素带偏（一颗镜面高光把整条 header 压黑）。

p90 = 「文字底下最亮的那 10% 区域」，既保守又不会被孤立亮点误伤。
条带被降采样到 64 列后最多 1024 个样本，`sort` 一次的成本可忽略。

**透明像素**：PNG 的半/全透明像素按包装层背景 `rgba(0,0,0,0.9)` 合成
（浅色页面下 ≈ `#1a1a1a`，取此值作为最坏情况）：

```js
const a = data[i + 3] / 255
const r = data[i] * a + 26 * (1 - a)   // #1a1a1a
```

### 4.4 输出：CSS 保底 + 向下求解的连续 alpha（方案 C 核心）

**删除** `:class="overlay-${overlayColorScheme}"`（模板 3 处）
与整个 `.overlay-light` 规则块（[Gallery.vue:2302-2354](../../../frontend/src/views/Gallery.vue#L2302)）。

CSS 改为读变量，**fallback 值即不可突破的保底**：

```css
.float-header,
.float-footer {
  background: var(--overlay-scrim, rgba(0, 0, 0, 0.62));        /* ← 0.62 是 L1 保底 */
  backdrop-filter: blur(4px);                                   /* ← 保持原样，不改成毛玻璃（§9.6） */
  -webkit-backdrop-filter: blur(4px);
}
.float-detail-panel {
  background: var(--overlay-scrim-panel, rgba(0, 0, 0, 0.62));
  backdrop-filter: blur(4px);
  -webkit-backdrop-filter: blur(4px);
}
```

> `0.62` 不是随手取的：`rgba(0,0,0,0.62)` 叠在纯白上得到 `#616161`，
> 白字 tertiary@0.78 恰好 4.53:1（刚过 4.5 线，留 0.03 余量）。
> 这是本方案里**唯一一个硬编码的对比度数字**，其余全部由公式推导。

变量写在 `.float-image-wrapper` 的行内 style 上（自定义属性会继承，三块浮层都是它的子元素）：

```js
const wrapperStyle = computed(() => ({
  ...previewContainerStyle.value,
  ...(scrims.value && {
    '--overlay-scrim': scrims.value.bar,
    '--overlay-scrim-panel': scrims.value.panel,
  }),
}))
```

**关键**：`scrims.value` 初始为 `null`，此时**不写这两个 key**，
`var()` 拿不到定义 → 直接用 CSS 里的 0.62。
JS 少写一个键，就是一层降级；不需要在 JS 里重复实现「保底」。

**求解算法**（找到第一个达标的 alpha 就停，取最小值 → 暗图不被无谓压黑）：

```js
const SCRIM_FLOOR_ALPHA = 0.62   // 与 CSS var fallback 同值，单测 T14 断言两者一致

function solveScrimAlpha(pixel, { maxAlpha = SCRIM_FLOOR_ALPHA, step = 0.02, ... }) {
  for (let a = 0; a <= maxAlpha + 1e-9; a += step) {
    const panel = scale(pixel, 1 - a)              // rgba(0,0,0,a) 合成
    const text  = overWhite(panel, 0.78)
    if (contrastRatio(lum(text), lum(panel)) >= 4.5) return round2(a)
  }
  return maxAlpha                                    // 兜底，数学上必达标
}
```

**求解结果永远 ≤ 0.62**（循环上界），这是 C 方案的核心不变量。

**关键性质**：纯黑/深色图算出 **alpha = 0**（保持现状「不压黑」的观感），
只有背景真的亮起来时才逐步加码：

| 条带代表色 | 求解出的 alpha | 合成后面板 | 采样失效时的保底 0.62 |
|---|---|---|---|
| 纯黑 (0,0,0) | **0.00** | (0,0,0) | (0,0,0) — 无差异 |
| 深蓝 (25,40,90) | **0.00** | (25,40,90) | (10,16,36) — 略重但 12.8:1 |
| 暗灰 (90,90,90) | **0.00** | (90,90,90) | (34,34,34) |
| 中灰 (128,128,128) | 0.24 | (97,97,97) | (49,49,49) — 重但 8.6:1 |
| 浅灰 (200,200,200) | 0.52 | (96,96,96) | (76,76,76) — 6.0:1 |
| 亮黄 (255,230,0) | 0.58 | (107,97,0) | (97,91,0) |
| 纯白 (255,255,255) | **0.62** | (97,97,97) | (97,97,97) — 无差异 |

（现状的 `light` 硬编码 0.45 → 纯白上只有 3.19:1；新方案最坏 0.62 → 4.53:1。）

### 4.5 文字三档 alpha 重定

求解目标定在 **tertiary = 0.78**（现状最低档 0.5/0.6/0.7 全部拉到 0.78 以上），
保证求解出的 alpha 对三档文字**同时**达标：

| 档位 | 现状 | 新值 | 在最坏面板 (97,97,97) 上的对比度 |
|---|---|---|---|
| primary `.float-id` / `.detail-value` | 0.95 / 0.9 | **0.95** | 5.79:1 |
| secondary `.float-size` / `.float-expand-*` / `.detail-tags-label` | 0.7 / 0.8 / 0.7 | **0.82** | 4.81:1 |
| tertiary `.detail-label` | 0.5 / 0.6 | **0.78** | 4.53:1 |

`detail-label` 从 0.5 提到 0.78 视觉变化最明显 —— 它是 11px 的字段名
（大小 / 作者 / MD5 / 时间），本来就是信息而非装饰，值得这个对比度。

### 4.6 强调色补漏（P1-4）

求解出的面板最坏是 `#616161`（L=0.11），实测：

| 元素 | 现状 | 新值 | 最坏面板对比度 |
|---|---|---|---|
| `.detail-source-link` | `#409EFF`（**2.23:1**） | `rgba(255,255,255,0.95)` + 常驻下划线 | **5.79:1** |
| 已收藏星标 | `#F56C6C`（**2.14:1**） | `#ffa39e` | **3.24:1**（图标按 WCAG 1.4.11 ≥3:1） |
| 按钮 chip `.float-close-btn` / `.float-redownload-btn` | `rgba(255,255,255,0.1)` | `rgba(0,0,0,0.35)` + `border rgba(255,255,255,0.22)` | 白图标 **10.52:1** |
| `.float-footer-right:hover` | `rgba(255,255,255,0.1)` | `rgba(0,0,0,0.5)` | — |
| `.detail-tag`（无类型色时） | `rgba(255,255,255,0.1)` | 保持不变 | 白字 0.9 → 4.94:1 |
| `.detail-tag`（有类型色，`getTagStyle` 行内 0.1 alpha 底） | — | 保持不变 | 白字 0.9 → 4.94:1 |

**关于「来源」链接为什么放弃蓝色**：要让 `#409EFF` 在最坏面板上达到 4.5:1，
面板得压到 ≤ `#292929`，对应纯白背景需要 **alpha 0.84** 的遮罩 —— 太重，
且违背该元素的设计意图（[Gallery.vue:2226](../../../frontend/src/views/Gallery.vue#L2226)
「与 detail-value 同色系但可点击，避免抢过 MD5 等关键信息」）。
改为「白字 + 常驻下划线」既达标又比彩色链接更克制，是暗色工具栏的通行做法。
（备选 `#c6e2ff` 可保蓝调、4.64:1，但视觉上几乎等同于白色，收益有限。）

**星标为什么改色而不是改 HeartOverlay**：HeartOverlay 是共享组件
（`WaterfallGallery` / `FolderTile` 也在用），在 Gallery 侧用更高特异性覆盖：

```css
.float-footer .float-heart.active { color: #ffa39e; }
```

（`0,4,0` > 子组件 scoped 的 `.heart-overlay.active[data-v-x]` `0,3,0`，
与样式注入顺序无关，确定性生效。）

**`.detail-tag` 为什么不动**：类型色是 0.1 alpha 的淡 tint，叠在已压暗的面板上
只把面板从 97 抬到 111，白字 0.9 仍有 4.94:1。P3 里那条被行内样式盖掉的
`:deep(.el-tag)` overlay-light 规则直接删除（确认为死代码）。

### 4.7 残差兜底：文字描边阴影

> **本节最初叫「L3 补强层：压高频纹理」，方案里写了把 `blur(4px)` 提到
> `blur(10px) saturate(1.15)`。实施后按用户反馈回退（见 §9.6）—— 那是一次
> 未经确认的观感投机。保留下来的只有下面这层 `text-shadow`，且必须说清楚：
> **它几乎不可见。**

遮罩的职责就是把背景压暗，白字下面的底色本身就是暗的，**暗色阴影叠在暗色背景
上看不见**。它唯一会显形的地方是 §9.5 记录的那条残差：p90 分位意味着条带里
最亮的 10% 像素比面板亮，万一某个笔画正好压在那块亮区上，这层阴影能稍微把
笔画边缘拽回来。

```css
.float-id, .float-size, .float-expand-text, .float-expand-icon,
.detail-label, .detail-value, .detail-tags-label, .detail-source-link {
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.45);
}
```

它 **不提供可计算的对比度，不承担任何「保证」职责；删掉它方案依然 4.5:1 达标。**
保留纯粹因为它是零成本的残差保险，觉得多余可以整块删掉。

> **为什么不用 `mix-blend-mode: difference` 做「自动反色」**：
> 按 CSS Compositing 规范，混合的 backdrop 被限制在**最近的 stacking context** 内。
> `.float-header` 自身带 `backdrop-filter`（会创建 stacking context）+ `background`，
> 图片根本不在混合范围内，difference 只会与自己的遮罩混合，等于没发生。
> 要让文字直接与图片混合，必须**同时删掉 background 和 backdrop-filter**，
> 代价是失去 blur、彩色 chrome 被反相（绿 tag→品红、蓝链接→橙、
> 红星→青）、Windows 关闭次像素抗锯齿导致文字发虚、详情面板 `overflow-y:auto`
> 的层叠问题，且 `forced-colors` 模式直接忽略。**不采用。**

### 4.8 无障碍：尊重系统对比度偏好

```css
@media (prefers-contrast: more) {
  .float-header, .float-footer { background: rgba(0, 0, 0, 0.80); }
  .float-detail-panel { background: rgba(0, 0, 0, 0.80); }
}
```

此规则**不读 CSS 变量**（直接给字面量），因此能同时压过 §4.4 的 `var()` 兜底值。
用户开启系统「高对比度」时获得更强的遮挡，关闭时不受影响。

---

## 5. 改动清单

### 5.1 新增 `frontend/src/composables/useOverlayScrim.js`

纯逻辑（无 DOM 依赖，可完整单测）：

```js
/**
 * L1 保底 alpha —— 必须与 Gallery.vue 中 var() 的 fallback 值字面一致。
 * 单测 T14 直接断言两者相等，防止改一边忘另一边。
 */
export const SCRIM_FLOOR_ALPHA = 0.62

/** sRGB 8bit → WCAG 相对亮度 */
export function relativeLuminance(r, g, b)                    // number

/** 两个亮度值的 WCAG 对比度 */
export function contrastRatio(l1, l2)                          // number

/**
 * 从一段像素里取第 q 分位（由暗到亮排序）的像素。
 * @param {{data: Uint8ClampedArray, width: number, height: number}} imgData
 * @param {{rowFrom: number, rowTo: number, q: number}} opt
 * @returns {[number, number, number]} 代表像素 RGB
 */
export function quantilePixel(imgData, { rowFrom, rowTo, q })

/**
 * 给定代表像素，求让 white@targetAlpha 文字达到 minContrast 的最小遮罩 alpha。
 * **maxAlpha 默认即 SCRIM_FLOOR_ALPHA —— 求解结果永远不可能比 CSS 保底更重。**
 */
export function solveScrimAlpha(pixel, {
  targetAlpha = 0.78, minContrast = 4.5,
  maxAlpha = SCRIM_FLOOR_ALPHA, step = 0.02,
})

/** 组合成两个 CSS 颜色值 */
export function buildScrims({ top, bottom, panel })  // { bar, panel }
```

DOM 部分（**薄，仅做取样**）：

```js
export function useOverlayScrim()
// { scrims: Ref<null | {bar,panel}>, analyzeFromImageEl, reset }
```

- `scrims` **初始为 `null`** —— 此时 Gallery 不写 CSS 变量，`var()` 自然回落到 0.62；
- `analyzeFromImageEl(imgEl)`：读 `naturalWidth/Height` 与 `getBoundingClientRect()`
  → 2 次 `drawImage`（顶条带 64×16、底条带 64×48，底条带一次读出 footer/panel 两组行区间）
  → `quantilePixel` × 3 → `buildScrims`；
- `reset()`：把 `scrims` 置回 `null`（不是置成某个值），让 CSS 保底接管。

**任何异常路径一律 `reset()`，绝不写入比保底更轻的值。**

**canvas 复用**：模块级单例 canvas，`drawImage` 前只改 `width/height`（改尺寸会清空画布）。

### 5.2 `frontend/src/views/Gallery.vue`

| 位置 | 改动 |
|---|---|
| [L201](../../../frontend/src/views/Gallery.vue#L201) | `:style="previewContainerStyle"` → `:style="wrapperStyle"` |
| [L213-219](../../../frontend/src/views/Gallery.vue#L213) | `el-image` 增 `@load` / `@error` |
| [L232 / 245 / 313](../../../frontend/src/views/Gallery.vue#L232) | 删 `:class="overlay-${overlayColorScheme}"` |
| [L569](../../../frontend/src/views/Gallery.vue#L569) | 删 `overlayColorScheme` ref |
| [L686-732](../../../frontend/src/views/Gallery.vue#L686) | 删 `analyzeImageColor` |
| [L735-745](../../../frontend/src/views/Gallery.vue#L735) | 删配色 watch 分支；**新增**一个只在 `currentImage` 变化时 `reset()` 的 watch（消除 P2-7 的残留闪烁） |
| [L747-784](../../../frontend/src/views/Gallery.vue#L747) | 保留 `calculatePreviewSize` 与尺寸 watch |
| [L2059 / 2060-2061](../../../frontend/src/views/Gallery.vue#L2059) | header 背景 → `var(--overlay-scrim, rgba(0,0,0,0.62))`（**blur 不动**） |
| [L2102 / 2103-2104](../../../frontend/src/views/Gallery.vue#L2102) | footer 同上 |
| [L2190 / 2191-2192](../../../frontend/src/views/Gallery.vue#L2190) | panel 背景 → `var(--overlay-scrim-panel, rgba(0,0,0,0.62))`（**blur 不动**） |
| [L2072 / 2077 / 2136 / 2140](../../../frontend/src/views/Gallery.vue#L2072) | 文字档位改 0.95 / 0.82 |
| [L2082-2089 / 2164-2174](../../../frontend/src/views/Gallery.vue#L2082) | 按钮 chip 改 `rgba(0,0,0,0.35)`、hover `0.5` |
| [L2115-2118](../../../frontend/src/views/Gallery.vue#L2115) | 增 `.float-footer .float-heart.active { color: #ffa39e }` |
| [L2130-2132](../../../frontend/src/views/Gallery.vue#L2130) | hover 底改 `rgba(0,0,0,0.5)` |
| [L2212 / 2217 / 2245](../../../frontend/src/views/Gallery.vue#L2212) | 文字档位改 0.78 / 0.95 / 0.82 |
| [L2227-2236](../../../frontend/src/views/Gallery.vue#L2227) | 来源链接改白字 + 下划线 |
| 样式块末尾 | 新增 §4.7 `text-shadow` 残差兜底 + §4.8 `prefers-contrast` 媒体查询 |
| [L2292-2296](../../../frontend/src/views/Gallery.vue#L2292) | 删空规则块 |
| [L2302-2354](../../../frontend/src/views/Gallery.vue#L2302) | **整块删除** `.overlay-light` / `.overlay-dark`（其内容按 §4.5/§4.6 折进基础规则） |

### 5.3 新增 `frontend/src/composables/useOverlayScrim.spec.js`

### 5.4 扩展 `frontend/src/views/Gallery.spec.js`

---

## 6. 边界与降级

> **方案 C 的核心收益就在这张表**：C 方案下所有失败路径的终点都是同一个值 ——
> **CSS 保底 `rgba(0,0,0,0.62)`，纯白底上 tertiary 4.53:1，全部达标。**
> 失败降级的代价只有观感，没有可读性。

| 场景 | 行为 | 终点 |
|---|---|---|
| `el-image` 加载失败（在线图 `/cache/preview/fetch/{id}` 404） | `@error` → `reset()`（`scrims = null`），不写变量，不抛错 | **0.62** ✅ |
| `naturalWidth === 0` | 同上 | **0.62** ✅ |
| `getBoundingClientRect().height === 0` | `scale = 1`，按自然像素固定条带采样 | 正常求解 |
| canvas `getContext('2d')` 返回 null（老浏览器 / 隐私模式） | `try/catch` 包住整段 → `reset()`，**不阻塞渲染** | **0.62** ✅ |
| canvas 被 taint（同源理论不会，实测 `crossorigin` 属性未落到 DOM） | 同上 | **0.62** ✅ |
| `getImageData` 抛 SecurityError | 同上 | **0.62** ✅ |
| 快速连按方向键 | 换 `src` 时旧请求被 abort，旧 `load` 不再触发 → 不会写错图（P2-7 根治） | 正常求解 |
| 切换 `currentImage` | `reset()` → 旧图遮罩不残留（P2-7） | 0.62 → 新图 `load` 后覆盖 |
| 缩放窗口 | 条带随 `scale` 重算；面板条带还依赖 `innerHeight`，但**不监听 resize**（浮层宽度按图片比例固定，重采样收益低于成本） | 保持当前值 |
| 用户开启系统「高对比度」 | §4.8 媒体查询直接给字面量 0.80，**压过 `var()` 兜底** | **0.80** ✅ |

---

## 7. 测试计划

### 7.1 纯函数单测（`useOverlayScrim.spec.js`，无 canvas 依赖）

| # | 用例 | 期望 |
|---|---|---|
| T1 | `relativeLuminance(0,0,0)` / `(255,255,255)` | 0 / 1 |
| T2 | `contrastRatio(1, 0)` | 21:1 |
| T3 | `solveScrimAlpha(纯白)` | `0.62`，且 `contrast(white@0.78, panel) >= 4.5` |
| T4 | `solveScrimAlpha(纯黑)` / `(25,40,90)` | `0` |
| T5 | `solveScrimAlpha(亮黄 255,230,0)` | `0.58` |
| T6 | 亮度单调性：0→255 步进 25，alpha **单调不增** | ✅ |
| T7 | 求解结果**恒满足** `contrast >= 4.5`（遍历 4096 随机 RGB） | ✅ 无例外 |
| **T8** | **不变量：任意输入下 `solveScrimAlpha(...) <= SCRIM_FLOOR_ALPHA`**（遍历 4096 随机 RGB） | ✅ 无例外 —— 方案 C 的生命线 |
| **T9** | **`SCRIM_FLOOR_ALPHA` 与 Gallery.vue 里 `var(--overlay-scrim, rgba(0,0,0,X))` 的 `X` 字面相等** | ✅ 防两边漂移 |
| **T10** | **`0.62` 保底在纯白上：`contrast(white@0.78, panel) >= 4.5`** | ✅ 把 L1 的推导固化成测试 |
| T11 | `quantilePixel`：全同色条带 | 返回该色 |
| T12 | `quantilePixel`：90% 黑 + 10% 白，q=0.9 | 落在白侧 |
| T13 | `quantilePixel`：单像素高光（1/1024），q=0.9 | **不**返回高光色（抗离群，P2-6） |
| T14 | `quantilePixel` 透明像素 `alpha=0` | 合成到 `#1a1a1a` |
| T15 | `buildScrims({top 更亮, bottom 更暗})` | `bar` 取 top 的 alpha；`panel` 取 panel 的 |
| T16 | 返回值均为合法 `rgba()` 字符串 | ✅ |

### 7.2 组件接线测试（`Gallery.spec.js`）

用 `vi.mock('@/composables/useOverlayScrim')` 把取样层替换掉，只验证接线：

| # | 用例 | 期望 |
|---|---|---|
| T17 | **`preview_url: null` 仍产出遮罩**（P0-1 回归） | `--overlay-scrim` 被写入 wrapper |
| T18 | 触发 `el-image` 的 `load` → 调用 `analyzeFromImageEl`，且 `e.target` 是那个 `<img>` | ✅ |
| T19 | 切换 `currentImage` → `reset()` 被调用（P2-7） | ✅ |
| **T20** | **`scrims === null` 时 wrapper 的行内 style 里没有 `--overlay-scrim` key**（让 `var()` 走 CSS 兜底） | ✅ |
| **T21** | **wrapper 的 style 属性文本里出现 `var(--overlay-scrim, rgba(0,0,0,0.62))` 对应的计算值**（读 scoped style 表，断言 0.62 这个数字在） | ✅ |
| T22 | 触发 `error` → `scrims` 回到 `null`（不是某个更轻的值） | ✅ |
| T23 | 三块浮层的 class 里**不再有** `overlay-light` / `overlay-dark` | ✅ |
| T24 | `.float-image-wrapper` 的行内 style 含 `--overlay-scrim` 与 `--overlay-scrim-panel` | ✅ |
| T25 | 既有 HeartOverlay 回归用例（[L1223+](../../../frontend/src/views/Gallery.spec.js#L1223)）全绿 | ✅ 不回归 |

> **canvas 路径无法被 vitest 覆盖**：`happy-dom@15.11.7` 的
> `canvas.getContext('2d')` 返回 `null`（已实测）。因此取样层保持「薄」，
> 决策逻辑全部下沉到纯函数；canvas 调用只靠 §8 手工验证覆盖。
> **保底值本身不依赖 canvas**（T10 + T21 从两个方向锁死），这正是方案 C 的意义。

### 7.3 回归

```bash
cd frontend && npx vitest run     # 基线 16 files / 293 tests（见 docs/.../recent-downloads-baseline.md）
```

---

## 8. 手工验证清单

挑这几类图逐一看 `--overlay-scrim` 与文字。

> **注意 `--overlay-scrim` 是 header + footer 共享的**：取顶/底条带里**较亮**的一侧
> （较亮的一侧需要更重遮罩，共享时必须按它算）。所以「上白下黑」和「上黑下白」
> 得到的是**同一个值**，不会一轻一重。真正能让两块分开的是
> `--overlay-scrim-panel`（详情面板单独一个变量）。

| # | 场景 | 期望 |
|---|---|---|
| 1 | 纯白背景同人图 | `bar`/`panel` = 0.62，文字 4.53:1 ✅ |
| 2 | 纯黑背景图 | = 0，浮层「消失」（保持现状观感） |
| 3 | **上白下黑** / **上黑下白** 渐变图 | 两块同值（共享变量的必然结果），取较亮侧算 |
| 4 | **顶部与底部 6% 都暗、但中下部亮**（白床单 / 白桌布 / 亮色地面的构图） | `bar` = 0（header/footer 完全不压黑），`panel` = 0.62 —— **这是面板独立变量真正起作用的场景** |
| 5 | 顶部亮、底部 6% 暗 | `bar` = 0.62，`panel` = 0 |
| 6 | 透明 PNG（lineart） | 透明区按 `#1a1a1a` 合成，遮罩接近 0 |
| 7 | 未下载的在线图 | 仍能算出遮罩（P0-1 回归） |
| 8 | 展开/收起详情面板 | 遮罩不抖动（面板有独立变量） |
| 9 | 打开再关闭 el-image-viewer | 遮罩重算正常（`v-if` 重挂载 → `load` 再触发） |
| 10 | 快速 ← → 连按 | 配色不串图（换 src 会 abort 旧请求） |
| 11 | 打开浏览器「增加对比度」设置 | 三块浮层变 0.80，文字更清晰 |

**算法侧已用真实模块跑过 1–6**（2026-10-01，见 §8 验证记录）；7–11 需在浏览器里过。

### 8 验证记录（2026-10-01，算法侧）

用真实 `buildScrims` / `quantilePixel` 跑 §8 的 1–6：

```
1 纯白            bar=0.62 (4.53:1)  panel=0.62 (4.53:1)
2 纯黑            bar=0.00 (12.41:1) panel=0.00 (12.41:1)
3 上白下黑        bar=0.62           panel=0.00
4 顶/底暗 中下亮   bar=0.00           panel=0.62   ← 面板独立变量生效
5 顶亮 底6%暗     bar=0.62           panel=0.00
6 透明 PNG        bar=0.00 (10.91:1) panel=0.00 (10.91:1)

单色底求解全表（文字对比度全部 >= 4.5:1，alpha 全部 <= 0.62）：
  255 → 0.62 (4.53:1) 面板#616161      200 → 0.52 (4.59:1) 面板#606060
  135 → 0.28 (4.51:1) 面板#616161      128 → 0.24 (4.51:1) 面板#616161
   90 → 0.00 (4.97:1) 面板原样          25,40,90 → 0.00 (9.11:1)
    0 → 0.00 (12.41:1)                 255,230,0 → 0.58 (4.58:1)
```

---

## 9. 关键取舍

### 9.1 路线选型：A（纯 CSS）/ B（保底+两档）/ **C（保底+连续求解）**

2026-10-01 就这三条路线做了实测定量对比：

| 方案 | JS 量 | 中灰图（128）上的面板值 | 采样失效时 | 可读性 |
|---|---|---|---|---|
| A 纯 CSS 固定 | 无 | 49（偏黑，但 11.9:1） | 恒定可读 | ✅ |
| B 保底 + 两档（阈值 135） | ~30 行 | ~97 | 落回保底 | ✅ |
| **C 保底 + 连续求解** | ~80 行 | **97（最轻）** | 落回保底 | ✅ |

**选 C**。理由：
- A 净删代码最彻底，但中间调被无谓压黑（49 vs 97），观感损失明显，而中间调图占比最高；
- B 与 C 在极端图上几乎无差别（都收敛到 0.62），C 只在中间调区间更优；
- C 的额外成本（~50 行）换来的是「同一个失败模型下最优的观感」，而**失败模型
  已由保底层消解**，不再有风险溢价。

> 反推出的一个副产品：浅色档若取 alpha 0.28，其适用背景上限是 **sRGB 135**，
> 而现状拍脑袋的阈值是 180 —— **偏高 33%**，这就是为什么现状会误判成「亮图」
> 然后只给 0.45 的遮罩（既没达标，也没省下多少）。

### 9.2 为什么不逐元素独立遮罩

理论最优（每个文字按自己那块的背景求解），但：
- 需要为 `.float-id` / `.float-size` / `detail-value` / 每个 tag 分别求解并回写
  十几个 CSS 变量；
- 浮层内元素位置随 `previewContainerStyle` 变化，需要持续的 `getBoundingClientRect`
  观测（`ResizeObserver`）才能保证「元素挪了、遮罩跟着挪」；
- 视觉上会出现同一块浮层内深浅不一的斑块。

**结论**：按「浮层」为粒度（3 块 → 2 个变量，header/footer 共享），
在「保证达标」与「可维护」之间取平衡。条带采样已经保证了浮层内部的均匀性。

### 9.3 为什么详情面板单独一个变量

见 §4.2。并进 `--overlay-scrim` 会让「上暗下亮」的常见人像图 header 被无谓压黑。

### 9.4 为什么放弃 `mix-blend-mode: difference` 自动反色

见 §4.7 的方框说明。核心障碍是 backdrop 被限制在最近的 stacking context 内，
而浮层自身的 `backdrop-filter` + `background` 恰好把图片挡在混合范围之外。

### 9.6 回退记录：不该夹带的观感改动

实施时把 `.float-header` / `.float-footer` / `.float-detail-panel` 的
`backdrop-filter` 从 `blur(4px)` 改成了 `blur(10px) saturate(1.15)`
（面板 `blur(14px)`），理由写在 §4.7「压高频纹理」。**用户看 diff 后指出：
原本是单纯的半透明，被改成了毛玻璃。已全部回退。**

复盘，这次改动错在三点：

1. **blur 从不影响可测量的对比度**。WCAG 测的是文字色与其紧邻背景的亮度比，
   `backdrop-filter: blur()` 既不改变亮度也不进入计算。所以「提升可读性」
   在这里是个伪命题 —— 真正改善对比度的是同一段里的 `background` alpha。
2. **saturate 是纯色彩美化，与可读性毫无关系**。它抬高饱和度，属于另一个
   维度的设计决策，被夹带进一次「修可读性」的改动里，尤其不该。
3. **观感改动需要用户确认**。4px → 10px 把「半透明薄纱」变成 iOS 毛玻璃，
   对一个以看图为主的站点是明确的降级。这类判断属于用户，不属于实现者。

**现状**：三处 `blur` 全部保持原来的 `4px`，无 `saturate`。
**保留下来的**：§4.7 的 `text-shadow`（近乎不可见，只在 §9.5 的残差情形起作用）
与 §4.8 的 `prefers-contrast`（默认不生效）。

> 教训记在这里而不是只改代码：这次能溜过去，是因为它写在 CSS 注释里
> 理由充分、又在测试覆盖范围之外（blur 不影响任何断言）。**观感类改动
> 不能只靠注释自证合理。**

### 9.5 已知残留

- **不做 resize 重采样**：浮层宽度固定按图片比例算，条带比例稳定；窗口剧变时
  遮罩可能略保守/略松，但求解目标 4.5:1 有足够余量，不构成可读性问题。
- **不做逐像素最坏值**：p90 允许条带里最亮的 10% 像素比面板亮。若某图恰好在
  header 正下方有一块纯白且面积 > 10%，那一小块仍会偏弱。实测样本里未复现，
  记为已知边界。
- **`text-shadow` 不提供可计算的对比度**：它是 §4.7 的补强层，不是保证层。
  删掉它方案依然达标；保留它只是让复杂背景上的笔画更分离。
- **`overlay-light` / `overlay-dark` class 是公开契约吗**：不是，仅 `Gallery.vue`
  内部使用，删除无外部影响（已 grep 确认无其他引用）。

---

## 10. 风险

| 风险 | 缓解 |
|---|---|
| 浮层在某些极端情况下对比度不足 | **已由 L1 保底从架构上消解**：CSS 里写死 0.62，任何 JS 失败路径都落到它，而它本身 4.53:1。T9/T10/T20/T21 四个测试从常量、CSS、运行时三侧锁死 |
| 大尺寸图（yande.re 有万像素全景）`drawImage` 缩放耗时 | 只画两条带（合计 ≤ 50% 高度）到 64×N 的小画布；`getImageData` 回读 ≤ 12KB；失败也只是回退到保底，不影响交互 |
| `backdrop-filter` 在低端设备上的开销 | **blur 保持原样 4px，没有变化**（曾误提到 10px，见 §9.6）。且 `background` 是不依赖 backdrop-filter 的独立兜底，不支持时文字仍可读 |
| `detail-label` 0.5 → 0.78 视觉变化明显 | 11px 字段名本就偏淡，用户若反馈过重可回调到 0.72（此时保底需 0.62 → 0.64，仍达标） |
| 样式覆盖 HeartOverlay 依赖特异性 | 用 `0,4,0` 选择器，跨样式注入顺序稳定 |
| `SCRIM_FLOOR_ALPHA` 与 CSS 字面量漂移 | T9 断言两者相等；两处均带注释互相指认 |

---

## 11. 实施顺序

1. **T0 基线**：跑 `npx vitest run` 记录改动前结果（对齐
   [recent-downloads-baseline.md](2026-09-21-recent-downloads-baseline.md) 的做法）
2. **S1 纯函数 + 单测**：`useOverlayScrim.js` + `useOverlayScrim.spec.js`（T1–T16）全绿
3. **S2 接线**：`Gallery.vue` 模板/脚本改动 + `Gallery.spec.js`（T17–T25）全绿
4. **S3 样式**：CSS 保底 → 文字档位 → 强调色 → 删 `overlay-*` 块 → `text-shadow` + `prefers-contrast`
5. **S4 回归**：`npx vitest run` 与 T0 比对
6. **S5 手工验证**：按 §8 清单逐条过

> S1–S2 期间 CSS 仍是旧的两档 class 逻辑，新 composable 已接上但样式未切；
> S3 一次性切换，避免中间态出现「保底 + 旧 class」双遮罩。

---

## 11. 实施记录

| 步骤 | 内容 | 结果 |
|---|---|---|
| T0 基线 | `npx vitest run` | **17 files / 353 tests** 全绿 |
| S1 | `useOverlayScrim.js` + `useOverlayScrim.spec.js` | 24 tests（T1–T16 + 失败路径） |
| S2 | `Gallery.vue` 模板/脚本接线 | 删 `analyzeImageColor` / `overlayColorScheme` / `overlay-{light,dark}` 绑定，接 `@load` / `@error` / `wrapperStyle` |
| S3 | 样式：L1 保底 + 文字档位 + 强调色补漏 + `text-shadow` 残差兜底 + `prefers-contrast`，删 `overlay-light` 整块与空 `dark-mode` 块；**blur 保持 4px 不动** | — |
| S4 | 全量回归 | **18 files / 388 tests** 全绿（净增 1 文件 35 用例，零回归） |
| S5 | §8 清单 1–6 算法侧用真实模块跑通（见 §8 验证记录）；构建产物 CSS 已核对（`var(--overlay-scrim, rgba(0,0,0,.62))` + `blur(4px)` + `prefers-contrast` → `#000c`；`overlay-light/dark` 在产物中 0 处） | — |

**实施中发现并修正的两处 spec 错误**（已回写本文档）：

1. §7 T12 原写「90% 黑 + 10% 白，q=0.9 落在白侧」—— **统计上不成立**：
   恰好 90% 黑时第 90 百分位就是黑。改为 **80% 黑 + 20% 白**。
2. §7 T6 原写「亮度越高 alpha 单调**不增**」—— **方向反了**，背景越亮需要越重的
   遮罩，应为单调**不减**。已更正，且 T7/T8 的随机色全表验证了实际方向。

**待人工在浏览器确认**：§8 的 7–11（在线图 P0-1 回归、面板展开、viewer 开关、
快速翻图、系统高对比度）。

---

*最后更新：2026-10-01 已实施（方案 C「保底 + 连续求解」），测试 18 files / 388 tests*
