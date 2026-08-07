"""验证 _on_folder_trigger 不依赖请求 ContextVar

背景：修复 BaseDAO 静默 fallback 后，APScheduler 回调（无请求上下文）
调用 favorite_dao.get_by_id 会抛 RuntimeError。
正确做法是回调内用 with DAO() as dao: 显式创建 session，并把整个加载放到
to_thread 中避免冻事件循环。
"""
import sys
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]) + "/backend")

import pytest


def test_on_folder_trigger_uses_with_context(monkeypatch):
    """_on_folder_trigger 必须在 with 上下文内调用 DAO，不能依赖单例 session"""
    from src.infrastructure import scheduler as sm
    from src.dao.favorite_dao import FavoriteDao

    captured = {"called_in_with": False}

    class FakeFolder:
        id = 999
        schedule_enabled = False  # 跳过 schedule_enabled 检查立刻 return

    def fake_get_by_id(self, folder_id):
        if self._session is not None:
            captured["called_in_with"] = True
        return FakeFolder()

    monkeypatch.setattr(FavoriteDao, "get_by_id", fake_get_by_id)

    asyncio.run(sm._on_folder_trigger(999))

    assert captured["called_in_with"], (
        "DAO get_by_id 调用时 self._session 应为非 None（在 with 内）"
    )


def test_on_folder_trigger_runs_in_thread(monkeypatch):
    """_on_folder_trigger 必须用 asyncio.to_thread 跑 DAO，不能在事件循环线程执行"""
    from src.infrastructure import scheduler as sm
    from src.dao.favorite_dao import FavoriteDao
    import threading

    main_thread_id = threading.get_ident()
    captured = {"dao_thread_id": None}

    class FakeFolder:
        id = 999
        schedule_enabled = False

    def fake_get_by_id(self, folder_id):
        captured["dao_thread_id"] = threading.get_ident()
        return FakeFolder()

    monkeypatch.setattr(FavoriteDao, "get_by_id", fake_get_by_id)

    asyncio.run(sm._on_folder_trigger(999))

    assert captured["dao_thread_id"] is not None
    assert captured["dao_thread_id"] != main_thread_id, (
        "DAO get_by_id 应在非主线程执行（to_thread 调度的）"
    )
