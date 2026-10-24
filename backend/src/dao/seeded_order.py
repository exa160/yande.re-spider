"""随机浏览的确定性排序表达式（seed → 固定顺序）。

同一 seed + 同一候选池 ⇒ 完全相同的图片序列，因此磁贴预览
（/random_browse/preview?seed=...）与瀑布流（/gallery/load random_seed=...）
可以展示同一批图、同一顺序；翻页也不会因重新随机而重复/丢图。

方言差异：
- SQLite：注册 Python UDF ``yande_seeded_hash(id, seed)``，返回 ``hash((id, seed))``；
- MariaDB / MySQL / PostgreSQL：``MD5(CONCAT(id, ':', seed))``，在数据库内计算。

``hash((int, int))`` 不受 PYTHONHASHSEED 影响（随机化只作用于 str/bytes），
同一部署的多个 worker / 进程结果一致；seed 本身不跨重启持久化，因此无需
保证跨 Python 版本的稳定性。
"""

from sqlalchemy import event, func
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from src.models.database.yande import YandeData

_SQLITE_UDF_NAME = "yande_seeded_hash"


def _seeded_hash(image_id: int, seed: int) -> int:
    return hash((image_id, seed))


def install_sqlite_seeded_hash(engine: Engine) -> None:
    """在 SQLite engine 的每个新连接上注册 ``yande_seeded_hash`` UDF。

    必须在 engine 创建后、首次连接创建前调用（``get_db_engine`` 已在
    ``Base.metadata.create_all`` 前调用）。

    不要在查询路径里动态 ``create_function``：StaticPool 下同一个
    sqlite3.Connection 可能正被其它线程执行语句，此时
    ``sqlite3_create_function`` 返回 SQLITE_MISUSE，Python 抛
    ``OperationalError: Error creating function``（已实测可复现）。
    """
    if engine.dialect.name != "sqlite":
        return

    @event.listens_for(engine, "connect")
    def _register_seeded_hash(dbapi_connection, _connection_record) -> None:
        dbapi_connection.create_function(
            _SQLITE_UDF_NAME, 2, _seeded_hash, deterministic=True
        )


def seeded_order_expr(session: Session, seed: int) -> ColumnElement:
    """返回确定性排序表达式；调用方需再以 ``YandeData.id`` 作为次级排序键。"""
    if session.get_bind().dialect.name == "sqlite":
        # UDF 由 install_sqlite_seeded_hash 在 connect 时注册
        return func.yande_seeded_hash(YandeData.id, seed)
    # MariaDB / MySQL / PostgreSQL 都支持 md5 + concat
    return func.md5(func.concat(YandeData.id, ":", str(seed)))
