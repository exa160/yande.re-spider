"""在线浏览（source='yande'）与 include_online 合并路径的收藏状态注入测试。

背景：
    我的最爱二级页（/my_favorites/images）已通过显式置 is_favorited=True 修复空心
    爱心，但「在线浏览」与「收藏夹 include_online 合并」两条路径此前完全没有注入
    收藏状态 —— 在线浏览时爱心恒为空心，与 README「所有图片右下角展示爱心」不符。

覆盖：
    1. 双判断分支（与本地 query_local_database 对称）：
       - include=False                  → 不挂 is_favorited
       - include=True + 总开关关        → 不挂 is_favorited（零 DB 开销）
       - include=True + 总开关开        → 正确挂 True/False
    2. include_online 合并路径：合并进来的在线图片同样带收藏状态

为什么必须 mock 在线 API：
    query_yande_api 内部会发真实 HTTP 请求到 yande.re。测试中一律 mock
    YandeApi.get_ranking 返回构造好的 YandePostData，保证离线可重复。

实现要点：
    - in-memory sqlite + ContextVar session（与 test_gallery_load_include_favorite 同款）
    - patch src.services.gallery.config 控制后端总开关
    - patch src.services.gallery.YandeApi 拦截网络
"""
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
import sqlalchemy
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.common.constant import Rating
from src.dao.database import Base
from src.middleware.session import _request_session
from src.models.database.my_favorite import MyFavorite
from src.models.request.gallery import GalleryLoadRequest
from src.models.response.yande import YandePostData


@pytest.fixture
def in_memory_session(monkeypatch):
    """干净的 in-memory sqlite + ContextVar session。"""
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
        yield session
    finally:
        _request_session.reset(token)
        session.close()


def _yande_post_item(image_id: int) -> dict:
    """构造一条最小可用的 yande.re post（YandePostItem 全部必填字段）。"""
    ts = datetime(2024, 1, 1)
    return {
        "id": image_id,
        "tags": "rating:s",
        "created_at": ts,
        "updated_at": ts,
        "author": "tester",
        "change": 0,
        "source": f"http://yande.re/post/show?id={image_id}",
        "score": 0,
        "md5": f"m{image_id}",
        "file_size": 1024,
        "file_ext": "jpg",
        "file_url": f"http://yande.re/image/{image_id}.jpg",
        "is_shown_in_index": True,
        "preview_url": f"http://yande.re/preview/{image_id}.jpg",
        "preview_width": 100,
        "preview_height": 100,
        "actual_preview_width": 100,
        "actual_preview_height": 100,
        "sample_url": f"http://yande.re/sample/{image_id}.jpg",
        "sample_width": 100,
        "sample_height": 100,
        "sample_file_size": 512,
        "jpeg_url": f"http://yande.re/jpeg/{image_id}.jpg",
        "jpeg_width": 100,
        "jpeg_height": 100,
        "jpeg_file_size": 512,
        "rating": "s",
        "is_rating_locked": False,
        "has_children": False,
        "parent_id": None,
        "status": "active",
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


def _mock_yande_api(image_ids):
    """构造一个 mock 的 YandeApi 实例，get_ranking 返回指定 id 的 post 列表。"""
    post_data = YandePostData.model_validate(
        [_yande_post_item(i) for i in image_ids]
    )
    fake_api = MagicMock()
    fake_api.get_ranking.return_value = post_data
    return fake_api


def _make_request(**overrides) -> GalleryLoadRequest:
    defaults = {
        "page": 1,
        "page_size": 20,
        "source": "yande",
        "include_favorite_status": False,
        "random": False,
    }
    defaults.update(overrides)
    return GalleryLoadRequest(**defaults)


# ============================================================
# 双判断分支 1：include_favorite_status=False → 不挂状态
# ============================================================


def test_online_include_false_does_not_attach_status(in_memory_session):
    """include_favorite_status=False：在线图片不挂 is_favorited（保持 None）。"""
    from src.services.gallery import GalleryService

    fake_api = _mock_yande_api([1, 2, 3])
    with patch("src.services.gallery.YandeApi", return_value=fake_api), \
            patch("src.services.gallery.config") as mock_config:
        mock_config.favorites.enable_my_favorites = True  # 总开关开也不挂
        images, total = GalleryService.query_yande_api(_make_request())

    assert total == 3
    for img in images:
        assert getattr(img, "is_favorited", None) is None


# ============================================================
# 双判断分支 2：include=True 但总开关关 → 强制不查表（零开销）
# ============================================================


def test_online_switch_off_does_not_query_my_favorite(in_memory_session):
    """总开关关闭时必须不查 my_favorite —— 这是「避免增加数据库开销」的核心契约。

    光断言 is_favorited 未挂载是不够的：实现完全可以查了表再丢弃结果。
    因此监听 session 的 do_orm_execute 事件，统计发往 my_favorite 表的语句数。
    """
    from src.services.gallery import GalleryService

    fake_api = _mock_yande_api([1, 2, 3])
    in_memory_session.add(MyFavorite(image_id=2))
    in_memory_session.commit()

    my_favorite_statements = []
    # 必须挂 engine 级：query_yande_api 内部 YandeDataRepository 自建 session，
    # 与测试 session 不是同一个对象，session 级事件收不到
    engine = in_memory_session.get_bind()

    @sqlalchemy.event.listens_for(engine, "before_cursor_execute")
    def _count_my_favorite_queries(conn, cursor, statement, parameters, context, executemany):
        if "my_favorite" in statement:
            my_favorite_statements.append(statement)

    try:
        with patch("src.services.gallery.YandeApi", return_value=fake_api), \
                patch("src.services.gallery.config") as mock_config:
            mock_config.favorites.enable_my_favorites = False
            images, _ = GalleryService.query_yande_api(
                _make_request(include_favorite_status=True)
            )
    finally:
        sqlalchemy.event.remove(engine, "before_cursor_execute",
                                _count_my_favorite_queries)

    assert len(images) == 3
    for img in images:
        assert getattr(img, "is_favorited", None) is None
    # 关键断言：总开关关闭时对 my_favorite 零查询
    assert my_favorite_statements == [], (
        f"总开关关闭时不应查询 my_favorite，实际执行了: {my_favorite_statements}"
    )


def test_online_switch_on_queries_my_favorite_once(in_memory_session):
    """总开关开启时只发一条 IN 查询（而非每张图一条），避免 N+1。"""
    from src.services.gallery import GalleryService

    fake_api = _mock_yande_api([1, 2, 3, 4, 5])
    in_memory_session.add(MyFavorite(image_id=2))
    in_memory_session.commit()

    my_favorite_statements = []
    engine = in_memory_session.get_bind()

    @sqlalchemy.event.listens_for(engine, "before_cursor_execute")
    def _count_my_favorite_queries(conn, cursor, statement, parameters, context, executemany):
        if "my_favorite" in statement:
            my_favorite_statements.append(statement)

    try:
        with patch("src.services.gallery.YandeApi", return_value=fake_api), \
                patch("src.services.gallery.config") as mock_config:
            mock_config.favorites.enable_my_favorites = True
            images, _ = GalleryService.query_yande_api(
                _make_request(include_favorite_status=True)
            )
    finally:
        sqlalchemy.event.remove(engine, "before_cursor_execute",
                                _count_my_favorite_queries)

    assert len(images) == 5
    assert len(my_favorite_statements) == 1, (
        f"5 张图应只发 1 条 IN 查询，实际 {len(my_favorite_statements)} 条"
    )


# ============================================================
# 双判断分支 3：include=True 且总开关开 → 正确注入 True/False
# ============================================================


def test_online_switch_on_attaches_correct_status(in_memory_session):
    """总开关开启时，一次 IN 查询即可给全部在线图片打上正确的收藏标记。"""
    from src.services.gallery import GalleryService

    fake_api = _mock_yande_api([1, 2, 3])
    for fid in (2,):
        in_memory_session.add(MyFavorite(image_id=fid))
    in_memory_session.commit()

    with patch("src.services.gallery.YandeApi", return_value=fake_api), \
            patch("src.services.gallery.config") as mock_config:
        mock_config.favorites.enable_my_favorites = True
        images, _ = GalleryService.query_yande_api(
            _make_request(include_favorite_status=True)
        )

    status_map = {img.id: getattr(img, "is_favorited", None) for img in images}
    assert status_map == {1: False, 2: True, 3: False}


def test_online_switch_on_all_favorited(in_memory_session):
    """全部已收藏时全部为 True。"""
    from src.services.gallery import GalleryService

    fake_api = _mock_yande_api([7, 8])
    for fid in (7, 8):
        in_memory_session.add(MyFavorite(image_id=fid))
    in_memory_session.commit()

    with patch("src.services.gallery.YandeApi", return_value=fake_api), \
            patch("src.services.gallery.config") as mock_config:
        mock_config.favorites.enable_my_favorites = True
        images, _ = GalleryService.query_yande_api(
            _make_request(include_favorite_status=True)
        )

    assert all(getattr(img, "is_favorited", None) is True for img in images)


# ============================================================
# include_online 合并路径：收藏夹 + 在线内容合并
# ============================================================


def test_favorites_include_online_merged_images_have_status(in_memory_session):
    """收藏夹 source 且 include_online=True：合并进来的在线图片也要带收藏状态。

    回归：此前合并路径只把在线图片 append 进来，从不注入 is_favorited，
    导致收藏夹在线模式下同一列表里本地图有爱心、在线图没有。
    """
    from src.api.v1.gallery import load_gallery

    # 本地已下载 1 张（已收藏）
    from src.models.database.yande import YandeData

    local = YandeData(
        id=100,
        tags="rating:s",
        width=100,
        height=100,
        file_ext="jpg",
        file_size=1024,
        file_url="http://a/100.jpg",
        preview_url="http://pa/100.jpg",
        md5="m100",
        author="t",
        rating=Rating.S,
        down_flag=True,
        created_at=datetime(2024, 1, 1),
    )
    in_memory_session.add(local)
    in_memory_session.add(MyFavorite(image_id=100))
    in_memory_session.commit()

    fake_folder = MagicMock()
    fake_folder.tags = "rating:s"

    # 在线返回 2 张，其中 2 已收藏
    fake_api = _mock_yande_api([2, 3])
    in_memory_session.add(MyFavorite(image_id=2))
    in_memory_session.commit()

    with patch("src.services.gallery.YandeApi", return_value=fake_api), \
            patch("src.dao.favorite_dao.favorite_dao.get_by_id",
                  return_value=fake_folder), \
            patch("src.services.gallery.config") as mock_config:
        mock_config.favorites.enable_my_favorites = True
        resp = awaitable_call(load_gallery, _make_request(
            source="favorites",
            favorite_id=1,
            include_online=True,
            include_favorite_status=True,
        ))

    data = resp.data
    ids = [img.id for img in data]
    assert 100 in ids and 2 in ids and 3 in ids
    status = {img.id: getattr(img, "is_favorited", None) for img in data}
    # 本地图：已收藏 → True
    assert status[100] is True
    # 在线图：2 已收藏 → True；3 未收藏 → False
    assert status[2] is True
    assert status[3] is False


def awaitable_call(async_fn, *args, **kwargs):
    """在同步测试中驱动 async 路由函数。"""
    import asyncio

    return asyncio.run(async_fn(*args, **kwargs))
