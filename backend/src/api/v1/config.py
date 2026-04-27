"""
配置管理相关API路由
"""

from typing import Optional

import yaml
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from src import path_constant
from src.common import config
from src.common.constant import ErrMsg
from src.middleware.errors import APIException
from src.common.settings import DownloaderConfig, DatabaseConfig
from src.models.request.config import ApiConfig, ResetConfig
from src.models.response.base_response import BaseResponse
from src.models.response.config import ConfigResponse

router = APIRouter()


@router.get("")
async def get_system_config() -> ConfigResponse:
    return ConfigResponse(data=config)


@router.put("/api")
async def update_api_config(api_config: ApiConfig) -> BaseResponse:
    try:
        tmp_config = config.yande_api.model_dump(mode="json")
        tmp_config.update(api_config)
        config.update_config(ApiConfig.model_validate(tmp_config))
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

