# 本地 Tag 匹配：默认精确 + 通配兼容 — 设计文档

**状态**：Draft
**日期**：2026-07-18
**分支**：`feature`
**类型**：行为变更 + 测试补齐

---

## 1. 目标

将 `backend/src/dao/yande_data_dao.py::_tag_filter` 的默认匹配语义从“`LIKE '%tag%'` 子串”改为“完整 tag token 匹配”，同时保留与 yande.re DSL 对齐的前缀 / 中间通配：

| 用户输入 | 匹配语义 | 示例（命中 / 不命中） |
|---|---|---|
| `pan` | 精确 token 匹配 | 命中 `pan`；不命中 `pantus`、`japan_paint` |
| `pan*` | 前缀通配 | 命中 `pan`、`pantus`；不命中 `japan_paint` |
| `p*n` | 中间通配（与 yande.re 一致） | 命中 `pan`、`pantus`、`pein`；不命中 `pa`、`panda` |
| `-pan`、`-pan*`、`-p*n` | 排除语义（按上述规则取 NOT） | 同上规则取反 |
| `*` 或 `-*` | 纯 `*` 单独输入 → 静默忽略 | 不过滤 |

明确**不在范围内**：

- 标签下拉 / 浏览的 `tag_dao.search_tags` / `get_tags_with_stats`（`LIKE '%kw%'`）保留模糊。
- 艺术家 `artist_dao.search_artists`（同 LIKE）保留模糊。
- 在线 yande.re 查询：后端 `search_trans` / `PostRankQueryParams` 把 `tags` 原样转发，yande.re 站点自身对 `pan*` 与 `p*n` 都支持通配，**零改动**。

## 2. 背景与根因

### 现状

- `YandeData.tags` 是 `Text` 列，空格分隔字符串（见 `backend/src/models/database/yande.py:19`）。
- 本地 tag 过滤走 `_tag_filter`（`dao/yande_data_dao.py:55-65`）：
  ```python
  filters.append(YandeData.tags.contains(tag))       # 子串
  filters.append(~YandeData.tags.contains(tag.strip("-")))  # 排除
  return and_(*filters)
  ```
- 用户搜 `pan` → `LIKE '%pan%'`，命中 `pantus`、`pantsu`、`japan_paint` 等所有子串。

### 调用面

唯一过滤函数 `_tag_filter` 被两个调用方共用：

1. `YandeDataRepository.query`（`dao/yande_data_dao.py:96-141`）→ `POST /api/v1/gallery/load` 本地分支。
2. `YandeDataRepository.get_max_id_for_tags`（`dao/yande_data_dao.py:147-156`）→ 收藏夹调度增量模式首次游标兜底（`favorite_scheduler.py:55-58`）。

共用同一函数意味着：本任务改一处即可同时对齐调度增量游标与图库筛选。

### 现有测试约束

- `unit_test/test_max_id_for_tags.py`：用 `_zzz` 后缀避免子串碰撞，不直接断言精确 vs 模糊语义。
- `conftest.py`：autouse fixture 保护 `yande_data` 表；新测试可复用。

## 3. 设计要点

### 3.1 `_tag_filter` 新规则

伪代码：

```python
@staticmethod
def _tag_filter(tags: str):
    parts = [t for t in tags.split() if t.strip()]
    filters = []
    for raw in parts:
        negated = raw.startswith("-")
        token = raw[1:] if negated else raw
        if not token or token == "*":
            continue  # 纯 * 忽略

        if "*" in token:
            cond = or_(
                YandeData.tags.like(token, autoescape=True),
                YandeData.tags.like(f"% {token}", autoescape=True),
            )
        else:
            cond = or_(
                YandeData.tags == token,
                YandeData.tags.like(f"{token} %", autoescape=True),
                YandeData.tags.like(f"% {token}", autoescape=True),
                YandeData.tags.like(f"% {token} %", autoescape=True),
            )

        filters.append(~cond if negated else cond)

    return and_(*filters)
```

要点：

- 默认精确（无 `*`）→ 整 token 比较；空 token / 纯 `*` → 静默跳过。
- 通配（`token` 含 `*`）→ 复用 yande.re 同款语法：`like(token, autoescape=True)` 生成 `LIKE 'p%n' ESCAPE '\'`；`autoescape` 对 `%`、`_`、`\` 字面化，确保 `*` 不会被错误转义而失效。`"% " + token` 处理中间位置。
- 多 token 仍以 `and_(*filters)` 组合，**保持 AND 语义**不变。
- SQLite / MariaDB 共享标准 `LIKE`，无需方言分支；MariaDB collation 与 `*` 不冲突。

### 3.2 兼容性

- 老调用方未传 `*` 即视为精确（语义变更是本任务的核心目标，不做兼容开关）。
- 在线模式零改动：yande.re DSL 默认就是 token 精确 + `*` 通配，用户在前端键入 `pan*` 自然落到请求体，站点解析一致。
- 收藏夹 `tags` 字段为字符串，`_parse_tags_to_params` 已过滤元字段；新规则只在 `_tag_filter` 内识别 `*`，与现有逻辑互不干扰。调度游标与图库筛选自动对齐。

### 3.3 风险与缓解

| 风险 | 缓解 |
|---|---|
| 老收藏夹 `cat` 实际命中 `category`，改精确后少图 | 这是核心目标，不视为风险；文档/PR 描述明确说明 |
| `like(token, autoescape=True)` 与中间通配互斥 | 测试断言覆盖 `p*n` 命中与不命中；若失败切到 `escape='!'` + 自定义拆分 |
| `tags` 列无索引，性能不变 | 现状即全表扫，保持 |
| MariaDB collation 与大小写敏感性 | 当前已不敏感，行为不变；如需严格大小写另立任务 |

### 3.4 不在范围内

- 标签下拉 / 标签浏览模糊搜索：保留 `LIKE '%kw%'`。
- 在线 yande.re 查询：零改动。
- 收藏夹 preview / `_refresh_local_count` 的展示数字：因 `_tag_filter` 同步变化，自动对齐，无需特殊处理。
- 前端 UI：零改动；用户键入 `pan*` 即触发通配。

## 4. 测试计划

### 4.1 新增 `unit_test/dao/test_tag_filter_modes.py`

- 精确：`pan` 命中 `pan`，不命中 `pantus`、`japan_paint`。
- 前缀通配：`pan*` 命中 `pan`、`pantus`，不命中 `japan_paint`。
- 中间通配：`p*n` 命中 `pan`、`pantus`、`pein`，不命中 `pa`、`panda`。
- 排除：`pantus` 排除后保留 `panties`（精确 token 边界）。
- 混合：`pan ~foo` AND 组合正确。
- 纯 `*` 与 `-*` 不抛错、不过滤。
- 转义：用户输入 `pan%_x` → 字面匹配（`autoescape=True` 验证）。

### 4.2 现有测试调整

`unit_test/test_max_id_for_tags.py` 种子改为 `_zzz_exact` 等避免与新精确语义冲突；`_cleanup_tag` 仍用 `contains()` 是合理的（清理阶段不要求精确）。

### 4.3 conftest

无需扩展。

## 5. 文档更新

- `backend/src/dao/yande_data_dao.py::_tag_filter` docstring 改写为新规则。
- `AGENTS.md` “快速参考”与 `docs/design.md`（如涉及）补充一句：本地 tag 默认精确，`*` 通配与 yande.re 一致。
- `README.md` “本地模式 tag 强制 AND” 章节不变（语义未变）。

## 6. 影响面

| 文件 | 变更类型 |
|---|---|
| `backend/src/dao/yande_data_dao.py` | `_tag_filter` 重写 + docstring |
| `backend/src/dao/yande_data_dao.py` | `YandeDataQueryParams.tags` Field 描述补 `*` 通配说明 |
| `unit_test/dao/test_tag_filter_modes.py` | 新文件 |
| `unit_test/test_max_id_for_tags.py` | 种子字符串改 `_zzz_exact` |
| `AGENTS.md` | 文档补充 |
| `README.md` | 可选补充 |