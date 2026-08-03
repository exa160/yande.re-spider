
from typing import Optional

import requests

from src.common.constant import ErrMsg, ProxyMode, path_constant
from src.common.settings import config


def configure_proxy_session(session: requests.Session) -> requests.Session:
    """按 ProxyMode 三态统一配置 requests Session 的代理与 trust_env。

    | mode    | trust_env | proxies                  |
    |---------|-----------|--------------------------|
    | OFF     | False     | 清空                     |
    | CUSTOM  | False     | proxies.http/https       |
    | SYSTEM  | True      | 清空（让 requests 读环境）|

    强制 OFF/CUSTOM 都关 trust_env，避免 requests 默认 trust_env=True 时被
    环境变量里的 HTTP_PROXY 偷偷生效（即原代码「关闭代理实际未关」的问题）。
    """
    mode = config.yande_api.proxy_enable
    session.proxies.clear()

    if mode == ProxyMode.CUSTOM:
        session.trust_env = False
        session.proxies.update(config.yande_api.proxies.model_dump(mode="json"))
    elif mode == ProxyMode.SYSTEM:
        session.trust_env = True
    else:
        session.trust_env = False

    return session


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
        # Connection refused：OFF 模式按网络错误归类，CUSTOM/SYSTEM 时通常为代理端口未启动
        if "Connection refused" in error_msg or "ECONNREFUSED" in error_msg:
            if config.yande_api.proxy_enable != ProxyMode.OFF:
                return ErrMsg.PROXY_ERROR, f"Proxy connection refused: {error_msg}"
            return ErrMsg.NETWORK_ERROR, f"Connection refused: {error_msg}"
        return ErrMsg.NETWORK_ERROR, f"Connection failed: {error_msg}"

    # 其他错误默认使用通用错误
    return ErrMsg.QUERY_ERROR, f"Request failed: {error_msg}"