"""
收藏夹管理 API 路由
"""

from fastapi import APIRouter

from src.common.constant import ErrMsg
from src.dao.favorite_dao import favorite_dao
from src.middleware.errors import APIException
from src.models.request.favorites import (
    FavoriteFolderCreate,
    FavoriteFolderUpdate,
    LastSyncedIdResetRequest,
    ReorderRequest,
)
from src.models.response.base_response import BaseResponse
from src.models.response.favorites import (
    FavoriteFolderPreviewResponse,
    FavoriteFolderRefreshResponse,
    FavoriteFolderResponse,
    FavoriteFolderUpdateResponse,
    FavoriteFoldersResponse,
    FavoriteFoldersWithPreviewResponse,
    FolderCountResponse,
    FolderScheduleStatusData,
    FolderScheduleStatusResponse,
    ScheduleTriggerResponse,
)
from src.services.favorites import FavoritesService

router = APIRouter()


@router.get("", response_model=FavoriteFoldersResponse, summary="获取所有收藏夹")
async def get_all_folders() -> FavoriteFoldersResponse:
    """
    获取所有收藏夹，按排序权重排列
    """
    try:
        folders = FavoritesService.get_all_folders()
        return FavoriteFoldersResponse(data=folders)
    except Exception as e:
        raise APIException(ErrMsg.QUERY_ERROR, e=e)


@router.get("/with-preview", response_model=FavoriteFoldersWithPreviewResponse, summary="获取所有收藏夹")
async def get_folders_with_preview() -> FavoriteFoldersWithPreviewResponse:
    """
    获取所有收藏夹及其图片数量
    # TODO: 文件夹图片预览
        - 考虑到性能问题，可能不适合频繁调用
        - 访问时会刷新本地数量
        - 可选接口，单纯获取列表建议调用 /api/favorites 接口
        - 适用于需要同时展示收藏夹列表和图片预览的场景
        - 可能会增加接口响应时间，视收藏夹数量和图片数量而定
        - 前端可根据实际需求选择调用哪个接口
        - 未来可能增加分页支持以优化性能
    """
    try:
        folders = FavoritesService.get_folders_with_preview()
        return FavoriteFoldersWithPreviewResponse(message=ErrMsg.OK.msg, data=folders)
    except Exception as e:
        raise APIException(ErrMsg.QUERY_ERROR, e=e)


@router.post("", response_model=FavoriteFolderResponse, summary="创建收藏夹")
async def create_folder(folder: FavoriteFolderCreate) -> FavoriteFolderResponse:
    """创建新收藏夹"""
    try:
        new_folder = FavoritesService.create_folder(folder)
        return FavoriteFolderResponse(message=ErrMsg.OK, data=new_folder)
    except Exception as e:
        raise APIException(ErrMsg.CREATE_ERROR, e=e)


@router.get("/{folder_id}", response_model=FavoriteFolderResponse, summary="获取收藏夹详情")
async def get_folder(folder_id: int) -> FavoriteFolderResponse:
    """获取指定收藏夹详情"""
    # 访问时刷新本地数量
    folder = FavoritesService._refresh_local_count(folder_id)
    if not folder:
        raise APIException(ErrMsg.FAVORITE_FOLDER_NOT_FOUND)
    return FavoriteFolderResponse(data=folder)


@router.put("/{folder_id}", response_model=FavoriteFolderUpdateResponse, summary="更新收藏夹")
async def update_folder(folder_id: int, folder: FavoriteFolderUpdate) -> FavoriteFolderUpdateResponse:
    """更新收藏夹信息"""
    try:
        updated = FavoritesService.update_folder(folder_id, folder)
    except ValueError as e:
        raise APIException(ErrMsg.SCHEDULE_INVALID_CRON, data={"detail": str(e)}, e=e)
    if not updated:
        raise APIException(ErrMsg.FAVORITE_FOLDER_NOT_FOUND)
    return FavoriteFolderUpdateResponse(message="更新成功", data=updated)


@router.delete("/{folder_id}", response_model=BaseResponse, summary="删除收藏夹")
async def delete_folder(folder_id: int) -> BaseResponse:
    """删除收藏夹"""
    success = FavoritesService.delete_folder(folder_id)
    if not success:
        raise APIException(ErrMsg.FAVORITE_FOLDER_NOT_FOUND)
    return BaseResponse(message="删除成功")


@router.post("/reorder", response_model=BaseResponse, summary="批量更新排序")
async def reorder_folders(request: ReorderRequest) -> BaseResponse:
    """批量更新收藏夹排序"""
    try:
        success = FavoritesService.reorder_folders(request.folder_ids)
        if not success:
            raise APIException(ErrMsg.UPDATE_ERROR)
        return BaseResponse(message="排序更新成功")
    except APIException:
        raise
    except Exception as e:
        raise APIException(ErrMsg.UPDATE_ERROR, e=e)


@router.get(
    "/{folder_id}/preview", response_model=FavoriteFolderPreviewResponse, summary="预览收藏夹查询结果"
)
async def preview_folder(folder_id: int, limit: int = 6) -> FavoriteFolderPreviewResponse:
    """预览收藏夹查询结果，返回前N张图片"""
    result = FavoritesService.preview_folder(folder_id, limit)
    if not result:
        raise APIException(ErrMsg.FAVORITE_FOLDER_NOT_FOUND)
    return FavoriteFolderPreviewResponse(message=ErrMsg.OK.msg, data=result)


@router.post(
    "/{folder_id}/refresh", response_model=FavoriteFolderRefreshResponse, summary="手动刷新收藏夹数量"
)
async def refresh_folder_count(folder_id: int) -> FavoriteFolderRefreshResponse:
    """手动刷新指定收藏夹的本地数量"""
    result = FavoritesService.get_folder(folder_id)
    if not result:
        raise APIException(ErrMsg.FAVORITE_FOLDER_NOT_FOUND)
    return FavoriteFolderRefreshResponse(message="刷新成功", data=result)


@router.post(
    "/{folder_id}/online-count", response_model=FolderCountResponse, summary="更新在线数量"
)
async def update_online_count(folder_id: int, count: int) -> FolderCountResponse:
    """更新收藏夹的在线图片数量"""
    success = FavoritesService.update_online_count(folder_id, count)
    if not success:
        raise APIException(ErrMsg.FAVORITE_FOLDER_NOT_FOUND)
    return FolderCountResponse(message="更新成功", data={"count": count})


@router.post(
    "/{folder_id}/refresh-online", response_model=FolderCountResponse, summary="刷新在线数量"
)
async def refresh_online_count(folder_id: int) -> FolderCountResponse:
    """从 yande.re XML API 刷新收藏夹的在线图片数量"""
    count = FavoritesService.refresh_online_count(folder_id)
    if count is None:
        raise APIException(ErrMsg.QUERY_ERROR)
    return FolderCountResponse(message="刷新成功", data={"count": count})


@router.post(
    "/{folder_id}/local-count", response_model=FolderCountResponse, summary="更新本地数量"
)
async def update_local_count(folder_id: int, count: int) -> FolderCountResponse:
    """更新收藏夹的本地图片数量"""
    success = FavoritesService.update_local_count(folder_id, count)
    if not success:
        raise APIException(ErrMsg.FAVORITE_FOLDER_NOT_FOUND)
    return FolderCountResponse(message="更新成功", data={"count": count})


@router.post(
    "/{folder_id}/schedule/trigger",
    response_model=ScheduleTriggerResponse,
    summary="手动触发收藏夹调度",
)
async def trigger_folder_schedule(folder_id: int) -> ScheduleTriggerResponse:
    from src.services.favorite_scheduler import run_folder_schedule
    folder = favorite_dao.get_by_id(folder_id)
    if not folder:
        raise APIException(ErrMsg.FAVORITE_FOLDER_NOT_FOUND)
    if not folder.schedule_enabled:
        raise APIException(ErrMsg.SCHEDULE_DISABLED)
    try:
        stats = await run_folder_schedule(folder_id)
        return ScheduleTriggerResponse(message="触发成功", data=stats)
    except Exception as e:
        raise APIException(ErrMsg.SCHEDULE_TRIGGER_ERROR, e=e)


@router.get(
    "/{folder_id}/schedule/status",
    response_model=FolderScheduleStatusResponse,
    summary="获取收藏夹调度状态",
)
async def get_folder_schedule_status(folder_id: int) -> FolderScheduleStatusResponse:
    folder = favorite_dao.get_by_id(folder_id)
    if not folder:
        raise APIException(ErrMsg.FAVORITE_FOLDER_NOT_FOUND)
    return FolderScheduleStatusResponse(
        message=ErrMsg.OK.msg,
        data=FolderScheduleStatusData.model_validate(folder),
    )


@router.post(
    "/{folder_id}/schedule/reset-sync",
    response_model=FavoriteFolderResponse,
    summary="重置 last_synced_id 同步游标",
)
async def reset_last_synced_id(
    folder_id: int,
    request: LastSyncedIdResetRequest = LastSyncedIdResetRequest(),
) -> FavoriteFolderResponse:
    """重置增量调度游标：value=null 清空（首次行为），value=整数 设为该值"""
    folder = favorite_dao.get_by_id(folder_id)
    if not folder:
        raise APIException(ErrMsg.FAVORITE_FOLDER_NOT_FOUND)
    try:
        updated = favorite_dao.reset_last_synced_id(folder_id, request.value)
    except ValueError as e:
        raise APIException(ErrMsg.SCHEDULE_INVALID_RESET, data={"detail": str(e)}, e=e)
    if not updated:
        raise APIException(ErrMsg.FAVORITE_FOLDER_NOT_FOUND)
    return FavoriteFolderResponse(message="同步游标已重置", data=updated)
