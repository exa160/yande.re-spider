"""「最近下载」请求模型

对应 POST /api/v1/recent_downloads/clear 的请求体（设计文档 §3.3）。

注意：GET /count 与 GET /preview 只用 query 参数，没有 request body，
因此本文件只定义清除接口所需的模型。
"""
from typing import Literal, Optional

from pydantic import BaseModel, Field


class ClearRecordsRequest(BaseModel):
    """清除「最近下载」记录请求。

    - mode="before_days"：按时间清除，days 必填（1-3650 天）
    - mode="all"：清空全部已完成记录，days 忽略

    mode 非法值由 pydantic 直接判 422；``before_days`` 缺 days 不在模型层拦
    （days 允许为 None，与 mode 的组合校验放在 service/API 层显式报错），
    以便返回统一业务错误码而不是 422。
    """

    mode: Literal["before_days", "all"] = Field(
        ...,
        description="清除模式: before_days=清除 N 天前的记录 | all=清空全部已完成记录",
    )
    days: Optional[int] = Field(
        default=None,
        ge=1,
        le=3650,
        description="mode=before_days 时必填：清除 N 天前的记录（N 取 1-3650）",
    )
