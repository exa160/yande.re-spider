"""
配置管理相关API路由
"""

from fastapi import APIRouter, Query

from src.common.constant import ErrMsg
from src.common.settings import (
    ApiConfig,
    DatabaseConfig,
    DownloaderConfig,
    FavoritesConfig,
    TagCacheConfig,
)
from src.middleware.errors import APIException
from src.models.response.base_response import BaseResponse
from src.models.response.config import ConfigResponse
from src.services.config import ConfigService

router = APIRouter()


@router.get("", response_model=ConfigResponse, summary="获取系统配置")
async def get_system_config() -> ConfigResponse:
    """获取系统配置"""
    return ConfigResponse(data=ConfigService.get_system_config())


@router.get("/favorites", response_model=BaseResponse[FavoritesConfig], summary="获取收藏夹配置")
async def get_favorites_config_endpoint() -> BaseResponse[FavoritesConfig]:
    """获取收藏夹配置（我的最爱 / 收藏夹 UI 开关 + 显示偏好）"""
    return BaseResponse(message=ErrMsg.OK.msg, data=ConfigService.get_favorites_config())


@router.get(
    "/tag-cache", response_model=BaseResponse[TagCacheConfig], summary="获取标签缓存配置"
)
async def get_tag_cache_config_endpoint() -> BaseResponse[TagCacheConfig]:
    """获取标签缓存配置（定时增量刷新开关 + cron + 每页条数）"""
    return BaseResponse(
        message=ErrMsg.OK.msg, data=ConfigService.get_tag_cache_config()
    )


@router.put("/api", response_model=BaseResponse, summary="更新API配置")
async def update_api_config(api_config: ApiConfig) -> BaseResponse:
    """更新 API 配置"""
    success = ConfigService.update_api_config(api_config)
    if not success:
        raise APIException(ErrMsg.CONFIG_UPDATE_ERROR)
    return BaseResponse(message=ErrMsg.CONFIG_UPDATE_SUCCESS)


@router.put("/downloader", response_model=BaseResponse, summary="更新下载器配置")
async def update_downloader_config(down_config: DownloaderConfig) -> BaseResponse:
    """更新下载器配置"""
    success = ConfigService.update_downloader_config(down_config)
    if not success:
        raise APIException(ErrMsg.CONFIG_UPDATE_ERROR)
    return BaseResponse(message=ErrMsg.CONFIG_UPDATE_SUCCESS)


@router.put("/database", response_model=BaseResponse, summary="更新数据库配置")
async def update_database_config(database_config: DatabaseConfig) -> BaseResponse:
    """更新数据库配置"""
    success = ConfigService.update_database_config(database_config)
    if not success:
        raise APIException(ErrMsg.CONFIG_UPDATE_ERROR)
    return BaseResponse(message=ErrMsg.CONFIG_UPDATE_SUCCESS)


@router.put("/favorites", response_model=BaseResponse, summary="更新收藏夹配置")
async def update_favorites_config_endpoint(
    favorites_config: FavoritesConfig,
) -> BaseResponse:
    """更新收藏夹配置"""
    success = ConfigService.update_favorites_config(favorites_config)
    if not success:
        raise APIException(ErrMsg.CONFIG_UPDATE_ERROR)
    return BaseResponse(message=ErrMsg.CONFIG_UPDATE_SUCCESS)


@router.put(
    "/tag-cache", response_model=BaseResponse, summary="更新标签缓存配置"
)
async def update_tag_cache_config_endpoint(
    tag_cache_config: TagCacheConfig,
) -> BaseResponse:
    """更新标签缓存配置。

    保存成功后会立即重挂定时任务（开关/cron 变更免重启生效）；
    cron 非法由 Pydantic validator 直接拦下（422），不会写进配置文件。
    """
    success = ConfigService.update_tag_cache_config(tag_cache_config)
    if not success:
        raise APIException(ErrMsg.CONFIG_UPDATE_ERROR)
    return BaseResponse(message=ErrMsg.CONFIG_UPDATE_SUCCESS)


@router.post("/test-connection", response_model=BaseResponse, summary="测试数据库连接")
async def test_database_connection(database_config: DatabaseConfig) -> BaseResponse:
    """测试数据库连接"""
    result = ConfigService.test_database_connection(database_config)
    return BaseResponse(message=result["message"], data={"success": result["success"]})


@router.post("/reset", response_model=BaseResponse, summary="重置配置")
async def reset_config(
    section: str = Query(..., description="配置类型: api, downloader, database, favorites, tag_cache"),
) -> BaseResponse:
    """重置指定段的配置"""
    success, message = ConfigService.reset_config(section)
    if not success:
        raise APIException(ErrMsg.CONFIG_RESET_ERROR, data=message)
    return BaseResponse(message="Reset success.")
