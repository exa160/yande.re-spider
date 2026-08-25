# 收藏夹模式优化 — 设计文档

**状态**：Draft
**日期**：2026-08-21
**分支**：`feature-favorites-mode`（基于现有 v1 计划 commit `844b8a4`）
**类型**：优化 + Bug 修复 + 数据契约扩展

---

## 1. 目标

针对 PR #36 review 反馈与实测中的 5 类问题，进行第二轮优化：

1. **上下文面板自适应**：AdvancedQuery 根据收藏夹 tab 的子视图（一级/二级）切换面板布局与可用配置
2. **路由持久化**：浏览器刷新后保留 `querySource='favorites'` 状态
3. **缩略图安全模式**：一级页面文件夹缩略图受 safeMode 影响（rating 非 Safe 则高斯模糊）
4. **状态隔离 bug**：从其他 tab 切到收藏夹时清空遗留 tag/搜索
5. **Folder chip 锁定**：二级页面进入时 folder chip 不可被用户删除

明确**不在范围内**：

- 收藏夹名称/标签编辑、文件夹拖拽（已有但未在瀑布流内）
- 一级页面"按名称+标签过滤"的实时客户端过滤（保留当前 `folderSearchKeyword` 行为，本次仅整合进 AdvancedQuery）
- "我的最爱"功能
- 服务端限流（继续依赖浏览器 6 并发连接）

---

## 2. 背景与现状

### 2.1 当前 querySource 三态

`Gallery.vue` 当前仅支持：
- `'yande'` → 在线 2 联按钮
- `'local'` → 本地 2 联按钮
- `'favorites'` → 本地模式扩展的 3 联按钮（folder-list / folder-detail）

`querySource` 状态仅存于内存，刷新即丢。

### 2.2 AdvancedQuery 当前 sourceMode prop

仅支持 `'local' | 'yande'` 二元，通过 prop 下传。`advanced-panel` 内大量 `v-if="sourceMode === 'yande'"` 字段专属控制。

### 2.3 当前 /favorites/with-preview 响应

```json
{
  "items": [{
    "id": 1, "name": "...", "tags": "...", "color": "...",
    "local_count": 42, "online_count": 120,
    "preview_images": [
      {"id": 1001, "width": 1920, "height": 1080}
    ]
  }],
  "total": 5,
  "has_more": false
}
```

`preview_images` 缺 `rating`，FolderTile 无法判断安全模式是否模糊。

### 2.4 /api/v1/gallery/load 当前 source 字段

`GalleryLoadRequest.source: Optional[str] = "local"`，路由根据 source 路由 `query_local_database` 或 `query_yande_api`。没有 `'favorites'` 分支。

---

## 3. 架构与数据流

### 3.1 模式分层

```
Gallery.vue (root)
├─ querySource: 'yande' | 'local' | 'favorites' (localStorage 持久化)
├─ favoritesView: null | 'folders' | 'folder-detail'
└─ favoritesMode (新): null | 'folders' | 'folder-detail'

AdvancedQuery.vue (props 新增)
└─ mode: 'gallery' | 'favorites-folders' | 'favorites-folder-detail'
   ├─ 'gallery'：原行为（advanced-panel + 一级标签）
   ├─ 'favorites-folders'：隐藏 advanced-panel；一级搜索 = 收藏夹 name+tags 过滤
   └─ 'favorites-folder-detail'：保留 advanced-panel；显示"在线内容"开关；folder chip 锁
```

### 3.2 后端契约扩展

#### `/favorites/with-preview?page=N&page_size=M&tile_size=adaptive|small|medium|large`

新增 `tile_size` 参数：
- `adaptive`（默认）：按屏幕宽度由前端决定 tile 内预览图数（沿用当前 4/6/8 规则）
- `small`：固定 4 张
- `medium`：固定 6 张
- `large`：固定 8 张

后端按 `tile_size` 决定返回 `preview_images` 的数量。

#### `/favorites/with-preview` 响应 `preview_images` 增加 `rating`

```json
{
  "id": 1001, "width": 1920, "height": 1080,
  "rating": "Safe"   // 新增
}
```

#### `/api/v1/gallery/load` 增加 favorites 专属分支

新增 `GalleryLoadRequest` 字段：
- `include_online: bool = False`：仅在 source='favorites' 时生效

路由逻辑：
```python
if request.source == "favorites":
    # 第一步：用 folder_id 获取 folder.tags
    # 第二步：调用 query_local_database（folder.tags + downloaded_only=True）
    images, total = await asyncio.to_thread(GalleryService.query_local_database, request)
    # 第三步：若 include_online=True，再调 query_yande_api 合并
    if request.include_online:
        yande_images, _ = await asyncio.to_thread(GalleryService.query_yande_api, request)
        # 去重合并（按 id，local 优先）
        images = dedup_by_id(images + yande_images)
elif request.source == "local":
    images, total = await asyncio.to_thread(GalleryService.query_local_database, request)
else:
    images, total = await asyncio.to_thread(GalleryService.query_yande_api, request)
```

### 3.3 前端 UI 变化

#### Gallery.vue — mode 下传 + 持久化

```vue
<AdvancedQuery
  :source-mode="querySource"
  :mode="querySource === 'favorites' ? favoritesView : 'gallery'"
  ref="queryRef"
/>
```

#### AdvancedQuery.vue — mode prop + 面板条件渲染

`mode === 'favorites-folders'`：
- 隐藏 `.advanced-panel` 区块
- 一级搜索 placeholder 改为 "搜索收藏夹名称或标签"
- 搜索 onChange 调用 `filterFavorites(keyword)`（通过 emit 'favorites-filter' 给父组件）

`mode === 'favorites-folder-detail'`：
- 显示 `.advanced-panel` 但增加新字段：`是否展示在线内容` 开关（`include_online` ref）
- folder chip 上的 X 按钮隐藏（`hide-favorite-close` prop）
- search onChange 调用 `handleSearch` 走 `/api/v1/gallery/load` 带 `include_online`

`mode === 'gallery'`：现有行为不变。

#### FolderTile.vue — safeMode 高斯模糊

新增 prop `safeMode: Boolean`。模板内 `<img>` 加 `class="safe-blur"` 当 `safeMode && previewImage.rating !== 'Safe'`。

#### Gallery.vue — localStorage 持久化

```javascript
// onMounted
const saved = localStorage.getItem('gallery_source')
if (saved && ['yande', 'local', 'favorites'].includes(saved)) {
  querySource.value = saved
  if (saved === 'favorites') {
    favoritesView.value = 'folders'
    loadFolders(1)
  } else {
    handleSearch({})
  }
}

// watch querySource → localStorage
watch(querySource, (val) => localStorage.setItem('gallery_source', val))
```

---

## 4. 状态/生命周期边界

### 4.1 状态转移（与原计划保持一致，补充 mode）

| 用户动作 | querySource | favoritesView | AdvancedQuery.mode |
|---------|-------------|---------------|--------------------|
| 首次加载（localStorage 有 favorites） | 'favorites' | 'folders' | 'favorites-folders' |
| 首次加载（无/默认值 local） | 'local' | null | 'gallery' |
| 点「收藏夹」按钮 | 'favorites' | 'folders' | 'favorites-folders' |
| 点文件夹 tile | 'favorites' | 'folder-detail' | 'favorites-folder-detail' |
| 点返回 | 'favorites' | 'folders' | 'favorites-folders' |
| 点「在线」/「本地」 | 'yande'/'local' | null | 'gallery' |
| 浏览器刷新（localStorage=favorites） | 'favorites' | 'folders'（自动恢复） | 'favorites-folders' |
| 浏览器刷新（localStorage=local） | 'local' | null | 'gallery' |

### 4.2 切 tab 清空

`handleSourceChange('favorites')` 时调用 `queryRef.value?.reset()`（已存在）。但当前 reset 只清空 tags + searchText + selectedFavorite，本次需在调用 reset 后**额外清空**遗留的 advanced-panel state（通过新增 `resetAdvancedPanel()` 方法暴露）。

`handleSourceChange('yande' | 'local')` 同上。

### 4.3 Folder chip 锁定

新增 prop `lockFavoriteChip: Boolean`（默认 false）。Level 2 进入时为 true：

```vue
<AdvancedQuery :lock-favorite-chip="favoritesView === 'folder-detail'" />
```

AdvancedQuery 模板：
```vue
<el-icon v-if="!lockFavoriteChip" @click.stop="clearSelectedFavorite"><Close /></el-icon>
<span v-else class="lock-icon">🔒</span>
```

---

## 5. 文件清单

### 5.1 后端

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `backend/src/models/response/favorites.py` | 修改 | `FolderPreviewImageMinimal` 加 `rating` 字段 |
| `backend/src/services/favorites.py` | 修改 | `_preview_count_for_local_count` 按 `tile_size` 决定返回数量；DAO `query_random_for_tags` 抽样时包含 rating |
| `backend/src/dao/yande_data_dao.py` | 修改 | `query_random_for_tags` 选择列表加 `rating` |
| `backend/src/api/v1/favorites.py` | 修改 | `/with-preview` 接受 `tile_size` Query 参数 |
| `backend/src/models/request/gallery.py` | 修改 | `GalleryLoadRequest` 加 `include_online` 字段；source 增加 'favorites' 选项 |
| `backend/src/api/v1/gallery.py` | 修改 | `/load` 路由分发 source='favorites' 逻辑（含 include_online 合并） |
| `backend/src/services/gallery.py` | 修改 | 可能需要新增 `query_favorites(favorite_id, include_online)` 或在路由层组合 |

### 5.2 前端

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `frontend/src/api/favorites.js` | 修改 | `getFoldersWithPreview(page, pageSize, tileSize)` 加 tile_size 参数 |
| `frontend/src/api/gallery.js` | 修改 | `loadGallery` 函数支持 `source: 'favorites'` + `include_online` |
| `frontend/src/components/AdvancedQuery.vue` | 修改 | 新增 `mode` + `lockFavoriteChip` props；面板条件渲染；folder chip close 隐藏；新增 `favorites-filter` emit |
| `frontend/src/components/FolderTile.vue` | 修改 | 新增 `safeMode` prop；`safe-blur` class |
| `frontend/src/views/Gallery.vue` | 修改 | `mode` prop 下传；localStorage 持久化；切 tab 时 `queryRef.value?.reset()` 已清空 + 额外 `resetAdvancedPanel()`；`loadFolders` 传 `tileSize` |

---

## 6. 测试

### 6.1 后端

新增测试：
- `test_with_preview_tile_size`：`tile_size=small` 返回 4 张；`medium` 6 张；`large` 8 张；`adaptive` 走 local_count 分档
- `test_preview_images_include_rating`:验证 `preview_images[i].rating` 字段存在
- `test_gallery_load_source_favorites`：source='favorites' + folder_id=X 返回 local 匹配
- `test_gallery_load_include_online`：source='favorites' + include_online=true 同时返回 local + yande 去重

### 6.2 前端

新增/修改测试：
- `FolderTile.spec.js`：新增 `safeMode=true + rating=Explicit` 时 img 有 safe-blur class
- `AdvancedQuery.spec.js`（新）：mode='favorites-folders' 隐藏 advanced-panel；mode='favorites-folder-detail' 显示包含在线内容开关；lockFavoriteChip=true 隐藏 X 按钮
- `Gallery.spec.js`：补充 localStorage 持久化测试 + 切 tab 清空测试

---

## 7. 风险与权衡

| 风险 | 缓解 |
|------|------|
| `/api/v1/gallery/load` 增加 favorites 分支影响老调用 | source 默认值是 'local'；新字段 `include_online` 默认 False，向后兼容 |
| localStorage 持久化 querySource 可能误导用户 | 跨 session 状态合理（vs 浏览器私有 session）；明确注释意图 |
| include_online=true 时合并去重需新逻辑 | 按 id 优先取 local；测试覆盖；不影响 single-source 调用 |
| AdvancedQuery.mode 三态增加复杂度 | 清晰枚举值；旧 prop sourceMode 保留（向后兼容）；mode 优先 |

### 7.1 YAGNI 决策

- ❌ 不做收藏夹跨 session 同步（localStorage 足够）
- ❌ 不做"在线内容"开关的服务端缓存
- ❌ 不做 user tag 锁定（用户明确说"只锁 folder chip"）
- ❌ 不做 tile 尺寸拖拽调整（4 档开关够用）

---

## 8. 实施步骤（高层）

1. 后端：`preview_images` 加 `rating` 字段（model + DAO）
2. 后端：`/favorites/with-preview` 加 `tile_size` 参数
3. 后端：`/api/v1/gallery/load` 加 source='favorites' + `include_online`
4. 前端：`FolderTile` 加 `safeMode` 高斯模糊
5. 前端：`AdvancedQuery` mode 三态 + lockFavoriteChip
6. 前端：API client 更新（favorites.js tile_size, gallery.js include_online）
7. 前端：`Gallery.vue` mode prop + localStorage 持久化 + 切 tab 清空
8. 前端 + 后端：单元测试 + 集成测试
9. 全套测试 + LSP 检查

---

*最后更新：2026-08-21*