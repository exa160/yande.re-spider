"""
下载管理相关API路由
"""

from typing import Optional, List

from fastapi import APIRouter, HTTPException, Query

from src.common.constant import TaskStatus, ErrMsg
from src.middleware.errors import APIException
from src.models.request.download import DownloadTaskCreate
from src.models.response.base_response import BaseResponse
from src.models.response.common import (
    TaskCreatedResponse,
    TaskCreatedData,
    BatchTaskCreatedResponse,
    BatchTaskCreatedData,
)
from src.models.response.download import (
    ProgressData,
    ProgressResponse,
    TaskListResponse,
    DownloadTaskResponse,
)
from src.services.download import DownloadService

router = APIRouter()


@router.post("/task", response_model=TaskCreatedResponse, summary="创建下载任务")
async def create_download_task(task: DownloadTaskCreate) -> TaskCreatedResponse:
    """创建单个下载任务"""
    try:
        task_id = await DownloadService.create_task(task.model_dump())
        return TaskCreatedResponse(
            message="下载任务创建成功", data=TaskCreatedData(task_id=task_id)
        )
    except Exception as e:
        raise APIException(ErrMsg.CREATE_ERROR, e=e)


@router.post(
    "/task/batch", response_model=BatchTaskCreatedResponse, summary="批量创建下载任务"
)
async def create_batch_download_tasks(
    tasks: List[DownloadTaskCreate],
) -> BatchTaskCreatedResponse:
    """批量创建下载任务"""
    try:
        task_ids = await DownloadService.create_batch_tasks(
            [task.model_dump() for task in tasks]
        )
        return BatchTaskCreatedResponse(
            message=f"成功创建 {len(task_ids)} 个下载任务",
            data=BatchTaskCreatedData(task_ids=task_ids),
        )
    except Exception as e:
        raise APIException(ErrMsg.CREATE_ERROR, e=e)


@router.get("/tasks", response_model=TaskListResponse, summary="获取任务列表")
async def get_download_tasks(
    status: Optional[TaskStatus] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> TaskListResponse:
    """获取下载任务列表（支持状态过滤和分页）"""
    try:
        tasks, total = DownloadService.get_tasks(status, page, page_size)
        return TaskListResponse(
            total=total,
            page=page,
            page_size=page_size,
            data=tasks
        )
    except Exception as e:
        raise APIException(ErrMsg.QUERY_ERROR, e=e)


@router.get(
    "/task/{task_id}", response_model=DownloadTaskResponse, summary="获取任务详情"
)
async def get_download_task(task_id: str) -> DownloadTaskResponse:
    """获取单个任务详情"""
    task = DownloadService.get_task(task_id)
    if not task:
        raise APIException(ErrMsg.TASK_NOT_FOUND)
    return DownloadTaskResponse(message=ErrMsg.OK.msg, data=task)


@router.get(
    "/task/{task_id}/progress", response_model=ProgressResponse, summary="获取任务进度"
)
async def get_task_progress(task_id: str) -> ProgressResponse:
    """获取任务进度"""
    progress = DownloadService.get_task_progress(task_id)
    if not progress:
        raise APIException(ErrMsg.TASK_NOT_FOUND)
    return ProgressResponse(message=ErrMsg.OK.msg, data=ProgressData(**progress))


@router.post("/task/{task_id}/start", response_model=BaseResponse, summary="启动任务")
async def start_download_task(task_id: str) -> BaseResponse:
    """启动下载任务"""
    success, message = await DownloadService.start_task(task_id)
    if not success:
        raise APIException(ErrMsg.TASK_START_ERROR if "不存在" not in message else ErrMsg.NOT_FOUND, data={"detail": message})
    return BaseResponse(message=message)


@router.post("/task/{task_id}/pause", response_model=BaseResponse, summary="暂停任务")
async def pause_download_task(task_id: str) -> BaseResponse:
    """暂停下载任务"""
    success, message = DownloadService.pause_task(task_id)
    if not success:
        raise APIException(ErrMsg.TASK_PAUSE_ERROR if "不存在" not in message else ErrMsg.NOT_FOUND, data={"detail": message})
    return BaseResponse(message=message)


@router.post("/task/{task_id}/resume", response_model=BaseResponse, summary="恢复任务")
async def resume_download_task(task_id: str) -> BaseResponse:
    """恢复下载任务"""
    success, message = await DownloadService.resume_task(task_id)
    if not success:
        raise APIException(ErrMsg.TASK_RESUME_ERROR if "不存在" not in message else ErrMsg.NOT_FOUND, data={"detail": message})
    return BaseResponse(message=message)


@router.post("/task/{task_id}/cancel", response_model=BaseResponse, summary="取消任务")
async def cancel_download_task(task_id: str) -> BaseResponse:
    """取消下载任务"""
    success, message = DownloadService.cancel_task(task_id)
    if not success:
        raise APIException(ErrMsg.TASK_CANCEL_ERROR if "不存在" not in message else ErrMsg.NOT_FOUND, data={"detail": message})
    return BaseResponse(message=message)


@router.delete("/task/{task_id}", response_model=BaseResponse, summary="删除任务")
async def delete_download_task(task_id: str) -> BaseResponse:
    """删除下载任务"""
    if not DownloadService.delete_task(task_id):
        raise APIException(ErrMsg.TASK_NOT_FOUND)
    return BaseResponse(message="任务已删除")


@router.get("/history", response_model=TaskListResponse, summary="获取下载历史")
async def get_download_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> TaskListResponse:
    """获取下载历史记录"""
    try:
        completed_tasks, total = DownloadService.get_download_history(page, page_size)
        return TaskListResponse(
            total=total,
            page=page,
            page_size=page_size,
            data=completed_tasks
        )
    except Exception as e:
        raise APIException(ErrMsg.QUERY_ERROR, e=e)


@router.get("/queue/status", response_model=BaseResponse, summary="获取队列状态")
async def get_queue_status() -> BaseResponse:
    """获取下载队列状态"""
    try:
        return BaseResponse(
            message=ErrMsg.OK.msg, data=DownloadService.get_queue_status()
        )
    except Exception as e:
        raise APIException(ErrMsg.QUERY_ERROR, e=e)
