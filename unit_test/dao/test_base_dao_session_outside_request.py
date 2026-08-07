"""验证 BaseDAO 单例在无请求上下文时抛 RuntimeError

背景：原代码 try/except Exception 兜底，导致后台调度/CLI 等无请求上下文
场景静默创建未托管 Session，连接泄漏。
修复后与 RequestSessionMiddleware.get_session() 严格模式一致。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]) + "/backend")

import pytest


def test_base_dao_session_raises_when_no_request_context():
    """无请求上下文时，BaseDAO 单例 session 属性必须抛 RuntimeError"""
    from src.dao.favorite_dao import FavoriteDao
    from src.dao.download_task_dao import DownloadTaskDao
    from src.dao.yande_data_dao import YandeDataRepository
    from src.dao.tag_dao import TagRepository

    for dao_class in (FavoriteDao, DownloadTaskDao, YandeDataRepository, TagRepository):
        dao = dao_class()
        with pytest.raises(RuntimeError, match="RequestSessionMiddleware not active"):
            _ = dao.session
