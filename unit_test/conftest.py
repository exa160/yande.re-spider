"""pytest 全局配置 + sqlite 文件备份/恢复 fixture

每个测试前后自动备份 + 还原 backend/data/yande_data.db，
即使测试抛异常或被 SIGINT 中断也能保证数据安全。

保护范围：整个 sqlite 文件（包含 yande_data / image_data /
favorite_folders / download_tasks / yande_tags / yande_artists /
tag_local_stats / yandeRE 等所有表）。

历史背景：
- 早期版本（commit f93fc04 诊断报告）只备份 yande_data 单表，无法防护其他表被污染。
  收藏夹/下载任务等模块的测试会修改 favorite_folders / download_tasks 等表，
  旧 fixture 不覆盖 → 真实生产数据被覆盖丢失。
- 现升级到文件级备份 + engine.dispose()，覆盖所有 schema/data 变更。

实现细节：
- setup:    shutil.copy2(.db, .db.pytest_bak)
- teardown: engine.dispose() 关闭所有连接 → copy2(.pytest_bak, .db) 还原 → 清理 .bak
- .pytest_bak 在 backend/data/ 内（已被 .gitignore 行 209 忽略）
- 性能开销：~22MB 文件复制一次约 30-50ms（SSD），100 个测试约 +3-5s，可接受
"""
import shutil
import sys
from pathlib import Path

# conftest.py 在 unit_test/ 下，src/ 在 backend/ 下；显式注入 backend/ 到 sys.path
# 才能让 pytest 在任意 cwd 下都能 import src.xxx（避免依赖外部 PYTHONPATH）
_BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

import pytest

from src.common.constant import path_constant
from src.dao.database import _cached_engine


@pytest.fixture(autouse=True)
def _protect_sqlite_db():
    """每个测试自动备份/还原整个 sqlite 数据库文件

    用法：autouse=True，所有测试自动应用，无需显式引用。
    """
    db_path = path_constant.sqlite_file
    backup_path = db_path.with_name(db_path.name + ".pytest_bak")

    # setup: 备份（copy2 保留 mtime，copy2 已存在会自动覆盖）
    shutil.copy2(db_path, backup_path)

    try:
        yield
    finally:
        # teardown: 还原（即使测试抛异常或 SIGINT 也执行）
        try:
            # 关键：先 dispose engine 关闭 StaticPool 的共享连接，
            # 否则还原 .db 后旧连接仍指向旧 inode，下次 session 操作会读到不一致的数据
            if _cached_engine is not None:
                _cached_engine.dispose()
            shutil.copy2(backup_path, db_path)
        finally:
            # 清理备份文件（无论还原是否成功都执行）
            if backup_path.exists():
                backup_path.unlink()
