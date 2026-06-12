"""
查询预设管理API路由
"""
from fastapi import APIRouter

from src.common.constant import ErrMsg
from src.models.request.query import QueryParams
from src.models.response.base_response import BaseResponse

router = APIRouter()


@router.get("/presets", response_model=BaseResponse, summary="获取查询预设列表")
async def get_query_presets() -> BaseResponse:
    """获取查询预设列表"""
    return BaseResponse(message=ErrMsg.OK.msg, data={"presets": []})


@router.post("/presets", response_model=BaseResponse, summary="保存查询预设")
async def save_query_preset(name: str, params: QueryParams) -> BaseResponse:
    """保存查询预设"""
    return BaseResponse(message="预设保存成功", data={"name": name})


@router.delete(
    "/presets/{preset_id}", response_model=BaseResponse, summary="删除查询预设"
)
async def delete_query_preset(preset_id: int) -> BaseResponse:
    """删除查询预设"""
    return BaseResponse(message="预设删除成功")
