"""随机浏览 seed 一致性测试。

验证 /random_browse/preview 与 /gallery/load(random_seed=...) 使用同一套
确定性排序时满足：
1. 同 seed 的预览前 N 张 === 瀑布流第 1 页前 N 张，且顺序相同；
2. 同 seed 翻页无重复、并集覆盖完整候选池；
3. 同 seed 多次调用顺序稳定，不同 seed 顺序不同；
4. 不传 seed 时保持旧行为（全部返回、id 不重复）。
"""

import threading
from datetime import datetime
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.common.constant import Rating
from src.dao.database import Base
from src.dao.seeded_order import install_sqlite_seeded_hash
from src.dao.yande_data_dao import YandeDataRepository
from src.middleware.session import _request_session
from src.models.database.yande import YandeData
from src.models.request.gallery import GalleryLoadRequest
from src.services.gallery import GalleryService


@pytest.fixture
def in_memory_session(monkeypatch):
    """干净的 in-memory sqlite + ContextVar session。"""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # 与 dao/database.py 一致：必须在首次连接前注册 UDF
    install_sqlite_seeded_hash(engine)
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


def _seed_yande(sess, image_id: int) -> YandeData:
    rec = YandeData(
        id=image_id,
        tags="rating:s",
        width=100,
        height=100,
        file_ext="jpg",
        file_size=1024,
        file_url=f"http://a/{image_id}.jpg",
        preview_url=f"http://pa/{image_id}.jpg",
        md5=f"m{image_id}",
        author="t",
        created_at=datetime(2024, 1, 1),
        down_flag=True,
        rating=Rating.S,
    )
    sess.add(rec)
    return rec


@pytest.fixture
def pool_of_25(in_memory_session):
    for i in range(1, 26):
        _seed_yande(in_memory_session, i)
    in_memory_session.commit()
    return in_memory_session


def _load_seed(page: int, page_size: int, seed: int):
    req = GalleryLoadRequest(
        page=page,
        page_size=page_size,
        random=True,
        random_seed=seed,
    )
    return GalleryService.query_local_database(req)


def _preview_ids(seed: int, limit: int = 8):
    with YandeDataRepository() as repo:
        rows = repo.query_random_for_tags(
            tags="",
            limit=limit,
            downloaded_only=True,
            seed=seed,
        )
    return [row.id for row in rows]


def test_preview_matches_gallery_first_page(pool_of_25):
    """磁贴预览的 8 张 === 瀑布流第 1 页前 8 张（顺序一致）。"""
    preview = _preview_ids(seed=42)
    images, total = _load_seed(page=1, page_size=10, seed=42)

    assert [img.id for img in images[:8]] == preview
    assert total == 25


def test_seeded_pagination_is_disjoint_and_complete(pool_of_25):
    """同 seed 翻页不重复，三页并集覆盖全部 25 张。"""
    page1, _ = _load_seed(page=1, page_size=10, seed=42)
    page2, _ = _load_seed(page=2, page_size=10, seed=42)
    page3, _ = _load_seed(page=3, page_size=10, seed=42)

    ids1 = [img.id for img in page1]
    ids2 = [img.id for img in page2]
    ids3 = [img.id for img in page3]

    assert len(ids1) == 10
    assert len(ids2) == 10
    assert len(ids3) == 5
    assert set(ids1).isdisjoint(ids2)
    assert set(ids2).isdisjoint(ids3)
    assert set(ids1 + ids2 + ids3) == set(range(1, 26))


def test_same_seed_is_stable(pool_of_25):
    first = _preview_ids(seed=7, limit=25)
    second = _preview_ids(seed=7, limit=25)
    assert first == second


def test_different_seed_changes_order(pool_of_25):
    assert _preview_ids(seed=1, limit=25) != _preview_ids(seed=2, limit=25)


def test_random_without_seed_keeps_old_behavior(pool_of_25):
    req = GalleryLoadRequest(page=1, page_size=25, random=True)
    with patch("src.services.gallery.config") as mock_config:
        mock_config.favorites.enable_my_favorites = False
        images, total = GalleryService.query_local_database(req)

    ids = [img.id for img in images]
    assert total == 25
    assert len(ids) == 25
    assert len(set(ids)) == 25


def test_sqlite_udf_is_registered_on_connect():
    """回归：UDF 必须在 connect 事件里注册。

    修复前在查询路径动态 create_function，遇到同一 StaticPool 连接上
    其它线程的活跃语句会抛 ``OperationalError: Error creating function``。
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    install_sqlite_seeded_hash(engine)
    with engine.connect() as conn:
        names = {
            row[0]
            for row in conn.exec_driver_sql("PRAGMA function_list").fetchall()
        }
    assert "yande_seeded_hash" in names


def test_seeded_order_expr_does_not_register_during_active_statement(pool_of_25):
    """回归：构造排序表达式不能触碰连接。

    旧实现在这里调用 create_function；当同一 StaticPool 连接上还有活跃语句时，
    sqlite3 会抛 ``OperationalError: Error creating function``。
    """
    from sqlalchemy import select

    from src.dao.seeded_order import seeded_order_expr

    cursor = pool_of_25.execute(select(YandeData.id))
    errors = []

    def worker():
        try:
            with YandeDataRepository() as repo:
                seeded_order_expr(repo.session, 42)
        except Exception as exc:  # noqa: BLE001
            errors.append(repr(exc))

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join()
    cursor.fetchall()

    assert errors == []


def test_non_sqlite_dialect_compiles_to_md5_concat():
    """MariaDB / MySQL / PostgreSQL 分支编译为 MD5(CONCAT(id, ':', seed))。"""
    from types import SimpleNamespace

    from sqlalchemy import select
    from sqlalchemy.dialects import mysql

    from src.dao.seeded_order import seeded_order_expr

    class _FakeSession:
        def get_bind(self):
            return SimpleNamespace(dialect=SimpleNamespace(name="mariadb"))

    expr = seeded_order_expr(_FakeSession(), 123)
    sql = str(
        select(YandeData.id).order_by(expr).compile(dialect=mysql.dialect())
    ).lower()
    assert "md5(concat(" in sql
