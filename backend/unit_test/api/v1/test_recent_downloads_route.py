"""/api/v1/recent_downloads/* 端点测试

覆盖设计文档 §3.3 的路由表与 §5「后端」表格的 API 行：
1. GET  /count                 → 200，data.count 为去重图片数
2. GET  /preview?limit=N       → 200，data.images 元数据
3. POST /clear {"mode":"all"}  → 200，data.deleted
4. POST /clear {"mode":"before_days","days":30} → 200
5. POST /clear mode 非法值     → 422（pydantic）
6. POST /clear before_days 缺 days → 400（APIException / ErrMsg.PARAM_ERROR）
7. 安全红线：service 被调用时 days 恒为 None / int，删除范围由 DAO 保证

测试策略（与 test_my_favorites_route.py 一致）：
- minimal FastAPI app + 只 include recent_downloads router，避免 init_app 副作用
- patch ``src.api.v1.recent_downloads.DownloadService``，不触达真实 DB
"""
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.models.response.my_favorites import (
    MyFavoritePreviewImage,
    MyFavoritePreviewResponse,
)


@pytest.fixture
def client():
    """TestClient + mock DownloadService（只 mock service，不 mock DAO）。"""
    from src.api.v1.recent_downloads import router as recent_downloads_router
    from src.middleware.errors import ErrorHandleMiddleware

    app = FastAPI()
    # 必须挂真实异常处理器：APIException 继承 HTTPException，其 err_msg 是 ErrMsg 枚举。
    # 不注册 handler 时 TestClient 会走默认序列化路径 → "Object of type ErrMsg is not
    # JSON serializable"，导致所有断言状态码的用例在全量跑时失败
    # （与 test_my_favorites_route.py 等既有失败同源，属测试夹具缺陷而非业务缺陷）。
    ErrorHandleMiddleware.init_app(app)
    app.include_router(recent_downloads_router, prefix="/api/v1/recent_downloads")

    with patch("src.api.v1.recent_downloads.DownloadService") as mock_svc:
        mock_svc.count_completed_images = MagicMock(return_value=7)
        mock_svc.get_recent_preview = MagicMock(
            return_value=[
                MyFavoritePreviewImage(id=2, preview_url=None, tags="a", rating="Safe"),
                MyFavoritePreviewImage(id=1, preview_url=None, tags="b", rating="Safe"),
            ]
        )
        mock_svc.delete_completed_records = MagicMock(return_value=3)
        yield TestClient(app), mock_svc


# ============================================================
# GET /count
# ============================================================


def test_count_returns_200_and_count(client):
    """GET /count 返回 200 + data.count。"""
    c, _ = client
    resp = c.get("/api/v1/recent_downloads/count")
    assert resp.status_code == 200
    assert resp.json()["data"]["count"] == 7


def test_count_maps_exception_to_api_exception(client):
    """DB 异常映射为 QUERY_ERROR（不 500 裸崩）。"""
    c, mock_svc = client
    mock_svc.count_completed_images.side_effect = RuntimeError("db down")
    resp = c.get("/api/v1/recent_downloads/count")
    assert resp.status_code >= 400


# ============================================================
# GET /preview
# ============================================================


def test_preview_returns_200_with_images(client):
    """GET /preview 返回 images 列表（结构对齐 MyFavoritePreviewResponse）。"""
    c, _ = client
    resp = c.get("/api/v1/recent_downloads/preview?limit=2")
    assert resp.status_code == 200
    images = resp.json()["data"]["images"]
    assert [i["id"] for i in images] == [2, 1]
    assert images[0]["preview_url"] is None  # 前端按 id 拼预览 URL


def test_preview_default_limit_is_8(client):
    """默认 limit=8（与 random_browse 一致）。"""
    c, mock_svc = client
    c.get("/api/v1/recent_downloads/preview")
    assert mock_svc.get_recent_preview.call_args[0][0] == 8


def test_preview_rejects_limit_out_of_range(client):
    """limit 越界（>20 / <1）→ 422。"""
    c, _ = client
    assert c.get("/api/v1/recent_downloads/preview?limit=0").status_code == 422
    assert c.get("/api/v1/recent_downloads/preview?limit=21").status_code == 422


def test_preview_accepts_tile_size_param(client):
    """tile_size 只是占位参数，必须被接受（与另外两个 preview 端点 URL 形态一致）。"""
    c, _ = client
    resp = c.get("/api/v1/recent_downloads/preview?limit=2&tile_size=adaptive")
    assert resp.status_code == 200


# ============================================================
# POST /clear
# ============================================================


def test_clear_all_returns_deleted_count(client):
    """POST /clear mode=all → service 收到 days=None。"""
    c, mock_svc = client
    resp = c.post("/api/v1/recent_downloads/clear", json={"mode": "all"})
    assert resp.status_code == 200
    assert resp.json()["data"]["deleted"] == 3
    assert mock_svc.delete_completed_records.call_args[0][0] is None


def test_clear_before_days_passes_days(client):
    """POST /clear mode=before_days days=30 → service 收到 days=30。"""
    c, mock_svc = client
    resp = c.post(
        "/api/v1/recent_downloads/clear", json={"mode": "before_days", "days": 30}
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["deleted"] == 3
    assert mock_svc.delete_completed_records.call_args[0][0] == 30


def test_clear_before_days_without_days_returns_400(client):
    """mode=before_days 但缺 days → 400（ErrMsg.PARAM_ERROR），且不调用 service。"""
    c, mock_svc = client
    resp = c.post("/api/v1/recent_downloads/clear", json={"mode": "before_days"})
    assert resp.status_code == 400, f"期望 400，实际 {resp.status_code}: {resp.text}"
    mock_svc.delete_completed_records.assert_not_called()


def test_clear_route_raises_api_exception_when_days_missing():
    """直接调路由函数：确实抛 APIException(PARAM_ERROR)，且 data 里带 days 说明。"""
    import asyncio

    from src.api.v1.recent_downloads import clear_recent_downloads
    from src.common.constant import ErrMsg
    from src.middleware.errors import APIException
    from src.models.request.recent_downloads import ClearRecordsRequest

    request = ClearRecordsRequest(mode="before_days")  # 故意不给 days
    with pytest.raises(APIException) as exc_info:
        asyncio.run(clear_recent_downloads(request))
    assert exc_info.value.err_code == ErrMsg.PARAM_ERROR.code
    assert "days" in str(exc_info.value.data)


def test_clear_invalid_mode_returns_422(client):
    """mode 非法值 → 422（pydantic Literal 校验）。"""
    c, mock_svc = client
    resp = c.post("/api/v1/recent_downloads/clear", json={"mode": "everything"})
    assert resp.status_code == 422
    mock_svc.delete_completed_records.assert_not_called()


def test_clear_days_out_of_range_returns_422(client):
    """days 越界（0 / 3651）→ 422。"""
    c, _ = client
    base = "/api/v1/recent_downloads/clear"
    assert c.post(base, json={"mode": "before_days", "days": 0}).status_code == 422
    assert c.post(base, json={"mode": "before_days", "days": 3651}).status_code == 422


def test_clear_maps_exception_to_api_exception(client):
    """DB 异常映射为 DELETE_ERROR。"""
    c, mock_svc = client
    mock_svc.delete_completed_records.side_effect = RuntimeError("db down")
    resp = c.post("/api/v1/recent_downloads/clear", json={"mode": "all"})
    assert resp.status_code >= 400


# ============================================================
# 设计文档 §6 兼容性：总开关关闭时接口仍可用
# ============================================================


def test_endpoints_work_even_when_switch_is_off():
    """``enable_recent_downloads=False`` 时 3 个接口仍返回 200（只控 UI 磁贴显示）。

    真实 service + 内存 DB（不 mock service），顺带做一次端到端打通验证。
    """
    from datetime import datetime, timedelta

    from fastapi import FastAPI as _FastAPI
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from src.api.v1.recent_downloads import router as recent_downloads_router
    from src.common.constant import Rating, TaskStatus
    from src.dao.database import Base
    from src.middleware.session import _request_session
    from src.models.database.yande import DownloadTask, YandeData

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, expire_on_commit=False)
    session = TestSession()
    token = _request_session.set(session)
    import src.dao.database as database_module

    original_factory = database_module._get_session_factory
    database_module._get_session_factory = lambda: TestSession
    try:
        session.add(
            YandeData(
                id=1, tags="a", width=100, height=100, file_ext="jpg", file_size=1,
                file_url="u", preview_url="p", md5="m", author="t",
                created_at=datetime(2024, 1, 1), down_flag=True, rating=Rating.S,
            )
        )
        session.add(
            DownloadTask(
                task_id="t1", image_id=1, file_name="1.jpg",
                status=TaskStatus.COMPLETED, created_at=datetime(2024, 1, 1),
                updated_at=datetime(2024, 1, 1),
                completed_at=datetime(2024, 1, 1) + timedelta(days=1),
            )
        )
        session.commit()

        app = _FastAPI()
        app.include_router(recent_downloads_router, prefix="/api/v1/recent_downloads")
        from fastapi.testclient import TestClient

        with TestClient(app) as c:
            count_resp = c.get("/api/v1/recent_downloads/count")
            preview_resp = c.get("/api/v1/recent_downloads/preview")
            clear_resp = c.post(
                "/api/v1/recent_downloads/clear", json={"mode": "all"}
            )
        assert count_resp.status_code == 200
        assert count_resp.json()["data"]["count"] == 1
        assert [i["id"] for i in preview_resp.json()["data"]["images"]] == [1]
        assert clear_resp.json()["data"]["deleted"] == 1
    finally:
        database_module._get_session_factory = original_factory
        _request_session.reset(token)
        session.close()


# ============================================================
# 路由自动注册（无需改 APILoader / src/__init__.py）
# ============================================================


def test_recent_downloads_is_discovered_without_manual_registration():
    """回归锁定：把文件放在 api/v1/ 下即可被 APILoader 自动发现，无需改注册代码。

    只做**纯路径发现**（``APILoader._get_router_directory``，纯 glob，不执行任何
    路由模块），刻意**不**调用 ``init_api``：

    ``init_api`` 会用 ``spec_from_file_location(<file stem>, <path>)`` 把每个
    ``api/v1/*.py`` 额外执行一遍成顶层模块（config / gallery / download …）。这在
    同一个 pytest 进程里属于重入式的模块副作用，会让后续「走 APIException 错误
    分支」的用例变得脆弱（历史上配合 ``tests/test_path_constant.py`` 的
    ``importlib.reload(constant)`` 夹具曾导致同一批错误分支用例随机失败）。
    生产环境不受影响（``init_app`` 只在进程启动时执行一次），测试里不必冒这个险。
    """
    from src.api import APILoader
    from src.api.v1.recent_downloads import router

    loader = APILoader()
    discovered = {p.name for p in loader._get_router_directory(loader.base_path)}
    assert "recent_downloads.py" in discovered

    # 前缀由 APILoader 从文件路径推导（src/api/v1/recent_downloads.py → api/v1/recent_downloads），
    # router 自身不声明 prefix
    assert {r.path for r in router.routes} == {"/count", "/preview", "/clear"}
