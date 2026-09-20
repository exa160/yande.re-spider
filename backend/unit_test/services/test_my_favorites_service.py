"""MyFavoritesService 单元测试

覆盖：
1. add(image_id) - 行为：写入 my_favorite + 条件触发下载
   - 图片不存在：raise ValueError
   - 写入持久化：count +1
   - enable_favorite_autodownload=True 且 down_flag=False：触发下载
   - enable_favorite_autodownload=False：不触发下载
   - down_flag=True（已下载）：不触发下载
2. remove(image_id) - 幂等
3. count() - 返回正确数量

实现说明：
- pytest-asyncio 未在 pyproject.toml 中（不安装新依赖），改用 asyncio.run() 同步包装 async 测试
- 测试 DAO 需要显式 session；与 test_favorite_with_preview_optimizations.py 同款的
  in_memory_session + ContextVar + monkeypatch _get_session_factory 模式
- 严格遵循 brief 的 7 个测试语义，但用 sync 函数表达
"""
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.common.constant import Rating
from src.dao.database import Base
from src.dao.my_favorite_dao import MyFavoriteDao
from src.middleware.session import _request_session
from src.models.database.yande import YandeData
from src.services.my_favorites import MyFavoritesService


@pytest.fixture
def in_memory_session(monkeypatch):
    """干净的 in-memory sqlite + ContextVar session，详见 test_favorite_with_preview_optimizations.py。"""
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


@pytest.fixture
def seed_image(in_memory_session):
    """插入 id=42, down_flag=False 的测试图片。返回 session 以便测试覆写字段。"""
    rec = YandeData(
        id=42,
        tags="rating:s",
        width=100,
        height=100,
        file_ext="jpg",
        file_size=1024,
        file_url="http://a/42.jpg",
        preview_url="http://pa/42.jpg",
        md5="m42",
        author="t",
        rating=Rating.S,
        down_flag=False,
        created_at=datetime(2024, 1, 1),
    )
    in_memory_session.add(rec)
    in_memory_session.commit()
    return in_memory_session


@pytest.fixture
def enable_autodownload_true():
    """Mock config.favorites.enable_favorite_autodownload = True"""
    with patch("src.services.my_favorites.config") as mock_config:
        mock_config.favorites.enable_favorite_autodownload = True
        yield mock_config


@pytest.fixture
def enable_autodownload_false():
    """Mock config.favorites.enable_favorite_autodownload = False"""
    with patch("src.services.my_favorites.config") as mock_config:
        mock_config.favorites.enable_favorite_autodownload = False
        yield mock_config


# ============================================================
# Tests
# ============================================================


def test_add_raises_for_nonexistent_image(seed_image, enable_autodownload_true):
    """add() 对不存在的 image_id 应 raise ValueError。"""
    with pytest.raises(ValueError, match="not found"):
        asyncio.run(MyFavoritesService.add(999))


def test_add_persists_record(seed_image, enable_autodownload_true):
    """add() 成功路径：写入 my_favorite（DownloadService 走 mock，不实际触发）。"""
    with patch("src.services.my_favorites.DownloadService") as mock_dl:
        mock_dl.create_task = AsyncMock()
        asyncio.run(MyFavoritesService.add(42))
    assert MyFavoritesService.count() == 1


def test_add_with_autodownload_true_triggers_download(seed_image, enable_autodownload_true):
    """enable_favorite_autodownload=True 且图片未下载时，触发 DownloadService.create_task。"""
    with patch("src.services.my_favorites.DownloadService") as mock_dl:
        mock_dl.create_task = AsyncMock()
        asyncio.run(MyFavoritesService.add(42))
        mock_dl.create_task.assert_called_once_with(42)


def test_add_with_autodownload_false_does_not_trigger_download(seed_image, enable_autodownload_false):
    """enable_favorite_autodownload=False 时，不触发下载（即便未下载）。"""
    with patch("src.services.my_favorites.DownloadService") as mock_dl:
        mock_dl.create_task = AsyncMock()
        asyncio.run(MyFavoritesService.add(42))
        mock_dl.create_task.assert_not_called()


def test_add_for_downloaded_image_does_not_trigger_download(seed_image, enable_autodownload_true):
    """已下载图片（down_flag=True）即使 enable_favorite_autodownload=True 也不触发下载。"""
    seed_image.query(YandeData).filter(YandeData.id == 42).update({"down_flag": True})
    seed_image.commit()

    with patch("src.services.my_favorites.DownloadService") as mock_dl:
        mock_dl.create_task = AsyncMock()
        asyncio.run(MyFavoritesService.add(42))
        mock_dl.create_task.assert_not_called()


def test_remove_is_idempotent(seed_image, enable_autodownload_true):
    """remove() 对不存在的 image_id 不报错（幂等）。"""
    # 不抛异常即通过
    MyFavoritesService.remove(999)


def test_count_returns_correct(seed_image, enable_autodownload_true):
    """count() 返回 my_favorite 表的实际行数。"""
    MyFavoriteDao.add(seed_image, image_id=42)
    assert MyFavoritesService.count() == 1