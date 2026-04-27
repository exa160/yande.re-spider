from typing import Literal, Optional

from pydantic import BaseModel, Field


class ApiConfig(BaseModel):
    class ProxiesConfig(BaseModel):
        http: str = ""
        https: str = ""
    proxy_enable: bool = Field(default=False)
    proxies: ProxiesConfig = ProxiesConfig()
    timeout: int = Field(default=30)
    retry: int = Field(3, description='yandere失败重试')
    

class ResetConfig(BaseModel):
    section: Literal['api', 'downloader', 'database'] = Field(..., description="配置类型")
