from http import HTTPStatus
from typing import Generic, TypeVar

from fastapi import FastAPI, status, HTTPException
from loguru import logger
from starlette.responses import JSONResponse

from backend.src.common.constant import ErrMsg
from backend.src.models.response.base_response import ErrorResponse

T = TypeVar('T')


class APIException(HTTPException, Generic[T]):
    def __init__(self, err_msg: str | ErrMsg, err_code: str = '0000', data: T = None, e: Exception = None):
        self.err_code = err_code
        self.http_status = HTTPStatus.OK
        if isinstance(err_msg, ErrMsg):
            self.err_code = err_msg.code
            self.err_msg = err_msg.msg
            self.http_status = err_msg.http_status
        else:
            self.err_msg = err_msg
        if e:
            self.err_msg += str(e)
        self.data = data
        super().__init__(status_code=self.http_status.value, detail=self.err_msg)


class ErrorHandleMiddleware:
    @staticmethod
    def init_app(app: FastAPI):
        @app.exception_handler(APIException)
        async def global_exception_handler(request, exc):
            logger.error(f"Exception: {exc}")
            return JSONResponse(
                status_code=exc.http_status.value,
                content=ErrorResponse(
                    code=exc.err_code,
                    message=exc.err_msg, data=exc.data
                ).model_dump(mode="json")
            )

        # 全局异常处理
        @app.exception_handler(Exception)
        async def global_exception_handler(request, exc):
            logger.error(f"Exception: {exc}")
            return JSONResponse(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR.value,
                content=ErrorResponse(
                    message=f"{HTTPStatus.INTERNAL_SERVER_ERROR.description}: {str(exc)}"
                ).model_dump(mode="json")
            )
