from typing import List, Optional

from pydantic import BaseModel, Field

from src.infrastructure.download_queue import TaskStore
from src.models.database.yande import YandeData
from src.models.response.base_response import BaseResponse, PaginatedResponse


class DownloadTaskInfo(TaskStore.DownloadTask):
    """下载任务信息"""
    yande_data: Optional[YandeData] = Field(None, exclude=True)



class ProgressResponse(BaseResponse[TaskStore.ProgressData]):
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


class TaskStatusCount(BaseModel):
    """各状态任务计数"""

    pending: int = Field(0, description="等待中任务数")
    downloading: int = Field(0, description="下载中任务数")
    paused: int = Field(0, description="已暂停任务数")
    completed: int = Field(0, description="已完成任务数")
    failed: int = Field(0, description="失败任务数")
    cancelled: int = Field(0, description="已取消任务数")


class TaskStatusCountResponse(BaseResponse[TaskStatusCount]):
    """任务状态计数响应"""

    ...
