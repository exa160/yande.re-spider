from enum import Enum
from http import HTTPStatus
from pathlib import Path

from pydantic import BaseModel, ConfigDict

# ==================== Rating 映射 ====================
RATING_DISPLAY_MAP = {
    "s": "Safe",
    "q": "Questionable",
    "e": "Explicit",
}


# ==================== Pydantic 模型基类 ====================
class ConstantModel(BaseModel):
    model_config = ConfigDict(frozen=True)


class CommonConstant(ConstantModel):
    supported_image_exts: list[str] = ["jpg", "jpeg", "png", "gif", "webp"]
    file_write_placeholder: bytes = b"\x00"


# ==================== 路径配置 ====================
class PathConstant(ConstantModel):
    base_dir: Path = Path(__file__).parent.parent.parent

    download_dir: Path = base_dir / "downloads"
    previews_dir: Path = download_dir / "previews"
    originals_dir: Path = download_dir / "originals"
    config_dir: Path = base_dir / "config"
    config_file: Path = config_dir / "config.yaml"
    data_dir: Path = base_dir / "data"
    sqlite_file: Path = data_dir / "yande_data.db"
    log_dir: Path = base_dir / "log"
    frontend_dist: Path = base_dir / "frontend" / "dist"


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

    # 图库界面
    LOAD_YANDE_DATA_ERROR = ("0010", "Failed to load yande data.", HTTPStatus.INTERNAL_SERVER_ERROR)
    LOAD_PREVIEW_DATA_ERROR = ("0010", "Failed to load preview data.", HTTPStatus.NOT_FOUND)
    SAVE_PREVIEW_DATA_ERROR = ("0010", "Failed to save preview data.", HTTPStatus.NOT_FOUND)

    # 配置相关
    CONFIG_UPDATE_ERROR = ("1001", "Config update error.", HTTPStatus.INTERNAL_SERVER_ERROR)
    CONFIG_RESET_ERROR = ("1002", "Config reset error.", HTTPStatus.INTERNAL_SERVER_ERROR)

    # 收藏夹
    REFRESH_LOCAL_COUNT_FAILED = ("2001", "Failed to refresh local count.", HTTPStatus.OK)   #  刷新本地数量失败，但不影响主流程，返回 200 并在消息中说明
    FAVORITE_FOLDER_NOT_FOUND = ("2404", "Favorite folder not found.", HTTPStatus.NOT_FOUND)

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
