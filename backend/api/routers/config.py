"""
配置管理相关API路由
"""

import os
import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.dao.yande_data import refresh_engine

router = APIRouter()

CONFIG_DIR = Path(__file__).parent.parent.parent.parent / "config"
CONFIG_FILE = CONFIG_DIR / "data.cfg"


class ApiConfig(BaseModel):
    retry_times: int = Field(default=3)
    timeout: int = Field(default=30)
    proxy_enable: bool = Field(default=False)
    proxy: Optional[str] = Field(default=None)


class DownloaderConfig(BaseModel):
    thread_num: int = Field(default=4)
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


def load_json_config() -> dict:
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return {}


def save_json_config(config_data: dict):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(config_data, f, indent=4)


def clamp(value, default, min_val=None, max_val=None):
    if min_val is not None and value < min_val:
        return min_val
    if max_val is not None and value > max_val:
        return max_val
    return value


@router.get("/", response_model=SystemConfigResponse)
async def get_system_config():
    try:
        config_data = load_json_config()

        api_cfg = config_data.get("yande_api", {})
        downloader_cfg = config_data.get("downloader", {})
        database_cfg = config_data.get("database", {})

        retry_val = api_cfg.get("retry", 3)
        if isinstance(retry_val, str):
            retry_val = int(retry_val)

        timeout_val = api_cfg.get("timeout", 30)
        if isinstance(timeout_val, str):
            timeout_val = int(timeout_val)

        proxy_enable = api_cfg.get("proxy_enable", False)
        proxy_val = api_cfg.get("proxy", None)

        thread_num = downloader_cfg.get("thread_num", 4)
        if isinstance(thread_num, str):
            thread_num = int(thread_num)

        chunk_size = downloader_cfg.get("chunk_size", 10)
        if isinstance(chunk_size, str):
            chunk_size = int(chunk_size)

        split_size = downloader_cfg.get("split_size", 200)
        if isinstance(split_size, str):
            split_size = int(split_size)

        retry_times = downloader_cfg.get("retry", 3)
        if isinstance(retry_times, str):
            retry_times = int(retry_times)

        port_val = database_cfg.get("port", 3306)
        if isinstance(port_val, str):
            port_val = int(port_val)

        return SystemConfigResponse(
            api=ApiConfig(
                retry_times=clamp(retry_val, 3, 0, 500),
                timeout=clamp(timeout_val, 30, 1, 300),
                proxy_enable=proxy_enable,
                proxy=proxy_val,
            ),
            downloader=DownloaderConfig(
                thread_num=clamp(thread_num, 4, 1, 32),
                chunk_size=clamp(chunk_size, 10, 1, 102400),
                split_size=clamp(split_size, 200, 1, 1000000),
                retry_times=clamp(retry_times, 3, 0, 500),
            ),
            database=DatabaseConfig(
                enable=database_cfg.get("enable", False),
                host=database_cfg.get("host", "localhost"),
                port=port_val,
                user=database_cfg.get("user", "root"),
                password=database_cfg.get("password", ""),
                schema_name=database_cfg.get("schema_name", "Pictures"),
                datatable=database_cfg.get("datatable", "YandeRE"),
            ),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取配置失败: {str(e)}")


@router.put("/api")
async def update_api_config(config: ApiConfig):
    try:
        config_data = load_json_config()

        if "yande_api" not in config_data:
            config_data["yande_api"] = {}

        config_data["yande_api"]["retry"] = config.retry_times
        config_data["yande_api"]["timeout"] = config.timeout

        config_data["yande_api"]["proxy_enable"] = config.proxy_enable
        config_data["yande_api"]["proxy"] = config.proxy

        if config.proxy_enable and config.proxy:
            config_data["yande_api"]["proxies"] = {
                "http": config.proxy,
                "https": config.proxy,
            }
        else:
            config_data["yande_api"]["proxies"] = None

        save_json_config(config_data)
        return {"message": "API配置更新成功"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新失败: {str(e)}")


@router.put("/downloader")
async def update_downloader_config(config: DownloaderConfig):
    try:
        config_data = load_json_config()

        if "downloader" not in config_data:
            config_data["downloader"] = {}

        config_data["downloader"]["thread_num"] = config.thread_num
        config_data["downloader"]["chunk_size"] = config.chunk_size
        config_data["downloader"]["split_size"] = config.split_size
        config_data["downloader"]["retry"] = config.retry_times

        save_json_config(config_data)
        return {"message": "下载器配置更新成功"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新失败: {str(e)}")


@router.put("/database")
async def update_database_config(config: DatabaseConfig):
    try:
        config_data = load_json_config()

        if "database" not in config_data:
            config_data["database"] = {}

        config_data["database"]["enable"] = config.enable
        config_data["database"]["host"] = config.host
        config_data["database"]["port"] = config.port
        config_data["database"]["user"] = config.user
        config_data["database"]["password"] = config.password
        config_data["database"]["schema_name"] = config.schema_name
        config_data["database"]["datatable"] = config.datatable

        save_json_config(config_data)
        refresh_engine()
        return {"message": "数据库配置更新成功"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新失败: {str(e)}")


@router.post("/test-connection")
async def test_database_connection(config: DatabaseConfig):
    try:
        if config.enable:
            from sqlalchemy import create_engine

            engine = create_engine(
                f"mariadb+mariadbconnector://{config.user}:{config.password}@"
                f"{config.host}:{config.port}/{config.schema_name}?charset=utf8"
            )
            conn = engine.connect()
            conn.close()
            return {"success": True, "message": "数据库连接成功"}
        else:
            db_path = CONFIG_DIR / "yande_data.db"
            if db_path.exists():
                return {"success": True, "message": "SQLite数据库文件存在"}
            return {"success": True, "message": "SQLite数据库未配置，使用默认路径"}
    except Exception as e:
        return {"success": False, "message": f"连接失败: {str(e)}"}


@router.post("/reset")
async def reset_config(section: Optional[str] = None):
    try:
        config_data = load_json_config()

        if section is None:
            return {"message": "请指定要重置的配置段: api, downloader, database"}

        if section == "api":
            config_data["yande_api"] = {
                "retry": 3,
                "timeout": 30,
                "proxies": None,
                "headers": {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                },
            }
        elif section == "downloader":
            config_data["downloader"] = {
                "thread_num": 4,
                "chunk_size": 10,
                "split_size": 200,
                "retry": 3,
            }
        elif section == "database":
            config_data["database"] = {
                "enable": False,
                "host": "localhost",
                "port": 3306,
                "user": "root",
                "password": "",
                "schema_name": "Pictures",
                "datatable": "YandeRE",
            }
        else:
            return {"message": f"未知配置段: {section}"}

        save_json_config(config_data)
        return {"message": f"{section}配置已重置"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"重置失败: {str(e)}")


@router.get("/export")
async def export_config():
    try:
        config_data = load_json_config()
        return {"message": "配置导出成功", "config": config_data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导出失败: {str(e)}")


@router.post("/import")
async def import_config(config: dict):
    try:
        save_json_config(config)
        return {"message": "配置导入成功"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导入失败: {str(e)}")
