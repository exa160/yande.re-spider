from enum import Enum
from typing import Optional

from pydantic import BaseModel


class FileInfo(BaseModel):
    """下载文件的信息"""

    id: Optional[int] = None
    file_path: str
    file_size: int
    md5: Optional[str] = None
    url: str


class IterStatus(Enum):
    next = "continue"
    stop = "stop"
