"""回归测试：FavoritesService.get_folders_with_preview 不应注入虚拟 folder。

锁定 v1 报错已修复：旧实现曾向响应列表注入「我的最爱」(id='my-favorites' 或 id=-1)
和「随机浏览」(id='random') 虚拟条目，未来任何修改都不能重新引入这种行为。

实现要点：
- 使用 Task 4 / Task 6 / Task 7 已验证的 in_memory_session 模式
  (StaticPool + ContextVar + monkeypatch _get_session_factory)。
- 测试调用真实 FavoritesService.get_folders_with_preview (NOT mocked)，
  让 Pydantic 响应模型 FavoriteFolderWithMinimalPreview 实际校验 id: int，
  若注入字符串 sentinel ('my-favorites'/'random') Pydantic 会直接 ValidationError。
- 不在响应模型上加 is_system 字段断言——该字段在 FavoriteFolderWithMinimalPreview
  中不存在（Pydantic BaseModel）；只能通过 id 类型 / 值断言锁定回归。
- _seed_real_folder 通过 favorite_dao.create() 写真实 ORM 行，覆盖前缀逻辑。
"""
from datetime import datetime

import pytest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.common.constant import Rating
from src.dao.favorite_dao import favorite_dao
from src.dao.yande_data_dao import YandeDataRepository
from src.models.database.yande import Base, FavoriteFolder, YandeData
from src.middleware.session import _request_session
from src.services.favorites import FavoritesService


# ============================================================
# Fixtures (与 test_favorite_with_preview_optimizations.py 同源)
# ============================================================


@pytest.fixture
def in_memory_session(monkeypatch):
    """干净的 in-memory sqlite + ContextVar session。

    StaticPool 保证 favorite_dao (module-level) 和 YandeDataRepository (with-block)
    都连同一引擎，看到 DAO 单例足以覆盖前缀逻辑。
    """
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


def _seed_real_folder(
    sess, name: str, tags: str, local_count: int = 10
) -> FavoriteFolder:
    """通过 favorite_dao 单例种入一行真实 ORM 行，覆盖前缀逻辑。"""
    folder = favorite_dao.create(name=name, tags=tags)
    favorite_dao.update(folder.id, local_count=local_count)
    sess.commit()
    return folder


def _seed_yande(sess, image_id: int, tags: str, rating: Rating = Rating.S) -> None:
    """种一张 YandeData，避免 preview 阶段 query 报连怒。"""
    rec = YandeData(
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
        rating=rating,
    )
    sess.add(rec)


# ============================================================
# Tests
# ============================================================


def test_get_folders_with_preview_does_not_inject_virtual_my_favorites(
    in_memory_session,
):
    """回归锁定：「我的最爱」虚拟 folder 不再注入。

    v1 曾注入 id='my-favorites' (字符串) 或 id=-1 (int sentinel) 的虚拟条目。
    本测试种 2 行真实 FavoriteFolder，验证响应中只返回真实行，不含虚拟项。

    失败模式（如果回归出现）：
    - 响应中某项 id='my-favorites' → 'my-favorites' not in ids 失败
    - 响应中某项 id=-1 → -1 not in ids 失败
    - 注入的虚拟项是 Pydantic 不接受的字符串 → ValidationError 抛出
    """
    # 种 2 张预览图（避免 preview 阶段 query 报错）
    _seed_yande(in_memory_session, 101, "alpha")
    _seed_yande(in_memory_session, 102, "beta")
    # 种 2 个真实 FavoriteFolder（覆盖前缀逻辑的「真实行」）
    folder_a = _seed_real_folder(
        in_memory_session, name="My Alpha", tags="alpha", local_count=1
    )
    folder_b = _seed_real_folder(
        in_memory_session, name="My Beta", tags="beta", local_count=1
    )

    items, total, has_more = FavoritesService.get_folders_with_preview(
        page=1, page_size=20
    )

    ids = [item.id for item in items]

    # 1. 数量等于真实行数（虚拟项不存在）
    assert len(items) == 2, (
        f"应只返回 2 个真实 folder，注入虚拟项后实际 {len(items)} 个：ids={ids}"
    )
    assert total == 2, f"total 应为 2，实际 {total}"
    assert has_more is False

    # 2. 所有 id 必须为 int（Pydantic 校验后字符串 sentinel 会变 ValidationError）
    assert all(isinstance(item.id, int) for item in items), (
        f"所有 id 应为 int，实际 {[type(item.id).__name__ for item in items]}"
    )

    # 3. 「我的最爱」虚拟项的两种 sentinel 都不能出现
    assert "my-favorites" not in ids, (
        f"虚拟 folder id='my-favorites' 被注入：ids={ids}"
    )
    assert -1 not in ids, (
        f"虚拟 folder id=-1 被注入：ids={ids}"
    )

    # 4. 真实 folder 必须出现（正向验证）
    assert folder_a.id in ids
    assert folder_b.id in ids


def test_get_folders_with_preview_does_not_inject_virtual_random(in_memory_session):
    """回归锁定：「随机浏览」虚拟 folder 不再注入。

    v1 曾注入 id='random' (字符串) 的虚拟条目。本测试种 2 行真实
    FavoriteFolder，验证响应中只返回真实行。

    失败模式（如果回归出现）：
    - 响应中某项 id='random' → 'random' not in ids 失败
    - 注入的虚拟项是 Pydantic 不接受的字符串 → ValidationError 抛出
    """
    _seed_yande(in_memory_session, 201, "gamma")
    _seed_yande(in_memory_session, 202, "delta")
    folder_a = _seed_real_folder(
        in_memory_session, name="My Gamma", tags="gamma", local_count=1
    )
    folder_b = _seed_real_folder(
        in_memory_session, name="My Delta", tags="delta", local_count=1
    )

    items, total, _ = FavoritesService.get_folders_with_preview(
        page=1, page_size=20
    )

    ids = [item.id for item in items]

    # 1. 数量等于真实行数
    assert len(items) == 2, (
        f"应只返回 2 个真实 folder，实际 {len(items)} 个：ids={ids}"
    )
    assert total == 2

    # 2. 所有 id 必须为 int
    assert all(isinstance(item.id, int) for item in items), (
        f"所有 id 应为 int，实际 types={[type(item.id).__name__ for item in items]}"
    )

    # 3. 「随机浏览」虚拟项的 sentinel 不能出现
    assert "random" not in ids, (
        f"虚拟 folder id='random' 被注入：ids={ids}"
    )

    # 4. 同时再次锁定「我的最爱」sentinel（防御未来同时重新引入两个虚拟项）
    assert "my-favorites" not in ids
    assert -1 not in ids

    # 5. 真实 folder 必须出现
    assert folder_a.id in ids
    assert folder_b.id in ids