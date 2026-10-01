"""DownloadService「最近下载」相关方法的单元测试。

覆盖设计文档 §5「后端」表格中的 Service 行：
- ``delete_completed_records(days=None)`` 全清
- ``delete_completed_records(days=30)`` 按时间清

以及与 DAO 同口径的 count / list / preview 编排逻辑。

Session 约定：in-memory SQLite + StaticPool + ContextVar + monkeypatch
``_get_session_factory``（与 test_my_favorites_service.py / test_gallery_load_random.py
同款）。必须用 StaticPool：``download_task_dao`` 是模块级单例、
``YandeDataRepository`` 走 with-block 各自建 session，StaticPool 才能保证两者
连到同一个内存库。
"""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.common.constant import Rating, TaskStatus
from src.dao.database import Base
from src.middleware.session import _request_session
from src.models.database.yande import DownloadTask, YandeData
from src.services.download import DownloadService


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
    monkeypatch.setattr("src.dao.database._get_session_factory", lambda: TestSession)
    try:
        yield session
    finally:
        _request_session.reset(token)
        session.close()


def _seed_yande(sess, image_id: int, tags: str = "a") -> None:
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
            md5=f"m{image_id}",
            author="t",
            created_at=datetime(2024, 1, 1),
            down_flag=True,
            rating=Rating.S,
        )
    )


def _seed_task(sess, task_id, image_id, status, completed_at) -> None:
    sess.add(
        DownloadTask(
            task_id=task_id,
            image_id=image_id,
            file_name=f"{image_id}.jpg",
            status=status,
            created_at=datetime(2024, 1, 1),
            updated_at=datetime(2024, 1, 1),
            completed_at=completed_at,
        )
    )


@pytest.fixture
def seeded(in_memory_session):
    """3 张已完成（recent/old/null）+ 3 条非 completed 记录。

    | image | 记录 | 说明 |
    |-------|------|------|
    | 1 | completed @ now-1d     | 近期，days=30 保留 |
    | 2 | completed @ now-60d    | 过期，days=30 清除 |
    | 3 | completed @ NULL       | 跳过下载分支，任何模式都保留 |
    | 4 | failed @ now          | 非 completed，任何模式都保留 |
    | 5 | pending / downloading / paused / cancelled | 非 completed，保留 |
    """
    now = datetime.now()
    for i in (1, 2, 3, 4, 5):
        _seed_yande(in_memory_session, i, tags=f"tag{i}")
    _seed_task(in_memory_session, "t1", 1, TaskStatus.COMPLETED, now - timedelta(days=1))
    _seed_task(in_memory_session, "t2", 2, TaskStatus.COMPLETED, now - timedelta(days=60))
    _seed_task(in_memory_session, "t3", 3, TaskStatus.COMPLETED, None)
    _seed_task(in_memory_session, "t4", 4, TaskStatus.FAILED, now - timedelta(days=2))
    _seed_task(in_memory_session, "t5a", 5, TaskStatus.PENDING, None)
    _seed_task(in_memory_session, "t5b", 5, TaskStatus.DOWNLOADING, None)
    _seed_task(in_memory_session, "t5c", 5, TaskStatus.PAUSED, None)
    _seed_task(in_memory_session, "t5d", 5, TaskStatus.CANCELLED, None)
    in_memory_session.commit()
    return in_memory_session


def _task_ids(sess) -> set:
    return {r.task_id for r in sess.query(DownloadTask).all()}


# ============================================================
# delete_completed_records(days=None) → 全清
# ============================================================


def test_delete_all_records_removes_completed_only(seeded):
    """days=None 全清：只删 completed 且 completed_at 非空的记录。"""
    deleted = DownloadService.delete_completed_records()
    assert deleted == 2, f"应删 2 条 completed 记录，实际 {deleted}"
    assert _task_ids(seeded) == {"t3", "t4", "t5a", "t5b", "t5c", "t5d"}


def test_delete_all_records_never_deletes_non_completed(seeded):
    """安全红线：全清后所有非 completed 记录必须原样存活。"""
    DownloadService.delete_completed_records()
    remaining = {r.task_id: r.status for r in seeded.query(DownloadTask).all()}
    assert remaining == {
        "t3": TaskStatus.COMPLETED,  # completed_at 为 NULL，不在删除范围
        "t4": TaskStatus.FAILED,
        "t5a": TaskStatus.PENDING,
        "t5b": TaskStatus.DOWNLOADING,
        "t5c": TaskStatus.PAUSED,
        "t5d": TaskStatus.CANCELLED,
    }


def test_delete_all_records_is_idempotent(seeded):
    """重复调用返回 0，不报错。"""
    DownloadService.delete_completed_records()
    assert DownloadService.delete_completed_records() == 0


# ============================================================
# delete_completed_records(days=N) → 按时间清
# ============================================================


def test_delete_before_days_30_removes_old_only(seeded):
    """days=30：只清 now-60d 那条，now-1d 保留。"""
    deleted = DownloadService.delete_completed_records(days=30)
    assert deleted == 1, f"应只删 1 条过期记录，实际 {deleted}"
    assert _task_ids(seeded) == {"t1", "t3", "t4", "t5a", "t5b", "t5c", "t5d"}


def test_delete_before_days_never_deletes_non_completed(seeded):
    """安全红线：按时间清除同样不碰非 completed 记录。

    即使用一个足够大的天数（1 天 > 数据里最新那条 completed 的年龄），
    failed / pending / downloading / paused / cancelled 仍必须原样存活。
    """
    DownloadService.delete_completed_records(days=1)
    remaining = {r.task_id: r.status for r in seeded.query(DownloadTask).all()}
    for task_id, status in (
        ("t4", TaskStatus.FAILED),
        ("t5a", TaskStatus.PENDING),
        ("t5b", TaskStatus.DOWNLOADING),
        ("t5c", TaskStatus.PAUSED),
        ("t5d", TaskStatus.CANCELLED),
    ):
        assert remaining.get(task_id) == status, (
            f"非 completed 记录 {task_id} 被误删/被改状态：{remaining}"
        )


def test_delete_before_days_zero_clears_everything_before_now(seeded):
    """days=0 时 cutoff=now，清掉 now 之前的全部 completed 记录（语义等同全清）。

    API 层用 ``Field(ge=1)`` 拦掉 days=0，这里只锁定 service 的 cutoff 换算语义。
    """
    deleted = DownloadService.delete_completed_records(days=0)
    assert deleted == 2, f"应删 2 条 completed 记录，实际 {deleted}"
    assert _task_ids(seeded) == {"t3", "t4", "t5a", "t5b", "t5c", "t5d"}


def test_delete_before_days_keeps_count_consistent(seeded):
    """清除后角标计数同步下降（列表/计数同源）。"""
    assert DownloadService.count_completed_images() == 2
    DownloadService.delete_completed_records(days=30)
    assert DownloadService.count_completed_images() == 1
    DownloadService.delete_completed_records()
    assert DownloadService.count_completed_images() == 0


# ============================================================
# count / list / preview 编排
# ============================================================


def test_count_completed_images_is_deduped(in_memory_session):
    """同一张图多条 completed 只计 1。"""
    now = datetime.now()
    for i in (1, 2):
        _seed_yande(in_memory_session, i)
    _seed_task(in_memory_session, "a", 1, TaskStatus.COMPLETED, now)
    _seed_task(in_memory_session, "b", 1, TaskStatus.COMPLETED, now)
    _seed_task(in_memory_session, "c", 2, TaskStatus.COMPLETED, None)
    in_memory_session.commit()
    assert DownloadService.count_completed_images() == 1


def test_list_completed_image_ids_preserves_desc_order(seeded):
    """列表按完成时间倒序，且跳过 completed_at 为 NULL 的记录。"""
    rows = DownloadService.list_completed_image_ids(page=1, page_size=10)
    assert [r[0] for r in rows] == [1, 2], f"实际 {[r[0] for r in rows]}"


def test_get_recent_preview_returns_images_in_download_order(seeded):
    """preview 按完成时间倒序，并带上 yande_data 的 tags 元数据。"""
    items = DownloadService.get_recent_preview(limit=8)
    assert [i.id for i in items] == [1, 2]
    assert items[0].tags == "tag1"
    assert items[0].preview_url is None  # 前端按 id 拼预览图 URL


def test_get_recent_preview_respects_limit(seeded):
    """limit 生效。"""
    assert len(DownloadService.get_recent_preview(limit=1)) == 1


def test_get_recent_preview_skips_orphan_tasks(in_memory_session):
    """download_task 有记录但 yande_data 无元数据时跳过（不抛错）。"""
    now = datetime.now()
    _seed_yande(in_memory_session, 1)
    _seed_task(in_memory_session, "ok", 1, TaskStatus.COMPLETED, now - timedelta(days=1))
    _seed_task(in_memory_session, "orphan", 999, TaskStatus.COMPLETED, now)
    in_memory_session.commit()
    items = DownloadService.get_recent_preview(limit=8)
    assert [i.id for i in items] == [1]


def test_get_recent_preview_empty_when_no_records(in_memory_session):
    """无记录返回空列表。"""
    assert DownloadService.get_recent_preview(limit=8) == []


def test_get_recent_preview_survives_session_expiry(monkeypatch):
    """回归：preview 不能把 ORM 实例带出 ``with`` 块（DetachedInstanceError）。

    背景：既有 preview 用例的夹具用了 ``expire_on_commit=False``，ORM 属性永不
    过期，因此**掩盖**了一个真实缺陷 —— ``get_recent_preview`` 曾把 YandeData
    ORM 实例存进 dict 带出 ``with YandeDataRepository()`` 块，块退出关闭 session
    后再访问 ``rec.tags`` / ``rec.rating`` 触发惰性刷新：

        sqlalchemy.orm.exc.DetachedInstanceError: Instance <YandeData> is not
        bound to a Session; attribute refresh operation cannot proceed

    生产环境 ``_get_session_factory()`` 用默认 ``expire_on_commit=True``，
    commit/close 后所有属性立即过期，**必然**触发该异常 → ``/recent_downloads/preview``
    整个 500。生产默认的 session 工厂下跑一遍，即可锁死该回归。
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    # expire_on_commit=True —— 对齐生产 _get_session_factory 的默认行为
    TestSession = sessionmaker(bind=engine, expire_on_commit=True)
    monkeypatch.setattr("src.dao.database._get_session_factory", lambda: TestSession)

    seed = TestSession()
    _seed_yande(seed, 1, tags="tag1")
    _seed_yande(seed, 2, tags="tag2")
    _seed_task(seed, "t1", 1, TaskStatus.COMPLETED, datetime.now())
    _seed_task(seed, "t2", 2, TaskStatus.COMPLETED, datetime.now() - timedelta(days=1))
    seed.commit()
    seed.close()  # 立刻关闭：所有属性已过期，模拟 with 块退出后的真实状态

    items = DownloadService.get_recent_preview(limit=8)
    assert [i.id for i in items] == [1, 2]
    assert [i.tags for i in items] == ["tag1", "tag2"]


def test_get_recent_preview_serializes_rating_as_display(monkeypatch):
    """preview 的 rating 必须能被前端安全模式识别。

    ``MyFavoritePreviewImage.rating`` 的**字段类型是 Rating 枚举**（不是 str），
    ``serialize_rating`` 只在 Pydantic ``model_dump(mode="json")`` 阶段才转成
    ``Rating.display``（'Safe'/'Questionable'/'Explicit'）。若这里传成数据库原值
    's'，前端按 'Safe' 比较的安全模式会全图模糊。

    故本用例断言两件事：Service 层拿到的是 Rating 枚举（而非裸字符串），
    且经 ``model_dump(mode="json")`` 后输出 display 字符串。
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, expire_on_commit=True)
    monkeypatch.setattr("src.dao.database._get_session_factory", lambda: TestSession)

    seed = TestSession()
    _seed_yande(seed, 1)
    seed.query(YandeData).filter(YandeData.id == 1).one().rating = Rating.S
    _seed_task(seed, "t1", 1, TaskStatus.COMPLETED, datetime.now())
    seed.commit()
    seed.close()

    items = DownloadService.get_recent_preview(limit=8)
    assert len(items) == 1
    # 契约①：Service 层返回 Rating 枚举
    assert items[0].rating == Rating.S
    # 契约②：经 Pydantic 序列化后必须是 display 字符串（前端按 'Safe' 比较）
    assert items[0].model_dump(mode="json")["rating"] == Rating.S.display == "Safe"
