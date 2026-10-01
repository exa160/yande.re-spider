"""回归测试：「最近下载」**不得**改变 ``get_folders_with_preview`` 的行为。

设计文档 §1.2 / §5 明确：
- ❌ 不动 ``get_folders_with_preview``
- ❌ 回归用例：「行为完全不变（**不注入**虚拟 folder）」

背景：磁贴「我的最爱 / 随机浏览 / 最近下载」是**前端** ``useFavoriteFoldersList.js``
的 virtualTiles push 出来的虚拟磁贴，后端 ``FavoritesService.get_folders_with_preview``
只返回真实 ``favorite_folders`` 表的行。历史回归（v1）曾在后端注入
id='my-favorites' / id='random' 的字符串 sentinel 虚拟条目，导致 Pydantic
``FavoriteFolderWithMinimalPreview.id: int`` 校验失败。

本文件锁定第三种 sentinel（'recent-downloads'）也不会被后端注入，
并顺带再次锁死前两种，防止未来有人"顺手"加回来。
"""
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.common.constant import Rating
from src.dao.favorite_dao import favorite_dao
from src.middleware.session import _request_session
from src.models.database.yande import Base, YandeData
from src.services.favorites import FavoritesService


@pytest.fixture
def in_memory_session(monkeypatch):
    """干净的 in-memory sqlite + ContextVar session（与既有回归测试同款）。"""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, expire_on_commit=False)
    session = TestSession()
    token = _request_session.set(session)
    monkeypatch.setattr("src.dao.database._get_session_factory", lambda: TestSession)
    try:
        yield session
    finally:
        _request_session.reset(token)
        session.close()


def _seed_yande(sess, image_id: int, tags: str) -> None:
    sess.add(
        YandeData(
            id=image_id,
            tags=tags,
            width=100,
            height=100,
            file_ext="jpg",
            file_size=1024,
            file_url=f"http://a/{image_id}.jpg",
            preview_url=f"http://pa/{image_id}.jpg",
            sample_url=f"http://sa/{image_id}.jpg",
            jpeg_url=f"http://j/{image_id}.jpg",
            md5=f"m{image_id}",
            author="t",
            created_at=datetime(2024, 1, 1),
            down_flag=True,
            rating=Rating.S,
        )
    )


def _seed_real_folder(sess, name: str, tags: str, local_count: int = 1) -> int:
    folder = favorite_dao.create(name=name, tags=tags)
    favorite_dao.update(folder.id, local_count=local_count)
    sess.commit()
    return folder.id


def test_recent_downloads_is_not_injected_as_virtual_folder(in_memory_session):
    """种 2 个真实 folder，验证响应里既没有 'recent-downloads' 也没有其它虚拟项。"""
    _seed_yande(in_memory_session, 301, "rd")
    _seed_yande(in_memory_session, 302, "rd")
    folder_a = _seed_real_folder(in_memory_session, "RD Alpha", "rd")
    folder_b = _seed_real_folder(in_memory_session, "RD Beta", "rd")

    items, total, has_more = FavoritesService.get_folders_with_preview(page=1, page_size=20)

    ids = [item.id for item in items]
    assert len(items) == 2, f"应只返回 2 个真实 folder，实际 {len(items)}：{ids}"
    assert total == 2
    assert has_more is False
    assert folder_a in ids and folder_b in ids

    # 第三种虚拟 sentinel 不得出现
    assert "recent-downloads" not in ids
    # 前两种虚拟 sentinel 也不得复活（防御未来同时重新引入）
    assert "my-favorites" not in ids
    assert "random" not in ids
    assert -1 not in ids
    assert all(isinstance(i, int) for i in ids)


def test_recent_downloads_count_does_not_leak_into_folders(in_memory_session):
    """即使存在 completed 下载任务，folder 列表的数量/内容也不受影响。"""
    from datetime import timedelta

    from src.common.constant import TaskStatus
    from src.models.database.yande import DownloadTask

    _seed_yande(in_memory_session, 401, "leak")
    in_memory_session.add(
        DownloadTask(
            task_id="rd-1",
            image_id=401,
            file_name="401.jpg",
            status=TaskStatus.COMPLETED,
            created_at=datetime(2024, 1, 1),
            updated_at=datetime(2024, 1, 1),
            completed_at=datetime(2024, 1, 1) + timedelta(days=1),
        )
    )
    in_memory_session.commit()
    _seed_real_folder(in_memory_session, "RD Leak", "leak")

    items, total, _ = FavoritesService.get_folders_with_preview(page=1, page_size=20)
    assert total == 1
    assert len(items) == 1
