# 收藏夹设置面板重构 + 像素自适应 — 设计文档

**状态**：Draft
**日期**：2026-08-22
**分支**：`feature-favorites-mode`（基于 `65f7104`）
**类型**：UX 重构 + 自适应逻辑修正

---

## 1. 目标

针对用户 PR review 的 3 项反馈进行 UX 优化：

1. **左上角 4 档 tile 尺寸开关移入高级设置**：与「收藏夹」相关配置一起管理
2. **高级设置新增「收藏夹」栏目**：包含「是否在主页显示收藏夹」三联开关 + tile 尺寸 4 档
3. **自适应功能修正**：按文件夹 tile 实际宽度像素判断展示图片数量（非后端硬编码）

明确**不在范围内**：

- 移除后端 `/favorites/with-preview` 的 `tile_size` 参数（保留向后兼容，'adaptive' 改为返 8 张）
- 收藏夹按钮位置变更（仍在 3 联按钮组）
- 「我的最爱」功能
- 高级面板本身的重新设计

---

## 2. 背景与现状

### 2.1 当前 4 档开关位置

`Gallery.vue:47-58` 的 toolbar-left 区域，radio-group 含 `adaptive / 4 / 6 / 8`。

**问题**：
- 与主搜索栏视觉割裂
- 不在「收藏夹」统一设置中，违反上下文一致性

### 2.2 当前后端 tile_size 行为

`backend/src/services/favorites.py:_preview_count_for_local_count(local_count, tile_size)`：
- `adaptive` → 按 `local_count` 分档（<50→4, 50-199→6, ≥200→8）
- `small/medium/large` → 固定 4/6/8

**问题**：
- 自适应完全在后端硬编码，按 local_count（文件夹图片总数）分档
- 与 tile 实际宽度无关 — 屏幕宽 / 列数改变时不会自适应

### 2.3 三联开关现状

无此功能，需要新增。

---

## 3. 架构与数据流

### 3.1 模式分层（更新）

```
AdvancedQuery.vue (props 新增)
└─ favoritesConfig: { buttonMode: 'hidden'|'shown'|'default', tileSize: 'adaptive'|'4'|'6'|'8' }
   或拆成两个独立 props (buttonMode + tileSize)，由 Gallery 传值
   AdvancedPanel 新增「收藏夹」section 在所有 mode 都显示
```

### 3.2 三联开关语义（`buttonMode`）

| 值 | 行为 |
| |  |
|--- | ---|
| `hidden` | toolbar-left 不显示「收藏夹」按钮（querySource 只剩 'yande'/'local'）|
| `shown` | 显示按钮，但 onMounted 默认 querySource='local' |
| `default` | 显示按钮，且 onMounted 默认 querySource='favorites'（首次访问时）|

### 3.3 自适应按像素判断（前端纯实现）

```
FolderTile 挂载时：
  1. measure tile 实际宽度 (offsetWidth)
  2. 计算显示张数：
     - width >= 450px → 8 张
     - 300-449px → 6 张
     - < 300px → 4 张
  3. 裁剪 preview_images.slice(0, N) 渲染

后端变化（最小）：
  - tile_size='adaptive' → 固定返回 8 张（移除 local_count 分档）
  - 其他 tile_size 保持现状
```

**向后兼容**：后端 `/favorites/with-preview?tile_size=adaptive` 现在永远返 8 张，前端自动按像素裁剪到合适张数。Tile_size='4'/'6'/'8' 仍可手动固定。

---

## 4. 状态/生命周期边界

### 4.1 状态转移表（更新）

| 用户动作 | querySource | favoritesView | buttonMode |
|----------|-------------|---------------|------------|
| 首次访问（buttonMode='hidden'） | 'local' | null | 'hidden' |
| 首次访问（buttonMode='shown'） | 'local' | null | 'shown' |
| 首次访问（buttonMode='default'） | 'favorites' | 'folders' | 'default' |
| 点「收藏夹」按钮（buttonMode='default'） | 'favorites' | 'folders' | 不变 |
| 点文件夹 tile | 'favorites' | 'folder-detail' | 不变 |
| 点返回 | 'favorites' | 'folders' | 不变 |
| 点「在线」/「本地」（buttonMode='hidden'） | 'yande'/'local' | null | 'hidden' |
| 点「在线」/「本地」（buttonMode='shown'/'default'） | 'yande'/'local' | null | 保持 |

### 4.2 localStorage 新增键

| 键 | 值 | 默认 |
| |  |  |
| --- | --- |  |
| `gallery_source` | 'yande' / 'local' / 'favorites' | 见 `buttonMode` |
| `gallery_tile_size` | 'adaptive' / '4' / '6' / '8' | 'adaptive' |
| `gallery_favorites_button_mode` | 'hidden' / 'shown' / 'default' | 'shown' |

### 4.3 AdvancedQuery 暴露

新增 defineExpose 方法：
- `setFavoritesButtonMode(mode)` / 状态提升到 Gallery 持久化
- `setFavoritesTileSize(size)` / 同上
- 已有 `setIncludeOnline` 模式（Task 5 已实现）

---

## 5. 文件清单

### 5.1 后端

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `backend/src/services/favorites.py` | 修改 | `_preview_count_for_local_count`：`tile_size='adaptive'` 返 8，不再按 local_count 分档 |

### 5.2 前端

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `frontend/src/views/Gallery.vue` | 修改 | 移除 toolbar-left 4 档开关；新增 buttonMode ref + localStorage；onMounted 根据 buttonMode 设置默认 querySource；tobar 条件渲染「收藏夹」按钮（hidden 时隐藏）|
| `frontend/src/components/AdvancedQuery.vue` | 修改 | advanced-panel 顶部新增「收藏夹」section（含 buttonMode 三联开关 + tile 尺寸 4 档）；所有 mode 都显示 |
| `frontend/src/components/FolderTile.vue` | 修改 | 实现像素自适应：测量 tile 宽度 → 计算 N → 裁剪 preview_images |
| `frontend/src/views/Gallery.spec.js` | 修改 | 补充 buttonMode 行为测试 |
| `frontend/src/components/AdvancedQuery.spec.js` | 修改 | 补充「收藏夹」section 行为测试 |
| `frontend/src/components/FolderTile.spec.js` | 修改 | 补充像素自适应测试 |

---

## 6. 测试

### 6.1 后端

新增 / 修改：
- `test_favorite_tile_size_adaptive_returns_8`：tile_size='adaptive' 无论 local_count 多少都返 8 张
- 更新 `test_tile_size_small_returns_4` 等保留 4 档固定行为测试

### 6.2 前端

新增 / 修改：
- `Gallery.spec.js`：
  - `buttonMode='hidden'` 时 toolbar 不显示收藏夹按钮
  - `buttonMode='default'` 时 onMounted 默认 querySource='favorites'
  - buttonMode 切换 → localStorage 同步
- `AdvancedQuery.spec.js`：
  - 三联开关渲染测试（hidden/shown/default 三选项）
  - 4 档 radio 渲染测试
- `FolderTile.spec.js`：
  - 像素自适应测试（mock offsetWidth → 期望渲染 N 张）
  - 边界值测试（width=300、450）

---

## 7. 风险与权衡

| 风险 | 缓解 |
|------|------|
| 移除左上角 4 档开关是 UX 破坏性变更 | 移动到高级设置后位置更明确，附 commit message 说明 |
| 三联开关枚举与现有开关语义不同 | localStorage 新键 `gallery_favorites_button_mode` 不污染旧状态 |
| 自适应后端 tile_size='adaptive' 永远返 8，浪费带宽 | 带宽增加有限（<10KB），换来前端完全控制 |
| FolderTile 像素测量时机（mount vs visible） | 用 ResizeObserver + IntersectionObserver 双重触发 |
| localStorage schema 变化（新增 key） | 新 key 默认值明确，旧 localStorage 不受影响 |

### 7.1 YAGNI 决策

- ❌ 不做 per-folder 像素阈值覆盖（所有 folder 共享同一套阈值）
- ❌ 不做 tile_size='auto-dense' 等额外档位（4 档够用）
- ❌ 不做服务端 cache by tile_size（每页查询差异大，缓存收益小）

---

## 8. 实施步骤（高层）

1. 后端：tile_size='adaptive' 改为返 8（service 调整 + 测试）
2. 前端：FolderTile 像素自适应（measure + slice + 测试）
3. 前端：AdvancedQuery.advanced-panel 加「收藏夹」section（含三联开关 + 4 档 radio）
4. 前端：Gallery.vue 移除 toolbar 4 档开关；新增 buttonMode ref + localStorage + 按钮条件渲染
5. 前端 + 后端：测试 + 集成
6. 全套验证 + LSP

---

*最后更新：2026-08-22*