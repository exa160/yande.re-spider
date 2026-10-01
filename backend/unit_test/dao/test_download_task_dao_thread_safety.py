"""DownloadTaskDao 线程安全回归测试（PR #51 自查发现）。

## 背景

``src/dao/download_task_dao.py`` 末尾有一个模块级单例::

    download_task_dao = DownloadTaskDao()

而 ``BaseDAO.__enter__`` 把 session 挂在**实例自己**的 ``self._session`` 上::

    def __enter__(self):
        if self._session is None:
            self._session = _get_session_factory()()
            self.owns_session = True
        return self

于是两个请求线程同时 ``with download_task_dao as dao:`` 时，第二个线程看到
``self._session`` 已非 None，会**直接复用第一个线程的 Session**；第一个线程
的 ``__exit__`` 随后 close 掉它，第二个线程继续在已关闭的 session 上操作。

API 路由全部通过 ``asyncio.to_thread`` 调用这些 DAO，所以这不是理论问题：
前端 ``refreshAll()`` 会并发打 ``/download/tasks/count`` 与
``/recent_downloads/count``，两者必然落在线程池的不同线程上。
本 PR 新增的 ``POST /recent_downloads/clear`` 是唯一的**写**端点，
撞上就是破坏性操作失败。

## 实测（8 线程 × 40 次，与生产参数一致）

=====================================  ==========================
配置                                     结果
=====================================  ==========================
模块级单例 + 真实连接池（MariaDB 模式）    **SIGSEGV，进程直接崩溃**
每线程独立实例 + 真实连接池               0 / 320
模块级单例 + StaticPool（SQLite 模式）    23 / 320 异常
每线程独立实例 + StaticPool               16 / 320 异常
=====================================  ==========================

因此 service 层一律改用 ``with DownloadTaskDao() as dao:``。
本测试锁定「service 层不再使用模块级单例开 session」这一约束。

注意：SQLite 模式下残留的 16/320 来自 ``StaticPool``（全进程共用一条
DBAPI 连接，``check_same_thread=False`` 允许跨线程传递但 SQLite C 层并不
线程安全），与 DAO 单例无关，**改 DAO 实例解决不了**。这是既有的架构级
问题，需单独处理，不在本 PR 范围内。
"""

import re
import threading
from pathlib import Path

import pytest

SERVICE_PATH = (
    Path(__file__).resolve().parents[2] / "src" / "services" / "download.py"
)


class TestServiceDoesNotUseDaoSingleton:
    """静态约束：service 层不得用模块级单例开 session。"""

    def _source(self) -> str:
        return SERVICE_PATH.read_text(encoding="utf-8")

    def test_no_with_on_module_level_singleton(self):
        """不得出现 `with download_task_dao as dao:`（复用他人 Session）。"""
        offenders = [
            f"line {i}: {line.strip()}"
            for i, line in enumerate(self._source().split("\n"), 1)
            if line.strip() == "with download_task_dao as dao:"
        ]
        assert not offenders, (
            "service 层仍用模块级 download_task_dao 单例开 session，"
            "并发下会共享 Session（MariaDB 模式下实测 SIGSEGV）：\n"
            + "\n".join(offenders)
        )

    def test_with_sites_use_fresh_instance(self):
        """所有 `with ... as dao:` 的 DownloadTaskDao 都必须是新实例。"""
        bad = re.findall(r"with download_task_dao as dao:", self._source())
        assert not bad

        # 数量断言：防止将来新增调用点时忘记跟上
        fresh = re.findall(r"with DownloadTaskDao\(\) as dao:", self._source())
        assert len(fresh) == 5, (
            f"预期 5 处 `with DownloadTaskDao() as dao:`，实际 {len(fresh)} 处；"
            "若新增了调用点请同步本测试的断言"
        )


class TestConcurrentAccessDoesNotCorruptResults:
    """动态回归：多线程并发调用时结果必须稳定且不抛异常。"""

    def test_concurrent_reads_return_consistent_counts(self, tmp_path, monkeypatch):
        """并发读同一张表，所有线程都应拿到同一个正确结果。

        用 NullPool（每 session 独立连接）——等价于 MariaDB 模式的连接池行为。
        """
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import NullPool

        import src.dao.database as dbmod
        from src.common.constant import TaskStatus
        from src.models.database.yande import Base, DownloadTask
        from src.dao.download_task_dao import DownloadTaskDao

        engine = create_engine(
            f"sqlite:///{tmp_path / 'conc.db'}",
            poolclass=NullPool,
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(engine, tables=[DownloadTask.__table__])
        factory = sessionmaker(bind=engine, expire_on_commit=False)

        import datetime as dt

        now = dt.datetime.now()
        seed = factory()
        for i in range(1, 21):
            seed.add(
                DownloadTask(
                    task_id=f"t{i}",
                    image_id=i,
                    file_name=f"{i}.jpg",
                    status=TaskStatus.COMPLETED,
                    completed_at=now,
                    created_at=now,
                    updated_at=now,
                )
            )
        seed.commit()
        seed.close()

        # 让 DAO 的 __enter__ 拿到临时库（而不是真实 yande_data.db）
        monkeypatch.setattr(dbmod, "_get_session_factory", lambda: factory)

        results = []
        errors = []
        lock = threading.Lock()

        def worker():
            try:
                for _ in range(5):
                    # 关键：每线程独立实例，不共享 Session
                    with DownloadTaskDao() as dao:
                        n = dao.count_completed_distinct_images()
                    with lock:
                        results.append(n)
            except Exception as exc:  # pragma: no cover - 失败时给出可读信息
                with lock:
                    errors.append(f"{type(exc).__name__}: {exc}")

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, "并发读出现异常：\n" + "\n".join(sorted(set(errors)))
        assert results, "没有任何线程拿到结果"
        assert set(results) == {20}, (
            f"并发下计数不一致：期望恒为 20，实际 {sorted(set(results))}"
        )
