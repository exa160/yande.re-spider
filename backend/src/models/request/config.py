from typing import Literal, Optional

from pydantic import BaseModel, Field


class ResetConfig(BaseModel):
    section: Literal['api', 'downloader', 'database'] = Field(..., description="配置类型")
