"""/api/v1/my-favorites/* 路由

提供 5 个端点：
- GET    /my-favorites          分页列出我的最爱（按 created_at DESC）
- POST   /my-favorites/{id}     加入我的最爱（幂等；UNIQUE image_id 兜底）
- DELETE /my-favorites/{id}     取消我的最爱（幂等）
- GET    /my-favorites/count    我的最爱总数
- GET    /my-favorites/preview  我的最爱预览图元数据（独立接口，不复用 favorites 的 preview）

路由前缀说明：本文件由 APILoader 自动发现，APILoader 会把 file path（api/v1/my_favorites）
作为 URL 前缀挂载到 FastAPI app，因此 router 自身不再声明 prefix。
"""
from fastapi import APIRouter, Query

from src.common.constant import ErrMsg
from src.middleware.errors import APIException
from src.models.response.base_response import BaseResponse
from src.models.response.my_favorites import (
    MyFavoriteCountResponse,
    MyFavoritesListResponse,
    MyFavoritePreviewResponse,
)
from src.services.my_favorites import MyFavoritesService

router = APIRouter()


@router.get("", response_model=BaseResponse[MyFavoritesListResponse], summary="我的最爱列表")
async def list_my_favorites(
    page: int = Query(1, ge=1, description="页码，从 1 开始"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
) -> BaseResponse[MyFavoritesListResponse]:
    """分页列出我的最爱（按 created_at DESC）。"""
    try:
        items, total = MyFavoritesService.list_paginated(page=page, page_size=page_size)
        return BaseResponse(
            message=ErrMsg.OK.msg,
            data=MyFavoritesListResponse(
                total=total,
                page=page,
                page_size=page_size,
                # service 已把 ORM DateTime 序列化为 ISO 8601 字符串，直接传 Pydantic items 即可
                data=items,
            ),
        )
    except Exception as e:
        raise APIException(ErrMsg.QUERY_ERROR, e=e)


@router.post("/{image_id}", response_model=BaseResponse, summary="加入我的最爱")
async def add_my_favorite(image_id: int) -> BaseResponse:
    """加入我的最爱。幂等（UNIQUE image_id 兜底）。

    ValueError 表示 image_id 在 yande_data 中不存在（service 层抛出），
    统一映射为 404 NOT_FOUND，与 ErrMsg 约定保持一致。
    """
    try:
        await MyFavoritesService.add(image_id)
        return BaseResponse(message="已加入我的最爱")
    except ValueError as e:
        raise APIException(ErrMsg.NOT_FOUND, data={"detail": str(e)})
    except Exception as e:
        raise APIException(ErrMsg.CREATE_ERROR, e=e)


@router.delete("/{image_id}", response_model=BaseResponse, summary="取消我的最爱")
async def remove_my_favorite(image_id: int) -> BaseResponse:
    """取消我的最爱（幂等）。不存在不报错。"""
    try:
        MyFavoritesService.remove(image_id)
        return BaseResponse(message="已取消我的最爱")
    except Exception as e:
        raise APIException(ErrMsg.DELETE_ERROR, e=e)


@router.get("/count", response_model=BaseResponse[MyFavoriteCountResponse], summary="我的最爱总数")
async def count_my_favorites() -> BaseResponse[MyFavoriteCountResponse]:
    """我的最爱总数（用于收藏夹列表前端插入磁贴的角标）。"""
    try:
        count = MyFavoritesService.count()
        return BaseResponse(message=ErrMsg.OK.msg, data=MyFavoriteCountResponse(count=count))
    except Exception as e:
        raise APIException(ErrMsg.QUERY_ERROR, e=e)


@router.get(
    "/preview",
    response_model=BaseResponse[MyFavoritePreviewResponse],
    summary="我的最爱预览",
)
async def get_my_favorites_preview(
    limit: int = Query(20, ge=1, le=100, description="预览图数量上限"),
    tile_size: str = Query(
        "adaptive",
        description="tile 尺寸占位：adaptive/small/medium/large。本接口不直接消费该值，"
        "仅为与 /favorites/with-preview 的 URL 形态保持一致，方便前端共用 query 参数。",
        pattern="^(adaptive|small|medium|large)$",
    ),
) -> BaseResponse[MyFavoritePreviewResponse]:
    """为文件夹展示页提供我的最爱预览图（独立接口，不复用 favorites 的 preview）。

    tile_size 当前未传递给 service（service.get_preview 仅支持 limit 参数）；
    保留为 query 参数是为了前端能用同一套 URL 模板，避免对 /preview 单独写分支。
    """
    try:
        images = MyFavoritesService.get_preview(limit=limit)
        return BaseResponse(
            message=ErrMsg.OK.msg,
            data=MyFavoritePreviewResponse(images=images),
        )
    except Exception as e:
        raise APIException(ErrMsg.QUERY_ERROR, e=e)
