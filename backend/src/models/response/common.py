"""
通用响应模型
"""

from typing import List

from pydantic import BaseModel

from src.models.response.base_response import BaseResponse


class TaskCreatedData(BaseModel):
    """任务创建数据"""

    task_id: str


class BatchTaskCreatedData(BaseModel):
    """批量任务创建数据"""

    task_ids: List[str]


class PreviewUrlData(BaseModel):
    """预览URL数据"""

    preview_url: str = ""
    sample_url: str = ""
    file_url: str = ""


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


class PreviewUrlResponse(BaseResponse[PreviewUrlData]):
    """预览URL响应"""

    ...


class CountResponse(BaseResponse[CountData]):
    """数量响应"""

    ...


class SuccessResponse(BaseResponse[SuccessData]):
    """成功响应"""

    ...
