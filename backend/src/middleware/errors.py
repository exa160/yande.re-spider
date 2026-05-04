import traceback
from http import HTTPStatus
from typing import Generic, TypeVar, Any

from fastapi import FastAPI, HTTPException
from loguru import logger
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse

from src.common.constant import ErrMsg
from src.models.response.base_response import ErrorResponse

T = TypeVar('T')


class APIException(HTTPException, Generic[T]):
    def __init__(self, err_msg: str | ErrMsg, err_code: str = None, data: Any = None, e: Exception = None):
        self.http_status = HTTPStatus.OK
        if isinstance(err_msg, ErrMsg):
            # 优先使用传入的 err_code，否则使用 ErrMsg 中的 code
            self.err_code = err_code if err_code else err_msg.code
            self.err_msg = err_msg.msg
            self.http_status = err_msg.http_status
        else:
            self.err_code = err_code if err_code else '0000'
            self.err_msg = err_msg
        if e:
            self.err_msg += str(e)
        # 只有当 T 是具体类型（非 TypeVar）且 data 不为 None 时才验证
        if data is not None and isinstance(T, type) and hasattr(T, 'model_validate'):
            self.data = T.model_validate(data)
        else:
            self.data = data
        super().__init__(status_code=self.http_status.value, detail=self.err_msg)


class ErrorHandleMiddleware:
    @staticmethod
    def init_app(app: FastAPI):
        # APIException 专用处理
        @app.exception_handler(APIException)
        async def api_exception_handler(request, exc):
            logger.error(f"APIException: {exc}")
            logger.error(f"traceback: {traceback.format_exc()}")
            return JSONResponse(
                status_code=exc.http_status.value,
                content=ErrorResponse(
                    code=exc.err_code,
                    message=exc.err_msg, data=exc.data
                ).model_dump(mode="json")
            )

        @app.exception_handler(StarletteHTTPException)
        async def http_exception_handler(request, exc):
            logger.error(f"APIException: {exc}")
            logger.error(f"traceback: {traceback.format_exc()}")
            return JSONResponse(
               status_code=exc.status_code,
               content=ErrorResponse(
                    code=ErrMsg.INTERNAL_ERROR.code,
                    message=exc.detail
                    ).model_dump(mode="json")
                )

        # 全局异常处理（捕获所有未处理的 Exception）
        @app.exception_handler(Exception)
        async def global_exception_handler(request, exc):
            logger.error(f"Unhandled Exception: {exc}")
            logger.error(f"traceback: {traceback.format_exc()}")
            return JSONResponse(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR.value,
                content=ErrorResponse(
                    message=f"{HTTPStatus.INTERNAL_SERVER_ERROR.description}: {str(exc)}"
                ).model_dump(mode="json")
            )
