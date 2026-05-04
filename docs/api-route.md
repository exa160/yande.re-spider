# API 路由编写规范

## 路由文件模板

```python
"""
[模块名称] API路由
"""

from typing import Optional, List

from fastapi import APIRouter, Query, status
from pydantic import BaseModel, Field

from backend.src.models.response.base_response import BaseResponse
from backend.src.models.response.[模块] import [模块]Response
from backend.src.common.constant import ErrMsg
from backend.src.middleware.errors import APIException
from backend.src.services.[模块] import [模块]Service

router = APIRouter()

# ============================================
# Request Models（使用 Pydantic + Field 校验）
# ============================================

class CreateItemRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    tags: List[str] = Field(default_factory=list)
    enabled: bool = Field(default=True)


class UpdateItemRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)


# ============================================
# Response Models（放在 models/response/）
# ============================================

class ItemResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    tags: List[str]
    enabled: bool


# ============================================
# API Endpoints
# ============================================

@router.get("", response_model=BaseResponse)
async def get_items(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: Optional[str] = None,
) -> BaseResponse:
    """获取列表（分页）"""
    try:
        items, total = [模块]Service.get_items(page, page_size, keyword)
        return BaseResponse(
            message=ErrMsg.OK.msg,
            data={"items": items, "total": total, "page": page, "page_size": page_size}
        )
    except Exception as e:
        raise APIException(ErrMsg.QUERY_ERROR, e=e)


@router.get("/{item_id}", response_model=ItemResponse)
async def get_item(item_id: int) -> ItemResponse:
    """获取单个详情"""
    item = [模块]Service.get_by_id(item_id)
    if not item:
        raise APIException(ErrMsg.LOAD_PREVIEW_DATA_ERROR, e=Exception("Item not found"))
    return ItemResponse(**item)


@router.post("", response_model=BaseResponse, status_code=status.HTTP_201_CREATED)
async def create_item(request: CreateItemRequest) -> BaseResponse:
    """创建"""
    try:
        item_id = [模块]Service.create(request)
        return BaseResponse(message="创建成功", data={"id": item_id})
    except Exception as e:
        raise APIException(ErrMsg.CREATE_ERROR, e=e)


@router.put("/{item_id}", response_model=BaseResponse)
async def update_item(item_id: int, request: UpdateItemRequest) -> BaseResponse:
    """更新"""
    try:
        [模块]Service.update(item_id, request)
        return BaseResponse(message="更新成功")
    except ValueError as e:
        raise APIException(ErrMsg.LOAD_PREVIEW_DATA_ERROR, e=Exception("Error"))
    except Exception as e:
        raise APIException(ErrMsg.UPDATE_ERROR, e=e)


@router.delete("/{item_id}", response_model=BaseResponse)
async def delete_item(item_id: int) -> BaseResponse:
    """删除"""
    try:
        [模块]Service.delete(item_id)
        return BaseResponse(message="删除成功")
    except Exception as e:
        raise APIException(ErrMsg.DELETE_ERROR, e=e)
```

## 关键规则

1. **Request Model** 放在 `models/request/` 目录，使用 `Field()` 定义校验
2. **Response Model** 放在 `models/response/` 目录，**必须**带数据结构的响应必须继承 `BaseResponse`，且注明data数据结构
3. **API 函数** 必须声明返回类型注解
4. **异常处理** 统一使用 `APIException(ErrMsg.XXX, e=e)` 模式
5. **HTTP状态码**：201 创建、400 参数错误、404 不存在、500 服务器错误