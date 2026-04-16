"""
收藏夹管理 API 路由
"""

from datetime import datetime
from typing import List

from fastapi import APIRouter, HTTPException

from backend.src.dao.favorite_dao import favorite_dao
from backend.src.models.favorite import (
    FavoriteFolderCreate,
    FavoriteFolderUpdate,
    FavoriteFolder,
    FavoriteFolderWithCount,
    ReorderRequest,
)
from backend.src.dao.yande_data import YandeDataRepository
from backend.src.infrastructure.yande_api import YandeApi

router = APIRouter()


@router.get("", response_model=List[FavoriteFolder], summary="获取所有收藏夹")
async def get_all_folders():
    """获取所有收藏夹，按排序权重排列"""
    folders = favorite_dao.get_all()
    return [
        FavoriteFolder(
            id=f.id,
            name=f.name,
            tags=f.tags,
            color=f.color,
            icon=f.icon,
            sort_order=f.sort_order,
            local_count=f.local_count or 0,
            online_count=f.online_count or 0,
            last_refresh=f.last_refresh,
            created_at=f.created_at,
            updated_at=f.updated_at,
        )
        for f in folders
    ]


@router.get(
    "/with-count",
    response_model=List[FavoriteFolderWithCount],
    summary="获取收藏夹及图片数量",
)
async def get_folders_with_count():
    """
    获取所有收藏夹及其图片数量
    本地模式直接返回 local_count（已缓存）
    不主动刷新，避免频繁查询数据库
    """
    folders = favorite_dao.get_all()

    result = []
    for f in folders:
        result.append(
            FavoriteFolderWithCount(
                id=f.id,
                name=f.name,
                tags=f.tags,
                color=f.color,
                icon=f.icon,
                sort_order=f.sort_order,
                local_count=f.local_count or 0,
                online_count=f.online_count or 0,
                last_refresh=f.last_refresh,
                created_at=f.created_at,
                updated_at=f.updated_at,
                preview_images=[],
            )
        )

    return result


@router.post("", response_model=FavoriteFolder, summary="创建收藏夹")
async def create_folder(folder: FavoriteFolderCreate):
    """创建新收藏夹，并刷新本地图片数量"""
    count = favorite_dao.count()
    new_folder = favorite_dao.create(
        name=folder.name,
        tags=folder.tags,
        color=folder.color,
        icon=folder.icon,
        sort_order=folder.sort_order if folder.sort_order else count,
    )

    # 创建时刷新本地数量
    _refresh_local_count(new_folder.id, folder.tags)

    return FavoriteFolder(
        id=new_folder.id,
        name=new_folder.name,
        tags=new_folder.tags,
        color=new_folder.color,
        icon=new_folder.icon,
        sort_order=new_folder.sort_order,
        local_count=new_folder.local_count or 0,
        online_count=new_folder.online_count or 0,
        last_refresh=new_folder.last_refresh,
        created_at=new_folder.created_at,
        updated_at=new_folder.updated_at,
    )


@router.get("/{folder_id}", response_model=FavoriteFolder, summary="获取收藏夹详情")
async def get_folder(folder_id: int):
    """
    获取指定收藏夹详情
    访问时刷新本地数量
    """
    folder = favorite_dao.get_by_id(folder_id)
    if not folder:
        raise HTTPException(status_code=404, detail="收藏夹不存在")

    # 访问时刷新本地数量
    _refresh_local_count(folder_id, folder.tags)

    # 重新获取最新数据
    folder = favorite_dao.get_by_id(folder_id)

    return FavoriteFolder(
        id=folder.id,
        name=folder.name,
        tags=folder.tags,
        color=folder.color,
        icon=folder.icon,
        sort_order=folder.sort_order,
        local_count=folder.local_count or 0,
        online_count=folder.online_count or 0,
        last_refresh=folder.last_refresh,
        created_at=folder.created_at,
        updated_at=folder.updated_at,
    )


@router.put("/{folder_id}", response_model=FavoriteFolder, summary="更新收藏夹")
async def update_folder(folder_id: int, folder: FavoriteFolderUpdate):
    """更新收藏夹信息"""
    update_data = folder.model_dump(exclude_unset=True)
    updated = favorite_dao.update(folder_id, **update_data)
    if not updated:
        raise HTTPException(status_code=404, detail="收藏夹不存在")

    # 如果 tags 变化，刷新本地数量
    if "tags" in update_data:
        _refresh_local_count(folder_id, update_data["tags"])

    # 重新获取最新数据
    updated = favorite_dao.get_by_id(folder_id)

    return FavoriteFolder(
        id=updated.id,
        name=updated.name,
        tags=updated.tags,
        color=updated.color,
        icon=updated.icon,
        sort_order=updated.sort_order,
        local_count=updated.local_count or 0,
        online_count=updated.online_count or 0,
        last_refresh=updated.last_refresh,
        created_at=updated.created_at,
        updated_at=updated.updated_at,
    )


@router.delete("/{folder_id}", summary="删除收藏夹")
async def delete_folder(folder_id: int):
    """删除收藏夹"""
    success = favorite_dao.delete(folder_id)
    if not success:
        raise HTTPException(status_code=404, detail="收藏夹不存在")
    return {"message": "删除成功"}


@router.post("/reorder", summary="批量更新排序")
async def reorder_folders(request: ReorderRequest):
    """批量更新收藏夹排序"""
    success = favorite_dao.reorder(request.folder_ids)
    if not success:
        raise HTTPException(status_code=500, detail="排序更新失败")
    return {"message": "排序更新成功"}


@router.get("/{folder_id}/preview", summary="预览收藏夹查询结果")
async def preview_folder(folder_id: int, limit: int = 6):
    """
    预览收藏夹查询结果，返回前N张图片
    同时刷新本地数量
    """
    folder = favorite_dao.get_by_id(folder_id)
    if not folder:
        raise HTTPException(status_code=404, detail="收藏夹不存在")

    try:
        search_params = _parse_tags_to_params(folder.tags)
        with YandeDataRepository() as repo:
            images, total = repo.query(
                page=1, page_size=limit, downloaded_only=True, **search_params
            )

        _refresh_local_count(folder_id, folder.tags)

        return {
            "total": total,
            "preview_images": images[:limit],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"预览失败: {str(e)}")


@router.post("/{folder_id}/refresh", summary="手动刷新收藏夹数量")
async def refresh_folder_count(folder_id: int):
    """手动刷新指定收藏夹的本地数量"""
    folder = favorite_dao.get_by_id(folder_id)
    if not folder:
        raise HTTPException(status_code=404, detail="收藏夹不存在")

    _refresh_local_count(folder_id, folder.tags)

    folder = favorite_dao.get_by_id(folder_id)
    return {
        "local_count": folder.local_count or 0,
        "online_count": folder.online_count or 0,
        "last_refresh": folder.last_refresh,
    }


@router.post("/{folder_id}/online-count", summary="更新在线数量")
async def update_online_count(folder_id: int, count: int):
    """
    更新收藏夹的在线图片数量
    由前端在瀑布流加载完成后调用
    """
    folder = favorite_dao.get_by_id(folder_id)
    if not folder:
        raise HTTPException(status_code=404, detail="收藏夹不存在")

    favorite_dao.update(folder_id, online_count=count, last_refresh=datetime.now())
    return {"online_count": count}


@router.post("/{folder_id}/refresh-online", summary="刷新在线数量")
async def refresh_online_count(folder_id: int):
    """
    从 yande.re XML API 刷新收藏夹的在线图片数量
    """
    folder = favorite_dao.get_by_id(folder_id)
    if not folder:
        raise HTTPException(status_code=404, detail="收藏夹不存在")

    yande_api = YandeApi()
    count = yande_api.get_count(folder.tags or "")

    if count < 0:
        raise HTTPException(status_code=500, detail="获取在线数量失败")

    favorite_dao.update(folder_id, online_count=count, last_refresh=datetime.now())
    return {"online_count": count}


@router.post("/{folder_id}/local-count", summary="更新本地数量")
async def update_local_count(folder_id: int, count: int):
    """
    更新收藏夹的本地图片数量
    由前端在瀑布流加载完成后调用
    """
    folder = favorite_dao.get_by_id(folder_id)
    if not folder:
        raise HTTPException(status_code=404, detail="收藏夹不存在")

    favorite_dao.update(folder_id, local_count=count, last_refresh=datetime.now())
    return {"local_count": count}


def _refresh_local_count(folder_id: int, tags: str):
    """刷新收藏夹的本地图片数量"""
    try:
        search_params = _parse_tags_to_params(tags)
        with YandeDataRepository() as repo:
            _, total = repo.query(
                page=1, page_size=1, downloaded_only=True, **search_params
            )
        favorite_dao.update(folder_id, local_count=total, last_refresh=datetime.now())
    except Exception:
        favorite_dao.update(folder_id, local_count=0, last_refresh=datetime.now())


def _parse_tags_to_params(tags_str: str) -> dict:
    """解析标签字符串为查询参数"""
    params = {}

    if not tags_str:
        return params

    parts = tags_str.split()
    for part in parts:
        if part.startswith("rating:"):
            rating = part.split(":", 1)[1]
            params["rating"] = rating
        elif part.startswith("score:>"):
            score = part.split(":", 1)[1]
            params["min_score"] = int(score)
        elif part.startswith("score:<"):
            score = part.split(":", 1)[1]
            params["max_score"] = int(score)
        elif part.startswith("order:"):
            order = part.split(":", 1)[1]
            params["sort_by"] = order
        elif part.startswith("width:>="):
            width = part.split(":", 1)[1]
            params["min_width"] = int(width)
        elif part.startswith("width:<="):
            width = part.split(":", 1)[1]
            params["max_width"] = int(width)
        elif part.startswith("height:>="):
            height = part.split(":", 1)[1]
            params["min_height"] = int(height)
        elif part.startswith("height:<="):
            height = part.split(":", 1)[1]
            params["max_height"] = int(height)
        elif part.startswith("ext:"):
            ext = part.split(":", 1)[1]
            params["file_type"] = ext
        elif not part.startswith("-"):
            if "tags" not in params:
                params["tags"] = []
            if isinstance(params["tags"], list):
                params["tags"].append(part)

    if "tags" in params and isinstance(params["tags"], list):
        params["tags"] = " ".join(params["tags"])

    return params
