"""
下载相关请求模型
"""

from typing import Optional

from pydantic import BaseModel, Field


class DownloadTaskCreate(BaseModel):
    """下载任务创建请求"""

    image_id: int = Field(..., description="图片ID")
    file_url: str = Field(..., description="文件URL")
    save_path: str = Field(..., description="保存路径")
    file_name: str = Field(..., description="文件名")
    thread_num: int = Field(4, ge=1, le=16, description="下载线程数")
    tags: Optional[str] = Field(None, description="标签")
    width: Optional[int] = Field(None, description="图片宽度")
    height: Optional[int] = Field(None, description="图片高度")
    rating: Optional[str] = Field(None, description="评分")
    author: Optional[str] = Field(None, description="作者")
    md5: Optional[str] = Field(None, description="MD5哈希")
    total_size: Optional[int] = Field(None, description="文件大小")
