from enum import Enum
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent.parent

DOWNLOADS_DIR = BASE_DIR / "downloads"
PREVIEWS_DIR = DOWNLOADS_DIR / "previews"
ORIGINALS_DIR = DOWNLOADS_DIR / "originals"

DATA_DIR = BASE_DIR / "data"

YANDE_RE_BASE_URL = "https://yande.re"
YANDE_RE_POST_API = f"{YANDE_RE_BASE_URL}/post.json"
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


class TaskStatus(str, Enum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


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

MD5_CHECK_ENABLED = True
FILE_WRITE_PLACEHOLDER = "\x00"
