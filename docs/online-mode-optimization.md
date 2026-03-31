# 在线模式优化方案

## 背景

当前在线模式 (source=yande) 查询 yande.re API 慢，瀑布流加载卡顿。
需要优化加载体验。

## 需求分析

### 1. 数据存储策略
- **写入时机**: 在线查询到的数据**立即写入数据库**（即使未下载）
- **存储结构**: 复用现有的 `yande_data` 表，用 `down_flag` 字段区分下载状态
- **无外键**: 不使用外键，避免额外操作成本

### 2. "上一次浏览位置" 定义
- 值为**最新一次查询结果中的最大 post id**
- 用于恢复浏览位置和连续性检测

### 3. yande.re API 特性
- 默认无参数时: `https://yande.re/post.json` 返回最新帖子 (id 降序)
- 支持参数: `page`, `tags`
- 无 `since_id` / `max_id` 参数，需自行实现分页

### 4. 加载策略
- **第一步**: 从数据库加载 20 条记录（id 降序）
- **第二步**: 异步补充在线查询结果
- **冲突处理**: 在线数据与本地冲突时**更新**而非忽略

### 5. 连续性检测与"加载更多"按钮
- 检测数据库中是否存在"断档"（缺失的 id）
- 根据断档位置动态调整"加载更多"按钮位置
- 可选：标记上一次的图片位置

## 数据库变更

### 新增字段 (yande_data 表)

| 字段 | 类型 | 说明 |
|-----|------|-----|
| `down_flag` | Boolean | True=已下载, False=仅浏览记录 |
| `last_browse_max_id` | Integer | 用户最后一次浏览的最大 id (会话级) |

### 现有字段复用
- 所有 yande API 返回的字段已存在于表中

## API 变更

### 新增端点

#### 1. 获取浏览状态
```
GET /api/v1/gallery/browse-state
Response: {
    "last_max_id": 12345,  # 上次浏览的最大 id
    "db_count": 100,       # 数据库总记录数
    "newest_in_db": 12350 # 数据库中最新记录的 id
}
```

#### 2. 增量同步在线数据
```
POST /api/v1/gallery/sync-online
Body: {
    "max_id": 12340,  # 当前展示的最小 id，服务器返回 < max_id 的数据
    "page_size": 20,
    "tags": ""
}
Response: {
    "synced_count": 20,     # 本次同步数量
    "new_max_id": 12320,   # 同步后的新最大 id (本地数据库中的)
    "has_gap": false,      # 是否有断档
    "gap_before_id": null  # 断档位置
}
```

#### 3. 批量插入/更新在线数据
```
POST /api/v1/gallery/batch-upsert
Body: {
    "posts": [...]  # yande API 返回的 post 数组
}
Response: {
    "inserted": 15,
    "updated": 5
}
```

### 修改端点

#### /api/v1/gallery/load
新增参数:
- `source`: "local" | "yande" | "hybrid" (新增 hybrid 模式)
- `last_max_id`: 上次查询的最大 id（仅 hybrid 模式）
- `fill_from_db_first`: Boolean = true (hybrid 模式先展示本地数据)

Response 新增字段:
- `has_gap`: Boolean - 是否有数据断档
- `gap_before_id`: Integer - 断档位置

## 前端交互流程 (Hybrid 模式)

### 初始化
1. 调用 `/api/v1/gallery/browse-state` 获取浏览状态
2. 如果 `last_max_id` 存在且 `db_count > 0`:
   - 调用 `/api/v1/gallery/load?source=local&max_id={last_max_id}` 获取本地数据
   - 同时调用 `/api/v1/gallery/sync-online` 异步同步数据
3. 如果 `db_count == 0`:
   - 调用 `/api/v1/gallery/load?source=yande` 直接加载在线数据

### 加载更多
1. 用户滚动到"加载更多"位置
2. 调用 `/api/v1/gallery/load?source=hybrid&last_max_id={current_min_id}`
3. 返回混合数据：`db数据 + 在线补充数据`

### 连续性检测
1. 同步时检测 `max_id` 与数据库中最大 id 的差值
2. 如果差值 > page_size，说明有断档
3. 在 UI 上显示"加载更多"按钮在断档位置

## 数据流

```
[前端请求]
    ↓
[Hybrid Loader]
    ↓
    ├─→ [DB Query] ──→ 返回本地数据
    ↓
[计算断档位置]
    ↓
    ├─→ [API Sync] ──→ 请求 yande.re ──→ 写入DB
    ↓
[返回混合结果 + gap信息]
    ↓
[前端展示 + 调整"加载更多"位置]
```

## 实现步骤

### Phase 1: 数据库变更
1. 创建数据库迁移脚本，添加 `down_flag` 字段（如果不存在）
2. 可选：添加 `last_browse_max_id` 字段

### Phase 2: Repository 变更
1. 在 `YandeDataRepository` 添加 `batch_upsert` 方法
2. 添加 `get_max_id` 方法
3. 添加 `check_continuous` 方法检测断档

### Phase 3: API 端点
1. 实现 `/gallery/browse-state`
2. 实现 `/gallery/sync-online`
3. 实现 `/gallery/batch-upsert`
4. 修改 `/gallery/load` 支持 hybrid 模式

### Phase 4: 前端集成
1. 修改 `GalleryView` 的加载逻辑
2. 实现 hybrid 模式的数据获取
3. 动态调整"加载更多"按钮位置
4. 添加 loading 状态和断档提示

## 文件变更清单

| 文件 | 变更 |
|-----|------|
| `backend/dao/database.py` | 确认 `down_flag` 字段存在 |
| `backend/dao/yande_data.py` | 添加 `batch_upsert`, `get_max_id`, `check_continuous` |
| `backend/api/routers/gallery.py` | 添加新端点，修改 `load` 端点 |
| `frontend/src/views/Gallery.vue` | 实现 hybrid 模式加载逻辑 |

## 注意事项

1. **性能**: 批量写入使用 `session.bulk_save_objects()` 或 `INSERT OR REPLACE`
2. **事务**: 批量操作使用事务保证一致性
3. **缓存**: 考虑缓存 `last_browse_max_id` 减少数据库查询
4. **错误处理**: 在线查询失败时优雅降级到纯本地模式
