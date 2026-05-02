from pydantic import BaseModel, Field


class RefreshTagsRequest(BaseModel):
    full_refresh: bool = Field(False, description="是否全量更新（limit=0获取全部）")
    limit: int = Field(100, ge=0, le=1000, description="每页数量，0表示获取全部")


class RefreshArtistsRequest(BaseModel):
    page: int = Field(1, ge=1, description="起始页码")
    max_pages: int = Field(10, ge=1, description="最大页数")
