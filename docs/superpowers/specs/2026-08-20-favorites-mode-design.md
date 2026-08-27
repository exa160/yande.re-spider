# 收藏夹模式 + 瀑布流文件夹视图 — 设计文档

**状态**：Draft
**日期**：2026-08-20
**分支**：`feature/favorites-mode`
**类型**：新功能 + 行为变更（前端模式扩展 + 后端接口增强）

---

## 1. 目标

在 Gallery 视图增加「收藏夹」作为第三种显示模式，收藏夹以「大文件夹」形式呈现，文件夹占位展示该收藏夹的随机图片（已下载）。点击文件夹进入普通瀑布流查看模式（与现有「在线/本地」一致），搜索栏复用现有 AdvancedQuery。

### 1.1 范围内

1. 新增 `querySource === 'favorites'` 第三模式
2. 3 联按钮组 [在线, 本地, 收藏夹]（仅在本地模式可见收藏夹按钮）
3. 收藏夹模式下文件夹以瀑布流 tile 渲染，内嵌随机预览图
4. `/favorites/with-preview` 接口补完（分页 + 内嵌精简预览元数据）
5. `/favorites/{folder_id}/preview` 接口增强（新增 `random` 参数）
6. 点击文件夹进入「文件夹图片视图」，搜索栏继承 folder.tags 筛选
7. 浮动返回按钮（仅文件夹图片视图出现，位于搜索栏左侧同高度）

### 1.2 不在范围内

- 「我的最爱」功能（`/preview` 接口加 TODO 注释占位）
- 文件夹图标重设计、文件夹颜色主题
- 文件夹拖拽排序（已在收藏夹面板支持；本设计不引入瀑布流视图内的排序）
- 收藏夹数量大屏展示优化（仍由 `local_count` / `online_count` 字段提供）
- 服务端限流（依赖浏览器原生 6 并发连接限制即可）

---

## 2. 背景与根因

### 2.1 现有模式状态

`Gallery.vue:325` 定义 `querySource = 'yande' | 'local'`，由 `<el-button-group>` 渲染 2 联按钮（`Gallery.vue:7-20`）。用户已在多个 PR（如 #28 代理模式）多次触及该按钮组，本次扩展为 3 联。

### 2.2 后端接口现状

| 接口 | 状态 | 用途 |
|------|------|------|
| `GET /favorites` | ✅ 正常 | 列表，不带预览 |
| `GET /favorites/with-preview` | ⚠️ **TODO 占位** | `preview_images=[]` 写死（`favorites.py:74`），需补完 |
| `GET /favorites/{id}/preview` | ⚠️ **孤儿接口** | 后端实现有但前端 0 处调用；返回排序前 N 张（非随机） |

### 2.3 现有瀑布流预览并发模式

`WaterfallGallery.vue:188` 定义 `MAX_PREVIEW_CONCURRENT = 10`，配合 `IntersectionObserver` 懒加载 + `srcEnabled` 门控实现并发控制。新增 FolderTile 完全复用该模式，**不引入新的并发控制库**。

---

## 3. 架构与状态机

### 3.1 顶层状态机

```
querySource: 'yande' | 'local' | 'favorites'
favoritesView: null | 'folders' | 'folder-detail'
selectedFavoriteFolder: FavoriteFolder | null
currentFolders: FavoriteFolderWithPreview[]   // 文件夹视图下的瀑布流数据
```

### 3.2 状态转移表

| 用户动作 | querySource | favoritesView | selectedFavoriteFolder |
|---------|-------------|---------------|------------------------|
| 首次加载 | 'local' | null | null |
| 点「收藏夹」按钮 | 'favorites' | 'folders' | null |
| 点文件夹 tile | 'favorites' | 'folder-detail' | folder |
| 点返回按钮 | 'favorites' | 'folders' | null |
| 点「在线」按钮 | 'yande' | null | null |
| 点「本地」按钮 | 'local' | null | null |

**关键不变量**：

- `querySource === 'yande'` 时按钮组只显示 [在线, 本地] 2 联
- `querySource === 'local'` 时按钮组显示 [在线, 本地, 收藏夹] 3 联
- `querySource === 'favorites'` 时按钮组保持 3 联（保证用户可点回本地）
- `favoritesView` 仅在 `querySource === 'favorites'` 时有意义
- 切换 `querySource` 自动重置 `favoritesView = null` 和 `selectedFavoriteFolder = null`

### 3.3 数据流

#### 文件夹列表视图（`favoritesView === 'folders'`）

```
Gallery.loadFolderList()
  → GET /favorites/with-preview?page=N&page_size=M
  → 响应：[{folder, preview_images: [{id, width, height}]}]
  → WaterfallGallery (itemType='folder')
    → FolderTile
      → 内部 srcEnabled 门控 + IntersectionObserver
      → 真实 URL: /api/v1/gallery/cache/preview/{id}
```

#### 文件夹图片视图（`favoritesView === 'folder-detail'`）

```
Gallery.handleSearch()  // 由 AdvancedQuery 触发
  → queryParams = { ...selectedFavoriteFolder.tags parsed, source: 'favorites' }
  → GET /gallery/load  // 复用现有接口
  → WaterfallGallery (itemType='image')  // 现有瀑布流逻辑
```

---

## 4. 后端变更

### 4.1 `GET /favorites/with-preview`

**位置**：`backend/src/api/v1/favorites.py:49-66` + `backend/src/services/favorites.py:50-77`

**变更**：

- 新增 query 参数 `page: int = 1`, `page_size: int = 20`（与 `/gallery/load` 一致）
- 响应 `FavoriteFoldersWithPreviewResponse` 改用 `BaseResponse` 包装 `total` / `has_more`
- 每条 folder 的 `preview_images` 改为精简模型：**仅含 `id, width, height`**
- 后端按 `local_count` 分档决定每文件夹返回图片数：
  - `local_count < 50` → 4 张
  - `50 ≤ local_count < 200` → 6 张
  - `local_count ≥ 200` → 8 张
- 分档常量集中在 `services/favorites.py` 模块顶部，便于调整

**新增响应模型**（`backend/src/models/response/favorites.py`）：

```python
class FolderPreviewImageMinimal(BaseModel):
    """收藏夹瀑布流用的精简预览元数据（不含 URL，前端自行拼）"""
    id: int
    width: Optional[int] = None
    height: Optional[int] = None
    model_config = ConfigDict(from_attributes=True)


class FavoriteFolderWithMinimalPreview(FavoriteFolder):
    preview_images: list[FolderPreviewImageMinimal] = Field(default_factory=list)


class FavoriteFoldersWithPreviewListData(BaseModel):
    items: list[FavoriteFolderWithMinimalPreview]
    total: int
    has_more: bool


class FavoriteFoldersWithPreviewResponse(BaseResponse[FavoriteFoldersWithPreviewListData]):
    ...
```

**DAO 新增方法**（`backend/src/dao/yande_data_dao.py`）：

```python
def query_random_for_tags(
    self,
    tags: str,
    limit: int,
    downloaded_only: bool = True,
) -> list[YandeData]:
    """按 tags 过滤，随机抽取 limit 条已下载图片"""
    # SQLAlchemy + func.random()（MariaDB/SQLite 兼容）
    ...
```

**Service 改造**（`backend/src/services/favorites.py:50-77`）：

```python
PREVIEW_COUNTS_BY_LOCAL_COUNT = [
    (50, 4),
    (200, 6),
    (float('inf'), 8),
]

def _preview_count_for_folder(local_count: int) -> int:
    for threshold, count in PREVIEW_COUNTS_BY_LOCAL_COUNT:
        if local_count < threshold:
            return count
    return 8


@staticmethod
def get_folders_with_preview(
    page: int = 1, page_size: int = 20
) -> tuple[list[FavoriteFolderWithMinimalPreview], int]:
    folders, total = favorite_dao.list_paginated(page=page, page_size=page_size)
    result = []
    for f in folders:
        limit = _preview_count_for_folder(f.local_count or 0)
        with YandeDataRepository() as repo:
            images = repo.query_random_for_tags(f.tags or "", limit=limit)
        result.append(
            FavoriteFolderWithMinimalPreview(
                **FavoriteFolder.model_validate(f).model_dump(),
                preview_images=[
                    FolderPreviewImageMinimal.model_validate(img)
                    for img in images
                ],
            )
        )
    has_more = page * page_size < total
    return result, total, has_more
```

**DAO 新增分页**（`backend/src/dao/favorite_dao.py`）：

```python
def list_paginated(self, page: int, page_size: int) -> tuple[list[FavoriteFolderModel], int]:
    """分页获取收藏夹，按 sort_order 升序，附带 total"""
    ...
```

### 4.2 `GET /favorites/{folder_id}/preview`

**位置**：`backend/src/api/v1/favorites.py:124-132`

**变更**：

- 新增 query 参数 `random: bool = False`（默认 false 保持向后兼容）
- `limit` 默认 6，最大 50
- `random=true` 时调用 `repo.query_random_for_tags()`，否则维持现有排序前 N 逻辑
- 添加注释：
  ```python
  # TODO: 后续「我的最爱」功能会用到此接口（单 folder 全量预览）
  ```

**API 端点改动**：

```python
@router.get(
    "/{folder_id}/preview",
    response_model=FavoriteFolderPreviewResponse,
    summary="预览收藏夹查询结果",
)
async def preview_folder(
    folder_id: int,
    limit: int = Query(6, ge=1, le=50),
    random: bool = Query(False, description="随机抽样"),
) -> FavoriteFolderPreviewResponse:
    """单收藏夹预览。random=true 时随机抽样，否则按当前排序取前 N 张。"""
    result = FavoritesService.preview_folder(folder_id, limit=limit, random=random)
    if not result:
        raise APIException(ErrMsg.FAVORITE_FOLDER_NOT_FOUND)
    return FavoriteFolderPreviewResponse(message=ErrMsg.OK.msg, data=result)
```

**Service 改动**：

```python
@staticmethod
def preview_folder(
    folder_id: int, limit: int = 6, random: bool = False
) -> Optional[dict]:
    folder = favorite_dao.get_by_id(folder_id)
    if not folder:
        return None
    try:
        search_params = FavoritesService._parse_tags_to_params(folder.tags)
        search_params.page = 1
        search_params.page_size = limit
        with YandeDataRepository() as repo:
            if random:
                images = repo.query_random_for_tags(
                    folder.tags or "", limit=limit, downloaded_only=True
                )
                _, total = repo.query(query_params=search_params, downloaded_only=True)
            else:
                images, total = repo.query(
                    query_params=search_params, downloaded_only=True
                )
        FavoritesService._refresh_local_count(folder_id)
        return {"total": total, "preview_images": images[:limit]}
    except Exception:
        return None
```

---

## 5. 前端变更

### 5.1 新增组件 `FolderTile.vue`

**位置**：`frontend/src/components/FolderTile.vue`

**Props**：

```typescript
defineProps<{
  folder: FavoriteFolderWithMinimalPreview
  saveDataMode: boolean
}>()
```

**核心逻辑**（完全复用 `WaterfallGallery.vue:336-385` 的并发模式）：

```typescript
const MAX_PREVIEW_CONCURRENT = 10
const loadingQueue = ref<number[]>([])
const srcEnabled = ref<Set<number>>(new Set())
const visibleIds = ref<Set<number>>(new Set())
let observer: IntersectionObserver | null = null

const onObserve = (entries: IntersectionObserverEntry[]) => {
  entries.forEach(entry => {
    const id = parseInt((entry.target as HTMLElement).dataset.imageId!)
    if (entry.isIntersecting) {
      visibleIds.value.add(id)
      if (!srcEnabled.value.has(id) && !loadingQueue.value.includes(id)) {
        loadingQueue.value.push(id)
        processQueue()
      }
    }
  })
}

const processQueue = () => {
  const available = MAX_PREVIEW_CONCURRENT - srcEnabled.value.size
  if (available <= 0) return
  const toProcess = Math.min(available, loadingQueue.value.length)
  for (let i = 0; i < toProcess; i++) {
    srcEnabled.value.add(loadingQueue.value.shift()!)
  }
}
```

**模板**：

```vue
<div class="folder-tile" @click="handleClick">
  <div class="folder-preview-grid" :style="`--cols: ${gridCols}`">
    <div
      v-for="img in folder.preview_images"
      :key="img.id"
      :data-image-id="img.id"
      class="folder-preview-cell"
    >
      <img
        v-if="!saveDataMode && srcEnabled.has(img.id)"
        :src="`/api/v1/gallery/cache/preview/${img.id}`"
        :alt="img.id.toString()"
        loading="lazy"
      />
      <div v-else class="folder-preview-placeholder">
        <el-icon><Picture /></el-icon>
      </div>
    </div>
  </div>
  <div class="folder-info">
    <span class="folder-name">{{ folder.name }}</span>
    <el-tag size="small">{{ folder.local_count || 0 }}</el-tag>
  </div>
</div>
```

**网格列数映射**：

- 4 张图 → 2 列（2×2 网格）
- 6 张图 → 3 列（2×3 或 3×2）
- 8 张图 → 4 列（2×4 或 4×2）

`gridCols` 用 `computed` 从 `folder.preview_images.length` 派生。

### 5.2 `WaterfallGallery.vue` 改造

**新增 prop**：

```typescript
defineProps<{
  ...existing props
  itemType: 'image' | 'folder'  // 新增
}>()
```

**模板**：

```vue
<div v-else ref="containerRef" class="waterfall-container" :style="`column-count: ${columnCount}`">
  <div v-if="itemType === 'image'">
    <!-- 现有 image 渲染逻辑完全保留 -->
  </div>
  <div v-else class="folder-tile-slot">
    <slot
      v-for="folder in reorderedItems"
      :key="folder.id"
      :folder="folder"
    />
  </div>
</div>
```

注意：`itemType='folder'` 时 **复用 `reorderedItems`**，但 Gallery.vue 传入 `images` 字段实际为 `currentFolders`（语义重载）。

### 5.3 `Gallery.vue` 改造

#### 5.3.1 模式按钮组扩展

**位置**：`Gallery.vue:7-20`

**变更**：

```vue
<el-button-group class="mode-buttons">
  <el-button :type="querySource === 'yande' ? 'primary' : ''" @click="handleSourceChange('yande')">
    在线
  </el-button>
  <el-button :type="querySource === 'local' ? 'primary' : ''" @click="handleSourceChange('local')">
    本地
  </el-button>
  <el-button
    v-if="querySource !== 'yande'"
    :type="querySource === 'favorites' ? 'primary' : ''"
    @click="handleSourceChange('favorites')"
  >
    收藏夹
  </el-button>
</el-button-group>
```

#### 5.3.2 新增状态

```typescript
const favoritesView = ref<'folders' | 'folder-detail' | null>(null)
const selectedFavoriteFolder = ref<FavoriteFolder | null>(null)
const currentFolders = ref<FavoriteFolderWithMinimalPreview[]>([])
const folderLoading = ref(false)
const folderHasMore = ref(false)
const folderPage = ref(1)
const FOLDER_PAGE_SIZE = 20
```

#### 5.3.3 模式切换改造

```typescript
const handleSourceChange = (newSource: 'yande' | 'local' | 'favorites') => {
  querySource.value = newSource
  favoritesView.value = null
  selectedFavoriteFolder.value = null
  currentFolders.value = []
  images.value = []
  selectedImages.value = []
  selectAll.value = false
  isIndeterminate.value = false

  if (newSource === 'favorites') {
    favoritesView.value = 'folders'
    loadFolders(1)
    return
  }

  if (Object.keys(queryParams.value).length > 0) {
    queryParams.value.source = newSource
    handleSearch(queryParams.value)
  } else {
    handleSearch({})
  }
}
```

#### 5.3.4 文件夹加载与分页

```typescript
const loadFolders = async (page: number) => {
  if (folderLoading.value) return
  folderLoading.value = true
  try {
    const res = await api.get(
      `/favorites/with-preview?page=${page}&page_size=${FOLDER_PAGE_SIZE}`
    )
    const { items, has_more } = res.data
    if (page === 1) {
      currentFolders.value = items
    } else {
      currentFolders.value.push(...items)
    }
    folderHasMore.value = has_more
    folderPage.value = page
  } catch (e) {
    ElMessage.error('加载收藏夹失败')
  } finally {
    folderLoading.value = false
  }
}

const handleFolderScrollBottom = () => {
  if (folderHasMore.value && !folderLoading.value) {
    loadFolders(folderPage.value + 1)
  }
}
```

#### 5.3.5 文件夹点击进入详情

```typescript
const handleFolderClick = (folder: FavoriteFolderWithMinimalPreview) => {
  selectedFavoriteFolder.value = folder
  favoritesView.value = 'folder-detail'
  // 复用现有 handleSearch，把 folder.tags 注入搜索栏
  queryRef.value?.selectFavorite(folder)
}
```

**AdvancedQuery 新增 `defineExpose` 方法**：

```typescript
// AdvancedQuery.vue
const selectFavorite = (folder: FavoriteFolder) => {
  selectedFavorite.value = folder
  if (folder.tags) {
    const favParams = parseFavoriteTagsToParams(folder.tags)
    Object.assign(queryParams, mapFavoriteParams(favParams))
  }
  showFavoritePanel.value = false
  handleSearch()
}

defineExpose({
  reset: () => { ... },
  selectFavorite,  // 新增
})
```

#### 5.3.6 返回按钮

**新增组件** `frontend/src/components/BackButton.vue`：

视觉风格与 `AdvancedQuery` 的 `search-panel` 保持一致（半透明 + blur），通过 CSS 媒体查询切换布局形态。

```vue
<template>
  <button v-if="visible" class="floating-back-btn" @click="$emit('click')">
    <el-icon><ArrowLeft /></el-icon>
  </button>
</template>

<script setup>
defineProps<{ visible: boolean }>()
defineEmits(['click'])
</script>

<style scoped>
.floating-back-btn {
  position: fixed;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  /* 与 AdvancedQuery .search-panel 保持一致：玻璃半透明 + blur */
  background: rgba(var(--bg-secondary-rgb, 255, 255, 255), 0.8);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid rgba(255, 255, 255, 0.2);
  color: var(--text-primary);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  z-index: 1000;
  transition: opacity 0.2s, background 0.2s;
}
html.dark-mode .floating-back-btn {
  background: rgba(var(--bg-secondary-rgb, 45, 45, 45), 0.8);
  border: 1px solid rgba(255, 255, 255, 0.1);
}
.floating-back-btn:hover {
  background: rgba(var(--bg-secondary-rgb, 255, 255, 255), 1);
}

/* 桌面端（≥ 980px）：与 AdvancedQuery 同一基线，悬浮于搜索栏左侧 */
@media (min-width: 980px) {
  .floating-back-btn {
    bottom: 28px;
    left: calc(50% - 450px - 60px); /* AdvancedQuery 左侧外 + 间距 */
    opacity: 0.8; /* 与搜索栏 0.8 背景一致：半透明玻璃视觉一致 */
  }
}

/* 移动端 / 窄屏（< 980px）：移到搜索栏上方，左对齐，更低透明度 */
@media (max-width: 979px) {
  .floating-back-btn {
    bottom: 78px; /* 搜索栏 bottom: 20px + 高度 ~58px + 间距 */
    left: 20px;
    opacity: 0.5; /* 更半透明，避免遮挡小屏内容 */
  }
}
</style>
```

**位置说明**：

- **桌面端（≥ 980px）**：固定于底部左侧，与 AdvancedQuery 的左侧外缘对齐，高度匹配（同基线 `bottom: 28px`），半透明度 0.85 与搜索栏背景的 0.8 视觉权重一致
- **移动端（< 980px）**：固定于搜索栏正上方（左对齐 `left: 20px`），半透明度降至 0.5 减少遮挡
- **`z-index: 1000`**：与 AdvancedQuery 平级，确保不被其他浮层覆盖

**Gallery.vue 集成**：

```vue
<BackButton
  :visible="querySource === 'favorites' && favoritesView === 'folder-detail'"
  @click="handleBackToFolders"
/>
```

**Gallery.vue 集成**：

```vue
<BackButton
  :visible="querySource === 'favorites' && favoritesView === 'folder-detail'"
  @click="handleBackToFolders"
/>
```

```typescript
const handleBackToFolders = () => {
  selectedFavoriteFolder.value = null
  favoritesView.value = 'folders'
  queryRef.value?.reset()
  images.value = []
}
```

#### 5.3.7 主区域条件渲染

```vue
<div class="gallery-content">
  <template v-if="querySource === 'favorites' && favoritesView === 'folders'">
    <FolderListView
      :folders="currentFolders"
      :loading="folderLoading"
      :has-more="folderHasMore"
      @folder-click="handleFolderClick"
      @scroll-bottom="handleFolderScrollBottom"
    />
  </template>
  <template v-else>
    <WaterfallGallery
      item-type="image"
      :images="images"
      :loading="loading"
      ...
    />
  </template>
</div>
```

### 5.4 `AdvancedQuery.vue` 暴露 `selectFavorite`

复用现有 `selectFavorite` 内部方法，`defineExpose` 时一并暴露，Gallery.vue 可主动调用以设置初始筛选状态。

---

## 6. 状态/生命周期边界

### 6.1 模式按钮的可见性

| querySource | 显示按钮 |
|-------------|----------|
| 'yande' | [在线, 本地] |
| 'local' | [在线, 本地, 收藏夹] |
| 'favorites' | [在线, 本地, 收藏夹] |

**理由**：在线模式是只读浏览场景，没必要给收藏夹入口；本地模式是用户自己的数据，扩展收藏夹。

### 6.2 搜索栏行为

| 视图 | 搜索栏状态 |
|------|-----------|
| 在线模式 | 现有 AdvancedQuery |
| 本地模式 | 现有 AdvancedQuery |
| 收藏夹文件夹列表 | 现有 AdvancedQuery（folder chip 未选） |
| 文件夹图片视图 | 现有 AdvancedQuery，folder chip 已锁，tags 已预填 |

返回按钮按下时调用 `queryRef.value?.reset()` 清空搜索栏状态，与「点在线/本地」行为一致。

### 6.3 多选行为

`favoritesView === 'folders'` 时禁用多选（folder 没有 down_flag 等下载语义）。

---

## 7. 文件清单

### 7.1 后端

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `backend/src/api/v1/favorites.py` | 修改 | `/with-preview` 加分页；`/{id}/preview` 加 `random` 参数 |
| `backend/src/services/favorites.py` | 修改 | `get_folders_with_preview` 实现分页+随机抽样；`preview_folder` 支持 `random` |
| `backend/src/dao/favorite_dao.py` | 修改 | 新增 `list_paginated` |
| `backend/src/dao/yande_data_dao.py` | 修改 | 新增 `query_random_for_tags` |
| `backend/src/models/response/favorites.py` | 修改 | 新增 `FolderPreviewImageMinimal` 等模型 |

### 7.2 前端

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `frontend/src/components/FolderTile.vue` | **新增** | 文件夹瀑布流 tile |
| `frontend/src/components/BackButton.vue` | **新增** | 浮动返回按钮 |
| `frontend/src/views/Gallery.vue` | 修改 | 3 联按钮、新增 favoritesView 状态、loadFolders 等 |
| `frontend/src/components/WaterfallGallery.vue` | 修改 | 新增 `itemType` prop + slot 渲染 |
| `frontend/src/components/AdvancedQuery.vue` | 修改 | `defineExpose` 暴露 `selectFavorite` |
| `frontend/src/api/favorites.js` | 修改 | 新增 `getFoldersWithPreviewPaginated` |

---

## 8. 测试

### 8.1 后端

新增 `backend/tests/test_favorites_with_preview.py`：

- `test_with_preview_pagination`：page=1/page=2 返回正确切片
- `test_with_preview_returns_total_and_has_more`：边界值（最后一页 has_more=False）
- `test_with_preview_count_tier`：local_count=10 → 4 张；local_count=100 → 6 张；local_count=500 → 8 张
- `test_with_preview_id_only_response`：响应 schema 仅含 id/width/height，不含 preview_url
- `test_preview_random`：random=true 返回结果与 random=false 不同（同一 folder 多次调用）
- `test_preview_random_limit`：`limit=9` 返回 9 条

### 8.2 前端

- `FolderTile.spec.js`：默认渲染、saveDataMode 退化、点击事件、并发门控
- `WaterfallGallery.spec.js`：扩展 folder itemType 测试
- `Gallery.spec.js`（如已有）：模式切换、favoritesView 转移

### 8.3 手动验证清单

- [ ] 在线模式下不显示「收藏夹」按钮
- [ ] 本地模式下点击「收藏夹」→ 进入文件夹列表
- [ ] 文件夹 tile 显示 4/6/8 张预览图（按 local_count 分档）
- [ ] 省流模式下文件夹 tile 退化为图标色块
- [ ] 滚动文件夹列表到底部自动加载下一页
- [ ] 点击文件夹 → 进入文件夹图片视图，搜索栏显示 ★folder  chip
- [ ] 文件夹图片视图下叠加额外 tag 进一步筛选生效
- [ ] 点返回按钮 → 回到文件夹列表，搜索栏清空
- [ ] 切换到「在线」/「本地」按钮自动重置 favoritesView

---

## 9. 风险与权衡

### 9.1 风险

| 风险 | 缓解 |
|------|------|
| `with-preview` 单次请求可能慢（每 folder 一次随机 SQL） | 分页 + 后端可选并发（先同步实现，监控后再决定是否改并行） |
| 文件夹数量大时随机抽样 SQL 性能 | 利用 `down_flag` + tags 索引；可后续引入缓存层 |
| FolderTile 渲染 N 张图影响首屏 | IntersectionObserver 仅加载视口内 |

### 9.2 YAGNI 决策

- ❌ 不做文件夹拖拽排序（已有面板支持）
- ❌ 不做文件夹内图片预览（进 folder-detail 即可）
- ❌ 不做收藏夹模式下的多选/批下载
- ❌ 不做服务端并发限制（依赖浏览器原生）
- ❌ 不做前端 JS 端并发池（FolderTile 复用 WaterfallGallery 已有的 srcEnabled 门控）

### 9.3 向后兼容

- `/favorites/{id}/preview` 的 `random` 参数默认 false，旧调用方不受影响
- `/favorites/with-preview` 响应 schema 改变（新增 items/total/has_more 包装）属于破坏性变更；但前端目前仅 favorites.js 引用，且其 `preview_images=[]` 本就是 TODO，不存在线上调用方

---

## 10. 实施步骤（高层）

1. 后端：`dao/favorite_dao.list_paginated` + `dao/yande_data_dao.query_random_for_tags`
2. 后端：`models/response/favorites.py` 新增精简模型
3. 后端：`services/favorites.py` 改造两个方法
4. 后端：`api/v1/favorites.py` 路由调整 + random 参数
5. 后端：单元测试
6. 前端：`FolderTile.vue` 新增（独立组件先完成）
7. 前端：`WaterfallGallery.vue` 加 itemType + slot
8. 前端：`Gallery.vue` 状态机改造 + 按钮组扩展
9. 前端：`AdvancedQuery.vue` 暴露 selectFavorite
10. 前端：`BackButton.vue` 新增 + 集成
11. 前端：组件测试 + 手动验证

---

## 附录 A：完整 API 契约

### A.1 `GET /favorites/with-preview?page=1&page_size=20`

**Response 200**：

```json
{
  "code": "0000",
  "message": "ok",
  "data": {
    "items": [
      {
        "id": 1,
        "name": "风景精选",
        "tags": "scenery rating:s",
        "color": "#409EFF",
        "icon": "folder",
        "sort_order": 0,
        "local_count": 42,
        "online_count": 120,
        "schedule_enabled": false,
        "preview_images": [
          {"id": 1001, "width": 1920, "height": 1080},
          {"id": 1002, "width": 1280, "height": 720},
          {"id": 1003, "width": 1600, "height": 900},
          {"id": 1004, "width": 2048, "height": 1366}
        ]
      }
    ],
    "total": 5,
    "has_more": false
  }
}
```

### A.2 `GET /favorites/{folder_id}/preview?limit=6&random=true`

**Response 200**：

```json
{
  "code": "0000",
  "message": "ok",
  "data": {
    "total": 42,
    "preview_images": [
      {
        "id": 1001,
        "tags": "scenery",
        "file_url": null,
        "preview_url": "yande/1001.jpg",
        "sample_url": null,
        "jpeg_url": null,
        "width": 1920,
        "height": 1080,
        "file_ext": "jpg",
        "file_size": 524288,
        "down_flag": true,
        "rating": "Safe"
      }
    ]
  }
}
```

---

*最后更新：2026-08-20*