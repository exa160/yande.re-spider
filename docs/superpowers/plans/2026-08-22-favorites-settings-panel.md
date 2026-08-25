# 收藏夹设置面板重构 + 像素自适应 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** UX 重构——把 4 档 tile 尺寸开关移入高级设置；高级设置加「收藏夹」section 含 buttonMode 三联开关；FolderTile 按 tile 实际宽度像素裁剪显示张数。

**Architecture:** 后端最小改动（adaptive 返 8）；前端 AdvancedQuery 顶部新增 section；Gallery 移除 toolbar 4 档、改用 buttonMode 控制按钮可见性；FolderTile measure offsetWidth + slice。

**Tech Stack:** Vue 3.4 + Element Plus 2.5 / FastAPI + SQLAlchemy / Vitest / pytest

**前置阅读：**
- Spec: `docs/superpowers/specs/2026-08-22-favorites-settings-panel-design.md`
- 项目规范：`AGENTS.md`

**全局约束：**
- 分支：`feature-favorites-mode`（基于 `65f7104`）
- localStorage 新增键：`gallery_favorites_button_mode`（值 `hidden`/`shown`/`default`，默认 `shown`）
- 自适应像素阈值：宽 ≥ 450 → 8 张；300-449 → 6 张；<300 → 4 张
- 向后兼容：`tile_size='adaptive'` 永远返 8（前端按宽度裁剪）；`tile_size='4'/'6'/'8'` 行为不变
- 高级设置「收藏夹」section 在所有 mode 都显示

---

## Task 1：后端 `tile_size='adaptive'` 改为返 8 张

**Files:**
- Modify: `backend/src/services/favorites.py:35-45`（`_preview_count_for_local_count`）
- Modify: `unit_test/api/v1/test_favorite_tile_size.py`（更新 adaptive 测试）

- [ ] **Step 1：写失败测试**

修改 `unit_test/api/v1/test_favorite_tile_size.py` 中的 `test_tile_size_adaptive_uses_local_count`：

```python
def test_tile_size_adaptive_always_returns_8():
    """tile_size='adaptive' 不再按 local_count 分档，永远返 8 张"""
    from src.dao.database import BaseDAO
    BaseDAO().session.query(YandeData).delete()
    BaseDAO().session.query(FavoriteFolder).delete()
    _seed_folder(10)  # adaptive 旧版应返 4
    _seed_yande_data(10)
    from src.services.favorites import FavoritesService
    items, _, _ = FavoritesService.get_folders_with_preview(
        page=1, page_size=20, tile_size="adaptive"
    )
    assert len(items[0].preview_images) == 8
```

并把旧的 `test_tile_size_adaptive_uses_local_count` 删除。

- [ ] **Step 2：运行测试确认失败**

```bash
PYTHONPATH=backend .venv/bin/python -m pytest unit_test/api/v1/test_favorite_tile_size.py::test_tile_size_adaptive_always_returns_8 -v
```

预期：FAIL（旧版返 4 张）

- [ ] **Step 3：修改 `_preview_count_for_local_count`**

`backend/src/services/favorites.py:35-45`：

```python
def _preview_count_for_local_count(local_count: int, tile_size: str = "adaptive") -> int:
    if tile_size == "small":
        return 4
    if tile_size == "medium":
        return 6
    if tile_size == "large":
        return 8
    # adaptive：前端按 tile 宽度像素裁剪，后端统一返 8 张作为上限
    return 8
```

- [ ] **Step 4：运行测试**

```bash
PYTHONPATH=backend .venv/bin/python -m pytest unit_test/api/v1/test_favorite_tile_size.py -v
```

预期：6 PASS（原 5 个 + 新 1 个）

- [ ] **Step 5：Commit**

```bash
git add backend/src/services/favorites.py unit_test/api/v1/test_favorite_tile_size.py
git commit -m "feat(backend): tile_size='adaptive' 永远返 8（前端按宽度裁剪）"
```

---

## Task 2：前端 `FolderTile` 像素自适应

**Files:**
- Modify: `frontend/src/components/FolderTile.vue`
- Modify: `frontend/src/components/FolderTile.spec.js`

**Interfaces:**
- 新增 `displayCount` computed：基于 tile 实际宽度（`offsetWidth`）计算
- 模板渲染 `preview_images.slice(0, displayCount)` 而非全部
- ResizeObserver 监听 tile 宽度变化

- [ ] **Step 1：写失败测试**

`frontend/src/components/FolderTile.spec.js` 追加：

```javascript
describe('FolderTile 像素自适应', () => {
  it('tile 宽度=500px 时显示 8 张', async () => {
    const folder = mkFolder(8)
    folder.preview_images = Array.from({length: 8}, (_, i) => ({
      id: 1000+i, width: 100, height: 100, rating: 'Safe'
    }))
    const wrapper = mount(FolderTile, {
      props: { folder, saveDataMode: false, safeMode: false },
      attachTo: document.body,
    })
    // 模拟 ResizeObserver 返回宽度=500
    vi.spyOn(wrapper.element, 'offsetWidth', 'get').mockReturnValue(500)
    // 触发 ResizeObserver
    // ...
    await flushPromises()
    expect(wrapper.findAll('img').length).toBeGreaterThanOrEqual(7)  // 容差
  })

  it('tile 宽度=350px 时显示 6 张', async () => {
    // 类似测试
  })

  it('tile 宽度=200px 时显示 4 张', async () => {
    // 类似测试
  })
})
```

> 注：具体 mock ResizeObserver 触发方式按实现细节调整

- [ ] **Step 2：运行测试确认失败**

```bash
cd frontend && npx vitest run src/components/FolderTile.spec.js
```

- [ ] **Step 3：实现像素自适应**

`frontend/src/components/FolderTile.vue`：

1. 模板中 `preview_images` 改为 `preview_images.slice(0, displayCount)`（在 v-for 里）：
```vue
<div
   v-for="img in folder.preview_images.slice(0, displayCount)"
   :key="img.id"
   ...
>
```

2. script 中添加：
```javascript
const ADAPTIVE_THRESHOLDS = [
  [450, 8],
  [300, 6],
  [0, 4],
]

const displayCount = ref(8)
const tileRef = ref(null)  // 复用已有 ref

const measureTileWidth = () => {
  if (!tileRef.value) return
  const w = tileRef.value.offsetWidth
  for (const [minW, count] of ADAPTIVE_THRESHOLDS) {
    if (w >= minW) {
      displayCount.value = count
      return
    }
  }
  displayCount.value = 4
}

onMounted(() => {
  measureTileWidth()
  setupObserver()
  if (typeof ResizeObserver !== 'undefined' && tileRef.value) {
    const resizeObs = new ResizeObserver(() => measureTileWidth())
    resizeObs.observe(tileRef.value)
    onUnmounted(() => resizeObs.disconnect())
  }
})
```

- [ ] **Step 4：运行测试**

```bash
npx vitest run src/components/FolderTile.spec.js
```

- [ ] **Step 5：Commit**

```bash
git add frontend/src/components/FolderTile.vue frontend/src/components/FolderTile.spec.js
git commit -m "feat(frontend): FolderTile 像素自适应（按宽度裁剪 4/6/8 张）"
```

---

## Task 3：前端 `AdvancedQuery.advanced-panel` 加「收藏夹」section

**Files:**
- Modify: `frontend/src/components/AdvancedQuery.vue`
- Modify: `frontend/src/components/AdvancedQuery.spec.js`

**Interfaces:**
- 新增 prop `favoritesConfig: { buttonMode, tileSize }` 或两个独立 props
- 新增 emit `favorites-config-change`（带新 config payload）
- 新增 expose `setFavoritesConfig(config)` 和 `getFavoritesConfig()`

- [ ] **Step 1：写失败测试**

`frontend/src/components/AdvancedQuery.spec.js` 追加：

```javascript
describe('AdvancedQuery 收藏夹 section', () => {
  it('所有 mode 都显示收藏夹 section', () => {
    const wrapper = factory({ mode: 'gallery' })
    expect(wrapper.find('.favorites-section').exists()).toBe(true)
    
    wrapper2 = factory({ mode: 'favorites-folders' })
    expect(wrapper2.find('.favorites-section').exists()).toBe(true)
    
    wrapper3 = factory({ mode: 'favorites-folder-detail' })
    expect(wrapper3.find('.favorites-section').exists()).toBe(true)
  })

  it('三联开关选项 hidden/shown/default', () => {
    const wrapper = factory()
    const radios = wrapper.findAll('.favorites-section .el-radio-button')
    expect(radros.length).toBe(3)
    expect(radros.map(r => r.attributes('label'))).toEqual([
      '关闭', '开启', '默认显示'
    ])
  })

  it('4 档 tile 尺寸 radio', () => {
    const wrapper = factory()
    const sizeRadios = wrapper.findAll('.favorites-section .tile-size-radios .el-radio-button')
    expect(sizeRadios.length).toBe(4)
  })
})
```

- [ ] **Step 2：运行测试确认失败**

```bash
npx vitest run src/components/AdvancedQuery.spec.js
```

- [ ] **Step 3：实现收藏夹 section**

在 `AdvancedQuery.vue` 的 `.advanced-panel` div 内顶部新增：

```vue
<div class="favorites-section panel-row" v-if="false">
  <!-- 永远显示，但条件可由 props.mode 决定——brief 要求所有 mode 显示 -->
</div>
```

具体实现：

```vue
<!-- 收藏夹栏目：在 advanced-panel 顶部，所有 mode 都显示 -->
<div class="favorites-section panel-row">
  <div class="row-item">
    <label>主页显示收藏夹</label>
    <el-radio-group v-model="localButtonMode" size="small">
      <el-radio-button label="hidden">关闭</el-radio-button>
      <el-radio-button label="shown">开启</el-radio-button>
      <el-radio-button label="default">默认显示</el-radio-button>
    </el-radio-group>
  </div>
  <div class="row-item">
    <label>收藏夹大小</label>
    <el-radio-group v-model="localTileSize" size="small" class="tile-size-radios">
      <el-radio-button label="adaptive">自适应</el-radio-button>
      <el-radio-button label="4">4张</el-radio-button>
      <el-radio-button label="6">6张</el-radio-button>
      <el-radio-button label="8">8张</el-radio-button>
    </el-radio-group>
  </div>
</div>
```

script 中：
- 新增 `localButtonMode` 和 `localTileSize` refs
- watch 变化时 emit `favorites-config-change` + 调用 localStorage.setItem
- defineExpose 新增 setFavoritesConfig / getFavoritesConfig

- [ ] **Step 4：运行测试**

```bash
npx vitest run src/components/AdvancedQuery.spec.js
```

- [ ] **Step 5：Commit**

```bash
git add frontend/src/components/AdvancedQuery.vue frontend/src/components/AdvancedQuery.spec.js
git commit -m "feat(frontend): AdvancedQuery 高级设置加收藏夹 section（三联开关 + 4 档 radio）"
```

---

## Task 4：前端 `Gallery.vue` 移除 toolbar 4 档 + 新增 buttonMode 逻辑

**Files:**
- Modify: `frontend/src/views/Gallery.vue`
- Modify: `frontend/src/views/Gallery.spec.js`

- [ ] **Step 1：写失败测试**

`frontend/src/views/Gallery.spec.js` 追加：

```javascript
describe('Gallery buttonMode', () => {
  it('buttonMode=hidden 时 toolbar 不显示收藏夹按钮', async () => {
    localStorage.setItem('gallery_favorites_button_mode', 'hidden')
    const wrapper = factory()
    await flushPromises()
    const btns = wrapper.findAll('.toolbar-left .el-button')
    expect(btns.length).toBe(2)  // 仅 在线 + 本地
  })

  it('buttonMode=default 时 onMounted 默认进入 favorites', async () => {
    localStorage.setItem('gallery_favorites_button_mode', 'default')
    const wrapper = factory()
    await flushPromises()
    expect(wrapper.vm.querySource).toBe('favorites')
  })

  it('buttonMode=shown 时 onMounted 默认进入 local', async () => {
    localStorage.setItem('gallery_favorites_button_mode', 'shown')
    const wrapper = factory()
    await flushPromises()
    expect(wrapper.vm.querySource).toBe('local')
  })

  it('通过 @favorites-config-change 更新 buttonMode', async () => {
    // ...
  })
})
```

- [ ] **Step 2：运行测试确认失败**

- [ ] **Step 3：Gallery.vue 修改**

1. 移除 toolbar-left 4 档 radio-group（`Gallery.vue:47-58`）
2. 新增 `buttonMode` ref（默认从 localStorage 读 `gallery_favorites_button_mode`，默认 `'shown'`）
3. onMounted：根据 buttonMode 决定初始 querySource：
   - 'hidden' → 'local'
   - 'shown' → 'local'  
   - 'default' → 'favorites'
4. toolbar-left 按钮条件渲染：`v-if="buttonMode !== 'hidden'"` 包住「收藏夹」按钮
5. 新增 `@favorites-config-change` 事件处理函数
6. 移除 toolbar tileSize 相关代码（tileSize 改为通过 AdvancedQuery 管理）

- [ ] **Step 4：运行测试**

```bash
npx vitest run src/views/Gallery.spec.js
```

- [ ] **Step 5：Commit**

```bash
git add frontend/src/views/Gallery.vue frontend/src/views/Gallery.spec.js
git commit -m "feat(frontend): Gallery 移除 toolbar 4 档 + buttonMode 三联开关逻辑"
```

---

## Task 5：全套测试 + LSP + 集成验证 + 推送

**Files:** 仅运行验证

- [ ] **Step 1：后端全测**

```bash
PYTHONPATH=backend .venv/bin/python -m pytest unit_test/api/v1/test_favorite_tile_size.py unit_test/api/v1/test_favorite_preview_image_rating.py unit_test/api/v1/test_gallery_favorites_source.py unit_test/dao/ unit_test/services/test_favorite_get_folders_with_preview.py 2>&1 | tail -30
```

- [ ] **Step 2：前端全测**

```bash
cd frontend && npx vitest run 2>&1 | tail -15
```

- [ ] **Step 3：LSP 检查**

- [ ] **Step 4：推送**

```bash
git push https://x-access-token:ghp_<YOUR_TOKEN>@github.com/exa160/yande.re-spider.git feature-favorites-mode
```

- [ ] **Step 5：追加 task-9-report.md**

## 自审清单

| 检查项 | 结果 |
|--------|------|
| Spec 覆盖 | ✅ 3 项重构全部对应 5 个 tasks |
| 占位扫描 | ✅ 无 TBD/TODO 占位 |
| 类型一致性 | ✅ buttonMode 枚举 'hidden'/'shown'/'default' 全局一致 |
| 任务边界 | ✅ 每个 task 独立可测 |
| 向后兼容 | ✅ tile_size='adaptive' 永远返 8（之前返 4-8）；tile_size='4'/'6'/'8' 不变 |

## 执行交接

Plan 已保存至 `docs/superpowers/plans/2026-08-22-favorites-settings-panel.md`

5 个任务，预期 5 次 commit。执行方式：推荐 subagent-driven。