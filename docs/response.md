# 响应模型规范

## BaseResponse（必须继承）

```python
from http import HTTPStatus
from typing import TypeVar, Generic, Optional, Any
from pydantic import BaseModel, model_validator
from backend.src.common.constant import ErrMsg

T = TypeVar('T')


class BaseResponse(BaseModel, Generic[T]):
    """
    统一响应类
    响应格式: {"code": "0000", "message": "OK.", "data": null}
    """
    code: str = '0000'
    message: Optional[str | ErrMsg] = ErrMsg.OK.msg
    data: Optional[T] = None

    @model_validator(mode='before')
    def extract_enum(self):
        """自动从 ErrMsg 枚举提取 code 和 message"""
        msg = self.get('message')
        if isinstance(msg, ErrMsg):
            self['code'] = msg.code
            self['message'] = msg.msg
        return self


class ErrorResponse(BaseResponse):
    """错误响应（code 固定为 9999）"""
    code: str = '9999'
```

## 带数据结构的响应标准用法
```python
from pydantic import BaseModel, Field

class DataItem(BaseModel):
    id: int = Field(..., description="id")
    name: str = Field(..., description="item name")

class DataResponse(BaseResponse[DataItem]):
    ...

DataResponse(message=ErrMsg.OK.msg, data={"id": 1, "name": "test"})
```
或
```python
from pydantic import BaseModel, Field



class DataResponse(BaseResponse):
    class DataItem(BaseModel):
        id: int = Field(..., description="id")
        name: str = Field(..., description="item name")
    data: DataItem = Field(..., description="return data")

DataResponse(message=ErrMsg.OK.msg, data={"id": 1, "name": "test"})
```
## 响应格式约定

| 场景 | code | message | data |
|------|------|---------|------|
| 成功 | `0000` | `ErrMsg.OK.msg` | 业务数据 |
| 错误 | 非`0000` | 错误描述 | 可选附加数据 |

## 响应示例

```python
# 标准成功响应
BaseResponse(message=ErrMsg.OK.msg)

# 简单数据响应
BaseResponse(message=ErrMsg.OK.msg, data=2)

# 带数据结构的响应（不允许直接使用BaseResponse）
DataResponse(message=ErrMsg.OK.msg, data={"id": 1, "name": "test"})

# 带错误码的成功响应
BaseResponse(message=ErrMsg.CONFIG_UPDATE_SUCCESS)

# 错误响应（通过 APIException）
raise APIException(ErrMsg.CONFIG_UPDATE_ERROR, e=e)
```