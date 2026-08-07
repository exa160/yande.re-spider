"""用户配置首次写入。

首启行为：
- 用户配置目录不存在 → 创建目录并写入 placeholder（password=''，proxy_enable=False）
- 文件已存在 → 不覆盖（保留用户修改）

打包内置的 config/config.yaml 永远是 placeholder（不入 git 敏感数据）。
"""
from __future__ import annotations

from pathlib import Path

from loguru import logger


DEFAULT_PLACEHOLDER_YAML = """\
# 默认配置（首启生成）。请通过 UI 修改，敏感字段请勿手改。
database:
  enable: false
  host: localhost
  port: 3306
  user: root
  password: ''
  schema_name: Pictures
yande_api:
  proxy_enable: false
  timeout: 30
  retry: 3
  proxies:
    http: ''
    https: ''
downloader:
  thread_num: 4
  max_concurrent_tasks: 3
  chunk_size: 10240
  split_size: 52428800
  retry_times: 3
scheduler:
  max_concurrent_schedules: 2
  max_images_per_run_default: 800
  per_page_limit: 100
app:
  debug: false
"""


def write_default_user_config(target: Path) -> None:
    """写入默认配置到目标路径。已存在则跳过。"""
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        logger.info(f"Config already exists at {target}, skip bootstrap.")
        return
    target.write_text(DEFAULT_PLACEHOLDER_YAML, encoding="utf-8")
    logger.info(f"Default config written to {target}.")
