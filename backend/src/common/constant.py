from enum import Enum
from http import HTTPStatus
from pathlib import Path

from pydantic import BaseModel, ConfigDict


# ==================== Rating 映射 ====================
RATING_MAP = {
    "Safe": "s",
    "Questionable": "q",
    "Explicit": "e",
    "s": "s",
    "q": "q",
    "e": "e",
    "S": "s",
    "Q": "q",
    "E": "e",
}
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
    post_api: str = f"{base_url}/post.json"
    tag_api: str = f"{base_url}/post.json"
    files_host: str = "files.yande.re"
    referer: str = f"{base_url}/"


class DownloadConstant(ConstantModel):
    ...


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
    OK = ("0000", "OK.")
    CONFIG_UPDATE_SUCCESS = ("0000", "Config update successful.")

    CONFIG_UPDATE_ERROR = ("1001", "Config update error.", HTTPStatus.INTERNAL_SERVER_ERROR)
    CONFIG_RESET_ERROR = ("1002", "Config reset error.", HTTPStatus.INTERNAL_SERVER_ERROR)

    NOT_FOUND_ERROR = ("1404", "Frontend not found.", HTTPStatus.NOT_FOUND)


path_constant = PathConstant()
yande_constant = YandeAPIConstant()