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
    rating: Optional[str] = Field(None, description="评分过滤")
    author: Optional[str] = Field(None, description="作者过滤")
    min_width: Optional[int] = Field(None, description="最小宽度")
    max_width: Optional[int] = Field(None, description="最大宽度")
    min_height: Optional[int] = Field(None, description="最小高度")
    max_height: Optional[int] = Field(None, description="最大高度")
    min_file_size: Optional[int] = Field(None, description="最小文件大小(KB)")
    max_file_size: Optional[int] = Field(None, description="最大文件大小(KB)")
    file_type: Optional[str] = Field(None, description="文件类型")
    sort_by: Optional[str] = Field("created_at", description="排序字段")
    sort_order: Optional[str] = Field("desc", description="排序方向")
    source: Optional[str] = Field(
        "local", description="数据源: yande=在线, local=本地数据库, hybrid=混合模式"
    )
    max_id: Optional[int] = Field(
        None, description="当前展示的最小 id，用于混合模式分页"
    )


class GalleryLoadResponse(BaseModel):
    total: int
    page: int
    page_size: int
    has_more: bool
    images: List[ImageDetail]
    has_gap: bool = Field(False, description="是否有数据断档")
    gap_before_id: Optional[int] = Field(None, description="断档位置的 id")


class BrowseStateResponse(BaseModel):
    last_max_id: Optional[int] = Field(None, description="数据库中最大 id")
    db_count: int = Field(0, description="数据库总记录数")
    newest_in_db: Optional[int] = Field(None, description="数据库最新记录 id")


class SyncOnlineRequest(BaseModel):
    max_id: Optional[int] = Field(None, description="当前展示的最小 id")
    page_size: int = Field(20, ge=1, le=100)
    tags: Optional[str] = ""


class SyncOnlineResponse(BaseModel):
    synced_count: int = Field(0, description="本次同步数量")
    new_max_id: Optional[int] = Field(None, description="同步后的新最大 id")
    has_gap: bool = Field(False, description="是否有断档")
    gap_before_id: Optional[int] = Field(None, description="断档位置")
    inserted: int = Field(0)
    updated: int = Field(0)


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
    )
    return images, total


def query_yande_api(params: dict) -> tuple[List[dict], int]:
    from backend.dao.yande_data import YandeDataRepository, _check_local_file

    yande_api = YandeApi()
    page = params.get("page", 1)
    tags = params.get("tags", "")

    success, yande_data = yande_api.get_ranking(page, tags)

    if not success:
        return [], 0

    repo = YandeDataRepository()
    images = []
    for item in yande_data.root:
        if params.get("rating") and params["rating"] != "All":
            rating_val = get_rating_value(params["rating"])
            if item.rating.value != rating_val:
                continue

        if params.get("min_width") and item.width < params["min_width"]:
            continue
        if params.get("max_width") and item.width > params["max_width"]:
            continue
        if params.get("min_height") and item.height < params["min_height"]:
            continue
        if params.get("max_height") and item.height > params["max_height"]:
            continue

        if params.get("author") and params["author"].lower() not in item.author.lower():
            continue

        file_ext = item.file_ext or "jpg"
        is_downloaded = repo.check_exists(item.id)
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
                "rating": RATING_DISPLAY_MAP.get(item.rating.value, item.rating.value),
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

    return images, len(images)


@router.post("/load", response_model=GalleryLoadResponse, summary="加载图库")
async def load_gallery(request: GalleryLoadRequest):
    try:
        from backend.dao.yande_data import YandeDataRepository

        params = request.model_dump()
        source = params.pop("source", "local")
        max_id = params.pop("max_id", None)

        has_gap = False
        gap_before_id = None

        if source == "local":
            images, total = query_local_database(params)
            has_more = len(images) >= params.get("page_size", 20)
        elif source == "hybrid":
            repo = YandeDataRepository()
            db_max_id = repo.get_max_id()

            if max_id is None:
                max_id = db_max_id

            if db_max_id and db_max_id > 0:
                db_images, db_total = repo.query_by_id_range(
                    max_id=max_id,
                    page=params.get("page", 1),
                    page_size=params.get("page_size", 20),
                )
                gap_info = repo.check_continuous(max_id)
                has_gap = gap_info["has_gap"]
                gap_before_id = gap_info["gap_before_id"]

                images = db_images
                total = db_total
                has_more = len(images) >= params.get("page_size", 20)
            else:
                images, total = query_yande_api(params)
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
            has_gap=has_gap,
            gap_before_id=gap_before_id,
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


@router.get("/browse-state", response_model=BrowseStateResponse, summary="获取浏览状态")
async def get_browse_state():
    try:
        from backend.dao.yande_data import YandeDataRepository

        repo = YandeDataRepository()
        db_max_id = repo.get_max_id()
        db_count = repo.get_count()

        return BrowseStateResponse(
            last_max_id=db_max_id,
            db_count=db_count,
            newest_in_db=db_max_id,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取浏览状态失败: {str(e)}")


@router.post(
    "/sync-online", response_model=SyncOnlineResponse, summary="同步在线数据到本地"
)
async def sync_online_data(request: SyncOnlineRequest):
    try:
        from backend.dao.yande_data import YandeDataRepository

        yande_api = YandeApi()
        repo = YandeDataRepository()

        current_max_id = repo.get_max_id()
        page = 1
        total_inserted = 0
        total_updated = 0
        synced_count = 0

        while synced_count < request.page_size:
            success, yande_data = yande_api.get_ranking(page, request.tags or "")

            if not success or not yande_data or not yande_data.root:
                break

            posts_to_save = []
            for item in yande_data.root:
                if request.max_id and item.id >= request.max_id:
                    continue

                posts_to_save.append(
                    {
                        "id": item.id,
                        "tags": item.tags,
                        "created_at": item.created_at,
                        "creator_id": item.creator_id,
                        "author": item.author,
                        "change": item.change,
                        "source": item.source,
                        "score": item.score,
                        "md5": item.md5,
                        "file_size": item.file_size,
                        "file_ext": item.file_ext,
                        "file_url": item.file_url,
                        "is_shown_in_index": item.is_shown_in_index,
                        "preview_url": item.preview_url,
                        "preview_width": item.preview_width,
                        "preview_height": item.preview_height,
                        "actual_preview_width": item.actual_preview_width,
                        "actual_preview_height": item.actual_preview_height,
                        "sample_url": item.sample_url,
                        "sample_width": item.sample_width,
                        "sample_height": item.sample_height,
                        "sample_file_size": item.sample_file_size,
                        "jpeg_url": item.jpeg_url,
                        "jpeg_width": item.jpeg_width,
                        "jpeg_height": item.jpeg_height,
                        "jpeg_file_size": item.jpeg_file_size,
                        "rating": item.rating.value
                        if hasattr(item.rating, "value")
                        else item.rating,
                        "is_rating_locked": item.is_rating_locked,
                        "has_children": item.has_children,
                        "parent_id": item.parent_id,
                        "status": item.status,
                        "is_pending": item.is_pending,
                        "width": item.width,
                        "height": item.height,
                        "is_held": item.is_held,
                    }
                )
                synced_count += 1

            if posts_to_save:
                result = repo.save_posts(posts_to_save, down_flag=False)
                total_inserted += result["inserted"]
                total_updated += result["updated"]

            page += 1

        new_max_id = repo.get_max_id()
        gap_info = repo.check_continuous(new_max_id or 0)

        return SyncOnlineResponse(
            synced_count=synced_count,
            new_max_id=new_max_id,
            has_gap=gap_info["has_gap"],
            gap_before_id=gap_info["gap_before_id"],
            inserted=total_inserted,
            updated=total_updated,
        )
    except Exception as e:
        import traceback

        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"同步失败: {str(e)}")


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
