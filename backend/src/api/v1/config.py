"""
配置管理相关API路由
"""

from typing import Optional

import yaml
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from backend.src import path_constant
from backend.src.common import config
from backend.src.common.constant import ErrMsg
from backend.src.middleware.errors import APIException
from backend.src.models.request.config import ResetConfig
from backend.src.models.response.base_response import BaseResponse
from backend.src.models.response.config import ConfigResponse

router = APIRouter()


class ApiConfig(BaseModel):
    retry_times: int = Field(default=3)
    timeout: int = Field(default=30)
    proxy_enable: bool = Field(default=False)
    proxy: Optional[str] = Field(default=None)


class DownloaderConfig(BaseModel):
    thread_num: int = Field(default=4)
    max_concurrent_tasks: int = Field(default=3)
    chunk_size: int = Field(default=10)
    split_size: int = Field(default=200)
    retry_times: int = Field(default=3)


class DatabaseConfig(BaseModel):
    enable: bool = Field(default=False)
    host: str = Field(default="localhost")
    port: int = Field(default=3306)
    user: str = Field(default="root")
    password: str = Field(default="")
    schema_name: str = Field(default="Pictures")
    datatable: str = Field(default="YandeRE")


class SystemConfigResponse(BaseModel):
    api: ApiConfig
    downloader: DownloaderConfig
    database: DatabaseConfig


@router.get("")
async def get_system_config() -> ConfigResponse:
    return ConfigResponse(data=config)


@router.put("/api")
async def update_api_config(api_config: ApiConfig) -> BaseResponse:
    try:
        config.update_config(ApiConfig.model_validate(api_config))
        return BaseResponse(message=ErrMsg.CONFIG_UPDATE_SUCCESS)
    except Exception as e:
        raise APIException(ErrMsg.CONFIG_UPDATE_ERROR, e=e)


@router.put("/downloader")
async def update_downloader_config(down_config: DownloaderConfig) -> BaseResponse:
    try:
        config.update_config(DownloaderConfig.model_validate(down_config))
        return BaseResponse(message=ErrMsg.CONFIG_UPDATE_SUCCESS)
    except Exception as e:
        raise APIException(ErrMsg.CONFIG_UPDATE_ERROR, e=e)


@router.put("/database")
async def update_database_config(database_config: DatabaseConfig) -> BaseResponse:
    try:
        config.update_config(DatabaseConfig.model_validate(database_config))
        return BaseResponse(message=ErrMsg.CONFIG_UPDATE_SUCCESS)
    except Exception as e:
        raise APIException(ErrMsg.CONFIG_UPDATE_ERROR, e=e)


@router.post("/test-connection")
async def test_database_connection(database_config: DatabaseConfig) -> BaseResponse:
    try:
        if database_config.enable:
            from sqlalchemy import create_engine

            engine = create_engine(
                f"mariadb+mariadbconnector://{database_config.user}:{database_config.password}@"
                f"{database_config.host}:{database_config.port}/{database_config.schema_name}?charset=utf8"
            )
            conn = engine.connect()
            conn.close()
            return BaseResponse(message="数据库连接成功", data={"success": True})
        else:
            db_path = path_constant.sqlite_file
            if db_path.exists():
                return {"success": True, "message": "SQLite数据库文件存在"}
            return {"success": True, "message": "SQLite数据库未配置，使用默认路径"}
    except Exception as e:
        return {"success": False, "message": f"连接失败: {str(e)}"}


@router.post("/reset")
async def reset_config(query: ResetConfig) -> BaseResponse:
    reset_map = {
        "api": ApiConfig,
        "downloader": DownloaderConfig,
        "database": DatabaseConfig
    }
    reset_model = reset_map.get(query.section)
    if reset_model is None:
        raise APIException(
            ErrMsg.CONFIG_RESET_ERROR,
            data=f"{query.section} not in {list(reset_map.keys())}."
        )
    config.update_config(reset_model())
    return BaseResponse(message="Reset success.")

