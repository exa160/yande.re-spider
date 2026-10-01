"""/api/v1/recent_downloads/* 路由

提供 3 个端点（收藏夹磁贴列表末尾的第三个虚拟磁贴「最近下载」）：
- GET  /api/v1/recent_downloads/count    最近下载的去重图片数（磁贴角标）
- GET  /api/v1/recent_downloads/preview  最近下载的预览图（瀑布流场景的磁贴预览）
- POST /api/v1/recent_downloads/clear    清除已完成记录（按天数 / 全清，二次确认由前端负责）

本文件由 APILoader 自动发现，挂载前缀为 ``/api/v1/recent_downloads``，router 自身
不再声明 prefix（与 random_browse.py / my_favorites.py 一致）。

==================== 数据源语义（务必先读）====================
「最近下载」的数据源是 **download_task 表的 completed_at**，不是 yande_data：
- yande_data 表没有「本地下载时间」列；created_at / updated_at 是 yande.re 图源的
  上传/更新时间（update_down_flag 刻意不更新它），与本地下载时间无关。
- 因此本期**不改表结构**，复用 download_task 的 completed_at 作为时间依据
  （设计文档 §2.1）。

筛选条件三者缺一不可（DAO 层强制）：
1. ``status == 'completed'``   —— 排除 pending/downloading/paused/failed/cancelled
2. ``completed_at IS NOT NULL`` —— 排除「文件已存在、跳过下载」分支产生的 NULL
3. ``GROUP BY image_id`` + ``MAX(completed_at)`` —— 重复下载去重，排序键取最新完成时间

==================== 已知取舍（OpenAPI 同步可见）====================
1. 用户删除下载任务记录 → 该图从「最近下载」消失，但**图片文件仍在磁盘**，
   ``yande_data.down_flag`` 不变（随机浏览 / 本地图库照常可见）。
2. 清除记录会**同时**清空下载管理页的「已完成」历史（共用同一批数据，已确认接受）。
3. 重复下载的任务 ``completed_at`` 为 NULL（``download_queue`` 跳过分支未写该字段），
   该类记录会沉底，不会出现在「最近下载」中（已确认接受）。
4. 清除**只删任务日志，不删图片文件**。

==================== 角标口径 ====================
本端点 count = ``COUNT(DISTINCT image_id)``（去重）；
``/random_browse/count`` = ``yande_data`` 表 down_flag=True 总数。
两者口径不同，正常情况下数字不会相撞。

==================== 开关 ====================
``config.favorites.enable_recent_downloads`` 只控制**前端是否显示磁贴**；
按设计文档 §6，即使开关关闭，这 3 个接口仍然可用（避免 UI 状态与后端行为耦合）。
"""
import asyncio
from typing import Optional

from fastapi import APIRouter, Query

from src.common.constant import ErrMsg
from src.middleware.errors import APIException
from src.models.response.base_response import BaseResponse
from src.models.response.my_favorites import (
    MyFavoriteCountResponse,
    MyFavoritePreviewResponse,
)
from src.models.response.recent_downloads import ClearRecordsResponse
from src.models.request.recent_downloads import ClearRecordsRequest
from src.services.download import DownloadService

router = APIRouter()


@router.get(
    "/count",
    response_model=BaseResponse[MyFavoriteCountResponse],
    summary="最近下载去重图片数（磁贴角标）",
)
async def get_recent_downloads_count() -> BaseResponse[MyFavoriteCountResponse]:
    """返回「最近下载」的去重图片数（磁贴角标）。

    口径 = ``COUNT(DISTINCT image_id)`` of completed 下载任务，与 /preview 完全同源；
    重复下载同一张图只算一次。响应模型复用 ``MyFavoriteCountResponse``
    （单字段 int），不为同一个契约再声明一个同构模型。
    """
    try:
        count = await asyncio.to_thread(DownloadService.count_completed_images)
        return BaseResponse(
            message=ErrMsg.OK.msg,
            data=MyFavoriteCountResponse(count=count),
        )
    except Exception as e:
        raise APIException(ErrMsg.QUERY_ERROR, e=e)


@router.get(
    "/preview",
    response_model=BaseResponse[MyFavoritePreviewResponse],
    summary="最近下载预览图",
)
async def get_recent_downloads_preview(
    limit: int = Query(8, ge=1, le=20, description="预览图数量上限"),
    tile_size: Optional[str] = Query(
        None,
        description="tile 尺寸占位（adaptive/small/medium/large）。"
        "与 /my_favorites/preview、/random_browse/preview URL 形态保持一致，本接口不消费该值",
    ),
) -> BaseResponse[MyFavoritePreviewResponse]:
    """返回最近 N 张下载完成的图片元数据（按完成时间倒序），用作磁贴预览图。

    ``preview_url`` 恒为 None：前端 ``FolderTile`` 会按 id 拼
    ``/api/v1/gallery/cache/preview/{id}``，与 /random_browse/preview 行为一致。
    rating 输出为 ``Rating.display``（'Safe'/'Questionable'/'Explicit'），
    与 ``MyFavoritePreviewImage.serialize_rating`` 的契约一致，前端安全模式
    模糊判断才能正确工作。
    """
    try:
        images = await asyncio.to_thread(DownloadService.get_recent_preview, limit)
        return BaseResponse(
            message=ErrMsg.OK.msg,
            data=MyFavoritePreviewResponse(images=images),
        )
    except Exception as e:
        raise APIException(ErrMsg.QUERY_ERROR, e=e)


@router.post(
    "/clear",
    response_model=BaseResponse[ClearRecordsResponse],
    summary="清除最近下载记录",
)
async def clear_recent_downloads(
    request: ClearRecordsRequest,
) -> BaseResponse[ClearRecordsResponse]:
    """清除已完成下载记录（**只删任务日志，不删图片文件**）。

    Args:
        request: ``{"mode": "before_days", "days": 30}`` 或 ``{"mode": "all"}``

    Returns:
        ``{"deleted": n}`` —— 被删除的任务记录条数

    校验与安全红线：
    - ``mode`` 非法值由 pydantic 判 422；
    - ``mode="before_days"`` 但 ``days`` 缺失 → 抛 ``APIException``（PARAM_ERROR）；
    - 删除条件由 DAO 固定为 ``status == COMPLETED AND completed_at IS NOT NULL``，
      **绝不**删除 pending/downloading/paused/failed/cancelled 记录
      （设计文档 §2.4 安全红线）。

    注意：DAO 是同步 DB 调用，必须 ``await asyncio.to_thread(...)`` 包装，
    否则会阻塞事件循环（与 ``delete_download_task`` 的既有写法一致）。
    """
    try:
        if request.mode == "before_days" and request.days is None:
            raise APIException(
                ErrMsg.PARAM_ERROR,
                data={"detail": "mode='before_days' 时必须提供 days（1-3650）"},
            )
        days = request.days if request.mode == "before_days" else None
        deleted = await asyncio.to_thread(DownloadService.delete_completed_records, days)
        return BaseResponse(
            message=ErrMsg.OK.msg,
            data=ClearRecordsResponse(deleted=deleted),
        )
    except APIException:
        raise
    except Exception as e:
        raise APIException(ErrMsg.DELETE_ERROR, e=e)
