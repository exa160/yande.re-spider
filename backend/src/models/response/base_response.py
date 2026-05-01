from http import HTTPStatus
from typing import TypeVar, Generic, Optional, Any

from pydantic import BaseModel, model_validator

from src.common.constant import ErrMsg

T = TypeVar('T')


class BaseResponse(BaseModel, Generic[T]):
    """
    统一响应类
    e.g.:
    {"code": "0000","message": "OK.","data":""}
    """
    code: str = ErrMsg.OK.code
    message: Optional[str | ErrMsg] = ErrMsg.OK.msg
    data: Optional[T] = None

    @model_validator(mode='before')
    def extract_enum(self):
        msg = self.get('message')
        if isinstance(msg, ErrMsg):
            self['code'] = msg.code
            self['message'] = msg.msg
        return self


class PaginatedResponse(BaseResponse[T]):
    """
    分页统一响应
    e.g.:
    {"code": "0000","message": "OK.","data":"","total": 100,"page": 1,"page_size": 20}
    """
    total: int
    page: int
    page_size: int


class ErrorResponse(BaseResponse[T]):
    code: str = ErrMsg.INTERNAL_ERROR.code
