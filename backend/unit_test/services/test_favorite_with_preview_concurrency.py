"""回归：with-preview 在 asyncio.to_thread 下并发调用不能死锁。

背景（2026-10-25 本地事故）：
- with-preview 改 to_thread 后仍使用请求级 favorite_dao 单例；
- SQLite 当时是 StaticPool 单连接，多个请求的 session 共用一条连接；
- 前端一次配置保存会触发多个 loadFolders（tileSize/previewOrder/pageSize
  watcher），并发请求把 sqlite 连接/事务状态踩坏，事件循环彻底卡死。

修复：服务改用 with FavoriteDao() 自建 session 并在 worker 内提交；SQLite
改为 QueuePool + WAL。本测试用临时文件库并发跑 6 次 with-preview，
超时即视为回归。
"""
import asyncio
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool

from src.dao.database import Base, _apply_sqlite_pragmas
from src.models.database.yande import FavoriteFolder, YandeData
from src.services.favorites import FavoritesService


def test_concurrent_with_preview_does_not_deadlock(tmp_path, monkeypatch):
    db_path = tmp_path / "concurrent.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"timeout": 30, "check_same_thread": False},
        poolclass=QueuePool,
        pool_size=5,
        max_overflow=10,
        pool_timeout=30,
    )
    _apply_sqlite_pragmas(engine)
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr("src.dao.database._get_session_factory", lambda: TestSession)

    seed = TestSession()
    for i in range(1, 6):
        seed.add(FavoriteFolder(name=f"f{i}", tags=f"tag{i}", local_count=0))
        seed.add(
            YandeData(
                id=i,
                tags=f"tag{i}",
                width=10,
                height=10,
                file_ext="jpg",
                file_size=1,
                file_url=f"http://a/{i}.jpg",
                preview_url=f"http://p/{i}.jpg",
                md5=f"m{i}",
                author="t",
                created_at=datetime(2024, 1, 1),
                down_flag=True,
            )
        )
    seed.commit()
    seed.close()

    async def run():
        calls = [
            asyncio.to_thread(
                FavoritesService.get_folders_with_preview, page=1, page_size=10
            )
            for _ in range(6)
        ]
        return await asyncio.wait_for(asyncio.gather(*calls), timeout=30)

    try:
        results = asyncio.run(run())
    finally:
        engine.dispose()

    assert len(results) == 6
    for items, total, _ in results:
        assert total == 5
        assert len(items) == 5
