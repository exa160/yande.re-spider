"""验证收藏夹 with-preview 接口的搜索 / 排序 / N+1 修复。

覆盖：
1. search_paginated: 按 name / tags 模糊匹配，多 token 之间 OR 关系
2. query_preview_for_tags: order=random/desc/asc 都返回 limit 条，order 控制正确
3. get_folders_with_preview: 新增 keyword / preview_order 参数；旧调用方式（仅 page/page_size）向后兼容
4. 性能：单 page 应只在 DAO 层跑 2 次 query（folder + preview 元数据），不复用旧实现 N+1
"""
from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.common.constant import Rating, TaskStatus
from src.dao.favorite_dao import favorite_dao
from src.dao.yande_data_dao import YandeDataRepository
from src.models.database.yande import Base, DownloadTask, FavoriteFolder, YandeData
from src.middleware.session import _request_session
from src.services.favorites import FavoritesService


@pytest.fixture
def in_memory_session(monkeypatch):
    """干净的 in-memory sqlite + ContextVar session，详见 test_favorite_preview_image_rating.py。"""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, expire_on_commit=False)
    session = TestSession()
    token = _request_session.set(session)
    monkeypatch.setattr(
        "src.dao.database._get_session_factory",
        lambda: TestSession,
    )
    try:
        yield session, engine
    finally:
        _request_session.reset(token)
        session.close()


def _seed_folder(sess, name: str, tags: str, local_count: int = 10) -> int:
    f = favorite_dao.create(name=name, tags=tags)
    folder_id = f.id
    favorite_dao.update(folder_id, local_count=local_count)
    return folder_id


def _seed_yande(sess, image_id: int, tags: str, rating: Rating = Rating.S, down_flag: bool = True) -> YandeData:
    rec = YandeData(
        id=image_id,
        tags=tags,
        width=100,
        height=100,
        file_ext="jpg",
        file_size=1024,
        file_url=f"http://a/{image_id}.jpg",
        preview_url=f"http://pa/{image_id}.jpg",
        md5=f"m{image_id}",
        author="t",
        created_at=datetime(2024, 1, 1),
        down_flag=down_flag,
        rating=rating,
    )
    sess.add(rec)
    sess.commit()
    return rec


# ============================================================
# 1. search_paginated
# ============================================================

def test_search_paginated_match_by_name(in_memory_session):
    """关键字命中 folder.name 即匹配（不区分大小写）。"""
    sess, _ = in_memory_session
    _seed_folder(sess, "桃矢姐妹", "touka_kawai")
    _seed_folder(sess, "其它文件夹", "other_tag")

    items, total = favorite_dao.search_paginated(
        page=1, page_size=20, keyword="桃矢"
    )
    assert total == 1
    assert len(items) == 1
    assert items[0].name == "桃矢姐妹"


def test_search_paginated_match_by_tags(in_memory_session):
    """关键字命中 folder.tags 即匹配。"""
    sess, _ = in_memory_session
    _seed_folder(sess, "fold1", "touka_kawai rating:s")
    _seed_folder(sess, "fold2", "completely_different")

    items, total = favorite_dao.search_paginated(
        page=1, page_size=20, keyword="touka"
    )
    assert total == 1
    assert items[0].name == "fold1"


def test_search_paginated_multi_token_or(in_memory_session):
    """多 token 之间是 OR 关系：任一 token 命中即匹配。"""
    sess, _ = in_memory_session
    _seed_folder(sess, "alpha", "tag_a tag_b")
    _seed_folder(sess, "beta", "tag_c")
    _seed_folder(sess, "gamma", "tag_d")

    items, total = favorite_dao.search_paginated(
        page=1, page_size=20, keyword="tag_a tag_c"
    )
    names = {f.name for f in items}
    assert total == 2
    assert names == {"alpha", "beta"}


def test_search_paginated_case_insensitive(in_memory_session):
    """大小写不敏感（SQL ILIKE / LIKE LOWER 都适用）。"""
    sess, _ = in_memory_session
    _seed_folder(sess, "CamelCase", "SomeTag")

    items, _ = favorite_dao.search_paginated(
        page=1, page_size=20, keyword="some"
    )
    assert len(items) == 1
    assert items[0].name == "CamelCase"


def test_search_paginated_empty_keyword_falls_back_to_list(in_memory_session):
    """空关键字应该走 list_paginated 全列表路径，不报错。"""
    sess, _ = in_memory_session
    _seed_folder(sess, "f1", "tag1")
    _seed_folder(sess, "f2", "tag2")

    items, total = favorite_dao.search_paginated(
        page=1, page_size=20, keyword="   "
    )
    assert total == 2
    assert len(items) == 2


def test_search_paginated_pagination(in_memory_session):
    """分页正确：page_size 控制返回数量，total 全量。"""
    sess, _ = in_memory_session
    for i in range(5):
        _seed_folder(sess, f"fold{i}", f"tag{i}")

    items, total = favorite_dao.search_paginated(
        page=1, page_size=2, keyword="tag"
    )
    assert total == 5
    assert len(items) == 2

    items2, total2 = favorite_dao.search_paginated(
        page=2, page_size=2, keyword="tag"
    )
    assert total2 == 5
    assert len(items2) == 2
    # 第 1 页和第 2 页不应该重复
    assert {f.id for f in items}.isdisjoint({f.id for f in items2})


# ============================================================
# 2. query_preview_for_tags
# ============================================================

def test_query_preview_for_tags_random(in_memory_session):
    """order=random 返回 limit 条，结果集大小正确。"""
    sess, _ = in_memory_session
    for i in range(10):
        _seed_yande(sess, image_id=1000 + i, tags="foo")

    with YandeDataRepository() as repo:
        rows = repo.query_preview_for_tags(
            tags="foo", limit=5, downloaded_only=True, order="random"
        )
    assert len(rows) == 5


def test_query_preview_for_tags_desc_returns_latest_first(in_memory_session):
    """order=desc 返回 ID 倒序（最新优先）。"""
    sess, _ = in_memory_session
    for i in range(10):
        _seed_yande(sess, image_id=2000 + i, tags="bar")

    with YandeDataRepository() as repo:
        rows = repo.query_preview_for_tags(
            tags="bar", limit=10, downloaded_only=True, order="desc"
        )
    ids = [r.id for r in rows]
    assert ids == sorted(ids, reverse=True)
    assert ids[0] == 2009
    assert ids[-1] == 2000


def test_query_preview_for_tags_asc_returns_earliest_first(in_memory_session):
    """order=asc 返回 ID 正序（最早优先）。"""
    sess, _ = in_memory_session
    for i in range(10):
        _seed_yande(sess, image_id=3000 + i, tags="baz")

    with YandeDataRepository() as repo:
        rows = repo.query_preview_for_tags(
            tags="baz", limit=10, downloaded_only=True, order="asc"
        )
    ids = [r.id for r in rows]
    assert ids == sorted(ids)
    assert ids[0] == 3000
    assert ids[-1] == 3009


# ============================================================
# 3. get_folders_with_preview: keyword + preview_order 透传
# ============================================================

def test_get_folders_with_preview_keyword_filters(in_memory_session):
    """get_folders_with_preview 透传 keyword 参数，filtered 后 total 正确。"""
    sess, _ = in_memory_session
    _seed_folder(sess, "target", "touka_kawai")
    _seed_folder(sess, "other1", "completely_different")
    _seed_folder(sess, "other2", "another_one")

    # 全文
    items_all, total_all, _ = FavoritesService.get_folders_with_preview(
        page=1, page_size=20
    )
    assert total_all == 3
    assert len(items_all) == 3

    # 关键字过滤
    items, total, has_more = FavoritesService.get_folders_with_preview(
        page=1, page_size=20, keyword="touka"
    )
    assert total == 1
    assert len(items) == 1
    assert items[0].name == "target"
    assert has_more is False


def test_get_folders_with_preview_preview_order_desc(in_memory_session):
    """preview_order=desc 控制预览元数据 ID 倒序。"""
    sess, _ = in_memory_session
    _seed_folder(sess, "fold_desc", "shared_tag")
    for i in range(8):
        _seed_yande(sess, image_id=4000 + i, tags="shared_tag")

    items, _, _ = FavoritesService.get_folders_with_preview(
        page=1, page_size=20, preview_order="desc"
    )
    preview = items[0].preview_images
    ids = [p.id for p in preview]
    assert ids == sorted(ids, reverse=True)
    assert ids[0] == 4007


def test_get_folders_with_preview_preview_order_asc(in_memory_session):
    """preview_order=asc 控制预览元数据 ID 正序。"""
    sess, _ = in_memory_session
    _seed_folder(sess, "fold_asc", "shared_tag")
    for i in range(8):
        _seed_yande(sess, image_id=5000 + i, tags="shared_tag")

    items, _, _ = FavoritesService.get_folders_with_preview(
        page=1, page_size=20, preview_order="asc"
    )
    preview = items[0].preview_images
    ids = [p.id for p in preview]
    assert ids == sorted(ids)
    assert ids[0] == 5000


def test_get_folders_with_preview_backward_compatible(in_memory_session):
    """旧调用方式（仅 page / page_size）必须保持向后兼容（修复 N+1 后签名扩展）。"""
    sess, _ = in_memory_session
    _seed_folder(sess, "legacy_call", "tag_legacy")
    _seed_yande(sess, image_id=6000, tags="tag_legacy")

    # 不传 tile_size / keyword / preview_order 仍要 work
    items, total, has_more = FavoritesService.get_folders_with_preview(
        page=1, page_size=20
    )
    assert total == 1
    assert len(items) == 1
    assert items[0].preview_images  # 默认 random 仍能返回至少 1 张
    assert has_more is False


# ============================================================
# 3.5 local_count 按需重算
#
# local_count 是缓存列，下载完成（down_flag False→True）后不会自动更新。
# 列表接口必须在「最近一次 completed 下载」晚于 last_refresh 时重算，
# 否则后台调度 / 收藏自动下载完成后角标会长期停在旧数字。
# ============================================================

def _seed_completed_download(sess, image_id: int, completed_at: datetime) -> None:
    sess.add(
        DownloadTask(
            task_id=f"task-{image_id}",
            image_id=image_id,
            file_name=f"{image_id}.jpg",
            status=TaskStatus.COMPLETED,
            completed_at=completed_at,
            created_at=completed_at,
        )
    )
    sess.commit()


def test_get_folders_with_preview_refreshes_stale_local_count(in_memory_session):
    """last_refresh 早于最近一次下载完成 → 列表返回并落库真实本地数量。"""
    sess, _ = in_memory_session
    folder_id = _seed_folder(sess, "fold_stale", "stale_tag", local_count=999)
    for i in range(3):
        _seed_yande(sess, image_id=9000 + i, tags="stale_tag", down_flag=True)
    for i in range(2):
        _seed_yande(sess, image_id=9100 + i, tags="stale_tag", down_flag=False)

    favorite_dao.update(folder_id, last_refresh=datetime(2024, 1, 1))
    _seed_completed_download(sess, image_id=9000, completed_at=datetime(2025, 1, 1))

    items, _, _ = FavoritesService.get_folders_with_preview(page=1, page_size=20)

    assert items[0].local_count == 3
    # 重算结果随请求 session 落库（expire 后仍读到 3 才算真的写了）
    sess.commit()
    sess.expire_all()
    assert favorite_dao.get_by_id(folder_id).local_count == 3


def test_get_folders_with_preview_refreshes_when_never_refreshed(in_memory_session):
    """last_refresh 为空（从未刷新过）→ 即使没有下载记录也要重算一次。"""
    sess, _ = in_memory_session
    folder_id = _seed_folder(sess, "fold_never", "never_tag", local_count=999)
    for i in range(2):
        _seed_yande(sess, image_id=9200 + i, tags="never_tag", down_flag=True)

    items, _, _ = FavoritesService.get_folders_with_preview(page=1, page_size=20)

    assert items[0].local_count == 2
    assert favorite_dao.get_by_id(folder_id).local_count == 2


def test_with_preview_route_refreshes_local_count(monkeypatch):
    """路由层回归：to_thread 内仍能拿到请求级 session，且响应返回重算后的数量。"""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, expire_on_commit=False)
    # 必须两处都 patch：middleware.session 在 import 时已绑定工厂引用
    monkeypatch.setattr("src.dao.database._get_session_factory", lambda: TestSession)
    monkeypatch.setattr("src.middleware.session._get_session_factory", lambda: TestSession)

    seed = TestSession()
    seed.add(FavoriteFolder(name="route_fold", tags="route_tag", local_count=999))
    seed.add(
        YandeData(
            id=9400,
            tags="route_tag",
            width=100,
            height=100,
            file_ext="jpg",
            file_size=1024,
            file_url="http://a/9400.jpg",
            preview_url="http://pa/9400.jpg",
            md5="m9400",
            author="t",
            created_at=datetime(2024, 1, 1),
            down_flag=True,
        )
    )
    seed.commit()
    seed.close()

    from src.api.v1.favorites import router as favorites_router
    from src.middleware.session import RequestSessionMiddleware

    app = FastAPI()
    app.include_router(favorites_router, prefix="/api/v1/favorites")
    RequestSessionMiddleware.init_app(app)
    with TestClient(app) as client:
        resp = client.get("/api/v1/favorites/with-preview?page=1&page_size=20")

    assert resp.status_code == 200
    item = resp.json()["data"]["items"][0]
    assert item["local_count"] == 1


def test_get_folders_with_preview_skips_recount_when_fresh(in_memory_session):
    """last_refresh 晚于最近一次下载完成 → 不重算（避免每次翻页都跑全量 COUNT）。"""
    sess, _ = in_memory_session
    folder_id = _seed_folder(sess, "fold_fresh", "fresh_tag", local_count=999)
    _seed_yande(sess, image_id=9300, tags="fresh_tag", down_flag=True)

    favorite_dao.update(folder_id, last_refresh=datetime(2025, 6, 1))
    _seed_completed_download(sess, image_id=9300, completed_at=datetime(2025, 1, 1))

    items, _, _ = FavoritesService.get_folders_with_preview(page=1, page_size=20)

    assert items[0].local_count == 999
    assert favorite_dao.get_by_id(folder_id).local_count == 999


# ============================================================
# 4. N+1 修复验证：单 page 不再为每个 folder 新开 session
# ============================================================

def test_get_folders_with_preview_uses_single_session(monkeypatch, in_memory_session):
    """get_folders_with_preview 不应每个 folder 都开/关 repo session。

    验证方式：monkey-patch YandeDataRepository.__enter__ 计数，
    旧实现 N=20 folders 时会触发 20 次 enter，新实现只 1 次。
    """
    sess, _ = in_memory_session
    for i in range(20):
        _seed_folder(sess, f"f{i}", f"tag_{i}")
        _seed_yande(sess, image_id=7000 + i, tags=f"tag_{i}")

    enter_count = 0
    original_init = YandeDataRepository.__init__

    def counting_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)

    original_enter = YandeDataRepository.__enter__

    def counting_enter(self):
        nonlocal enter_count
        enter_count += 1
        return original_enter(self)

    monkeypatch.setattr(YandeDataRepository, "__init__", counting_init)
    monkeypatch.setattr(YandeDataRepository, "__enter__", counting_enter)

    FavoritesService.get_folders_with_preview(page=1, page_size=20)

    assert enter_count == 1, (
        f"应为 1 个 repo session（修复 N+1），实际 {enter_count} 次。"
        "如果 = 20+ 表示 N+1 问题未修复。"
    )


# ============================================================
# 5. include_online：预览包含未下载图片
# ============================================================

def test_include_online_default_excludes_non_downloaded(in_memory_session):
    """默认 include_online=False 时只返回已下载图片，未下载被过滤。"""
    sess, _ = in_memory_session
    _seed_folder(sess, "fold_default", "shared_tag")
    for i in range(5):
        _seed_yande(sess, image_id=8000 + i, tags="shared_tag", down_flag=True)
    for i in range(3):
        _seed_yande(sess, image_id=8100 + i, tags="shared_tag", down_flag=False)

    items, _, _ = FavoritesService.get_folders_with_preview(
        page=1, page_size=20
    )
    preview_ids = [p.id for p in items[0].preview_images]
    assert all(8000 <= i <= 8004 for i in preview_ids), (
        f"include_online 默认 False 时应只返回 down_flag=True 的图片，实际 {preview_ids}"
    )


def test_include_online_true_returns_non_downloaded(in_memory_session):
    """include_online=True 时预览图同时包含未下载图片（未来「我的最爱」场景）。"""
    sess, _ = in_memory_session
    _seed_folder(sess, "fold_online", "shared_tag")
    for i in range(3):
        _seed_yande(sess, image_id=8200 + i, tags="shared_tag", down_flag=True)
    for i in range(5):
        _seed_yande(sess, image_id=8300 + i, tags="shared_tag", down_flag=False)

    items, _, _ = FavoritesService.get_folders_with_preview(
        page=1, page_size=20, include_online=True
    )
    preview_ids = [p.id for p in items[0].preview_images]
    # 应同时包含 downloaded（8200-8202）和 non_downloaded（8300-8304）
    assert any(8200 <= i <= 8202 for i in preview_ids), (
        f"应包含已下载图，实际 {preview_ids}"
    )
    assert any(8300 <= i <= 8304 for i in preview_ids), (
        f"include_online=True 应包含未下载图，实际 {preview_ids}"
    )


def test_include_online_cache_key_includes_flag(in_memory_session):
    """回归：相同 tags 在 include_online 切换时不能复用缓存（结果集不同）。

    验证 tags_query_cache key 必须包含 include_online 维度：
    - include_online=False 命中只返回 3 张已下载
    - include_online=True 命中返回 8 张（3 已下载 + 5 未下载）
    """
    sess, _ = in_memory_session
    _seed_folder(sess, "fold_cache", "shared_tag")
    for i in range(3):
        _seed_yande(sess, image_id=8400 + i, tags="shared_tag", down_flag=True)
    for i in range(5):
        _seed_yande(sess, image_id=8500 + i, tags="shared_tag", down_flag=False)

    # 第一次调用 include_online=False
    items1, _, _ = FavoritesService.get_folders_with_preview(
        page=1, page_size=20, include_online=False
    )
    len1 = len(items1[0].preview_images)

    # 第二次调用 include_online=True，缓存必须区分
    items2, _, _ = FavoritesService.get_folders_with_preview(
        page=1, page_size=20, include_online=True
    )
    len2 = len(items2[0].preview_images)

    assert len1 == 3, f"include_online=False 应返 3 张已下载，实际 {len1}"
    assert len2 == 8, f"include_online=True 应返 8 张（3+5），实际 {len2}"
    assert len1 != len2, "两次调用结果相同 → cache_key 缺少 include_online 维度"