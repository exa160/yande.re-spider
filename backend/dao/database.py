"""
数据库连接层（向后兼容）

本模块保留用于向后兼容，新的数据库模块位于 backend.src.model.database。

提供：
- MariaDBClient: 兼容旧的数据库操作接口
- get_db_engine: 兼容旧的引擎获取接口
"""

from sqlalchemy import select

from backend.src.model.database import DatabaseManager, get_session_factory
from backend.src.model.database.models import YandeData, YandeTag, YandeArtist


def get_db_engine():
    """获取数据库引擎（向后兼容）"""
    return DatabaseManager.get_engine()


def _ensure_all_models():
    """确保所有模型已导入（向后兼容）"""
    # 模型已在 backend.src.model.database.models 中定义
    pass


class MariaDBClient:
    """
    MariaDB 客户端（向后兼容封装）

    使用新的 DatabaseManager 进行会话管理。
    """

    def __init__(self):
        self._session = get_session_factory()()
        self.YandeData = YandeData

    def insert_data(self, sql_data: YandeData):
        """插入数据"""
        self._session.add(sql_data)
        self._session.commit()

    def insert_check_by_id(self, _id: int) -> bool:
        """检查ID是否存在"""
        stmt = select(YandeData).where(YandeData.id == _id)
        result = self._session.execute(stmt).scalar_one_or_none()
        return result is not None

    def insert_by_id(self, _id: int, sql_data: YandeData) -> bool:
        """根据ID插入数据（如果不存在）"""
        if not self.insert_check_by_id(_id):
            self.insert_data(sql_data)
            return True
        return False

    def update_down_flag(self, _id: int, down_flag: bool = True) -> bool:
        """更新下载标志"""
        try:
            stmt = select(YandeData).where(YandeData.id == _id)
            record = self._session.execute(stmt).scalar_one_or_none()
            if record:
                record.down_flag = down_flag
                self._session.commit()
                return True
            return False
        except Exception as e:
            self._session.rollback()
            print(f"Update down_flag failed: {e}")
            return False

    def close(self):
        """关闭会话"""
        if self._session:
            self._session.close()
            self._session = None
