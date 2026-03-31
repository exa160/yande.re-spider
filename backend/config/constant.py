"""
集中管理所有硬编码常量

所有硬编码的URL、路径、阈值、状态字符串等都应在此定义
"""

from enum import Enum
from pathlib import Path

# ============== 项目路径 ==============
# 基础路径 - 项目根目录
BASE_DIR = Path(__file__).parent.parent.parent

# 下载目录
DOWNLOADS_DIR = BASE_DIR / "downloads"
PREVIEWS_DIR = DOWNLOADS_DIR / "previews"
ORIGINALS_DIR = DOWNLOADS_DIR / "originals"

# 数据目录
DATA_DIR = BASE_DIR / "data"

# ============== Yande.re API ==============
YANDE_RE_BASE_URL = "https://yande.re"
YANDE_RE_POST_API = f"{YANDE_RE_BASE_URL}/post.json"
YANDE_RE_FILES_HOST = "files.yande.re"

# Referer 头
YANDE_RE_REFERER = f"{YANDE_RE_BASE_URL}/"

# ============== API 路径 ==============
API_V1_PREFIX = "/api/v1"
CACHE_PREVIEW_PATH = f"{API_V1_PREFIX}/cache/preview"
CACHE_ORIGINAL_PATH = f"{API_V1_PREFIX}/cache/original"

# ============== 超时设置 (秒) ==============
TIMEOUT_PREVIEW = 10  # 预览图下载超时
TIMEOUT_ORIGINAL = 30  # 原图下载超时
TIMEOUT_RANGE_DOWNLOAD = 50  # 分段下载超时
TIMEOUT_API_DEFAULT = 30  # API默认超时

# ============== 重试设置 ==============
RETRY_COUNT = 3  # API请求重试次数
RETRY_DOWNLOAD = 3  # 下载重试次数
RETRY_SLEEP_SECONDS = 6  # 重试间隔

# ============== 线程和分块设置 ==============
DEFAULT_THREAD_NUM = 4
DEFAULT_CHUNK_SIZE = 10 * 1024  # 10 KB
DEFAULT_SPLIT_SIZE = 5 * 1024 * 1024  # 5 MB

# ============== 缩略图设置 ==============
THUMBNAIL_MAX_SIZE = 300  # 最大边长
THUMBNAIL_QUALITY = 85  # JPEG质量
THUMBNAIL_RESAMPLING = "LANCZOS"  # 重采样方法


# ============== 下载任务状态 ==============
class TaskStatus(str, Enum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# ============== 评分映射 ==============
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

# ============== 分页默认值 ==============
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

# ============== 文件扩展名 ==============
SUPPORTED_IMAGE_EXTS = ["jpg", "jpeg", "png", "gif", "webp"]

# ============== 其他 ==============
MD5_CHECK_ENABLED = True
FILE_WRITE_PLACEHOLDER = "\x00"
