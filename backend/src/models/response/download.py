from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from src.common.constant import TaskStatus
from src.models.response.base_response import BaseResponse, PaginatedResponse


class ProgressData(BaseModel):
    task_id: str = Field(..., description="任务ID")
    status: TaskStatus = Field(TaskStatus.PENDING, description="任务状态")
    progress: float = Field(0.0, description="进度")
    downloaded_size: int = Field(0, description="已下载大小")
    speed: float = Field(0.0, description="下载速度")
    file_size: Optional[int] = Field(None, description="总大小")


class DownloadTaskInfo(ProgressData):
    file_name: Optional[str] = Field(None, description="文件名")
    error_message: Optional[str] = Field(None, description="错误信息")
    started_at: Optional[str] = Field(None, description="开始时间")
    completed_at: Optional[str] = Field(None, description="完成时间")
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat(), description="创建时间")


class ProgressResponse(BaseResponse[ProgressData]):
    ...


class DownloadTaskResponse(BaseResponse[DownloadTaskInfo]):
    ...


class TaskListResponse(PaginatedResponse[list[DownloadTaskInfo]]):
    ...


class TaskCreatedData(BaseModel):
    task_id: str


class BatchTaskCreatedData(BaseModel):
    task_ids: List[str]


class CountData(BaseModel):
    count: int


class SuccessData(BaseModel):
    success: bool = True


class TaskCreatedResponse(BaseResponse[TaskCreatedData]):
    ...


class BatchTaskCreatedResponse(BaseResponse[BatchTaskCreatedData]):
    ...


class CountResponse(BaseResponse[CountData]):
    ...


class SuccessResponse(BaseResponse[SuccessData]):
    ...
