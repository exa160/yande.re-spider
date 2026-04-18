"""
下载管理相关API路由
"""

import uuid
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.src.infrastructure.download_queue import (
    task_store,
    download_queue,
)
from backend.src.common.constant import TaskStatus

router = APIRouter()


class DownloadTaskCreate(BaseModel):
    image_id: int
    file_url: str
    save_path: str
    file_name: str
    thread_num: int = 4
    tags: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    rating: Optional[str] = None
    author: Optional[str] = None
    md5: Optional[str] = None
    total_size: Optional[int] = None


class DownloadTaskInfo(BaseModel):
    task_id: str
    image_id: int
    file_url: str
    save_path: str
    file_name: str
    status: TaskStatus
    progress: float
    downloaded_size: int
    total_size: Optional[int]
    speed: Optional[float] = None
    thread_num: int
    error_message: Optional[str]
    created_at: str
    started_at: Optional[str]
    completed_at: Optional[str]


class ProgressResponse(BaseModel):
    task_id: str
    status: TaskStatus
    progress: float
    downloaded_size: int
    total_size: Optional[int]
    speed: Optional[float] = None


@router.post("/task", response_model=dict)
async def create_download_task(task: DownloadTaskCreate):
    task_id = str(uuid.uuid4())
    task_store.create_task(task_id, task.model_dump())
    await download_queue.add_task(task_id)
    return {"message": "下载任务创建成功", "task_id": task_id}


@router.post("/task/batch", response_model=dict)
async def create_batch_download_tasks(tasks: List[DownloadTaskCreate]):
    task_ids = []
    for task in tasks:
        task_id = str(uuid.uuid4())
        task_store.create_task(task_id, task.model_dump())
        await download_queue.add_task(task_id)
        task_ids.append(task_id)
    return {"message": f"成功创建 {len(task_ids)} 个下载任务", "task_ids": task_ids}


@router.get("/tasks", response_model=dict)
async def get_download_tasks(
    status: Optional[TaskStatus] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    tasks, total = task_store.get_tasks(status, page, page_size)
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "tasks": [DownloadTaskInfo(**t) for t in tasks],
    }


@router.get("/task/{task_id}", response_model=DownloadTaskInfo)
async def get_download_task(task_id: str):
    task = task_store.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return DownloadTaskInfo(**task)


@router.get("/task/{task_id}/progress", response_model=ProgressResponse)
async def get_task_progress(task_id: str):
    task = task_store.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return ProgressResponse(
        task_id=task["task_id"],
        status=task["status"],
        progress=task["progress"],
        downloaded_size=task["downloaded_size"],
        total_size=task["total_size"],
        speed=task.get("speed"),
    )


@router.post("/task/{task_id}/start")
async def start_download_task(task_id: str):
    task = task_store.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task["status"] not in [TaskStatus.PENDING, TaskStatus.PAUSED, TaskStatus.FAILED]:
        raise HTTPException(status_code=400, detail="任务无法启动")
    task_store.update_task(task_id, {"status": TaskStatus.PENDING})
    await download_queue.add_task(task_id)
    return {"message": "任务已启动"}


@router.post("/task/{task_id}/pause")
async def pause_download_task(task_id: str):
    task = task_store.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task["status"] != TaskStatus.DOWNLOADING:
        raise HTTPException(status_code=400, detail="任务无法暂停")
    task_store.update_task(task_id, {"status": TaskStatus.PAUSED})
    return {"message": "任务已暂停"}


@router.post("/task/{task_id}/resume")
async def resume_download_task(task_id: str):
    task = task_store.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task["status"] != TaskStatus.PAUSED:
        raise HTTPException(status_code=400, detail="任务无法恢复")
    task_store.update_task(task_id, {"status": TaskStatus.PENDING})
    await download_queue.add_task(task_id)
    return {"message": "任务已恢复"}


@router.post("/task/{task_id}/cancel")
async def cancel_download_task(task_id: str):
    task = task_store.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task["status"] in [TaskStatus.COMPLETED, TaskStatus.CANCELLED]:
        raise HTTPException(status_code=400, detail="任务无法取消")
    task_store.update_task(
        task_id,
        {"status": TaskStatus.CANCELLED, "completed_at": task["completed_at"]},
    )
    return {"message": "任务已取消"}


@router.delete("/task/{task_id}")
async def delete_download_task(task_id: str):
    if not task_store.delete_task(task_id):
        raise HTTPException(status_code=404, detail="任务不存在")
    return {"message": "任务已删除"}


@router.get("/history", response_model=dict)
async def get_download_history(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)
):
    tasks, total = task_store.get_tasks(page=page, page_size=page_size)
    completed_tasks = [
        t
        for t in tasks
        if t["status"]
        in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]
    ]
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "records": [DownloadTaskInfo(**t) for t in completed_tasks],
    }


@router.get("/queue/status")
async def get_queue_status():
    return {
        "queue_size": download_queue.get_queue_size(),
        "max_concurrent": download_queue._get_max_concurrent(),
    }
