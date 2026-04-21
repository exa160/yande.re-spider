from sqlalchemy import (
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Session

from backend.src.common import config
from backend.src.models.database.yande import YandeData
import os


class Base(DeclarativeBase):
    pass


def get_db_engine():
    use_mariadb = config.database.enable and config.database.host

    if use_mariadb:
        engine = create_engine(
            f"mariadb+mariadbconnector://{config.database.user}:{config.database.password.get_secret_value()}@"
            f"{config.database.host}:{config.database.port}/{config.database.schema_name}"
        )
    else:
        db_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "data",
            "yande_data.db",
        )
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        engine = create_engine(f"sqlite:///{db_path}")
        Base.metadata.create_all(bind=engine)

    return engine


class MariaDBClient:
    def __init__(self):
        self.engine = get_db_engine()
        self.session = Session(bind=self.engine)
        self.YandeData = YandeData

    def insert_data(self, sql_data: YandeData):
        self.session.add(sql_data)
        self.session.commit()

    def insert_check_by_id(self, _id):
        q = self.session.query(self.YandeData).filter_by(id=_id).one_or_none()
        if q is None:
            return True
        return False

    def insert_by_id(self, _id, sql_data: YandeData):
        if self.insert_check_by_id(_id):
            self.insert_data(sql_data)

    def update_down_flag(self, _id: int, down_flag: bool = True):
        try:
            record = self.session.query(self.YandeData).filter_by(id=_id).first()
            if record:
                record.down_flag = down_flag
                self.session.commit()
                return True
            return False
        except Exception as e:
            self.session.rollback()
            print(f"Update down_flag failed: {e}")
            return False

    def close(self):
        self.session.close()
