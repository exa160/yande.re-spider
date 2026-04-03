"""
图库展示相关API路由
"""

from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Optional, List

from backend.infrastructure.yande_api import YandeApi
from backend.config.constant import (
    DOWNLOADS_DIR,
    TIMEOUT_PREVIEW,
    THUMBNAIL_MAX_SIZE,
    THUMBNAIL_QUALITY,
    RATING_DISPLAY_MAP,
)

router = APIRouter()


class ImageDetail(BaseModel):
    id: int
    tags: List[str]
    width: int
    height: int
    rating: str
    file_url: str
    preview_url: str
    sample_url: Optional[str]
    file_size: int
    file_ext: str
    author: str
    created_at: str
    md5: str
    score: Optional[int]
    is_downloaded: bool = Field(description="是否已下载")
    local_preview_path: Optional[str] = Field(None, description="本地预览图路径")
    local_file_path: Optional[str] = Field(None, description="本地原图路径")


class GalleryLoadRequest(BaseModel):
    page: int = Field(1, ge=1, description="页码")
    page_size: int = Field(20, ge=1, le=100, description="每页数量")
    tags: Optional[str] = Field(None, description="标签过滤")
    ratings: List[str] = Field(default_factory=list, description="评分过滤列表")
    author: Optional[str] = Field(None, description="作者过滤")
    min_width: Optional[int] = Field(None, description="最小宽度")
    max_width: Optional[int] = Field(None, description="最大宽度")
    min_height: Optional[int] = Field(None, description="最小高度")
    max_height: Optional[int] = Field(None, description="最大高度")
    min_file_size: Optional[int] = Field(None, description="最小文件大小(KB)")
    max_file_size: Optional[int] = Field(None, description="最大文件大小(KB)")
    file_types: List[str] = Field(default_factory=list, description="文件类型列表")
    min_score: Optional[int] = Field(None, description="最小评分")
    max_score: Optional[int] = Field(None, description="最大评分")
    order: Optional[str] = Field("date", description="排序: date, id, score")
    sort_order: Optional[str] = Field("desc", description="排序方向: desc, asc")
    source: Optional[str] = Field(
        "local", description="数据源: yande=在线, local=本地数据库"
    )


class GalleryLoadResponse(BaseModel):
    total: int
    page: int
    page_size: int
    has_more: bool
    images: List[ImageDetail]


def get_rating_value(rating_str: str) -> str:
    mapping = {
        "Safe": "s",
        "Questionable": "q",
        "Explicit": "e",
        "s": "s",
        "q": "q",
        "e": "e",
        "S": "s",
        "Q": "q",
        "E": "e",
    }
    return mapping.get(rating_str, rating_str)


def query_local_database(params: dict) -> tuple[List[dict], int]:
    from backend.dao.yande_data import YandeDataRepository

    repo = YandeDataRepository()
    images, total = repo.query(
        page=params.get("page", 1),
        page_size=params.get("page_size", 20),
        tags=params.get("tags"),
        rating=params.get("rating"),
        author=params.get("author"),
        min_width=params.get("min_width"),
        max_width=params.get("max_width"),
        min_height=params.get("min_height"),
        max_height=params.get("max_height"),
        min_file_size=params.get("min_file_size"),
        max_file_size=params.get("max_file_size"),
        file_type=params.get("file_type"),
        sort_by=params.get("sort_by", "created_at"),
        sort_order=params.get("sort_order", "desc"),
        downloaded_only=True,
    )
    return images, total


def query_yande_api(params: dict) -> tuple[List[dict], int]:
    from backend.dao.yande_data import YandeDataRepository, _check_local_file
    from backend.dao.database import MariaDBClient
    from backend.models.yande import Rating, YandeSearchTags
    from datetime import datetime as dt

    yande_api = YandeApi()
    page = params.get("page", 1)

    search_tags = YandeSearchTags(
        min_width=params.get("min_width"),
        max_width=params.get("max_width"),
        min_height=params.get("min_height"),
        max_height=params.get("max_height"),
        min_score=params.get("min_score"),
        max_score=params.get("max_score"),
        min_filesize=params.get("min_file_size"),
        max_filesize=params.get("max_file_size"),
        ratings=params.get("ratings", []),
        file_exts=params.get("file_types", []),
        order=params.get("order", "date"),
    )

    author_tags = params.get("author", "")
    success, yande_data = yande_api.get_ranking(
        page, tags=author_tags, search_tags=search_tags
    )

    if not success:
        return [], 0

    repo = YandeDataRepository()
    client = MariaDBClient()
    images = []

    for item in yande_data.root:
        file_ext = item.file_ext or "jpg"
        record_exists = repo.check_exists(item.id)
        is_downloaded = repo.check_downloaded(item.id)

        if not record_exists:
            rating_val = item.rating.value if item.rating else "s"
            if rating_val == "s":
                rating = Rating.S
            elif rating_val == "q":
                rating = Rating.R15
            else:
                rating = Rating.R18

            new_record = client.YandeData(
                id=item.id,
                tags=item.tags or "",
                created_at=item.created_at or dt.now(),
                updated_at=item.updated_at or dt.now(),
                creator_id=item.creator_id,
                author=item.author or "",
                change=item.change or 0,
                source=item.source or "",
                score=item.score or 0,
                md5=item.md5 or "",
                file_size=item.file_size or 0,
                file_ext=file_ext,
                file_url=item.file_url or "",
                is_shown_in_index=item.is_shown_in_index
                if hasattr(item, "is_shown_in_index")
                else True,
                preview_url=item.preview_url or "",
                preview_width=item.preview_width or 0,
                preview_height=item.preview_height or 0,
                actual_preview_width=item.actual_preview_width or 0,
                actual_preview_height=item.actual_preview_height or 0,
                sample_url=item.sample_url or "",
                sample_width=item.sample_width or 0,
                sample_height=item.sample_height or 0,
                sample_file_size=item.sample_file_size or 0,
                jpeg_url=item.jpeg_url or "",
                jpeg_width=item.jpeg_width or 0,
                jpeg_height=item.jpeg_height or 0,
                jpeg_file_size=item.jpeg_file_size or 0,
                rating=rating,
                is_rating_locked=item.is_rating_locked
                if hasattr(item, "is_rating_locked")
                else False,
                has_children=item.has_children
                if hasattr(item, "has_children")
                else False,
                parent_id=item.parent_id,
                status=item.status or "active",
                is_pending=item.is_pending if hasattr(item, "is_pending") else False,
                width=item.width or 0,
                height=item.height or 0,
                is_held=item.is_held if hasattr(item, "is_held") else False,
                down_flag=False,
            )
            try:
                client.insert_data(new_record)
            except Exception as e:
                pass

        local_preview = (
            _check_local_file(item.id, file_ext, "preview") if is_downloaded else None
        )
        local_original = (
            _check_local_file(item.id, file_ext, "original") if is_downloaded else None
        )

        images.append(
            {
                "id": item.id,
                "tags": item.tags.split() if item.tags else [],
                "width": item.width,
                "height": item.height,
                "rating": RATING_DISPLAY_MAP.get(item.rating.value, item.rating.value)
                if item.rating
                else "Safe",
                "file_url": item.file_url,
                "preview_url": item.preview_url,
                "sample_url": item.sample_url,
                "file_size": item.file_size,
                "file_ext": file_ext,
                "author": item.author,
                "created_at": str(item.created_at),
                "md5": item.md5,
                "score": item.score,
                "is_downloaded": is_downloaded,
                "local_preview_path": local_preview,
                "local_file_path": local_original,
            }
        )

    client.close()
    return images, len(images)


@router.post("/load", response_model=GalleryLoadResponse, summary="加载图库")
async def load_gallery(request: GalleryLoadRequest):
    try:
        params = request.model_dump()
        source = params.pop("source", "local")

        if source == "local":
            images, total = query_local_database(params)
            has_more = len(images) >= params.get("page_size", 20)
        else:
            images, total = query_yande_api(params)
            has_more = len(images) >= params.get("page_size", 20)

        return GalleryLoadResponse(
            total=total,
            page=request.page,
            page_size=request.page_size,
            has_more=has_more,
            images=images,
        )
    except Exception as e:
        import traceback

        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"加载失败: {str(e)}")


@router.get("/image/{image_id}", response_model=ImageDetail, summary="获取图片详情")
async def get_image_detail(
    image_id: int, source: str = Query("local", description="数据源")
):
    try:
        if source == "local":
            images, _ = query_local_database({"page": 1, "page_size": 1})
            for img in images:
                if img["id"] == image_id:
                    return ImageDetail(**img)
        else:
            images, _ = query_yande_api({"page": 1, "page_size": 100})
            for img in images:
                if img["id"] == image_id:
                    return ImageDetail(**img)

        raise HTTPException(status_code=404, detail="图片不存在")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


@router.get("/preview/{image_id}", summary="获取图片预览")
async def get_image_preview(image_id: int):
    return {"preview_url": "", "sample_url": "", "file_url": ""}


@router.post("/convert-to-download", summary="转换为下载任务")
async def convert_to_download_task(image_ids: List[int], save_path: str):
    return {"message": f"成功创建 {len(image_ids)} 个下载任务", "task_ids": []}


@router.get("/statistics", summary="获取图库统计")
async def get_gallery_statistics(source: str = Query("local", description="数据源")):
    try:
        if source == "local":
            images, total = query_local_database({"page": 1, "page_size": 10000})
            downloaded = total
        else:
            total = 0
            downloaded = 0

        rating_distribution = {"Safe": 0, "Questionable": 0, "Explicit": 0}
        for img in images:
            rating = img.get("rating", "Safe")
            if rating in rating_distribution:
                rating_distribution[rating] += 1

        return {
            "total_images": total,
            "downloaded_images": downloaded,
            "rating_distribution": rating_distribution,
            "file_type_distribution": {},
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"统计失败: {str(e)}")


@router.get("/cache/preview/{filename}")
async def get_preview_image(filename: str):
    from fastapi.responses import FileResponse
    from pathlib import Path

    preview_path = DOWNLOADS_DIR / "previews" / filename
    if preview_path.exists():
        return FileResponse(str(preview_path))
    return {"error": "Preview not found"}


@router.get("/cache/preview/generate/{image_id}")
async def generate_preview_from_original(image_id: int, file_ext: str = "jpg"):
    from fastapi.responses import FileResponse, JSONResponse
    from pathlib import Path
    import asyncio
    from backend.infrastructure.image_cache import ImageCache

    cache = ImageCache()
    preview_path = cache.PREVIEWS_DIR / f"{image_id}.{file_ext}"

    if preview_path.exists():
        return FileResponse(str(preview_path))

    original_path = cache.ORIGINALS_DIR / f"{image_id}.{file_ext}"
    if not original_path.exists():
        return JSONResponse({"error": "Original not found"}, status_code=404)

    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, generate_thumbnail, str(original_path), str(preview_path)
        )
        if preview_path.exists():
            return FileResponse(str(preview_path))
        return JSONResponse({"error": "Failed to generate preview"}, status_code=500)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/cache/preview/fetch/{image_id}")
async def fetch_and_cache_preview(
    image_id: int, preview_url: str = None, file_ext: str = "jpg"
):
    from fastapi.responses import FileResponse, JSONResponse
    from pathlib import Path
    import asyncio
    from backend.infrastructure.image_cache import ImageCache

    cache = ImageCache()
    preview_path = cache.PREVIEWS_DIR / f"{image_id}.{file_ext}"

    if preview_path.exists():
        return FileResponse(str(preview_path))

    if not preview_url:
        return JSONResponse({"error": "preview_url required"}, status_code=400)

    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, download_preview_image, preview_url, str(preview_path)
        )
        if preview_path.exists():
            return FileResponse(str(preview_path))
        return JSONResponse({"error": "Failed to download preview"}, status_code=500)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


def generate_thumbnail(
    original_path: str, preview_path: str, max_size: int = THUMBNAIL_MAX_SIZE
):
    from PIL import Image

    img = Image.open(original_path)
    img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
    if img.mode == "RGBA":
        img = img.convert("RGB")
    img.save(preview_path, "JPEG", quality=THUMBNAIL_QUALITY)


def download_preview_image(preview_url: str, preview_path: str):
    import requests
    from backend.config.settings import config

    proxies = config.yande_api.proxies if config.yande_api.proxies else None
    resp = requests.get(preview_url, proxies=proxies, timeout=TIMEOUT_PREVIEW)
    if resp.status_code == 200:
        with open(preview_path, "wb") as f:
            f.write(resp.content)


@router.get("/cache/original/{filename}")
async def get_original_image(filename: str):
    from fastapi.responses import FileResponse
    from pathlib import Path

    original_path = DOWNLOADS_DIR / "originals" / filename
    if original_path.exists():
        return FileResponse(str(original_path))
    return {"error": "Original not found"}
