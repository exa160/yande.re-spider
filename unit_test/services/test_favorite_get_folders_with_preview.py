"""测试 FavoritesService.get_folders_with_preview 分页 + 预览数分档

背景：
- favorite_dao 是模块级单例，BaseDAO 在严格模式下要求 RequestSessionMiddleware 提供 session。
  无 HTTP 请求上下文时，DAO 调用会 RuntimeError。
- 服务方法 get_folders_with_preview 直接使用 favorite_dao.list_paginated()，需要 session。
- 本测试用 _request_session_ctx 临时设置 _request_session contextvar，让单例 DAO 在测试中可用。
- _clean / _seed_* 用 `with X as dao:` 模式各自打开 session，与 brief 原型一致。
"""
import sys
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]) + "/backend")

from src.dao.database import _get_session_factory
from src.dao.favorite_dao import favorite_dao
from src.dao.yande_data_dao import YandeDataRepository
from src.middleware.session import _request_session
from src.models.database.yande import FavoriteFolder, YandeData
from src.services.favorites import FavoritesService


@contextmanager
def _request_session_ctx():
    """为 favorite_dao 单例临时提供 request session contextvar.

    服务方法 get_folders_with_preview 直接调用 favorite_dao.list_paginated()，
    该方法会通过 RequestSessionMiddleware.get_session() 取 session。
    测试环境无 HTTP 请求，需手动注入。
    """
    session = _get_session_factory()()
    token = _request_session.set(session)
    try:
        yield session
    finally:
        session.close()
        _request_session.reset(token)


def _clean() -> None:
    """清空 favorite_folders 和 yande_data 测试数据。

    conftest._protect_yande_data 会在测试后恢复 yande_data；
    favorite_folders 目前无保护（与项目其他测试一致），运行前请确认无生产收藏夹。
    """
    with _request_session_ctx():
        with YandeDataRepository() as repo:
            repo.session.query(YandeData).delete()
            repo.session.query(FavoriteFolder).delete()


def _seed_folder(local_count: int, name: str, tags: str = "sample") -> int:
    """创建收藏夹并设置 local_count，提交后返回 id."""
    with favorite_dao as dao:
        folder = dao.create(name=name, tags=tags)
        folder.local_count = local_count
        return folder.id


def _seed_yande_data(tag: str, count: int, start_id: int = 5000) -> None:
    """插入 count 条已下载图片."""
    with YandeDataRepository() as repo:
        for i in range(count):
            rec = YandeData(
                id=start_id + i,
                tags=tag,
                width=100, height=100,
                file_ext="jpg",
                file_size=1024,
                file_url=f"http://example.com/{i}.jpg",
                preview_url=f"http://example.com/p_{i}.jpg",
                md5=f"md5_{i}",
                author="tester",
                created_at=datetime(2024, 1, 1, 0, 0, 0),
                down_flag=True,
            )
            repo.session.add(rec)


def test_count_tier_small_folder_returns_4():
    _clean()
    _seed_folder(10, "small_folder")
    _seed_yande_data("sample", 10)
    with _request_session_ctx():
        items, total, has_more = FavoritesService.get_folders_with_preview(page=1, page_size=20)
    assert total == 1
    assert has_more is False
    assert len(items[0].preview_images) == 4


def test_count_tier_medium_folder_returns_6():
    _clean()
    _seed_folder(100, "medium_folder")
    _seed_yande_data("sample", 100)
    with _request_session_ctx():
        items, _, _ = FavoritesService.get_folders_with_preview(page=1, page_size=20)
    assert len(items[0].preview_images) == 6


def test_count_tier_large_folder_returns_8():
    _clean()
    _seed_folder(300, "large_folder")
    _seed_yande_data("sample", 300)
    with _request_session_ctx():
        items, _, _ = FavoritesService.get_folders_with_preview(page=1, page_size=20)
    assert len(items[0].preview_images) == 8


def test_pagination_total_and_has_more():
    _clean()
    for i in range(15):
        _seed_folder(0, f"f_{i}")
    with _request_session_ctx():
        items, total, has_more = FavoritesService.get_folders_with_preview(page=1, page_size=10)
    assert total == 15
    assert has_more is True
    assert len(items) == 10
    with _request_session_ctx():
        items2, total2, has_more2 = FavoritesService.get_folders_with_preview(page=2, page_size=10)
    assert total2 == 15
    assert has_more2 is False
    assert len(items2) == 5


def test_preview_images_only_id_width_height():
    _clean()
    _seed_folder(10, "f")
    _seed_yande_data("sample", 10)
    with _request_session_ctx():
        items, _, _ = FavoritesService.get_folders_with_preview(page=1, page_size=20)
    img = items[0].preview_images[0]
    # 仅暴露 id/width/height；preview_url 字段不应在精简模型中
    assert set(img.model_dump().keys()) == {"id", "width", "height"}