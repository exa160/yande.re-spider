from sqlalchemy import (
    Column,
    Integer,
    DateTime,
    String,
    create_engine,
    Boolean,
    Enum,
    JSON,
)
from sqlalchemy.orm import DeclarativeBase, Session

from backend.config.settings import config
from backend.models.yande import Rating
import os


class Base(DeclarativeBase):
    pass


def _ensure_all_models():
    """延迟导入所有 ORM 模型以确保 create_all 能创建所有表"""
    from backend.dao import favorite_dao  # noqa: F401


class YandeData(Base):
    __tablename__ = "yande_data"
    id = Column(Integer, unique=True, primary_key=True, comment="yande picture ID")
    down_flag = Column(
        Boolean, default=True, primary_key=True, comment="yande picture down status"
    )
    tags = Column(String(918), comment="picture tag", nullable=True)
    created_at = Column(DateTime, primary_key=True, comment="yande picture create time")
    updated_at = Column(DateTime, primary_key=True, comment="yande picture update time")
    creator_id = Column(Integer, comment="yande picture update auther ID")
    author = Column(
        String(32), nullable=True, comment="yande picture update auther name"
    )
    change = Column(Integer, nullable=True, comment="yande picture update auther ID")
    source = Column(String(918), comment="source url")
    score = Column(Integer, nullable=True, comment="yande picture score")
    md5 = Column(String(32), comment="yande picture md5")
    file_size = Column(Integer, comment="yande picture file size")
    file_ext = Column(String(6), primary_key=True, comment="picture type")
    file_url = Column(String(918), comment="down url")
    is_shown_in_index = Column(Boolean, comment="")
    preview_url = Column(String(918), comment="preview url")
    preview_width = Column(Integer)
    preview_height = Column(Integer)
    actual_preview_width = Column(Integer)
    actual_preview_height = Column(Integer)
    sample_url = Column(String(918), comment="sample url")
    sample_width = Column(Integer)
    sample_height = Column(Integer)
    sample_file_size = Column(Integer)
    jpeg_url = Column(String(918), comment="jpeg url")
    jpeg_width = Column(Integer)
    jpeg_height = Column(Integer)
    jpeg_file_size = Column(Integer)
    rating = Column(
        Enum(Rating, values_callable=lambda x: [e.value for e in x]), primary_key=True
    )
    is_rating_locked = Column(Boolean)
    has_children = Column(Boolean)
    parent_id = Column(Integer, nullable=True)
    status = Column(String(16))
    is_pending = Column(Boolean)
    width = Column(Integer, primary_key=True)
    height = Column(Integer, primary_key=True)
    is_held = Column(Boolean)
    frames_pending_string = Column(String(918), nullable=True)
    frames_pending = Column(JSON)
    frames_string = Column(String(918), nullable=True)
    frames = Column(JSON)
    is_note_locked = Column(Boolean)
    last_noted_at = Column(Integer)
    last_commented_at = Column(Integer)


def get_db_engine():
    use_mariadb = config.database.enable and config.database.host

    if use_mariadb:
        engine = create_engine(
            f"mariadb+mariadbconnector://{config.database.user}:{config.database.password}@"
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
        _ensure_all_models()
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
