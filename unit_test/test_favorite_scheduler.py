"""收藏夹定时调度测试。

设计文档：``docs/superpowers/specs/2026-10-19-favorite-scheduler-simplify-design.md``
§10 测试（10.1 删除 3 条 / 10.2 修改 7 条 / 10.3 新增 12 条）。

本文件锁死的核心不变量（回归即红）：

* **P0-1 游标方向**：查询串固定 ``order:id``（升序，无后缀）+ ``id:>{cursor}``，
  落库游标恒为「本次处理到的最大 id」，且它恰好就是下轮的续跑点。
  ⇒ 任何把「最大 id」当起点、或把遍历方向改回倒序的改动都会让
  ``test_incremental_advances_across_consecutive_runs`` / ``*_persists_last_synced_id`` 失败。
* **P0-2 旋钮下线** ``schedule_mode`` / ``schedule_max_images``：
  ``FavoriteDao.create()`` 不再暴露这两个形参，``register_folder`` 只剩 ``(folder_id, cron)``。
* **P1 无界翻页**：唯一上界是 ``config.scheduler.max_pages_per_run``。
* 缺陷 A（页级报错丢进度）/ B（``create_task`` 无去重）/ D（``skipped`` 不累加）/
  E（``pages_fetched`` 记错页码）/ H（deleted 条目缺 URL 致整页 ValidationError）。

⚠️ 数据安全：本文件跑在真实生产库上，由 ``unit_test/conftest.py`` 的
「整文件备份 → 测试 → 还原」fixture 保护。本文件额外在自身 fixture 里
做双保险清理（删收藏夹 + 按 tag 清 yande_data），且不复用固定 id。
"""
import asyncio
from contextlib import contextmanager
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from src.common.settings import Config
from src.dao.database import _get_session_factory
from src.dao.favorite_dao import FavoriteDao
from src.dao.yande_data_dao import YandeDataRepository
from src.infrastructure.yande_api import YandeApi
from src.models.database.yande import YandeData
from src.models.request.favorites import FavoriteFolderUpdate
from src.models.response.yande import YandePostData
from src.middleware.session import _request_session
from src.services import favorite_scheduler
from src.services.favorite_scheduler import run_folder_schedule
from src.services.favorites import FavoritesService

# 测试专用 tag：生产 yande_data 里绝不会命中，teardown 按它精确清理
_TAGS = "sched_test_zzz"

_real_post_rank_params_cls = YandeApi.PostRankQueryParams


# --------------------------------------------------------------------------
# autouse fixtures
# --------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _isolate_event_loop():
    import asyncio
    from src.infrastructure.scheduler import schedule_manager

    policy = asyncio.DefaultEventLoopPolicy()
    asyncio.set_event_loop_policy(policy)
    schedule_manager._scheduler = None
    schedule_manager._job_folder_map = {}
    yield
    schedule_manager._scheduler = None
    schedule_manager._job_folder_map = {}
    try:
        loop = asyncio.get_event_loop_policy().get_event_loop()
        if loop and not loop.is_closed():
            loop.close()
    except Exception:
        pass
    asyncio.set_event_loop_policy(None)
    asyncio.set_event_loop(None)


@pytest.fixture(autouse=True)
def _no_page_interval(monkeypatch):
    """把翻页间隔 patch 成 0（硬要求）。

    调度循环在两次翻页之间会 ``await asyncio.sleep(PAGE_INTERVAL_SEC)``，
    而 ``PAGE_INTERVAL_SEC = 10.0``；不 patch 的话本文件要跑几十分钟。
    循环体在**调用时**读模块全局量，故 patch 模块属性即可生效。
    """
    monkeypatch.setattr(favorite_scheduler, "PAGE_INTERVAL_SEC", 0.0)
    assert favorite_scheduler.PAGE_INTERVAL_SEC == 0.0


# ⚠️ 与本次「收藏夹调度简化」改造无关的既有环境问题（不是改造引入的）：
#    ``FavoritesService.update_folder`` 走**单例** ``favorite_dao``，
#    而 ``BaseDAO.session`` 的单例分支会调 ``RequestSessionMiddleware.get_session()``；
#    该方法自 commit 33a2616（2026-06-10 "Pure ASGI + DAO session refetch"）起
#    改为**严格模式**，请求 ContextVar 为 None 直接抛 RuntimeError 而不再静默 new session。
#    service 层本就在请求线程内跑，生产环境该 ContextVar 一定有值；
#    只有「测试里裸调 service 函数」才会踩到，故在这里补上等价于
#    「中间件已经跑过一次」的 session 上下文。不改任何生产代码，也不削弱断言。
@pytest.fixture(autouse=True)
def _active_request_session():
    session = _get_session_factory()()
    token = _request_session.set(session)
    try:
        yield session
    finally:
        _request_session.reset(token)
        session.close()


# --------------------------------------------------------------------------
# 工厂 / 工具
# --------------------------------------------------------------------------
@pytest.fixture
def sched_folder():
    """创建测试收藏夹（id 由 DB 自增，不写死），返回 folder_id。

    teardown 双保险：删收藏夹 + 按 purge_tag 清掉调度 upsert 进去的 yande_data 行。
    """
    created: list[tuple[int, str]] = []

    def _make(name: str, tags: str = _TAGS, purge_tag: str = _TAGS, **kwargs) -> int:
        with FavoriteDao() as dao:
            folder = dao.create(name=name, tags=tags, **kwargs)
            folder_id = folder.id
        created.append((folder_id, purge_tag))
        return folder_id

    yield _make

    for folder_id, purge_tag in created:
        with FavoriteDao() as dao:
            dao.delete(folder_id)
        session = _get_session_factory()()
        try:
            session.query(YandeData).filter(YandeData.tags.contains(purge_tag)).delete()
            session.commit()
        finally:
            session.close()


def _post_payload(image_id: int, *, status: str = "active", tags: str = _TAGS) -> dict:
    """构造一条 yande.re post 的**原始 JSON payload**（缺陷 H 的真实形态）。

    ``status="deleted"`` 时**完全不带** ``file_url`` / ``sample_url`` / ``jpeg_url``
    —— 实测中 deleted（dupe）条目就是这种形态，正是旧模型声明必填 str 时
    导致整页 ``ValidationError`` 的根因。
    """
    ts = datetime(2024, 1, 1)
    payload = {
        "id": image_id,
        "tags": tags,
        "created_at": ts,
        "updated_at": ts,
        "author": "tester",
        "change": 0,
        "source": f"http://yande.re/post/show?id={image_id}",
        "score": 0,
        "md5": f"{image_id:032d}",
        "file_size": 1024,
        "file_ext": "jpg",
        "is_shown_in_index": True,
        "preview_url": f"http://yande.re/preview/{image_id}.jpg",
        "preview_width": 100,
        "preview_height": 100,
        "actual_preview_width": 100,
        "actual_preview_height": 100,
        "sample_width": 100,
        "sample_height": 100,
        "sample_file_size": 512,
        "jpeg_width": 100,
        "jpeg_height": 100,
        "jpeg_file_size": 512,
        "rating": "s",
        "is_rating_locked": False,
        "has_children": False,
        "parent_id": None,
        "status": status,
        "is_pending": False,
        "width": 100,
        "height": 100,
        "is_held": False,
        "frames_pending_string": None,
        "frames_pending": None,
        "frames_string": None,
        "frames": None,
        "is_note_locked": False,
        "last_noted_at": 0,
        "last_commented_at": 0,
    }
    if status == "deleted":
        # deleted 条目的 preview_url 指向通用占位图，且没有三个下载 URL
        payload["preview_url"] = "http://yande.re/deleted-preview-1.png"
    else:
        payload["file_url"] = f"http://yande.re/image/{image_id}.jpg"
        payload["sample_url"] = f"http://yande.re/sample/{image_id}.jpg"
        payload["jpeg_url"] = f"http://yande.re/jpeg/{image_id}.jpg"
    return payload


def _post_item(image_id: int, **kwargs):
    """构造真实 ``YandePostData.YandePostItem``（不是 MagicMock）。

    必须是真实模型对象：调度层的 ``_upsert_item`` 会把它
    ``__dict__`` 直接喂给 ``sqlite_insert(YandeData).values(...)``，
    MagicMock 塞进去是垃圾列名，upsert 会被静默吞掉，断言就变成空转。
    """
    return YandePostData.YandePostItem.model_validate(_post_payload(image_id, **kwargs))


@contextmanager
def _patched_api(pages):
    """patch ``favorite_scheduler.YandeApi``。

    Args:
        pages: 逐页返回值列表。元素为 ``list[item]``（空 list = 该页无结果）
            或 ``Exception``（该页 API 报错）。
            **元素必须按 id 升序** —— 新实现依赖升序语义（见设计文档 §10 注）。

    Yields:
        mock 的 api 实例；用 ``_captured_tags`` / ``get_ranking.call_args_list``
        取实际发出的查询串。
    """
    side_effects = [
        p if isinstance(p, Exception) else MagicMock(root=list(p)) for p in pages
    ]
    with patch("src.services.favorite_scheduler.YandeApi") as mock_cls:
        # 保留真实 PostRankQueryParams，否则拿不到可断言的 .tags / .limit
        mock_cls.PostRankQueryParams = _real_post_rank_params_cls
        api = mock_cls.return_value
        if len(side_effects) == 1 and not isinstance(pages[0], Exception):
            api.get_ranking.return_value = side_effects[0]
        else:
            # 必须用 side_effect 而非 return_value：返回 Exception 对象不等于抛异常
            api.get_ranking.side_effect = side_effects
        yield api


@contextmanager
def _patched_create_task():
    """patch ``DownloadService.create_task``，返回 AsyncMock 便于断言调用序列。"""
    with patch(
        "src.services.favorite_scheduler.DownloadService.create_task",
        new_callable=AsyncMock,
    ) as mock_create:
        yield mock_create


def _config_with_max_pages(max_pages: int) -> Config:
    """复制当前 config，把 scheduler.max_pages_per_run 改成指定值。"""
    data = favorite_scheduler.config.model_dump()
    data["scheduler"]["max_pages_per_run"] = max_pages
    return Config.model_validate(data)


def _captured_tags(api) -> list[str]:
    """按调用顺序取回实际发给 yande.re 的 tags 查询串。"""
    return [c.args[0].tags for c in api.get_ranking.call_args_list]


def _cursor_of(folder_id: int):
    with FavoriteDao() as dao:
        return dao.get_by_id(folder_id).last_synced_id


def _seed_downloaded(image_ids) -> None:
    """预置若干 ``down_flag=True`` 的 yande_data 行（模拟「本地已存在且已下载」）。"""
    session = _get_session_factory()()
    try:
        now = datetime.now()
        for image_id in image_ids:
            session.query(YandeData).filter(YandeData.id == image_id).delete()
            session.add(YandeData(
                id=image_id, down_flag=True, tags=_TAGS,
                created_at=now, updated_at=now, creator_id=0, author="test",
                change=0, source="", score=0, md5=f"{image_id:032d}",
                file_size=0, file_ext="jpg", file_url="",
                is_shown_in_index=False, preview_url="", preview_width=0,
                preview_height=0, actual_preview_width=0, actual_preview_height=0,
                sample_url="", sample_width=0, sample_height=0, sample_file_size=0,
                jpeg_url="", jpeg_width=0, jpeg_height=0, jpeg_file_size=0,
                rating="s", is_rating_locked=False, has_children=False, parent_id=None,
                status="active", is_pending=False, width=0, height=0, is_held=False,
                is_note_locked=False, last_noted_at=0, last_commented_at=0,
            ))
        session.commit()
    finally:
        session.close()


def _local_item(image_id: int):
    with YandeDataRepository() as repo:
        return repo.get_by_id(image_id)


# ==========================================================================
# 保留用例（不在 §10.1 删除清单内）
# ==========================================================================
def test_run_folder_schedule_unenabled_executes_without_skip(sched_folder):
    """未启用 schedule 的 folder 调用 run_folder_schedule 也应执行（不跳过）

    plan 2026-07-19 §3.1 改动 2 的新行为：service 层不再检查 schedule_enabled，
    是否启用 schedule 由调用方（API endpoint 或 _on_folder_trigger 防御性检查）负责。
    """
    folder_id = sched_folder("test_unenabled_executes", tags=_TAGS)

    with _patched_create_task():
        with _patched_api([[]]) as api:
            stats = asyncio.run(run_folder_schedule(folder_id))

    assert stats.get("skipped") is not True, (
        f"未启用 schedule 的 folder 不应被 service 层跳过，但 stats={stats}"
    )
    assert "errors" in stats
    # 首页空 → break，pages_done 从未自增。旧断言是 1，那是缺陷 E 修复前的
    # 「记下页码」行为（把空页也算作抓到了 1 页），必须跟着改成 0。
    assert stats["pages_fetched"] == 0
    assert api.get_ranking.call_count == 1


def test_yande_api_failure_sets_failed_status(sched_folder):
    folder_id = sched_folder("test_api_fail", tags=_TAGS)

    with _patched_create_task():
        with _patched_api([Exception("api boom")]):
            stats = asyncio.run(run_folder_schedule(folder_id))

    assert any("api boom" in e for e in stats.get("errors", []))
    with FavoriteDao() as dao:
        reloaded = dao.get_by_id(folder_id)
    assert reloaded.last_schedule_status == "failed"
    # 一条都没处理成 → 游标保持 NULL（_mark_schedule_result 不覆盖）
    assert reloaded.last_synced_id is None


def test_run_folder_schedule_not_found():
    result = asyncio.run(run_folder_schedule(99999999))
    assert result == {"skipped": True, "reason": "not_found"}


def test_run_folder_schedule_pagination_stops_on_empty(sched_folder):
    folder_id = sched_folder("test_empty", tags=_TAGS)

    with _patched_create_task() as mock_create:
        with _patched_api([[], []]) as api:
            stats = asyncio.run(run_folder_schedule(folder_id))

    assert stats["enqueued"] == 0
    assert mock_create.await_count == 0
    assert api.get_ranking.call_count == 1, "首页空即 break，不该再翻页"
    with FavoriteDao() as dao:
        reloaded = dao.get_by_id(folder_id)
    assert reloaded.last_schedule_status == "success"


def test_reset_last_synced_id_to_none_clears_value(sched_folder):
    folder_id = sched_folder("test_reset_clear", tags=_TAGS)
    with FavoriteDao() as dao:
        dao.update(folder_id, last_synced_id=12345)
        assert dao.get_by_id(folder_id).last_synced_id == 12345

    with FavoriteDao() as dao:
        result = dao.reset_last_synced_id(folder_id, None)
    assert result is not None
    assert result.last_synced_id is None


def test_reset_last_synced_id_to_value(sched_folder):
    folder_id = sched_folder("test_reset_value", tags=_TAGS)
    with FavoriteDao() as dao:
        result = dao.reset_last_synced_id(folder_id, 98765)
    assert result is not None
    assert result.last_synced_id == 98765


# ==========================================================================
# §10.2 修改（7 条）
# ==========================================================================
def test_run_folder_schedule_last_id_stops(sched_folder):
    """升序遍历 + 游标语义：处理到 max 即停，落库游标 = 本轮处理到的最大 id。

    * 场景 A（NULL 游标 = 全量）：升序返回 [3000, 5001, 5002] → 全部处理，游标 5002
    * 场景 B（游标 4000 + 服务端忽略了 id:> 裁剪）：升序返回 [3000, 5001, 5002]
      → 防御性 break 在第一条 <= 游标处立即触发，本轮零进展且游标不被覆盖

    ⚠️ mock 必须**升序**。旧 fixture 的倒序写法断言的是被 P0-1 修复掉的错误行为。
    """
    folder_id = sched_folder("test_last_id_stops", tags=_TAGS)

    # 场景 A：NULL 游标 = 全量重扫
    with _patched_create_task() as mock_create:
        with _patched_api([[_post_item(3000), _post_item(5001), _post_item(5002)], []]):
            stats = asyncio.run(run_folder_schedule(folder_id))

    assert stats["enqueued"] == 3
    assert [c.args[0] for c in mock_create.await_args_list] == [3000, 5001, 5002]
    assert _cursor_of(folder_id) == 5002, "升序下游标必须等于本轮处理到的最大 id"

    # 场景 B：游标非空 + 服务端未按 id:> 裁剪 → 立刻停，游标保持不动
    with FavoriteDao() as dao:
        dao.update(folder_id, last_synced_id=4000)

    with _patched_create_task() as mock_create:
        with _patched_api([[_post_item(3000), _post_item(5001), _post_item(5002)], []]):
            stats = asyncio.run(run_folder_schedule(folder_id))

    assert stats["enqueued"] == 0
    assert mock_create.await_count == 0
    assert stats["errors"] == []
    assert _cursor_of(folder_id) == 4000, "零进展的一轮不得覆盖游标"


def test_run_folder_schedule_persists_last_synced_id(sched_folder):
    """成功运行后，folder.last_synced_id = 本次处理过的最大 item.id（升序 → 续跑点）。"""
    folder_id = sched_folder("test_persists_cursor", tags=_TAGS)

    with _patched_create_task():
        with _patched_api([[_post_item(5001), _post_item(5002)], []]):
            asyncio.run(run_folder_schedule(folder_id))

    with FavoriteDao() as dao:
        reloaded = dao.get_by_id(folder_id)
    assert reloaded.last_synced_id == 5002
    assert reloaded.last_schedule_status == "success"
    assert reloaded.last_schedule_stats["pages_fetched"] == 1


def test_run_folder_schedule_uses_existing_last_synced_id(sched_folder):
    """已有 last_synced_id 时直接拿它当增量起点。

    旧实现会先调 ``get_max_id_for_tags`` 回退，那个方法随本次改造一起删除
    （唯一调用方已移除），这里顺带断言它确实不存在了。
    """
    assert not hasattr(YandeDataRepository, "get_max_id_for_tags"), (
        "get_max_id_for_tags 已随游标语义改造删除，不应复活"
    )

    folder_id = sched_folder("test_existing_cursor", tags=_TAGS)
    with FavoriteDao() as dao:
        dao.update(folder_id, last_synced_id=4999)

    with _patched_create_task():
        with _patched_api([[_post_item(5001), _post_item(5002), _post_item(5003)], []]) as api:
            asyncio.run(run_folder_schedule(folder_id))

    assert "id:>4999" in _captured_tags(api)[0], "必须以库里的游标作增量起点"
    assert _cursor_of(folder_id) == 5003


def test_max_pages_reached_still_advances_last_synced_id(sched_folder):
    """§10.2 改写：页数上限（max_pages_per_run）触发时，游标推进到已完成页的最后一条。

    取代旧的 ``test_run_folder_schedule_max_images_break_advances_last_synced_id``
    —— ``schedule_max_images`` 旋钮已下线，单轮上界只剩页数。
    """
    folder_id = sched_folder("test_max_pages_cursor", tags=_TAGS)

    pages = [
        [_post_item(6001), _post_item(6002)],
        [_post_item(6003), _post_item(6004)],
        [_post_item(6005), _post_item(6006)],   # 不应被抓到
    ]
    with patch("src.services.favorite_scheduler.config", _config_with_max_pages(2)):
        with _patched_create_task() as mock_create:
            with _patched_api(pages) as api:
                stats = asyncio.run(run_folder_schedule(folder_id))

    assert api.get_ranking.call_count == 2, "第 3 页不该被抓"
    assert stats["pages_fetched"] == 2
    assert [c.args[0] for c in mock_create.await_args_list] == [6001, 6002, 6003, 6004]
    assert _cursor_of(folder_id) == 6004, "游标必须落在最后一个**完成**页的最后一条"


def test_concurrent_folder_limit():
    """并发上限已由配置项下线为模块常量。"""
    assert favorite_scheduler.MAX_CONCURRENT_SCHEDULES == 2
    assert favorite_scheduler._schedule_semaphore._value == 2


def test_per_page_limit_constant_is_100(sched_folder):
    """单页条数已由配置项下线为常量 100（yande.re post API 硬上限）。

    取代旧的 ``test_per_page_limit_used_from_config``。
    """
    assert favorite_scheduler.PER_PAGE_LIMIT == 100

    folder_id = sched_folder("test_per_page_constant", tags=_TAGS)
    with _patched_create_task():
        with _patched_api([[_post_item(7001)], [_post_item(7002)], []]) as api:
            asyncio.run(run_folder_schedule(folder_id))

    limits = [c.args[0].limit for c in api.get_ranking.call_args_list]
    assert limits, "Expected get_ranking to be called"
    assert all(limit == 100 for limit in limits), f"每页都应固定 100，实际 {limits}"


# ==========================================================================
# §10.3 新增（12 条）
# ==========================================================================
def test_incremental_advances_across_consecutive_runs(sched_folder):
    """锁 P0-1：连续两轮调度，第二轮必须从上一轮游标继续往前推。

    修复前：从最新往旧遍历却把「最大 id」当续跑点落库 → 每轮零进展 + 永久空洞。
    """
    folder_id = sched_folder("test_incremental_two_runs", tags=_TAGS)

    with _patched_create_task() as mock_create:
        # 第 1 轮：游标 NULL → 全量
        with _patched_api([[_post_item(5001), _post_item(5002)], []]):
            stats1 = asyncio.run(run_folder_schedule(folder_id))
        assert stats1["enqueued"] == 2
        assert _cursor_of(folder_id) == 5002

        # 第 2 轮：游标 5002 → 服务端按 id:>5002 返回新图
        with _patched_api([[_post_item(5003), _post_item(5004)], []]):
            stats2 = asyncio.run(run_folder_schedule(folder_id))
        assert stats2["enqueued"] == 2, "第二轮必须真的抓到新图（而不是原地打转）"
        assert _cursor_of(folder_id) == 5004

    assert [c.args[0] for c in mock_create.await_args_list] == [5001, 5002, 5003, 5004]


def test_second_run_sends_id_gt_cursor_and_asc(sched_folder):
    """锁 P0-1 的查询串形态：第二轮发 ``id:>{cursor}`` + ``order:id``（**不是** order:id_asc）。"""
    folder_id = sched_folder("test_query_shape", tags=_TAGS)

    with _patched_create_task():
        with _patched_api([[_post_item(5001), _post_item(5002)], []]) as api1:
            asyncio.run(run_folder_schedule(folder_id))
        first_tags = _captured_tags(api1)[0]

        with _patched_api([[_post_item(5003)], []]) as api2:
            asyncio.run(run_folder_schedule(folder_id))
        second_tags = _captured_tags(api2)[0]

    tokens = second_tags.split()
    assert "id:>5002" in tokens, f"第二轮查询串缺少 id:> 游标裁剪：{second_tags!r}"
    assert "order:id" in tokens, f"第二轮查询串缺少升序钉子：{second_tags!r}"
    assert "order:id_asc" not in second_tags, "order:id_asc 在 yande.re 上无效（§5.3.1）"
    assert "order:id_asc" not in first_tags
    assert first_tags.split().count("order:id") == 1, "order:id 只能追加一次"


def test_null_cursor_sends_no_id_filter(sched_folder):
    """§5.2：游标 NULL = 无起点 = 全量重扫，查询串不得带任何 id: token。"""
    folder_id = sched_folder("test_null_cursor_query", tags=_TAGS)

    with _patched_create_task():
        with _patched_api([[], []]) as api:
            asyncio.run(run_folder_schedule(folder_id))

    tags = _captured_tags(api)[0]
    tokens = tags.split()
    assert not [t for t in tokens if t.startswith("id:")], (
        f"NULL 游标不应发任何 id: 过滤，实际 {tags!r}"
    )
    assert "order:id" in tokens


def test_user_order_and_id_meta_are_stripped(sched_folder):
    """用户自带的 ``order:*`` / ``id:*`` meta-tag 必须剥离，其余 meta-tag 原样保留。"""
    raw_tags = f"rating:s order:id_desc id:<=500 {_TAGS}"
    folder_id = sched_folder(
        "test_strip_meta", tags=raw_tags, purge_tag=_TAGS
    )

    with _patched_create_task():
        with _patched_api([[], []]) as api:
            asyncio.run(run_folder_schedule(folder_id))

    tokens = _captured_tags(api)[0].split()
    assert "order:id_desc" not in tokens, "用户的降序会直接抵消掉升序钉子"
    assert "id:<=500" not in tokens, "用户的 id 范围会直接抵消掉增量裁剪"
    assert "rating:s" in tokens, "其余 meta-tag 必须保留（缺陷 C）"
    assert _TAGS in tokens
    assert "order:id" in tokens


def test_no_duplicate_enqueue_for_active_task(sched_folder):
    """锁缺陷 B：已在下载队列中的 image_id 不重复建任务。"""
    folder_id = sched_folder("test_no_dup_enqueue", tags=_TAGS)

    with patch(
        "src.services.favorite_scheduler._load_active_image_ids",
        return_value={5001},
    ):
        with _patched_create_task() as mock_create:
            with _patched_api([[_post_item(5001), _post_item(5002)], []]):
                stats = asyncio.run(run_folder_schedule(folder_id))

    assert mock_create.await_args_list == [call(5002)], (
        "5001 已有活跃任务，不应再建任务"
    )
    assert stats["enqueued"] == 1
    assert stats["skipped"] >= 1, "重复项必须计入 skipped"
    assert _cursor_of(folder_id) == 5002


def test_api_error_mid_run_still_advances_cursor(sched_folder):
    """锁缺陷 A：第 N 页 API 报错 → status=failed，但**已完成页的游标照常落库**。"""
    folder_id = sched_folder("test_api_error_cursor", tags=_TAGS)

    with _patched_create_task() as mock_create:
        with _patched_api([
            [_post_item(5001), _post_item(5002)],
            Exception("page 2 api error"),
        ]):
            stats = asyncio.run(run_folder_schedule(folder_id))

    assert any("page 2 api error" in e for e in stats["errors"])
    assert stats["pages_fetched"] == 1
    assert [c.args[0] for c in mock_create.await_args_list] == [5001, 5002]
    assert _cursor_of(folder_id) == 5002, "第 1 页的进度不能因第 2 页失败而丢失"

    with FavoriteDao() as dao:
        assert dao.get_by_id(folder_id).last_schedule_status == "failed"


def test_max_pages_run_bounds_crawl(sched_folder):
    """P1：单轮翻页数严格不超过 ``max_pages_per_run``。"""
    folder_id = sched_folder("test_max_pages_bound", tags=_TAGS)

    # 备足 10 页 —— 若没有页数上界，这就是一次近乎无限的抓取
    pages = [[_post_item(8000 + i), _post_item(8100 + i)] for i in range(10)]
    with patch("src.services.favorite_scheduler.config", _config_with_max_pages(2)):
        with _patched_create_task():
            with _patched_api(pages) as api:
                stats = asyncio.run(run_folder_schedule(folder_id))

    assert api.get_ranking.call_count == 2
    assert stats["pages_fetched"] == 2
    assert stats["enqueued"] == 4


def test_skipped_stat_is_accumulated(sched_folder):
    """锁缺陷 D：``stats["skipped"]`` 真累加（旧实现只记最后一条）。"""
    folder_id = sched_folder("test_skipped_accumulate", tags=_TAGS)
    _seed_downloaded([9001, 9002])

    with _patched_create_task() as mock_create:
        with _patched_api([[
            _post_item(9001),  # 本地已存在且已下载 → skipped
            _post_item(9002),  # 同上
            _post_item(9003),  # 新图 → 入队
        ], []]):
            stats = asyncio.run(run_folder_schedule(folder_id))

    assert stats["skipped"] == 2, f"已下载条目必须逐条累加，实际 {stats}"
    assert stats["enqueued"] == 1
    assert [c.args[0] for c in mock_create.await_args_list] == [9003]
    assert _cursor_of(folder_id) == 9003


def test_pages_fetched_counts_actual_pages(sched_folder):
    """锁缺陷 E：``pages_fetched`` = 实际成功抓取的页数（旧实现记成了「下页页码」）。"""
    folder_id = sched_folder("test_pages_fetched", tags=_TAGS)

    with _patched_create_task():
        with _patched_api([
            [_post_item(10001)],
            [_post_item(10002)],
            [],                       # 第 3 页空 → 循环自然结束
        ]) as api:
            stats = asyncio.run(run_folder_schedule(folder_id))

    assert api.get_ranking.call_count == 3
    assert stats["pages_fetched"] == 2, (
        "只有 2 页抓到了数据；记成 3 就是旧的「下页页码」bug"
    )

    with FavoriteDao() as dao:
        assert dao.get_by_id(folder_id).last_schedule_stats["pages_fetched"] == 2
    assert _cursor_of(folder_id) == 10002


def test_tags_change_clears_cursor(sched_folder):
    """换了一批候选 tag → 旧游标必然失效，update_folder 必须把它置 NULL。"""
    folder_id = sched_folder("test_tags_clear_cursor", tags=_TAGS)
    with FavoriteDao() as dao:
        dao.update(folder_id, last_synced_id=12345)

    updated = FavoritesService.update_folder(
        folder_id, FavoriteFolderUpdate(tags=f"{_TAGS}_changed")
    )
    assert updated is not None
    assert _cursor_of(folder_id) is None, "tags 变更后必须清游标（下次走全量重扫）"

    # 对照：不带 tags 的更新（只改 color）不得清游标
    with FavoriteDao() as dao:
        dao.update(folder_id, last_synced_id=12345)
    FavoritesService.update_folder(folder_id, FavoriteFolderUpdate(color="#123456"))
    assert _cursor_of(folder_id) == 12345, "非 tags 更新不得误清游标"


def test_deleted_posts_do_not_break_parsing():
    """锁缺陷 H-1：含 ``status="deleted"`` 且缺三个 URL 的条目，整页不再 ValidationError。"""
    deleted_payload = _post_payload(12346, status="deleted")
    for key in ("file_url", "sample_url", "jpeg_url"):
        assert key not in deleted_payload, f"{key} 应完全缺失（yande.re 对 deleted 就是不返回）"

    active_payload = _post_payload(12347)
    data = YandePostData.model_validate([deleted_payload, active_payload])

    assert len(data.root) == 2
    deleted, active = data.root
    assert deleted.status == "deleted"
    assert deleted.file_url is None and deleted.sample_url is None and deleted.jpeg_url is None
    assert active.file_url == "http://yande.re/image/12347.jpg"
    assert active.sample_url == "http://yande.re/sample/12347.jpg"
    assert active.jpeg_url == "http://yande.re/jpeg/12347.jpg"


def test_deleted_posts_skipped_and_cursor_advances(sched_folder):
    """锁缺陷 H-2：deleted 条目不落库、不入队、计入 skipped，**且游标仍推进过它**。

    游标若不推进，全量重扫会永远卡在第一条 deleted 上（§5.6）。

    ⚠️ deleted 条目刻意放在**本页最后一条**：只有这样「游标 = 页内最大 id」才
    真正等同于「游标跨过了 deleted」。若把它放在中间，后面还有 active 条目，
    游标照样会被推到后面那条 —— 断言就变成了空转，锁不住回归。
    """
    folder_id = sched_folder("test_deleted_skip", tags=_TAGS)
    active_id, deleted_id = 12345, 12346

    with _patched_create_task() as mock_create:
        with _patched_api([[
            _post_item(active_id),
            _post_item(deleted_id, status="deleted"),   # 本页最后一条
        ], []]):
            stats = asyncio.run(run_folder_schedule(folder_id))

    # 不入队
    assert [c.args[0] for c in mock_create.await_args_list] == [active_id]
    # 不落库（active 条目落库作为对照，证明 upsert 路径本身是通的）
    assert _local_item(deleted_id) is None, "deleted 条目会污染图库"
    assert _local_item(active_id) is not None
    # 计入 skipped
    assert stats["skipped"] >= 1
    # 游标仍推进过它 —— deleted 是本页最后一条，游标必须落在它身上
    assert _cursor_of(folder_id) == deleted_id, (
        "游标必须跨过 deleted 条目；否则全量重扫会永远卡在它身上"
    )
