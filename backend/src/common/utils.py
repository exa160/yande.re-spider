
from typing import Optional, MutableMapping

import requests

from src.common.constant import ErrMsg, path_constant
from src.common.settings import config


def get_proxy() -> Optional[MutableMapping[str, str]]:
    if config.yande_api.proxy_enable:
        return config.yande_api.proxies.model_dump(mode="json")
    return None


def check_local_file(image_id: int, file_ext: str, file_type: str) -> Optional[str]:
    base = path_constant.previews_dir if file_type == "preview" else path_constant.originals_dir
    extensions = (
        # , "jpeg", "png", "gif", "webp"
        ["jpg"] if file_type == "preview" else [file_ext]
    )
    for ext in extensions:
        file_path = base / f"{image_id}.{ext}"
        if file_path.exists():
            return f"{image_id}.{ext}"
    return None


def get_error_type_from_exception(e: Exception) -> tuple[ErrMsg, str]:
    """
    从异常中判断错误类型，返回 (ErrMsg, 详细错误信息)

    错误类型优先级：
    1. ProxyError - 代理配置错误
    2. Timeout - 请求超时
    3. ConnectionError - 网络连接错误
    4. 其他
    """
    error_msg = str(e)

    # 检查是否是代理错误
    if isinstance(e, requests.exceptions.ProxyError):
        return ErrMsg.PROXY_ERROR, f"Proxy connection failed: {error_msg}"

    # 检查是否是超时错误
    if isinstance(e, (requests.exceptions.Timeout, requests.exceptions.ConnectTimeout, requests.exceptions.ReadTimeout)):
        return ErrMsg.TIMEOUT_ERROR, f"Request timeout: {error_msg}"

    # 检查是否是连接错误
    if isinstance(e, requests.exceptions.ConnectionError):
        # 尝试获取更详细的错误信息
        if "Proxy" in error_msg or "proxy" in error_msg:
            return ErrMsg.PROXY_ERROR, f"Proxy connection failed: {error_msg}"
        # Connection refused 通常是网络问题或代理问题
        if "Connection refused" in error_msg or "ECONNREFUSED" in error_msg:
            if config.yande_api.proxy_enable:
                return ErrMsg.PROXY_ERROR, f"Proxy connection refused: {error_msg}"
            return ErrMsg.NETWORK_ERROR, f"Connection refused: {error_msg}"
        return ErrMsg.NETWORK_ERROR, f"Connection failed: {error_msg}"

    # 其他错误默认使用通用错误
    return ErrMsg.QUERY_ERROR, f"Request failed: {error_msg}"