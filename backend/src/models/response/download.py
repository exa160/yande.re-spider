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


class ActiveImageState(BaseModel):
    """单张图片的进行中下载任务"""

    image_id: int = Field(description="yande 图片 ID")
    task_id: str = Field(description="任务 UUID")
    status: str = Field(description="pending | downloading | paused")
    progress: float = Field(0.0, description="进度 0-1（内存实时值）")
    speed: float = Field(0.0, description="下载速度 bytes/s（内存实时值）")
    downloaded_size: int = Field(0, description="已下载大小（字节）")


class FinishedImageState(BaseModel):
    """单张图片刚结束（窗口期内）的下载任务"""

    image_id: int = Field(description="yande 图片 ID")
    status: str = Field(description="completed | failed | cancelled")


class ImageDownloadStates(BaseModel):
    """图片下载状态快照（前端「下载中 / 已下载」标识的数据源）"""

    active: List[ActiveImageState] = Field(
        default_factory=list, description="进行中任务（同一 image_id 只保留最新一条）"
    )
    finished: List[FinishedImageState] = Field(
        default_factory=list, description="窗口期内终态任务，用于收敛「下载中」标识"
    )


class ImageDownloadStatesResponse(BaseResponse[ImageDownloadStates]):
    """图片下载状态快照响应"""

    ...
