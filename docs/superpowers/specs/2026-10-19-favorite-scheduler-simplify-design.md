# 收藏夹调度简化与游标修复 — 设计文档

## 文档信息

- **项目名称**: yande.re-spider-next
- **功能名称**: 收藏夹定时调度（游标语义统一 + 冗余旋钮下线）
- **版本**: v1.0
- **创建日期**: 2026-10-19
- **状态**: 待审阅
- **关联**: `2026-06-05-favorite-folder-scheduled-tasks-design.md`（原始设计）、`2026-07-19-favorite-run-now-and-search-design.md`（手动触发与 `last_synced_id` 引入）

---

## 1. 背景

### 1.1 现状缺陷

收藏夹调度在 `75f454b`（引入持久化游标）与 `f8f67ef`（移除 `max_pages_per_run`）两次改动后累积了三个缺陷。

**缺陷 1（P0）：增量游标写反方向 → 调度永久卡死**

`post.json` 按 `id` **倒序**返回（该行为**未在 API 文档中说明**）。抓取循环从 page 1（最新）向旧遍历，遇到 `item.id <= last_id` 即停止 —— 在倒序流中，这个"续跑断点"实际是本次处理到的**最小 id**。但落库写的是 `processed_max_id`（本次处理到的**最大 id**）。

后果：第一次跑完游标 = 最新 id；第二次跑 page 1 第一条即命中 `id <= 游标` → 立刻 break → `processed_max_id` 为 None → 游标不写 → 此后每轮 `new_images=0`，游标永远不变，中间被跳过的 id 区间成为**永久空洞**。只要发生过一次被 `max_images` 截断的 run，收藏夹即进入该状态。

**缺陷 2（P0）：`max` 模式未实现**

```python
last_id = folder.last_synced_id            # 无条件采用
if last_id is None and folder.schedule_mode == "last_id":
    last_id = await asyncio.to_thread(_get_max_id_for_tags, raw_tags)
```

`last_id` 无条件取 `folder.last_synced_id`，因此 `max` 模式在游标非空后退化为 `last_id` 模式。两种模式的唯一差异是"首次运行时跳过 `get_max_id_for_tags` 兜底"，且首次运行写回游标后同样卡死。

**缺陷 3（P1）：无界翻页空转**

`f8f67ef` 删除 `max_pages_per_run` 后，循环唯一条件为 `while enqueued_count < max_images`。而 `enqueued_count` **仅在新图入队时递增**，已存在的图一律跳过 —— 当收藏夹没有新图时该条件永不触发，循环一路翻到 API 返回空页。`catgirl` 这类万级 tag = 数百页 × 每页 `sleep(10)`，单轮空转可达数小时，并长期占用 `max_concurrent_schedules` 的并发槽。

### 1.2 附带发现

| 编号 | 位置 | 问题 |
|---|---|---|
| A | `favorite_scheduler.py:114-117` | API 报错用 `raise`（原设计为 `break`）→ 整轮判 failed，前 N-1 页进度不落库 |
| B | `download.py:24-43` | `create_task` 无去重 → 重复调度产生重复下载任务 |
| C | `favorite_scheduler.py:98-99` | `tags_for_api` 经 `_parse_tags_to_params` 剥掉 `rating:`/`ext:`/`width:>=`/`-排除` → 打 yande.re 时过滤条件全部丢失 |
| D | `favorite_scheduler.py:75` | `stats["skipped"]` 初始化后从不累加，而响应契约声明其为"跳过入队的图数" |
| E | `favorite_scheduler.py:147-153` | `pages_fetched = page` 记的是"下页页码"；`sleep(10)` 无条件执行 |
| F | `settings.py:66` | `per_page_limit` 标注"API 上限 1000"，但 API 文档明确 `hard limit of 100 posts per request` |
| G | `yande_api.py:150-156` | `search_trans` 拼出 `order:id_asc` 等无效 order token，在线浏览的「ID 升序」静默失效（详见 §5.3.2） |
| H | `models/response/yande.py:33,42,45` | `status="deleted"`（dupe）条目**缺失 `file_url` / `sample_url` / `jpeg_url`**，而模型将三者声明为必填 `str` → 整页 `model_validate_json` 抛 `ValidationError`。**详见 §5.6，本设计下为阻塞项** |

---

## 2. 目标

1. 修正增量游标语义，使每次调度均有进展，且不产生空洞
2. 下线 `schedule_mode` 与 `schedule_max_images` 两组冗余旋钮
3. 恢复一个**唯一且可预测**的抓取上界，堵住无界翻页
4. 统一 tags 口径，使 API 侧与本地侧一致
5. 失败不丢弃已完成进度，入队去重

## 3. 非目标

- 不做调度历史统计、多月趋势
- 不做分布式调度
- 不引入 `max_pages_per_run` 的 UI 入口（本期仅 YAML 可调）
- 不修复 `settings.load_config` 校验失败覆盖用户配置的问题（另立单子）
- 不做 `schedule_mode` / `schedule_max_images` 列的物理删除

---

## 4. 决策汇总

| 维度 | 决策 |
|---|---|
| 调度模式 | **取消**。不再区分增量 / 全量，只保留一个游标 |
| 游标语义 | `last_synced_id IS NULL` = 无起点 = **下次全量重扫（从最早开始）**；非空 = 增量起点 |
| 全量入口 | 用户点击「清除游标」（置 NULL），下次调度从最早开始重扫 |
| tags 变更 | `update_folder` 检测到 tags 变更即置游标 NULL（换了一批候选图，旧游标必然失效） |
| 查询排序 | 显式追加 `order:id`（**升序**，无后缀），钉死未文档化的默认排序 |
| 游标裁剪 | 增量时追加 `id:>{cursor}`，下推服务端 |
| 抓取上界 | 唯一的 `max_pages_per_run`（默认 10，每页 100 → 单轮最多扫描 1000 张） |
| 每页条数 | 硬编码常量 100（API 硬上限，无第二个正确取值） |
| 翻页间隔 | 硬编码常量 10 秒（防限流） |
| 并发数 | 硬编码常量 2（防限流） |
| per-folder 上限 | **删除**（`schedule_max_images` + `max_images_per_run_default`） |
| feature flag | **不加**。回退路径游标语义为 min、与主路径相反，同列存两种语义必然出乱子 |

### 4.1 为什么删除 `schedule_max_images`

它保护不了最需要保护的场景。`max_images` 只数**入队数**，不数**扫描数**：

| 终止条件 | 触发时机 | 覆盖场景 |
|---|---|---|
| `enqueued_count >= max_images` | 仅在新图入队时才可能触发 | 热 tag 一次爆量 |
| API 返回空页 | 结果集走完 | 全量走完 |
| *（无）* | **全部已下载时 `enqueued` 恒为 0** | **无界翻页 —— 不覆盖** |

而 `max_pages_per_run` 用同一量纲（页）覆盖了两种场景：`min(pages×limit, max_images)` 这个算不清的隐式上限消失为 `max_pages × 100` 的唯一显式上限。保留 `max_images` 会让人误以为"有上限就安全"，这比删掉它更危险。

### 4.2 为什么删除 `schedule_mode`

"从最老开始全扫"在 `last_id` 模式下**今天就已存在** —— 只要游标为 NULL 且本地无匹配已下载图，就没有客户端 break，一路爬到空页。因此 `max` 模式并未提供 `last_id` 模式做不到的事，它唯一的"专属能力"就是那条已被证明有害的"忽略游标"分支。删除它等于删除一个恒等分支。

附带收益：全量重扫从"每个 cron tick 都爬一遍全历史"降级为"用户需要时才爬"。

---

## 5. 核心设计

### 5.1 常量与配置

```python
# backend/src/services/favorite_scheduler.py

# yande.re post API 硬上限（见 docs/api.mhtml: "There is a hard limit of 100
# posts per request."）。这是唯一正确取值，调小只会无谓地少拉，故不再做成配置。
PER_PAGE_LIMIT = 100

# 翻页间隔（秒）。防 yande.re 限流的临时措施（原 TODO：后续用请求队列统一限流）。
# 若调度日志中频繁出现 429 / 421，调大此值。
PAGE_INTERVAL_SEC = 10.0

# 同时抓取的收藏夹数。与 PAGE_INTERVAL_SEC 共同决定对站点的请求压力，
# 两者应同步调整（并发 × 1/间隔 = 站点侧看到的 QPS）。
# 若频繁被限流，调小此值。
MAX_CONCURRENT_SCHEDULES = 2
```

```python
# backend/src/common/settings.py
class SchedulerConfig(ConfigModel):
    max_pages_per_run: int = Field(
        10, ge=1, le=200,
        description="单收藏夹单次最多翻页数。每页固定 PER_PAGE_LIMIT=100 条，"
                    "故单轮最多扫描 max_pages_per_run * 100 张。"
                    "本期不提供 UI 入口，需调整时直接改 config.yaml 的 scheduler 段；"
                    "新建大 tag 收藏夹追平存量时可临时调大（如 200）。",
    )
```

删除字段：`max_concurrent_schedules`、`max_images_per_run_default`、`per_page_limit`。

**兼容性**：`settings.py` 中无任何 `extra='forbid'`（仅嵌套 `Headers` 使用 `extra='allow'`），Pydantic v2 默认 `ignore`，故用户 YAML 中遗留的三个旧键会被静默忽略，**不会触发 `load_config` 校验失败后覆盖 config.yaml 的地雷**。

### 5.2 游标语义

| `last_synced_id` | 查询串 | 起点 | 语义 |
|---|---|---|---|
| `NULL` | `{tags} order:id` | 最早的匹配图 | **全量重扫** |
| `12345` | `{tags} order:id id:>12345` | id > 12345 | 增量 |

游标在三种情况被置 NULL：

1. 用户点击「清除游标」（`POST /{id}/schedule/reset-sync`，`value` 省略或 null）
2. 收藏夹 tags 被修改（`update_folder` 检测 `"tags" in update_data`）
3. 新建收藏夹（初始即为 NULL）

**存量数据无需迁移**：旧实现写入的是"本次处理到的最大 id"，在升序语义下恰好就是正确的续跑点。

### 5.3 查询构造

```python
_ORDER_META_RE = re.compile(r"^order:")
_ID_META_RE = re.compile(r"^id:")


def _build_schedule_tags(raw_tags: str, cursor: Optional[int]) -> str:
    """构造调度专用的 yande.re 查询串。

    1. 剥离用户自带的 order:* / id:* meta-tag —— 用户在收藏夹 tags 里写
       `order:id_desc` 或 `id:<=500` 会直接抵消掉增量裁剪与升序
    2. 其余 meta-tag（rating:/ext:/width:>= 等）原样保留 —— 修复"只发裸 tag、
       rating 过滤全丢"的问题（缺陷 C）
    3. 固定追加 order:id —— 钉死未文档化的默认排序。**注意用 `order:id` 而非
       `order:id_asc`**：yande.re 的 order meta-tag 后缀规则不统一，
       `id` 升序为无后缀形式（降序才是 `order:id_desc`），而 `score` / `mpixels`
       等字段恰恰相反（`order:score_asc` 才升序）。详见 §5.3.1
    4. 追加 id:>{cursor} —— 游标裁剪下推服务端；cursor 为 None 即全量

    Args:
        raw_tags: 收藏夹原始 tags 字符串
        cursor: 当前游标；None 表示无起点（全量）

    Returns:
        拼接好的查询串
    """
    parts = [
        t for t in (raw_tags or "").split()
        if t and not _ORDER_META_RE.match(t) and not _ID_META_RE.match(t)
    ]
    parts.append("order:id")
    if cursor is not None:
        parts.append(f"id:>{cursor}")
    return " ".join(parts)
```

#### 5.3.1 `order:` meta-tag 的后缀规则不统一

yande.re 沿用 Danbooru 系的 `order:` 语法，但**各字段的后缀规则不一致**，这是本设计最容易踩的坑：

| 目标 | 正确写法 | 反例（无效） |
|---|---|---|
| id **升序** | `order:id`（无后缀） | ~~`order:id_asc`~~ |
| id 降序 | `order:id_desc` | —— |
| score 升序 | `order:score_asc` | ~~`order:score`~~ |
| score 降序 | `order:score`（无后缀） | —— |
| mpixels | `order:mpixels` / `order:mpixels_asc` | —— |

该清单来自本仓库自身的 `models/request/yande.py:32-33` 与 `models/request/gallery.py:43` 的注释，并已实测确认：

```
GET /post.json?limit=10&tags=id:%3E12345%20order:id        → 生效
GET /post.json?limit=10&tags=id:%3E12345%20order:id_asc    → 无效
```

**方向已实测确认（2026-10-19）**：上述第一条返回的 `id` 序列为
`12346, 12347, 12348, 12349, 12350, 12351, 12352, 12353, 12354, 12355` ——
**单调递增**且全部 > 12345。即 `order:id` 确为升序、`id:>` 裁剪确实生效，
游标-as-max 的语义成立。

> 附带观察：该响应中 id 12346 / 12349 / 12351 的 `status` 为 `"deleted"`
> （dupe），且**缺失 `file_url` / `sample_url` / `jpeg_url`** —— 见缺陷 H。

#### 5.3.2 顺带发现的既有缺陷：`search_trans` 会拼出无效的 `order:id_asc`

`infrastructure/yande_api.py:150-156` 用 `f"order:{sort_by}_{order}"` 拼接，因此：

| `sort_by` | `sort_order` | 实际拼接 | 有效性 |
|---|---|---|---|
| `id` | `desc`（默认值） | `order:id_desc` | ✅ |
| `id` | `asc` | `order:id_asc` | ❌ **无效** |
| `score` | `asc` | `order:score_asc` | ✅ |

后果：**在线浏览模式下「按 ID 升序」静默失效**（`AdvancedQuery.vue` 的 `sort_by:` / `sort_order:` token 可触达该组合，见 `AdvancedQuery.vue:867-870`）。默认路径是 `desc`，所以平时无感。

该缺陷与本次调度改造**不在同一 PR**（前者是在线浏览路径），但 `search_trans` 恰好是调度查询串的翻译参照，建议紧随其后单独修复：按 §5.3.1 的对照表显式映射，而非字符串拼接。

不再调用 `FavoritesService._parse_tags_to_params` —— 该方法服务于**本地** SQL 过滤（`_tag_filter` 把 `rating:s` 当字面 tag 匹配），语义与远端 DSL 不一致。

### 5.4 抓取循环

```python
async def run_folder_schedule(folder_id: int) -> dict:
    async with _schedule_semaphore:
        folder, status = await asyncio.to_thread(_load_folder_for_schedule, folder_id)
        if not folder:
            logger.warning(f"Folder {folder_id} not found, skip")
            return {"skipped": True, "reason": "not_found"}

        stats = {
            "new_images": 0, "enqueued": 0, "skipped": 0,
            "pages_fetched": 0, "duration_sec": 0.0, "errors": [],
        }
        start = time.monotonic()

        try:
            raw_tags = (folder.tags or "").strip()
            if not raw_tags:
                raise ValueError("folder has no tags configured")

            cursor: Optional[int] = folder.last_synced_id   # NULL 即全量
            max_pages = config.scheduler.max_pages_per_run
            tags_for_api = _build_schedule_tags(raw_tags, cursor)

            yande_api = YandeApi()
            active_ids: set[int] = set()      # 已在队列/下载中的 image_id
            processed_max_id: Optional[int] = None
            pages_done = 0
            page = 1
            stop = False

            while pages_done < max_pages:
                try:
                    rank_params = YandeApi.PostRankQueryParams(
                        page=page, limit=PER_PAGE_LIMIT, tags=tags_for_api
                    )
                    page_data = await asyncio.to_thread(yande_api.get_ranking, rank_params)
                    items = page_data.root if page_data else []
                except Exception as api_err:
                    # 保留已完成页的进度：break 而非 raise（缺陷 A）
                    stats["errors"].append(f"page {page} api error: {api_err}")
                    logger.exception(f"Folder {folder_id} page {page} failed")
                    break

                if not items:
                    break

                # 服务端若忽略 id:> 裁剪，自检并告警。
                # 注意升序下该场景是「彻底卡死」而非「重复抓取」：page 1 会是最老的
                # 若干条，first_item <= cursor 使下方防御性 break 立刻触发 → 本轮零进展，
                # 且每轮复现。因此必须显式告警，指引用户清除游标走全量路径兜底。
                if cursor is not None and items[0].id <= cursor:
                    logger.warning(
                        f"Folder {folder_id}: first item #{items[0].id} <= cursor "
                        f"#{cursor}. Server likely ignored the 'id:>' filter or the "
                        f"'order:id' ascending request; this run makes no progress. "
                        f"Clear the cursor (POST /api/v1/favorites/{folder_id}/"
                        f"schedule/reset-sync) to fall back to a full scan."
                    )

                active_ids.update(await asyncio.to_thread(_load_active_image_ids))
                pages_done += 1

                for item in items:
                    # 防御性兜底：正常情况下服务端已按 id:> 裁剪，此处不会触发
                    if cursor is not None and item.id <= cursor:
                        stop = True
                        break

                    stats["new_images"] += 1
                    if processed_max_id is None or item.id > processed_max_id:
                        processed_max_id = item.id

                    try:
                        action = await asyncio.to_thread(_upsert_item, item)
                        if action == "skipped":
                            stats["skipped"] += 1        # 修复缺陷 D
                            continue
                        if item.id in active_ids:        # 修复缺陷 B
                            stats["skipped"] += 1
                            continue
                        active_ids.add(item.id)
                        await DownloadService.create_task(item.id)
                        stats["enqueued"] += 1
                    except Exception as item_err:
                        stats["errors"].append(f"item {item.id} error: {item_err}")
                        logger.exception(f"Folder {folder_id} item {item.id} failed")
                        continue

                if stop:
                    break
                page += 1
                if pages_done < max_pages:
                    await asyncio.sleep(PAGE_INTERVAL_SEC)

            stats["pages_fetched"] = pages_done             # 修复缺陷 E
            stats["duration_sec"] = round(time.monotonic() - start, 2)

            await asyncio.to_thread(
                _mark_schedule_result, folder_id, "success", stats, processed_max_id
            )
            logger.info(
                f"Folder {folder_id} schedule {stats['pages_fetched']} pages: "
                f"new={stats['new_images']} enqueued={stats['enqueued']} "
                f"skipped={stats['skipped']} "
                f"duration={stats['duration_sec']}s cursor={processed_max_id}"
            )
            return stats

        except Exception as e:
            stats["errors"].append(str(e))
            stats["duration_sec"] = round(time.monotonic() - start, 2)
            # 失败同样推进游标：已 upsert 的条目不会重复入队（active_ids 去重保证）
            await asyncio.to_thread(
                _mark_schedule_result, folder_id, "failed", stats, processed_max_id
            )
            logger.exception(f"Folder {folder_id} schedule failed")
            return stats
```

### 5.5 辅助函数

```python
def _upsert_item(item) -> str:
    """Upsert 单条。

    Returns:
        'skipped'  —— 本地已存在且已下载，无需入队
        'enqueued' —— 新图或未下载，需要入队
    """
    with YandeDataRepository() as repo:
        existing = repo.get_by_id(item.id)
        repo.upsert(item)
        return "skipped" if (existing is not None and existing.down_flag) else "enqueued"


def _load_active_image_ids() -> set[int]:
    """已在下载队列中的 image_id（pending/downloading/paused）。

    用于入队去重：_upsert_item 只看 yande_data.down_flag，而刚入队尚未开始下载的
    记录 down_flag 仍为 False，重复调度会重复建任务。
    """
    with DownloadTaskDao() as dao:
        return set(dao.active_states_by_image().keys())


def _mark_schedule_result(
    folder_id: int, status: str, stats: dict, synced_id: Optional[int]
) -> None:
    """写回调度结果。synced_id 为 None（未处理任何一条）时不覆盖游标。"""
    with FavoriteDao() as dao:
        kwargs = {"last_schedule_status": status, "last_schedule_stats": stats}
        if synced_id is not None:
            kwargs["last_synced_id"] = synced_id
        dao.update(folder_id, **kwargs)
```

删除 `_get_max_id_for_tags`，并连带删除 `YandeDataRepository.get_max_id_for_tags`（唯一调用方已移除）。

### 5.6 已删除 / dupe 图片的处理（阻塞项）

#### 现象

`status="deleted"` 的条目（dupe / 已删除）**缺失三个 URL 字段**。实测返回中 id 12346 / 12349 / 12351 即为此类，其 `preview_url` 指向通用占位图 `deleted-preview-*.png`，且完全没有 `file_url` / `sample_url` / `jpeg_url`。

而 `models/response/yande.py:33,42,45` 将三者声明为**必填 `str`**（无 `Optional`、无默认值）：

```python
file_url: str      # ← deleted 条目中不存在
...
sample_url: str    # ← 同上
...
jpeg_url: str      # ← 同上
```

用实测 payload 直接验证：

```
ValidationError:
  - 0.file_url  -> Field required
  - 0.sample_url -> Field required
  - 0.jpeg_url -> Field required
```

因此 `YandeApi.get_ranking` → `YandePostData.model_validate_json` 对**任何包含 deleted 条目的页面**整体抛错。

#### 为什么本设计把它变成阻塞项

这是一个既有缺陷（在线浏览路径同样受影响），但**本设计大幅放大了它的触发概率**：

| | 遍历方向 | 起点区域 | deleted 密度 |
|---|---|---|---|
| 修复前 | 倒序（默认） | 最新 | 低（新图极少被删） |
| 修复后 | `order:id` 升序 | **最老** | **高**（老图 dupe/删除比例远高） |

「清除游标」触发的全量重扫正是从最老开始 —— page 1 命中 deleted 的概率很高，届时 `get_ranking` 抛 `ValidationError`，本轮立即判 failed，功能等于不可用。

#### 修复

**(1) 模型层** —— 三个字段改为可选：

```python
file_url: Optional[str] = None    # status=deleted 的条目不返回该字段
sample_url: Optional[str] = None
jpeg_url: Optional[str] = None
```

**(2) 调度层** —— 跳过不可下载的条目，且**不写入本地库**（deleted 条目写入 `yande_data` 会污染图库）：

```python
def _is_downloadable(item) -> bool:
    """deleted / dupe 条目无 file_url，既不能下载也不应落库。"""
    return item.status == "active" and bool(item.file_url)
```

循环内在 `stats["new_images"] += 1` 之前调用，返回 False 时计入 `stats["skipped"]` 并 `continue`。
**游标仍需推进**（`processed_max_id` 在跳过前更新），否则全量重扫会卡在第一条 deleted 上。

**(3) 在线浏览路径** —— 仅需 (1)，让整页不至于解析失败；是否展示 deleted 条目属产品决策，不在本设计范围。

---

## 6. 数据模型

**不新增列，不删除列。**

| 列 | 处置 |
|---|---|
| `schedule_mode` | **保留**（SQLite 无 alembic，drop 成本高），代码不再读取。存量 `'max'` 的收藏夹自动按增量运行 |
| `schedule_max_images` | **保留**，代码不再读取 |
| `last_synced_id` | 保留，更新列注释 |

`models/database/yande.py:132-135` 注释改为：

> 上次调度实际同步到的最大图片 ID；NULL = 无起点，下次调度从最早开始全量重扫。与 down_flag 解耦，避免被其他接口干扰。

`models/response/favorites.py:38` 的 Field description 同步更新。

---

## 7. API 设计

**全部向后兼容，无接口新增。**

| 变更 | 说明 |
|---|---|
| `FavoriteFolder.schedule_mode` | 保留，description 标注 `deprecated` |
| `FavoriteFolder.schedule_max_images` | 保留，description 标注 `deprecated` |
| `FavoriteFolderCreate/Update` | 两字段的 Field 与 validator 保留（存量前端继续传不 422），DAO 侧忽略不落库 |
| `POST /{id}/schedule/reset-sync` | 不变。`value` 省略或 null 即置 NULL（= 触发下次全量重扫） |

`reset-sync` 的 `value` 参数保留但不再需要在 UI 区分 null / 0 —— 前端继续传 `null` 即可。

---

## 8. 前端设计

### 8.1 `FavoritePanel.vue` 编辑面板

**删除**：

| 行 | 内容 |
|---|---|
| 202-207 | 「模式」`el-radio-group`（增量 / 最大） |
| 208-217 | 「单次上限」`el-input-number` |
| 351-352 | `form` 初始值中的两个字段 |
| 565-566 | 表单重置时的赋值 |
| 585-586 | 填充编辑值时的赋值 |
| 631-632 | 提交载荷中的两个字段 |

**修改**游标行的 popconfirm 文案（`:229`）：

```
原：重置同步游标？下次调度将从头开始（增量模式回退到当前已下载位置，全量模式直接全量）。
新：清除同步游标？下次调度将从最早的图片开始重扫全历史，用于补齐历史遗漏
    （如后来才补上本收藏夹标签的图片）。若只是想重新对齐，可先停用再启用调度。
```

游标行的展示值 `上次同步至 #N` 在新语义下**保持不变**（升序下 max 正是续跑点）。

### 8.2 `AdvancedQuery.vue`

**无改动**。`handleResetFolderSync(folder)` 继续 `resetFolderSync(folder.id, null)`。

### 8.3 `Config.vue`

**无改动**。`max_pages_per_run` 本期不提供 UI 入口，仅在 `settings.py` 的 Field description 中写明调整方式。

---

## 9. 错误处理

| 场景 | 处理 |
|---|---|
| 某页 API 报错/超时 | 记入 `errors[]`，`break` 结束本轮，**已处理页的游标照常落库**，status=failed |
| 某条 upsert / 建任务失败 | 记入 `errors[]`，`continue` 处理下一条 |
| 服务端忽略 `id:>` 裁剪 | 检测到 `items[0].id <= cursor` 时打 warning。升序下该场景意味着**本轮零进展且每轮复现**，warning 中指引用户清除游标走全量兜底（§5.4） |
| 条目 `status="deleted"` 或无 `file_url` | 跳过、不落库、计入 `stats["skipped"]`，**游标照常推进**（§5.6） |
| tags 为空 | 抛 `ValueError` → status=failed |
| folder 不存在 | 返回 `{"skipped": True, "reason": "not_found"}` |

---

## 10. 测试

### 10.1 删除

| 用例 | 原因 |
|---|---|
| `test_run_folder_schedule_max_images_limit` | `schedule_max_images` 已下线 |
| `test_run_folder_schedule_first_run_max_mode_skips_fallback` | 模式已下线 |
| `test_run_folder_schedule_first_run_last_id_mode_falls_back_to_max` | 兜底已删除 |

### 10.2 修改

| 用例 | 修改点 |
|---|---|
| `test_run_folder_schedule_last_id_stops` | mock 数据改升序 |
| `test_run_folder_schedule_persists_last_synced_id` | mock 数据改升序 |
| `test_run_folder_schedule_uses_existing_last_synced_id` | mock 数据改升序 |
| `test_run_folder_schedule_max_images_break_advances_last_synced_id` | 改写为「页数上限触发时游标推进」 |
| `test_run_folder_schedule_failure_does_not_advance_last_synced_id` | **反转**为「失败仍推进已处理页的游标」 |
| `test_concurrent_folder_limit` | 断言常量 `MAX_CONCURRENT_SCHEDULES` |
| `test_per_page_limit_used_from_config` | 断言常量 `PER_PAGE_LIMIT == 100` |

> 注：原测试的 mock 为 `[item_5002, item_5001]`（倒序）。新实现依赖**升序**语义，
> fixture 必须改为 `[item_5001, item_5002]`，否则断言的是被修复前的错误行为。

### 10.3 新增

| 用例 | 验证点 |
|---|---|
| `test_incremental_advances_across_consecutive_runs` | 增量模式连续两次运行第二次能继续推进（锁 P0-1） |
| `test_second_run_sends_id_gt_cursor_and_asc` | 第二次运行查询串含 `id:>{cursor}` 与 `order:id`（**不是** `order:id_asc`） |
| `test_null_cursor_sends_no_id_filter` | cursor=NULL 时查询串不含 `id:` |
| `test_user_order_and_id_meta_are_stripped` | tags 含 `order:id_desc` / `id:<=500` 时被剥离 |
| `test_no_duplicate_enqueue_for_active_task` | 已有活跃任务不重复建任务（锁缺陷 B） |
| `test_api_error_mid_run_still_advances_cursor` | 第 N 页报错 → failed 且游标推进到已完成页（锁缺陷 A） |
| `test_max_pages_run_bounds_crawl` | 页数上限触发时循环停止 |
| `test_skipped_stat_is_accumulated` | `stats["skipped"]` 真累加（锁缺陷 D） |
| `test_pages_fetched_counts_actual_pages` | `pages_fetched` 等于实际抓取页数（锁缺陷 E） |
| `test_tags_change_clears_cursor` | `update_folder` 改 tags 后游标置 NULL |
| `test_deleted_posts_do_not_break_parsing` | 含 `status="deleted"` 且缺 `file_url` 的条目，模型可正常解析（锁缺陷 H-1） |
| `test_deleted_posts_skipped_and_cursor_advances` | deleted 条目不落库、不入队、计入 skipped，且游标仍推进（锁缺陷 H-2） |

---

## 11. 风险与权衡

| 风险 | 应对 |
|---|---|
| ~~`order:id` / `id:>N` 的升序方向未验证~~ | **已实测确认（2026-10-19）**：返回 id 12346→12355 单调递增且全部 > 12345。设计前提成立，风险解除 |
| **`deleted` 条目使整页解析失败 —— 本设计下的阻塞项** | 升序改造把遍历起点从「最新」移到「最老」，而老图 dupe/删除比例最高，「清除游标」触发的全量重扫大概率在 page 1 命中。必须先做 §5.6 的模型层 + 调度层修复 |
| 服务端静默忽略未知 meta-tag | 循环内自检 + warning（见 §9） |
| 新建大 tag 收藏夹时从最早开始爬，单轮只推进 1000 张 | 这是"删除 per-folder 上限"的既定代价。追存量期间可临时调大 `max_pages_per_run`（description 已写明）。中止手段是停用调度开关——游标已落库，不会丢失进度，下次启用从游标继续 |
| 单轮入队上限从 800 提升至 1000 | `download_queue` 为无界 `asyncio.Queue()`，worker 3 个 + `Semaphore(3)` 限流，不会产生并发风暴 |
| 存量被旧 bug 写坏的"洞"在游标之下，增量补不回来 | 用户点一次「清除游标」即从最早重扫，洞被自动填平。无需数据修复 |
| 删除配置字段导致用户 YAML 校验失败 | 已验证无 `extra='forbid'`，旧键被静默忽略（见 §5.1） |
| `max_pages_per_run` 无 UI 入口 | 本期有意取舍；description 已写明调整方式 |

---

## 12. 变更清单

| 文件 | 操作 |
|---|---|
| `backend/src/services/favorite_scheduler.py` | 重写核心循环；新增 3 常量 + 2 正则 + 3 助手；删除 `_get_max_id_for_tags` 与 mode 分支 |
| `backend/src/common/settings.py` | `SchedulerConfig` 瘦身为 1 字段 |
| `backend/src/infrastructure/scheduler.py` | `register_folder` 删 `mode` / `max_images` 形参与校验 |
| `backend/src/lifecycle/scheduler.py` | `reload_from_db` dict 精简为 `{id, schedule_cron}` |
| `backend/src/dao/favorite_dao.py` | `create()` 删两个形参 |
| `backend/src/services/favorites.py` | `_sync_schedule` 简化；`create_folder` 透传删两项；`update_folder` 增 tags 变更联动 |
| `backend/src/dao/yande_data_dao.py` | 删 `get_max_id_for_tags` |
| `backend/src/models/response/yande.py` | `file_url` / `sample_url` / `jpeg_url` 改 `Optional[str] = None`（§5.6 阻塞修复） |
| `backend/src/models/response/favorites.py` | 两字段 description 标 deprecated；`last_synced_id` description 更新 |
| `backend/src/models/database/yande.py` | `last_synced_id` 列注释更新 |
| `frontend/src/components/FavoritePanel.vue` | 删「模式」+「单次上限」；游标文案改写 |
| `unit_test/test_favorite_scheduler.py` | 删 3 条、改 7 条、新增 12 条 |

### PR 拆分

| PR | 内容 |
|---|---|
| **PR1** | 后端核心 + §5.6 deleted 条目修复（去重为"失败也推进游标"的正确性前置；三者必须同批） |
| **PR2** | 前端删项 + 文案 + deprecate 清理 |
| **PR3**（独立） | `search_trans` 的 `order:` 后缀映射修复（在线浏览路径，见 §5.3.2） |
| **PR4**（独立） | `settings.load_config` 校验失败覆盖用户 config.yaml 的地雷 |

---

## 13. 验收清单

- [ ] 增量模式连续两次调度，第二次 `enqueued > 0` 或明确返回"无新图"且游标保持一致
- [ ] 游标列注释 / 响应 description / 前端文案三处口径一致
- [ ] `max` 模式存量收藏夹按增量正常运行
- [ ] 清除游标后下次调度从最早开始重扫
- [ ] 修改 tags 后游标被置 NULL
- [ ] tags 含 `rating:s` 时打 yande.re 的查询串仍含 `rating:s`
- [ ] 单轮翻页数不超过 `max_pages_per_run`
- [ ] 同一 image_id 不产生重复下载任务
- [ ] 某页 API 报错后 status=failed 且已完成页的游标已落库
- [ ] 全部 `schedule_max_images` / `schedule_mode` 业务引用已清除
- [x] `order:id` + `id:>` 已对真实 yande.re 实测通过，返回 id 单调递增且全部大于游标（2026-10-19）
- [ ] 含 deleted / dupe 条目的页能正常解析，不抛 `ValidationError`
- [ ] deleted 条目不写入本地库、不入队，且不阻断游标推进
- [ ] 在线浏览遇到 deleted 条目的页面不再整页失败
