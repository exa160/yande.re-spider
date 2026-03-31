"""
下载管理相关API路由
"""

import uuid
import threading
import time
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict
from threading import Thread

from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel, Field

from backend.config.settings import config
from backend.config.constant import (
    TaskStatus,
    DOWNLOADS_DIR,
    ORIGINALS_DIR,
    PREVIEWS_DIR,
    TIMEOUT_PREVIEW,
)
from backend.infrastructure.downloader import MultiDown

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


class TaskStore:
    """内存任务存储"""

    def __init__(self):
        self._tasks: Dict[str, Dict] = {}
        self._lock = threading.Lock()

    def create_task(self, task_id: str, task_data: dict) -> dict:
        with self._lock:
            self._tasks[task_id] = {
                "task_id": task_id,
                "image_id": task_data["image_id"],
                "file_url": task_data["file_url"],
                "save_path": task_data["save_path"],
                "file_name": task_data["file_name"],
                "thread_num": task_data.get("thread_num", 4),
                "status": TaskStatus.PENDING,
                "progress": 0.0,
                "downloaded_size": 0,
                "total_size": task_data.get("total_size", 0),
                "error_message": None,
                "created_at": datetime.now().isoformat(),
                "started_at": None,
                "completed_at": None,
                "tags": task_data.get("tags"),
                "width": task_data.get("width"),
                "height": task_data.get("height"),
                "rating": task_data.get("rating"),
                "author": task_data.get("author"),
                "md5": task_data.get("md5"),
            }
            return self._tasks[task_id]

    def get_task(self, task_id: str) -> Optional[dict]:
        with self._lock:
            return self._tasks.get(task_id)

    def get_tasks(
        self, status: Optional[TaskStatus] = None, page: int = 1, page_size: int = 20
    ) -> tuple[List[dict], int]:
        with self._lock:
            tasks = list(self._tasks.values())

            if status:
                tasks = [t for t in tasks if t["status"] == status]

            tasks.sort(key=lambda x: x["created_at"], reverse=True)
            total = len(tasks)
            start = (page - 1) * page_size
            end = start + page_size
            return tasks[start:end], total

    def update_task(self, task_id: str, updates: dict):
        with self._lock:
            if task_id in self._tasks:
                self._tasks[task_id].update(updates)

    def delete_task(self, task_id: str) -> bool:
        with self._lock:
            if task_id in self._tasks:
                del self._tasks[task_id]
                return True
            return False


task_store = TaskStore()


def run_download(task_id: str):
    """后台执行下载"""
    task = task_store.get_task(task_id)
    if not task:
        return

    task_store.update_task(
        task_id,
        {"status": TaskStatus.DOWNLOADING, "started_at": datetime.now().isoformat()},
    )

    try:
        import os
        import hashlib
        from pathlib import Path

        downloads_dir = DOWNLOADS_DIR
        originals_dir = ORIGINALS_DIR
        previews_dir = PREVIEWS_DIR

        originals_dir.mkdir(parents=True, exist_ok=True)
        previews_dir.mkdir(parents=True, exist_ok=True)

        file_ext = (
            task["file_name"].rsplit(".", 1)[-1] if "." in task["file_name"] else "jpg"
        )
        original_path = originals_dir / f"{task['image_id']}.{file_ext}"

        expected_md5 = task.get("md5")
        need_download = True

        if original_path.exists() and expected_md5:
            file_md5 = hashlib.md5(open(original_path, "rb").read()).hexdigest()
            if file_md5 == expected_md5:
                print(
                    f"Original exists and MD5 matches ({file_md5}), skipping download"
                )
                need_download = False
            else:
                print(f"Original exists but MD5 mismatch, re-downloading")

        if need_download:
            total_size = task.get("total_size", 0)
            downloaded_size = 0

            def progress_callback(chunk_mb: float):
                nonlocal downloaded_size
                downloaded_size += chunk_mb
                if total_size > 0:
                    progress = min(downloaded_size / (total_size / 1024 / 1024), 1.0)
                    task_store.update_task(
                        task_id,
                        {
                            "downloaded_size": int(downloaded_size * 1024 * 1024),
                            "progress": progress,
                        },
                    )

            MultiDown(
                url=task["file_url"],
                file_path=str(originals_dir),
                file_name=f"{task['image_id']}.{file_ext}",
                file_size=total_size,
                _md5=task.get("md5"),
                _id=task["image_id"],
                _show_progress=False,
                _progress_callback=progress_callback,
            )

        preview_url = task.get("preview_url")
        if preview_url:
            preview_path = previews_dir / f"{task['image_id']}.{file_ext}"
            if not preview_path.exists():
                try:
                    import requests

                    proxies = (
                        config.yande_api.proxies if config.yande_api.proxies else None
                    )
                    resp = requests.get(
                        preview_url, proxies=proxies, timeout=TIMEOUT_PREVIEW
                    )
                    if resp.status_code == 200:
                        with open(preview_path, "wb") as f:
                            f.write(resp.content)
                        print(f"Preview downloaded: {preview_path}")
                except Exception as e:
                    print(f"Failed to download preview: {e}")

        try:
            from backend.dao.database import MariaDBClient
            from backend.models.yande import Rating
            from datetime import datetime as dt

            client = MariaDBClient()

            rating_str = task.get("rating", "s")
            if rating_str in ["Safe", "s", "S"]:
                rating = Rating.S
            elif rating_str in ["Questionable", "q", "Q"]:
                rating = Rating.R15
            else:
                rating = Rating.R18

            new_record = client.YandeData(
                id=task["image_id"],
                tags=task.get("tags", ""),
                created_at=dt.now(),
                updated_at=dt.now(),
                creator_id=None,
                author=task.get("author", ""),
                change=0,
                source=task["file_url"],
                score=0,
                md5=task.get("md5", ""),
                file_size=task.get("total_size", 0),
                file_ext=task["file_name"].rsplit(".", 1)[-1]
                if "." in task["file_name"]
                else "jpg",
                file_url=task["file_url"],
                is_shown_in_index=True,
                preview_url=task["file_url"].replace("images", "previews"),
                width=task.get("width", 0),
                height=task.get("height", 0),
                rating=rating,
                is_rating_locked=False,
                has_children=False,
                parent_id=None,
                status="active",
                is_pending=False,
                is_held=False,
                down_flag=True,
            )
            client.insert_data(new_record)
            client.close()
        except Exception as db_err:
            print(f"Failed to write to database: {db_err}")

        task_store.update_task(
            task_id,
            {
                "status": TaskStatus.COMPLETED,
                "progress": 1.0,
                "completed_at": datetime.now().isoformat(),
            },
        )
    except Exception as e:
        task_store.update_task(
            task_id, {"status": TaskStatus.FAILED, "error_message": str(e)}
        )


@router.post("/task", response_model=dict)
async def create_download_task(
    task: DownloadTaskCreate, background_tasks: BackgroundTasks
):
    task_id = str(uuid.uuid4())

    task_data = task_store.create_task(task_id, task.model_dump())

    background_tasks.add_task(run_download, task_id)

    return {"message": "下载任务创建成功", "task_id": task_id}


@router.post("/task/batch", response_model=dict)
async def create_batch_download_tasks(
    tasks: List[DownloadTaskCreate], background_tasks: BackgroundTasks
):
    task_ids = []
    for task in tasks:
        task_id = str(uuid.uuid4())
        task_store.create_task(task_id, task.model_dump())
        background_tasks.add_task(run_download, task_id)
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
    )


@router.post("/task/{task_id}/start")
async def start_download_task(task_id: str, background_tasks: BackgroundTasks):
    task = task_store.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    if task["status"] not in [TaskStatus.PENDING, TaskStatus.PAUSED, TaskStatus.FAILED]:
        raise HTTPException(status_code=400, detail="任务无法启动")

    task_store.update_task(task_id, {"status": TaskStatus.PENDING})
    background_tasks.add_task(run_download, task_id)

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
async def resume_download_task(task_id: str, background_tasks: BackgroundTasks):
    task = task_store.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    if task["status"] != TaskStatus.PAUSED:
        raise HTTPException(status_code=400, detail="任务无法恢复")

    task_store.update_task(task_id, {"status": TaskStatus.PENDING})
    background_tasks.add_task(run_download, task_id)

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
        {"status": TaskStatus.CANCELLED, "completed_at": datetime.now().isoformat()},
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
