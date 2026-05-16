# 自动路由注册规范

## APILoader（自动路由发现）

```python
# backend/src/api/__init__.py
import inspect
import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Optional

from fastapi import FastAPI, APIRouter
from loguru import logger
from backend.src.common.constant import RouterMap


class APILoader:
    def __init__(self):
        self.base_path = Path(__file__).resolve().parent

    @staticmethod
    def init_app(app: FastAPI) -> FastAPI:
        api_loader = APILoader()
        api_loader.init_api(app)
        return app

    def registry_router_from_file(self, app: FastAPI, file_path: Path) -> ModuleType:
        module_name = file_path.stem
        prefix = file_path.relative_to(self.base_path.parent).with_suffix('')

        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Load API failed: {file_path}")

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        for router_name, obj in inspect.getmembers(module):
            if isinstance(obj, APIRouter):
                app.include_router(
                    obj,
                    prefix=f"/{str(prefix.as_posix())}",
                    tags=RouterMap.get_tags(module_name)
                )
        return module

    def init_api(self, app: FastAPI) -> None:
        logger.info("API registry start.")
        for file_path in self.base_path.rglob("*.py"):
            if file_path.name.startswith("_"):
                continue
            try:
                self.registry_router_from_file(app, file_path)
            except Exception as e:
                logger.warning(f"Load router failed: {e}")
        logger.info("API registry finish.")
```

## RouterMap（路由标签枚举）

```python
class RouterMap(Enum):
    config = ["配置"]
    download = ["下载"]
    favorites = ["收藏夹"]
    gallery = ["图库"]
    query = ["查询"]
    tag_cache = ["标签缓存"]

    @classmethod
    def get_tags(cls, name: str):
        member = cls.__members__.get(name)
        return member.value if member else None
```