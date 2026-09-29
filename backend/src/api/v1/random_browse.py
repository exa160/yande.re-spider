"""/api/v1/random_browse/* 路由

提供：
- GET /api/v1/random_browse/count   本地已下载图片总数（随机浏览候选池大小，磁贴角标）
- GET /api/v1/random_browse/preview  随机浏览磁贴的预览图（瀑布流场景）

设计要点：
- 复用 YandeDataRepository.query_random_for_tags(tags='', limit=N)：
  tags='' 时 _tag_filter 返回 None → 全库随机抽样
- 仅返回本地下载的图片（downloaded_only=True），保证预览图可访问
- 响应结构对齐 /api/v1/my_favorites/preview（MyFavoritePreviewResponse + MyFavoritePreviewImage），
  前端 FolderTile 渲染逻辑可直接复用（同字段、同 rating display 序列化）

随机浏览的语义边界：
- 每次刷新页面会重新抽样（与 /gallery/load?random=true 一致）
- 磁贴缩略图和瀑布流二级页的图片不保证一致（需 SQL seed 支持，已记入 docs/todo）
"""
from typing import Optional

from fastapi import APIRouter, Query

from src.common.constant import ErrMsg
from src.dao.yande_data_dao import YandeDataRepository
from src.middleware.errors import APIException
from src.models.response.base_response import BaseResponse
from src.models.response.my_favorites import (
    MyFavoriteCountResponse,
    MyFavoritePreviewImage,
    MyFavoritePreviewResponse,
)

router = APIRouter()


@router.get(
    "/count",
    response_model=BaseResponse[MyFavoriteCountResponse],
    summary="随机浏览候选池总数",
)
async def get_random_browse_count() -> BaseResponse[MyFavoriteCountResponse]:
    """返回本地已下载图片总数（随机浏览的候选池大小）。

    与 /preview 的抽样范围一致（``down_flag=True``），前端磁贴角标直接显示该值，
    不再固定显示 0。响应模型复用 ``MyFavoriteCountResponse``（单字段 count），
    避免为同一个 int 契约再声明一个同构模型。
    """
    try:
        with YandeDataRepository() as repo:
            count = repo.count_downloaded()
        return BaseResponse(
            message=ErrMsg.OK.msg,
            data=MyFavoriteCountResponse(count=count),
        )
    except Exception as e:
        raise APIException(ErrMsg.QUERY_ERROR, e=e)


@router.get(
    "/preview",
    response_model=BaseResponse[MyFavoritePreviewResponse],
    summary="随机浏览预览图",
)
async def get_random_browse_preview(
    limit: int = Query(8, ge=1, le=20, description="预览图数量上限"),
    tile_size: Optional[str] = Query(
        None,
        description="tile 尺寸占位（adaptive/small/medium/large）。与 /my_favorites/preview URL 形态保持一致",
    ),
) -> BaseResponse[MyFavoritePreviewResponse]:
    """随机抽样本地图片用作磁贴预览图。

    SQL: ``SELECT * FROM yande_data WHERE down_flag=true ORDER BY RANDOM() LIMIT N``
    每次返回不同的随机序列（无 seed）。
    """
    try:
        with YandeDataRepository() as repo:
            images = repo.query_random_for_tags(
                tags="",
                limit=limit,
                downloaded_only=True,
            )
        items = [
            MyFavoritePreviewImage(
                id=img.id,
                preview_url=None,  # 前端 FolderTile 会按 id 拼 /api/v1/gallery/cache/preview/{id}
                tags=img.tags or "",
                rating=img.rating.display if img.rating is not None else "",
            )
            for img in images
        ]
        return BaseResponse(
            message=ErrMsg.OK.msg,
            data=MyFavoritePreviewResponse(images=items),
        )
    except Exception as e:
        raise APIException(ErrMsg.QUERY_ERROR, e=e)