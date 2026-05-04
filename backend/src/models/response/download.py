from typing import List, Optional

from pydantic import BaseModel

from src.common.constant import TaskStatus
from src.models.response.base_response import BaseResponse, PaginatedResponse


class DownloadTaskInfo(BaseModel):
    """下载任务信息"""

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


class ProgressData(BaseModel):
    """任务进度数据"""

    task_id: str
    status: TaskStatus
    progress: float
    downloaded_size: int
    total_size: Optional[int]
    speed: Optional[float] = None


class ProgressResponse(BaseResponse[ProgressData]):
    """任务进度响应"""

    ...


class DownloadTaskResponse(BaseResponse[DownloadTaskInfo]):
    """下载任务响应"""

    ...



class TaskListResponse(PaginatedResponse[list[DownloadTaskInfo]]):
    """任务列表数据"""
    ...


class TaskCreatedData(BaseModel):
    """任务创建数据"""

    task_id: str


class BatchTaskCreatedData(BaseModel):
    """批量任务创建数据"""

    task_ids: List[str]


class CountData(BaseModel):
    """数量数据"""

    count: int


class SuccessData(BaseModel):
    """成功数据"""

    success: bool = True


class TaskCreatedResponse(BaseResponse[TaskCreatedData]):
    """任务创建响应"""

    ...


class BatchTaskCreatedResponse(BaseResponse[BatchTaskCreatedData]):
    """批量任务创建响应"""

    ...


class CountResponse(BaseResponse[CountData]):
    """数量响应"""

    ...


class SuccessResponse(BaseResponse[SuccessData]):
    """成功响应"""

    ...
