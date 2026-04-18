from http import HTTPStatus
from typing import TypeVar, Generic, Optional, Any

from pydantic import BaseModel, model_validator

from backend.src.common.constant import ErrMsg

T = TypeVar('T')


class BaseResponse(BaseModel, Generic[T]):
    """
    统一响应类
    e.g.:
    {"code": "0000","message": "OK.","data":""}
    """
    code: str = '0000'
    message: Optional[str | ErrMsg] = ErrMsg.OK.msg
    data: Optional[T] = None

    @model_validator(mode='before')
    def extract_enum(self):
        msg = self.get('message')
        if isinstance(msg, ErrMsg):
            self['code'] = msg.code
            self['message'] = msg.msg
        return self


class ErrorResponse(BaseResponse):
    code: str = '9999'
