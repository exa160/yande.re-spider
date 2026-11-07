# 滚动位置策略修复计划（收藏夹返回 / 切换页面不回顶）

日期：2026-11-06
范围：`frontend/src/views/Gallery.vue`、`frontend/src/router/index.js`、`frontend/src/main.js`

## 一、问题定位结论

滚动容器是 `window`（收藏夹一级列表、收藏夹二级瀑布流、普通瀑布流三块内容共用同一个滚动条，
在 `Gallery.vue` 模板中以 `v-if / v-else` 互斥渲染于同一位置）。

现有"位置记忆"只实现了 **一条** 路径，其余全部缺失，导致用户反馈的"点开不在顶端 /
切页面不在顶端 / 位置记忆失控"：

| 路径 | 现状 | 代码位置 |
|------|------|----------|
| 收藏夹二级页 → 一级页（返回） | 有快照 + 恢复，但只写一次 `scrollTop` | `Gallery.vue:1349-1361` / `1426-1476` |
| 一级页 → 二级页（点开） | **无任何复位**，沿用旧 `scrollY` | `Gallery.vue:1349-1361` |
| 切换 source（在线/本地/收藏夹/我的最爱/随机/最近下载） | **无任何复位** | `Gallery.vue:1483-1553` |
| 新搜索结果 | **无任何复位** | `Gallery.vue:1140-1193` |
| 路由切换（Gallery → Download/Config） | **router 无 `scrollBehavior`**，沿用旧 `scrollY` | `router/index.js:24-32` |

叠加"记忆"本身的竞态：

1. 恢复时只 `setPageScrollTop` 一次 → 预览图懒加载、瀑布流追加导致文档高度未定，
   浏览器把 `scrollTop` **钳制**到当时的最大可滚动高度 → 落点随机。
2. `scrollIntoView({ block: 'center' })`（`Gallery.vue:1405-1417`）与像素恢复是两套不同语义，
   同一功能出现两种落点 → "失控"。
3. `WaterfallGallery` 的 `IntersectionObserver`（`rootMargin: 200px`，
   `WaterfallGallery.vue:855-874`）会在恢复滚动时触发 `loadMore` → 追加内容 → 位置再漂。

## 二、统一策略（修复目标）

| 场景 | 行为 |
|------|------|
| 进入新视图（二级页 / 切 source / 切路由 / 新搜索） | **回到顶部** |
| 从二级页返回收藏夹一级页 | **恢复进入前的位置**（唯一的"位置记忆"） |
| 用户在自动定位过程中主动滚动 | 立即停止干预，把控制权交还用户 |

## 三、实施步骤

1. **滚动工具函数集中化**（`Gallery.vue`）
   - `getPageScrollTop` / `setPageScrollTop`（已有）保留。
   - 新增 `applyScrollTopStable(top)`：在时间窗口内持续重写目标 `scrollTop`，
     直到用户主动滚动（`scroll` 事件 `isTrusted === true`）或超时 → 消除高度未定导致的钳制。
   - 新增 `resetPageScrollToTop()`：进入新视图统一入口。
   - 新增 `scrollIntentId` 意图令牌：新的一次定位自动作废上一次，避免"回顶"与"定位"互相打架。
   - 新增锚点记忆 `captureScrollAnchor(folder)` / `restoreScrollAnchor(anchor)`：
     记录磁贴在视口中的偏移，返回时把同一磁贴恢复到同一偏移，
     免疫预览图懒加载引起的整体高度漂移；失败时回退像素恢复。

2. **接入点**（全部新增复位/稳定化，无一遗漏）
   - `enterFavoriteFolderDetail`：进入二级页前记录锚点快照，进入后 `resetPageScrollToTop()`。
   - `handleSourceChange`：切换视图 `resetPageScrollToTop()`。
   - `handleSearch`：`loadImages()` 完成后 `resetPageScrollToTop()`（新结果集回到顶部）。
   - 路由 `query.querySource` watch：`loadImages()` 后 `resetPageScrollToTop()`。
   - `handleFavoritesFilter`（一级页关键字过滤）：列表整体换内容 → `resetPageScrollToTop()`。
   - `reloadFolderList`（磁贴尺寸/预览配置变化导致列表重排）：`resetPageScrollToTop()`。
   - `handleBackToFolders`：优先锚点恢复 → 回退像素恢复（均走 `applyScrollTopStable`）。
   - `scrollToFolderTile`：定位前作废进行中的"回顶"意图。

3. **路由层**
   - `router/index.js` 增加 `scrollBehavior`：`savedPosition || { top: 0 }`。
   - `main.js` 设置 `history.scrollRestoration = 'manual'`，刷新页面行为确定（不从中间开始）。

4. **测试**
   - 现有 `Gallery.spec.js:3110-3154`（返回恢复 scrollTop）必须保持通过。
   - 新增用例：点开二级页回到顶部、切 source 回到顶部、路由切换回到顶部、
     用户主动滚动时停止自动定位。

## 四、第二轮修复：「反复进出收藏夹时，向下滚动一点会突然回顶」

用户反馈：**反复进出不同收藏夹，第二次进入某个收藏夹时，向下滚动一点会突然触发回顶**。

三个叠加成因：

| # | 成因 | 原实现 | 修复 |
|---|------|--------|------|
| A | **迟到的回顶** | `handleSearch` 的 `resetPageScrollTop()` 写在 `await loadImages()` **之后**。进入收藏夹的搜索有网络延迟；期间用户可能已滚动、甚至已退出并进入另一个收藏夹 → 上一次搜索的 await 迟到 resolve → 执行回顶 → 把当前视图从用户当前位置拽回顶部 | 复位移到 `await loadImages()` **之前**（与触发点同步），彻底消除"迟到写回" |
| B | **循环中止判据太弱** | `Date.now() - lastUserScrollAt < 300` 只在"用户刚滚过 300ms 内"才中止；用户滚完停下超过 300ms 后，循环继续写 0 → 拽回顶部 | 引入 `userScrollSeq`（用户每滚动一次 +1），循环里 `userScrollSeq !== seqAtStart` → **立即**中止 |
| C | **只认 `isTrusted`** | WebView / 内嵌浏览器合成的事件可能不带 `isTrusted` → 用户滚动完全不被识别 | 双保险兜底：目标位置可达（`scrollHeight - innerHeight`）而当前滚动位置已偏离目标 → 立即中止 |

新增「定位保护标记」`guard`（= 触发那一刻的 `userScrollSeq`）：

- 任何**异步**定位（补页后定位磁贴、恢复位置）在执行前检查 `isScrollGuardValid(guard)`；
  用户在此期间自己滚动过 → 放弃自动定位，不跟用户抢滚动条。
- 所有复位点都在触发那一刻 `captureScrollGuard()`，并把 guard 传给稳定写入循环。

## 五、第三轮修复（A + B）：返回一级页「闪一下」+「文件夹有上下位移」

### 5.1 症状与根因

| 症状 | 根因 | 证据 |
|------|------|------|
| **闪一下** | 收藏夹一级列表与二级瀑布流是 `v-if / v-else` **互斥渲染** → 进入二级页时一级页整棵 DOM 被卸载，返回时整棵重建。每个 `FolderTile` 都是新实例 → 组件内 `srcEnabled` 清空 → 预览图 `<img>` 的 src 全部失效 → 磁贴先空白、再按 10 并发队列逐批重新出现 | `Gallery.vue:115-143`、`FolderTile.vue:30/160/219-225/252-255` |
| **文件夹有上下位移** | ① 重建发生在旧滚动位置 → 先错位；② `resetAdvancedPanel()` 关闭高级面板触发 `<el-collapse-transition>` 约 300ms 高度动画 → 面板下方整个列表持续上移；③ 旧的 800ms 循环写回与该动画互相拉扯 | `AdvancedQuery.vue:187/1371-1374`、`Gallery.vue` 的 `applyScrollTopStable` |

### 5.2 A 方案：列表保持挂载（治本）

- `Gallery.vue` 模板：`v-if / v-else` → 两个 `WaterfallGallery` 并列 + `v-show` 切换可见性。
  一级列表在二级页期间只是隐藏，**DOM / 图片 src / 列分布 / 高度全部原样保留**
  → 既不闪，也不位移，返回时位置天然正确。
- `WaterfallGallery.vue`：
  - `updateColumnCount()` 宽度为 0（隐藏态）时保留上一次测量值 → 不会被误判成 1 列；
  - 新增 `ResizeObserver` 监听容器尺寸 → 组件在隐藏状态下挂载时，
    从隐藏变可见后补测一次列数（ResizeObserver 在绘制前触发 → 用户看不到列数跳变）。
- `AdvancedQuery.vue`：新增 `_resetAdvancedParamsNoClose()` —— 只重置参数、**不关闭**面板。
  返回一级页时改用它，避免 collapse 高度动画把列表顶来顶去（也保持用户自己的面板开合状态）。

### 5.3 B 方案：定位改为「一次性写入 + 偏差补写」

`applyScrollPosition({ anchor, pixelTarget, guard, duration, interval, threshold })`：

1. **一次性写入**：定位在 `nextTick` 里同步完成 → 浏览器首帧就是目标位置，
   不会出现"先错位再纠正"的可见跳动（旧实现是每 100ms 无条件重写）。
2. **锚点优先**：目标位置由锚点磁贴的视口偏移实时反算 → 布局变化时同一批磁贴仍停在视口同一位置；
   锚点不可用（无布局信息）时回退像素位置。
3. **偏差补写**：只有"实际位置偏离目标"且"目标可达"时才补写；
   目标可达却偏离 → 判定为用户接管（WebView 里 `isTrusted` 不可靠时的兜底）→ 立即停止干预。

### 5.4 契约变更（已同步更新测试）

| 变更 | 说明 |
|------|------|
| 返回一级页不再调用 `resetAdvancedPanel()` | 改为 `_resetAdvancedParamsNoClose()`（不关面板 → 无高度动画） |
| 页面上同时存在两个 `WaterfallGallery` 实例 | 需要断言"图片瀑布流"的测试改用 `findImageGallery(wrapper)`（按 `itemType` 区分） |

## 六、风险与边界
- 锚点恢复需要磁贴已渲染；未渲染时走 `ensureFolderPageLoaded` 补页后 `scrollIntoView` 定位。
- 锚点恢复依赖布局信息：`getBoundingClientRect().height === 0`（无布局环境，如测试用的
  happy-dom）时判定锚点不可用，自动回退像素恢复。
- `applyScrollTopStable` 依赖 `requestAnimationFrame`；定位循环最多持续 800ms、每 100ms
  写一次（避免每帧刷屏）；用户主动滚动（`scroll` 事件 `isTrusted === true`）或新的定位意图
  会立即终止循环；组件卸载时 `cancelScrollIntent()` 兜底。
- 收藏夹配置变化（`previewOrder` / `tileSize` 等）触发 `reloadFolderList` 时列表整体重排，
  位置记忆不适用 → 回到顶部。
- 锚点公式：`目标 scrollTop = 当前 scrollTop + (磁贴当前视口 top − 进入时的视口 top)`，
  两者必须在同一帧读取（DOM 已换、scroll 未变），否则会算错。
