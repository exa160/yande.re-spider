from enum import Enum
from http import HTTPStatus
from pathlib import Path

from pydantic import BaseModel, ConfigDict


YANDE_RE_BASE_URL = "https://yande.re"
YANDE_RE_POST_API = f"{YANDE_RE_BASE_URL}/post.json"
YANDE_RE_TAG_API = f"{YANDE_RE_BASE_URL}/post.json"
YANDE_RE_FILES_HOST = "files.yande.re"
YANDE_RE_REFERER = f"{YANDE_RE_BASE_URL}/"

API_V1_PREFIX = "/api/v1"
CACHE_PREVIEW_PATH = f"{API_V1_PREFIX}/cache/preview"
CACHE_ORIGINAL_PATH = f"{API_V1_PREFIX}/cache/original"

TIMEOUT_PREVIEW = 10
TIMEOUT_ORIGINAL = 30
TIMEOUT_RANGE_DOWNLOAD = 50
TIMEOUT_API_DEFAULT = 30

RETRY_COUNT = 3
RETRY_DOWNLOAD = 3
RETRY_SLEEP_SECONDS = 6

DEFAULT_THREAD_NUM = 4
DEFAULT_CHUNK_SIZE = 10 * 1024
DEFAULT_SPLIT_SIZE = 5 * 1024 * 1024

THUMBNAIL_MAX_SIZE = 300
THUMBNAIL_QUALITY = 85
THUMBNAIL_RESAMPLING = "LANCZOS"

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

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

SUPPORTED_IMAGE_EXTS = ["jpg", "jpeg", "png", "gif", "webp"]

FILE_WRITE_PLACEHOLDER = "\x00"


class ConstantModel(BaseModel):
    model_config = ConfigDict(frozen=True)


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


class DownloadConstant(ConstantModel):
    ...


class TaskStatus(str, Enum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


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
    CONFIG_UPDATE_SUCCESS = ("0000", "配置更新成功")

    CONFIG_UPDATE_ERROR = ("1001", "Config update error.", HTTPStatus.INTERNAL_SERVER_ERROR)
    CONFIG_RESET_ERROR = ("1002", "Config reset error.", HTTPStatus.INTERNAL_SERVER_ERROR)

    NOT_FOUND_ERROR = ("1404", "Frontend not found.", HTTPStatus.NOT_FOUND)


path_constant = PathConstant()
