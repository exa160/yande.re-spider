import re
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
        # 获取调用栈信息，用于日志追踪
        self._source_location = self._get_source_location()
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

    @staticmethod
    def _get_source_location() -> str:
        """获取最近的非框架调用位置"""
        for line in traceback.format_stack()[::-1]:
            # 跳过 middleware 和 framework 相关的文件
            if 'middleware' not in line and 'starlette' not in line and 'fastapi' not in line:
                # 提取文件路径和行号
                match = re.search(r'File "(.*?)", line (\d+)', line)
                if match:
                    return f"{match.group(1)}:{match.group(2)}"
        return "unknown"


class ErrorHandleMiddleware:
    @staticmethod
    def init_app(app: FastAPI):
        # APIException 专用处理
        @app.exception_handler(APIException)
        async def api_exception_handler(request, exc):
            logger.error(f"APIException: {exc.err_code} - {exc.err_msg}")
            logger.error(f"source: {exc._source_location}")
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
