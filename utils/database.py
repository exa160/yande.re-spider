from sqlalchemy import Column, Integer, Text, DateTime, String, create_engine, Boolean, Enum, JSON
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session

from utils.constant import config
from utils.items import Rating


class MariaDBClient:

    class Base(DeclarativeBase):
        pass

    class YandeData(Base):
        __tablename__ = config.database.datatable
        id = Column(Integer,unique=True, primary_key=True, comment='yande picture ID')
        down_flag = Column(Boolean, default=True, primary_key=True, comment='yande picture down status')
        tags = Column(String(918), comment='picture tag', nullable=True)
        created_at = Column(DateTime, primary_key=True, comment='yande picture create time')
        updated_at = Column(DateTime, primary_key=True, comment='yande picture update time')
        creator_id = Column(Integer, comment='yande picture update auther ID')
        author = Column(String(32), nullable=True, comment='yande picture update auther name')
        change = Column(Integer, nullable=True, comment='yande picture update auther ID')
        source = Column(String(918), comment='source url')
        score = Column(Integer, nullable=True, comment='yande picture score')
        md5 = Column(String(32), comment='yande picture md5')
        file_size = Column(Integer, comment='yande picture file size')
        # 文件类型
        file_ext = Column(String(6), primary_key=True, comment='picture type')
        # 主下载连接
        file_url = Column(String(918), comment='down url')
        is_shown_in_index = Column(Boolean, comment='')
        # 预览图信息
        preview_url = Column(String(918), comment='preview url')
        preview_width = Column(Integer)
        preview_height = Column(Integer)
        actual_preview_width = Column(Integer)
        actual_preview_height = Column(Integer)
        # 小图信息
        sample_url = Column(String(918), comment='sample url')
        sample_width = Column(Integer)
        sample_height = Column(Integer)
        sample_file_size = Column(Integer)
        # jpg信息
        jpeg_url = Column(String(918), comment='jpeg url')
        jpeg_width = Column(Integer)
        jpeg_height = Column(Integer)
        jpeg_file_size = Column(Integer)
        rating = Column(Enum(Rating, values_callable=lambda x: [e.value for e in x]), primary_key=True)
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

    def __init__(self):
        engine = create_engine('mariadb+mariadbconnector://'
                               f'{config.database.user}:'
                               f'{config.database.password}@'
                               f'{config.database.host}:{config.database.port}/'
                               f'{config.database.schema_name}?charset=utf8')
        self.Base.metadata.create_all(bind=engine)
        # self.session = sessionmaker(engine)()
        self.session = Session(bind=engine)

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

    def close(self):
        self.session.close()


if __name__ == '__main__':
    sql_cli = MariaDBClient()
    from utils.items import YandePostData
    with open(r"C:\Share\a.json", 'rb') as f:
        for i in YandePostData.model_validate_json(f.read()).root:
            sql_cli.insert_data(MariaDBClient.YandeData(**i.model_dump()))
            break
