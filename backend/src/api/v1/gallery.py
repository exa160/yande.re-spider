"""
图库展示相关API路由
"""
import asyncio
from typing import List

from fastapi import APIRouter, Query
from fastapi.responses import FileResponse

from src.common.constant import ErrMsg
from src.middleware.errors import APIException
from src.models.request.gallery import GalleryLoadRequest
from src.models.response.base_response import BaseResponse
from src.models.response.gallery import (
    ImageDetail,
    GalleryLoadResponse,
    ImageDetailResponse,
)
from src.services.gallery import GalleryService

router = APIRouter()


@router.post("/load", response_model=GalleryLoadResponse, summary="加载图库")
async def load_gallery(request: GalleryLoadRequest) -> GalleryLoadResponse:
    """加载图库数据（支持本地/在线模式）"""
    if request.source == "local":
        images, total = await asyncio.to_thread(GalleryService.query_local_database, request)
    else:
        images, total = await asyncio.to_thread(GalleryService.query_yande_api, request)

    has_more = len(images) >= request.page_size

    return GalleryLoadResponse(
        message=ErrMsg.OK.msg,
        data=images,
        total=total,
        page=request.page,
        page_size=request.page_size,
        has_more=has_more
        )


@router.get(
    "/image/{image_id}", response_model=ImageDetailResponse, summary="获取图片详情"
)
async def get_image_detail(
    image_id: int, source: str = Query("local", description="数据源")
) -> ImageDetailResponse:
    """获取单张图片详情"""
    image = await asyncio.to_thread(GalleryService.get_image_by_id, image_id, source)
    if not image:
        raise APIException(ErrMsg.NOT_FOUND)
    return ImageDetailResponse(message=ErrMsg.OK.msg, data=ImageDetail(**image))


@router.post(
    "/convert-to-download", response_model=BaseResponse, summary="转换为下载任务"
)
async def convert_to_download_task(
    image_ids: List[int], save_path: str
) -> BaseResponse:
    """将图片转换为下载任务"""
    return BaseResponse(
        message=f"成功创建 {len(image_ids)} 个下载任务"
    )


@router.get("/statistics", response_model=BaseResponse, summary="获取图库统计")
async def get_gallery_statistics(
    source: str = Query("local", description="数据源"),
) -> BaseResponse:
    """获取图库统计信息"""
    try:
        stats = GalleryService.get_statistics(source)
        return BaseResponse(message=ErrMsg.OK.msg, data=stats)
    except Exception as e:
        raise APIException(ErrMsg.QUERY_ERROR, e=e)


@router.get("/cache/preview/{image_id}", summary="获取预览图文件")
async def get_preview_image(image_id: int):
    """获取预览图文件"""
    preview_path = GalleryService.get_preview_path(f"{image_id}.jpg")
    if preview_path.exists():
        return FileResponse(str(preview_path))
    raise APIException(ErrMsg.NOT_FOUND)


@router.get("/cache/preview/generate/{image_id}", summary="生成预览图")
async def generate_preview_from_original(image_id: int, file_ext: str = "jpg"):
    """从原图生成预览图"""
    preview_path = await asyncio.get_event_loop().run_in_executor(
        None, GalleryService.generate_preview, image_id, file_ext
    )
    if preview_path:
        return FileResponse(str(preview_path))
    raise APIException(ErrMsg.NOT_FOUND)


@router.get("/cache/preview/local/{image_id}", summary="本地模式获取预览图")
async def get_preview_for_local(image_id: int):
    """本地模式获取预览图 - 优先从原图生成，其次从远程下载"""
    preview_path = await asyncio.get_event_loop().run_in_executor(
        None, GalleryService.get_preview_for_local, image_id
    )
    if preview_path:
        return FileResponse(str(preview_path))
    raise APIException(ErrMsg.NOT_FOUND)


@router.get("/cache/preview/fetch/{image_id}", summary="获取并缓存预览图")
async def fetch_and_cache_preview(image_id: int):
    """从远程获取并缓存预览图"""
    preview_path = await asyncio.get_event_loop().run_in_executor(
        None, GalleryService.fetch_and_cache_preview, image_id
    )
    if preview_path:
        return FileResponse(str(preview_path))
    raise APIException(ErrMsg.NOT_FOUND)


@router.get("/cache/original/{filename}", summary="获取原图文件")
async def get_original_image(filename: str):
    """获取原图文件"""
    original_path = GalleryService.get_original_path(filename)
    if original_path.exists():
        return FileResponse(str(original_path))
    raise APIException(ErrMsg.NOT_FOUND)
