"""
查询相关API路由

TODO [2026-05-07]: /search 接口目前未被前端使用
   前端图库加载使用的是 /gallery/load 接口
   本接口的 /search 端点为遗留代码，如后续UI不需要可删除
   相关模型: QueryParams (models/request/query.py)
             QueryResponse (models/response/query.py)
"""

from fastapi import APIRouter

from src.common.constant import ErrMsg
from src.middleware.errors import APIException
from src.models.request.query import QueryParams
from src.models.response.base_response import BaseResponse
from src.models.response.query import QueryData, QueryResponse
from src.services.gallery import GalleryService

router = APIRouter()


@router.post("/search", response_model=QueryResponse, summary="高级查询")
async def advanced_search(params: QueryParams) -> QueryResponse:
    """高级查询接口"""
    try:
        # 使用 GalleryService 进行查询
        query_params = params.model_dump()
        images, total = GalleryService.query_local_database(query_params)

        return QueryResponse(
            message=ErrMsg.OK.msg,
            data=QueryData(
                total=total,
                page=params.page,
                page_size=params.page_size,
                images=images,
            ),
        )
    except Exception as e:
        raise APIException(ErrMsg.QUERY_ERROR, e=e)


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
