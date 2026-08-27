# Final Fix Report — `feature-favorites-mode` 整支审查

## 触发

前一轮 fix-and-review loop 完成后，整支审查识别出 **1 Critical + 2 Important** 跨多个 prior commit 的问题，本次 fix dispatch 在单次 commit 内全部解决。

## 修复清单

### C1（Critical）：FolderTile 实例作用域

**文件**：`frontend/src/components/FolderTile.vue:88`

**Bug**：`onMounted` 中 `document.querySelector('.folder-tile')` 取的是 document 中**第一个**匹配的 `.folder-tile` 元素，而非当前 Vue 实例的根。在收藏夹瀑布流实际渲染场景下（多个 FolderTile 同时挂载），只有 Tile #1 的 preview images 会经过 IntersectionObserver 注册，Tiles #2..N 永远停留在 placeholder 状态。

**修复（3 处改动）**：

1. 模板根 `<div>` 加 `ref="tileRef"`：
   ```html
   <div ref="tileRef" class="folder-tile" @click="$emit('click', folder)">
   ```
2. script setup 增加 `const tileRef = ref(null)`（与 `loadingQueue` / `srcEnabled` / `visibleIds` 同区域）。
3. `onMounted` 用 `tileRef.value` 替代 `document.querySelector('.folder-tile')`。

`saveDataMode` watcher 不涉及 `document.querySelector('.folder-tile')`，无需调整。

### I1（Important）：补齐 `preview_folder(random=true)` API 测试

**文件**：`unit_test/api/v1/test_favorite_preview_random.py`（新建，5 个测试）

| 测试 | 覆盖 |
|------|------|
| `test_preview_random_default_is_false` | `?random` 不传 → service 收到 `random=False`，`limit=6` 默认 |
| `test_preview_random_true` | `?random=true` → service 收到 `random=True` |
| `test_preview_random_false_explicit` | `?random=false` → service 收到 `random=False` |
| `test_preview_random_limit_9` | `?random=true&limit=9` → service 收到 `limit=9` |
| `test_preview_random_limit_validation` | `?limit=200` → API 层 422 拦截，service 未被调用 |

策略：在 FastAPI TestClient + monkeypatch `FavoritesService.preview_folder`，校验 API 路由正确把 query 参数透传给 service。

### I2（Important）：补齐 Gallery.vue 状态机测试

**文件**：`frontend/src/views/Gallery.spec.js`（新建，4 个测试）

| 测试 | 覆盖 |
|------|------|
| `handleSourceChange("favorites")` | `favoritesView='folders'` + `getFoldersWithPreview(1, 20)` 被调用一次 |
| 点击 FolderTile | `favoritesView='folder-detail'` + `queryRef.selectFavorite(folder)` 被调用 |
| `handleBackToFolders` | `favoritesView` 重置 `'folders'` + `queryRef.reset()` 被调用 |
| BackButton `visible` | 仅在 `favoritesView='folder-detail'` 时为 true，其它状态均为 false |

**附带修复（Gallery.vue）**：新增 `const queryRef = ref(null)` 声明。
原状态机代码在 `handleFolderClick` / `handleBackToFolders` 中调用 `queryRef.value?.selectFavorite(...)`，但 `<script setup>` 内**未声明** `queryRef` ref —— Vue template ref 无法自动绑定到未声明变量，运行时 `queryRef is not defined`。I2 测试暴露此 bug，1 行修复即可对齐 Vue 3 template-ref 最佳实践。

## 验证结果

### 前端（`cd frontend && npx vitest run`）

```
✓ src/components/WaterfallGallery.spec.js (9 tests)
✓ src/components/FolderTile.spec.js        (7 tests, 含 C1 多实例回归)
✓ src/components/BackButton.spec.js        (3 tests)
✓ src/views/Download.spec.js               (2 tests)
✓ src/views/Gallery.spec.js                (4 tests, I2 新增)

Test Files  5 passed (5)
Tests       25 passed (25)
```

### 后端（`PYTHONPATH=backend pytest unit_test/api/v1/test_favorite_preview_random.py -v`）

```
test_preview_random_default_is_false     PASSED
test_preview_random_true                 PASSED
test_preview_random_false_explicit       PASSED
test_preview_random_limit_9              PASSED
test_preview_random_limit_validation     PASSED

5 passed
```

`unit_test/services/test_favorite_get_folders_with_preview.py` 原有 5 个测试仍全绿。

## Commit

- **分支**：`feature-favorites-mode`（HEAD = 3dd8472）
- **Commit**：`fix(favorites): C1 FolderTile template ref + I1/I2 test coverage`
- **文件**：
  - `frontend/src/components/FolderTile.spec.js`（modified）
  - `frontend/src/components/FolderTile.vue`（modified）
  - `frontend/src/views/Gallery.spec.js`（new）
  - `frontend/src/views/Gallery.vue`（modified，+1 行 `const queryRef = ref(null)`）
  - `unit_test/api/v1/test_favorite_preview_random.py`（new）

## 推前密钥扫描

```bash
git diff --cached | grep -iE '(password|secret|token|api[_-]?key)\s*[:=]\s*["\047][^"\047]+["\047]' \
  | grep -vE '""|null|<YOUR_|<CHANGE_'
# 输出为空 → 安全可推送
```

## 备注

- 本次未触碰 desktop/* 与 uv.lock（来自其它 session 的本地未提交变更，与本次 fix 无关）。
- 不进 commit 的工作区残留：`.omo/`、`config/data.cfg.bak`、`test_minimal.nsi`（均与本次 fix 无关）。