# 异常处理规范

## ErrMsg 枚举定义

```python
from enum import Enum
from http import HTTPStatus


class BaseMsgEnum(Enum):
    def __new__(cls, code: str, msg: str, http_status: HTTPStatus = None):
        obj = object.__new__(cls)
        obj.code = code
        obj.msg = msg
        obj.http_status = HTTPStatus.OK if http_status is None else http_status
        return obj


class ErrMsg(BaseMsgEnum):
    # 系统级
    OK = ("0000", "OK.")

    # 通用错误
    QUERY_ERROR = ("0001", "Query error.", HTTPStatus.INTERNAL_SERVER_ERROR)
    CREATE_ERROR = ("0002", "Create error.", HTTPStatus.INTERNAL_SERVER_ERROR)
    UPDATE_ERROR = ("0003", "Update error.", HTTPStatus.INTERNAL_SERVER_ERROR)
    DELETE_ERROR = ("0004", "Delete error.", HTTPStatus.INTERNAL_SERVER_ERROR)
    NOT_FOUND = ("0005", "Resource not found.", HTTPStatus.NOT_FOUND)
    PARAM_ERROR = ("0006", "Invalid parameter.", HTTPStatus.BAD_REQUEST)

    # 业务特定错误
    CONFIG_UPDATE_SUCCESS = ("0000", "配置更新成功")
    CONFIG_UPDATE_ERROR = ("1001", "Config update error.", HTTPStatus.INTERNAL_SERVER_ERROR)
    CONFIG_RESET_ERROR = ("1002", "Config reset error.", HTTPStatus.INTERNAL_SERVER_ERROR)
```

## APIException 使用

```python
from fastapi import HTTPException
from backend.src.middleware.errors import APIException

# 基本用法
raise APIException(ErrMsg.NOT_FOUND)

# 带附加数据
raise APIException(ErrMsg.PARAM_ERROR, data={"field": "name", "reason": "too long"})

# 捕获异常并传递
try:
    result = service.do_something()
except Exception as e:
    raise APIException(ErrMsg.QUERY_ERROR, e=e)

# 不使用 APIException 的情况（FastAPI 自动处理）
raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
```

## 错误中间件（ErrorHandleMiddleware）

```python
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
                    message=exc.err_msg,
                    data=exc.data
                ).model_dump(mode="json")
            )

        @app.exception_handler(Exception)
        async def global_exception_handler(request, exc):
            logger.error(f"Exception: {exc}")
            return JSONResponse(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR.value,
                content=ErrorResponse(
                    message=f"{HTTPStatus.INTERNAL_SERVER_ERROR.description}: {str(exc)}"
                ).model_dump(mode="json")
            )
```