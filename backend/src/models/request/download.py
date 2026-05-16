"""
下载相关请求模型
"""

from pydantic import BaseModel, Field


class DownloadTaskCreate(BaseModel):
    """下载任务创建请求 - 简化版，仅需传入 image_id"""

    image_id: int = Field(..., description="图片ID")
