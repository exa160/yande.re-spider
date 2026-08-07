from enum import Enum
from http import HTTPStatus
from pathlib import Path

from pydantic import BaseModel, ConfigDict


# ==================== Pydantic 模型基类 ====================
class ConstantModel(BaseModel):
    model_config = ConfigDict(frozen=True)


class CommonConstant(ConstantModel):
    supported_image_exts: list[str] = ["jpg", "jpeg", "png", "gif", "webp"]
    file_write_placeholder: bytes = b"\x00"


class DatabaseTableNameConstant(ConstantModel):
    yande_data: str = "yande_data"
    yande_tag: str = "yande_tags"
    yande_artist: str = "yande_artists"
    tag_local_stats: str = "tag_local_stats"
    favorite_folder: str = "favorite_folders"
    download_task: str = "download_tasks"



# ==================== 路径配置 ====================
class PathConstant(ConstantModel):
    # 客户端感知：动态计算
    install_dir: Path = Path(__file__).parent.parent.parent
    user_config_dir: Path = Path.home() / ".config" / "yande-spider"

    # 数据/下载/日志：跟随安装目录
    download_dir: Path = install_dir / "downloads"
    previews_dir: Path = download_dir / "previews"
    originals_dir: Path = download_dir / "originals"
    data_dir: Path = install_dir / "data"
    sqlite_file: Path = data_dir / "yande_data.db"
    log_dir: Path = install_dir / "logs"

    # 配置：用户目录
    config_dir: Path = user_config_dir / "config"
    config_file: Path = config_dir / "config.yaml"

    # 端口文件：与 config 同层
    port_file: Path = user_config_dir / "port"

    # 前端 dist：frozen 时在 _internal/frontend/dist，dev 时在仓库 frontend/dist
    frontend_dist: Path = install_dir / "frontend" / "dist"


# 暴露 base_dir 作为类属性，供 path_resolver.resolve_install_dir() 和测试打补丁使用
# Pydantic v2 把字段存到 model_fields，不会自动暴露为类属性
PathConstant.base_dir = Path(__file__).parent.parent.parent


# 冻结后用解析函数覆盖（避免 pydantic frozen 限制，使用 module-level 单例）
def _resolve_paths() -> None:
    """在模块导入后被 init_app 调用，把动态解析值写入全局单例。"""
    from src.common.path_resolver import resolve_install_dir, resolve_user_config_dir

    install = resolve_install_dir()
    user_cfg = resolve_user_config_dir()
    global path_constant
    path_constant = PathConstant(
        install_dir=install,
        user_config_dir=user_cfg,
        download_dir=install / "downloads",
        previews_dir=install / "downloads" / "previews",
        originals_dir=install / "downloads" / "originals",
        data_dir=install / "data",
        sqlite_file=install / "data" / "yande_data.db",
        log_dir=install / "logs",
        config_dir=user_cfg / "config",
        config_file=user_cfg / "config" / "config.yaml",
        port_file=user_cfg / "port",
        frontend_dist=install / "frontend" / "dist",
    )


path_constant = PathConstant()  # 默认值；init_app 时会被覆盖


class YandeAPIConstant(ConstantModel):
    base_url: str = "https://yande.re"
    post_json_api: str = f"{base_url}/post.json"
    post_xml_api: str = f"{base_url}/post.xml"
    tag_json_api: str = f"{base_url}/tag.json"
    tag_related_api: str = f"{base_url}/tag/related.json" # TODO tag关联查询
    artist_json_api: str = f"{base_url}/artist.json"
    files_host: str = "files.yande.re"
    referer: str = f"{base_url}/"


class DownloadConstant(ConstantModel): ...


# ==================== 任务状态 ====================
class TaskStatus(str, Enum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# ==================== 路由映射 ====================
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


class CleanupMode(str, Enum):
    """预览图清理模式"""
    CLEAN_LOCAL_PREVIEWS = "clean_local_previews"  # 局部清理：有原图可再生的 preview
    CLEAN_ALL_PREVIEWS = "clean_all_previews"      # 全量清理：清空整个 previews/ 目录


class ProxyMode:
    """代理模式三态常量。SYSTEM 指后端进程环境变量（HTTP_PROXY 等），非浏览器用户系统设置。

    与 ApiConfig.proxy_enable 的存储值一一对应：
    - OFF    = False   — 关闭代理
    - CUSTOM = True    — 使用自定义代理（ApiConfig.proxies）
    - SYSTEM = None    — 读取后端进程环境变量
    """
    OFF = False
    CUSTOM = True
    SYSTEM = None


# ==================== 其他常量 ====================
class Rating(str, Enum):
    S = "s"
    R15 = "q"
    R18 = "e"

    @property
    def code(self) -> str:
        return self.value  # 's', 'q', 'e'

    @property
    def display(self) -> str:
        return {
            "s": "Safe",
            "q": "Questionable",
            "e": "Explicit"
        }[self.value]


# ==================== 错误码枚举 ====================
class BaseMsgEnum(Enum):
    def __new__(cls, code: str, msg: str, http_status: HTTPStatus = None):
        obj = object.__new__(cls)
        obj.code = code
        obj.msg = msg
        obj.http_status = HTTPStatus.OK
        if http_status:
            obj.http_status = http_status
        return obj


class ErrMsg(BaseMsgEnum):
    # 无异常
    OK = ("0000", "OK.")
    CONFIG_UPDATE_SUCCESS = ("0000", "Config update successful.")

    # 通用错误
    QUERY_ERROR = ("0001", "Query error.", HTTPStatus.INTERNAL_SERVER_ERROR)
    CREATE_ERROR = ("0002", "Create error.", HTTPStatus.INTERNAL_SERVER_ERROR)
    UPDATE_ERROR = ("0003", "Update error.", HTTPStatus.INTERNAL_SERVER_ERROR)
    DELETE_ERROR = ("0004", "Delete error.", HTTPStatus.INTERNAL_SERVER_ERROR)
    NOT_FOUND = ("0005", "Resource not found.", HTTPStatus.NOT_FOUND)
    PARAM_ERROR = ("0006", "Invalid parameter.", HTTPStatus.BAD_REQUEST)

    # 网络相关错误
    NETWORK_ERROR = ("0101", "Network error. Please check your internet connection.", HTTPStatus.BAD_GATEWAY)
    PROXY_ERROR = ("0102", "Proxy error. Please check proxy settings.", HTTPStatus.BAD_GATEWAY)
    TIMEOUT_ERROR = ("0103", "Request timeout. Please try again later.", HTTPStatus.GATEWAY_TIMEOUT)

    # 图库界面
    LOAD_YANDE_DATA_ERROR = ("0010", "Failed to load yande data.", HTTPStatus.INTERNAL_SERVER_ERROR)
    LOAD_PREVIEW_DATA_ERROR = ("0011", "Failed to load preview data.", HTTPStatus.NOT_FOUND)
    SAVE_PREVIEW_DATA_ERROR = ("0012", "Failed to save preview data.", HTTPStatus.NOT_FOUND)
    CLEANUP_PREVIEW_ERROR = ("0013", "Failed to cleanup preview cache.", HTTPStatus.INTERNAL_SERVER_ERROR)

    # 配置相关
    CONFIG_UPDATE_ERROR = ("1001", "Config update error.", HTTPStatus.INTERNAL_SERVER_ERROR)
    CONFIG_RESET_ERROR = ("1002", "Config reset error.", HTTPStatus.INTERNAL_SERVER_ERROR)

    # 收藏夹
    REFRESH_LOCAL_COUNT_FAILED = ("2001", "Failed to refresh local count.", HTTPStatus.OK)   #  刷新本地数量失败，但不影响主流程，返回 200 并在消息中说明
    FAVORITE_FOLDER_NOT_FOUND = ("2404", "Favorite folder not found.", HTTPStatus.NOT_FOUND)

    SCHEDULE_INVALID_CRON = ("5001", "Invalid cron expression.", HTTPStatus.BAD_REQUEST)
    SCHEDULE_DISABLED = ("5002", "Schedule is disabled for this folder.", HTTPStatus.BAD_REQUEST)
    SCHEDULE_TRIGGER_ERROR = ("5003", "Failed to trigger schedule.", HTTPStatus.INTERNAL_SERVER_ERROR)
    SCHEDULE_STATUS_NOT_FOUND = ("5404", "Schedule status not found.", HTTPStatus.NOT_FOUND)
    SCHEDULE_INVALID_RESET = ("5004", "Invalid last_synced_id value.", HTTPStatus.BAD_REQUEST)

    # 下载任务
    TASK_START_ERROR = ("3001", "Failed to start task.", HTTPStatus.BAD_REQUEST)
    TASK_PAUSE_ERROR = ("3002", "Failed to pause task.", HTTPStatus.BAD_REQUEST)
    TASK_RESUME_ERROR = ("3003", "Failed to resume task.", HTTPStatus.BAD_REQUEST)
    TASK_CANCEL_ERROR = ("3004", "Failed to cancel task.", HTTPStatus.BAD_REQUEST)
    TASK_NOT_FOUND = ("3404", "Download task not found.", HTTPStatus.NOT_FOUND)

    NOT_FOUND_ERROR = ("x404", "Frontend not found.", HTTPStatus.NOT_FOUND)

    INTERNAL_ERROR = ("9999", "Internal server error.", HTTPStatus.INTERNAL_SERVER_ERROR)



path_constant = PathConstant()
yande_constant = YandeAPIConstant()
table_constant = DatabaseTableNameConstant()
