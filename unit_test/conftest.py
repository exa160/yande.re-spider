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
- setup:    shutil.copy2(.db, .db.pytest_bak.<pid>.<n>) 备份到**唯一名**临时文件
- teardown: engine.dispose() 关闭所有连接 → copy2(备份, .db) 还原 → 清理备份
- 备份在 backend/data/ 内（已被 .gitignore 行 209 忽略）
- 性能开销：~22MB 文件复制一次约 30-50ms（SSD），100 个测试约 +3-5s，可接受

⚠️ 并发安全（2026-10-01 事故修复）
------------------------------
旧实现用**固定**备份名 ``yande_data.db.pytest_bak``。两个 pytest 进程
（如同时跑 ``cd backend && pytest`` 与仓库根 ``pytest unit_test/``）会：

    P1: copy(.db → .pytest_bak)          P2: copy(.db → .pytest_bak)   ← 覆盖 P1 的备份
    P1: 测试写脏 .db                      P2: 测试写脏 .db
    P1: copy(.pytest_bak → .db) 还原      P2: copy(.pytest_bak → .db) 还原
    P1: unlink(.pytest_bak)               P2: unlink(...) → FileNotFoundError

互相还原 + 互删备份，**并发跑测试会损坏真实的 yande_data.db**（本次事故即
由此产生：yande_data 表 B 树 rootpage 3 损坏，全表不可读）。

现改为：
1. **唯一备份名**：``.pytest_bak.<pid>.<序号>``，不同进程永不冲突
2. **进程级文件锁**（fcntl.flock）把「备份 → 测试 → 还原」整段串行化，
   杜绝两个进程在同一 .db 上交错读写
3. **孤儿备份清理**：只清理本进程自己创建的备份文件，绝不删别人的
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

# conftest.py 在 unit_test/ 下，src/ 在 backend/ 下；显式注入 backend/ 到 sys.path
# 才能让 pytest 在任意 cwd 下都能 import src.xxx（避免依赖外部 PYTHONPATH）
_BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

import pytest

from src.common.constant import path_constant
from src.dao.database import _cached_engine

try:  # POSIX
    import fcntl

    _LOCK_EX = fcntl.LOCK_EX
    _LOCK_UN = fcntl.LOCK_UN
except ImportError:  # pragma: no cover - Windows
    fcntl = None
    _LOCK_EX = _LOCK_UN = None


def _acquire_db_lock(db_path: Path):
    """获取跨进程文件锁，串行化对 .db 的备份/还原。

    返回已加锁的文件对象（调用方负责 close 释放）。fcntl 不可用时返回 None，
    此时退化为「仅唯一备份名」保护（仍有残余风险，故在 docstring 中标注）。
    """
    if fcntl is None:
        return None
    lock_path = db_path.with_name(db_path.name + ".pytest.lock")
    fh = open(lock_path, "a+b")   # 不删除锁文件，避免 unlink 造成的锁失效竞态
    fcntl.flock(fh.fileno(), _LOCK_EX)
    return fh


def _release_db_lock(fh):
    if fh is None:
        return
    try:
        fcntl.flock(fh.fileno(), _LOCK_UN)
    finally:
        fh.close()


@pytest.fixture(autouse=True)
def _protect_sqlite_db():
    """每个测试自动备份/还原整个 sqlite 数据库文件（并发安全版）

    用法：autouse=True，所有测试自动应用，无需显式引用。
    """
    db_path = path_constant.sqlite_file

    # 新 clone / CI 上 backend/data/ 整个目录都不存在（被 .gitignore 排除），
    # 此时无库可备份。必须先判存在性，否则下面 copy2 会在 setup 抛
    # FileNotFoundError，autouse 会让该目录下每个测试都失败。
    if not db_path.exists():
        yield
        return

    # 整段临界区（备份 → 测试 → 还原）持锁，杜绝并发交错
    lock_fh = _acquire_db_lock(db_path)
    try:
        # 唯一备份名：同进程多次、不同进程并发都不冲突
        fd, backup_name = tempfile.mkstemp(
            prefix=db_path.name + ".pytest_bak.", dir=str(db_path.parent)
        )
        os.close(fd)
        backup_path = Path(backup_name)
        shutil.copy2(db_path, backup_path)

        restore_ok = False
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
                restore_ok = True
            finally:
                # 仅在还原成功后清理备份。还原失败时必须保留备份文件，
                # 否则生产库处于被测试改动后的状态且备份已删，无法手工恢复。
                # 只删本进程创建的备份（唯一名保证不会误删他人文件）
                if restore_ok and backup_path.exists():
                    backup_path.unlink()
    finally:
        _release_db_lock(lock_fh)
