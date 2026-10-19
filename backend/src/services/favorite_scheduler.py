"""收藏夹定时调度。

设计依据：``docs/superpowers/specs/2026-10-19-favorite-scheduler-simplify-design.md``

核心约定：
- 查询串显式追加 ``order:id``（**升序，无后缀**）钉死 yande.re 未文档化的默认排序
  （post.json 默认按 id **倒序**），增量时再追加 ``id:>{cursor}`` 把游标裁剪下推服务端。
- 游标语义统一：``last_synced_id IS NULL`` = 无起点 = **下次从最早开始全量重扫**；
  非空 = 增量起点。落库的游标恒为「本次处理到的最大 id」——升序下它恰好就是续跑点。
- 唯一的抓取上界是 ``config.scheduler.max_pages_per_run``（页），单页条数固定 100。
"""
from __future__ import annotations

import asyncio
import re
import time
from datetime import datetime
from typing import Any, Optional

from loguru import logger

from src.common import config
from src.dao.download_task_dao import DownloadTaskDao
from src.dao.favorite_dao import FavoriteDao
from src.dao.yande_data_dao import YandeDataRepository
from src.infrastructure.yande_api import YandeApi
from src.services.download import DownloadService

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

# 查询串构造：剥离用户自带的 order:* / id:* meta-tag
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


def _is_downloadable(item) -> bool:
    """deleted / dupe 条目无 file_url，既不能下载也不应落库。"""
    return item.status == "active" and bool(item.file_url)


def _load_folder_for_schedule(folder_id: int) -> tuple[Optional[Any], str]:
    """Load folder and mark as running. Returns (folder_dict_or_None, status)."""
    with FavoriteDao() as dao:
        folder = dao.get_by_id(folder_id)
        if not folder:
            return None, "not_found"
        dao.update(
            folder_id,
            last_schedule_status="running",
            last_scheduled_at=datetime.now(),
        )
        return folder, "ok"


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


_schedule_semaphore = asyncio.Semaphore(MAX_CONCURRENT_SCHEDULES)


async def run_folder_schedule(folder_id: int) -> dict:
    async with _schedule_semaphore:
        folder, status = await asyncio.to_thread(_load_folder_for_schedule, folder_id)
        if not folder:
            logger.warning(f"Folder {folder_id} not found, skip")
            return {"skipped": True, "reason": "not_found"}

        stats = {
            "new_images": 0,
            "enqueued": 0,
            "skipped": 0,
            "pages_fetched": 0,
            "duration_sec": 0.0,
            "errors": [],
        }
        start = time.monotonic()
        # 提到 try 之前初始化：except 分支要拿它落库游标，
        # 若放在 try 内且在其之前抛异常（如 tags 为空），会 UnboundLocalError。
        processed_max_id: Optional[int] = None

        try:
            raw_tags = (folder.tags or "").strip()
            if not raw_tags:
                raise ValueError("folder has no tags configured")

            cursor: Optional[int] = folder.last_synced_id   # NULL 即全量
            max_pages = config.scheduler.max_pages_per_run
            tags_for_api = _build_schedule_tags(raw_tags, cursor)

            yande_api = YandeApi()
            active_ids: set[int] = set()      # 已在队列/下载中的 image_id
            pages_done = 0
            page = 1
            stop = False
            api_failed = False

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
                    api_failed = True
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

                    # 游标先推进：deleted 条目不落库不入队，但必须让游标跨过它，
                    # 否则全量重扫会永远卡在第一条 deleted 上（§5.6）
                    if processed_max_id is None or item.id > processed_max_id:
                        processed_max_id = item.id

                    if not _is_downloadable(item):
                        stats["skipped"] += 1
                        continue

                    stats["new_images"] += 1

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

            # 设计文档 §5.4 示例在页级报错 break 后落到 "success"，
            # 但 §9 错误处理表与新增用例 test_api_error_mid_run_still_advances_cursor
            # 都要求 status=failed 且已完成页的游标照常落库 —— 此处以 §9 + 用例为准。
            status = "failed" if api_failed else "success"
            await asyncio.to_thread(
                _mark_schedule_result, folder_id, status, stats, processed_max_id
            )
            logger.info(
                f"Folder {folder_id} schedule {status}: "
                f"{stats['pages_fetched']} pages: "
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
