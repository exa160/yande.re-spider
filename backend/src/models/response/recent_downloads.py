"""「最近下载」响应模型

只定义清除接口的响应；count / preview 端点**复用** my_favorites 的
``MyFavoriteCountResponse`` / ``MyFavoritePreviewResponse``（同构契约，
不重复定义，见设计文档 §3.3）。
"""
from pydantic import BaseModel, Field


class ClearRecordsResponse(BaseModel):
    """清除记录结果

    只统计被删除的**任务记录条数**（不删图片文件，也不改 yande_data.down_flag）。
    """

    deleted: int = Field(..., ge=0, description="删除的记录条数")
