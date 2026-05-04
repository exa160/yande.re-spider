# 配置常量规范

## PathConstant（路径常量）

```python
from pathlib import Path
from pydantic import BaseModel, ConfigDict


class ConstantModel(BaseModel):
    model_config = ConfigDict(frozen=True)  # 不可变配置


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
    frontend_dist: Path = base_dir / "frontend-dist"


path_constant = PathConstant()
```

## TaskStatus（任务状态枚举）

```python
class TaskStatus(str, Enum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
```