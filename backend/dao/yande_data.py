from sqlalchemy import (
    select,
    func,
    Column,
    Integer,
    String,
    Boolean,
    DateTime,
    create_engine,
)
from sqlalchemy.orm import Session, declarative_base
from typing import List, Optional, Tuple
from backend.config.settings import config
import os


Base = declarative_base()


def get_db_engine():
    use_mariadb = config.database.enable and config.database.host

    if use_mariadb:
        engine = create_engine(
            f"mariadb+mariadbconnector://{config.database.user}:{config.database.password}@"
            f"{config.database.host}:{config.database.port}/{config.database.schema_name}"
        )
    else:
        db_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "data",
            "yande_data.db",
        )
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        engine = create_engine(f"sqlite:///{db_path}")
        Base.metadata.create_all(bind=engine)

    return engine


def get_table_name():
    return config.database.datatable if config.database.enable else "yande_data"


_cached_engine = None
_cached_table_name = None


def get_engine():
    global _cached_engine, _cached_table_name
    current_table_name = get_table_name()
    if _cached_engine is None or _cached_table_name != current_table_name:
        _cached_engine = get_db_engine()
        _cached_table_name = current_table_name
    return _cached_engine


def refresh_engine():
    global _cached_engine, _cached_table_name
    _cached_engine = None
    _cached_table_name = None


def _get_local_file_base():
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), "downloads")


def _check_local_file(image_id: int, file_ext: str, file_type: str) -> Optional[str]:
    base = _get_local_file_base()
    subdir = "previews" if file_type == "preview" else "originals"
    extensions = (
        ["jpg", "jpeg", "png", "gif", "webp"] if file_type == "preview" else [file_ext]
    )
    for ext in extensions:
        file_path = os.path.join(base, subdir, f"{image_id}.{ext}")
        if os.path.exists(file_path):
            return f"{image_id}.{ext}"
    return None


class YandeDataRepository:
    def __init__(self, session: Session = None):
        self._session = session

    @property
    def session(self) -> Session:
        if self._session is None:
            self._session = Session(bind=get_engine())
        return self._session

    def _get_model(self):
        table_name = get_table_name()

        class DynamicModel(Base):
            __tablename__ = table_name
            __table_args__ = {"extend_existing": True}
            id = Column(Integer, unique=True, primary_key=True)
            down_flag = Column(Boolean, default=True)
            tags = Column(String(918), nullable=True)
            created_at = Column(DateTime)
            updated_at = Column(DateTime)
            creator_id = Column(Integer)
            author = Column(String(32), nullable=True)
            change = Column(Integer, nullable=True)
            source = Column(String(918))
            score = Column(Integer, nullable=True)
            md5 = Column(String(32))
            file_size = Column(Integer)
            file_ext = Column(String(6))
            file_url = Column(String(918))
            is_shown_in_index = Column(Boolean)
            preview_url = Column(String(918))
            preview_width = Column(Integer)
            preview_height = Column(Integer)
            actual_preview_width = Column(Integer)
            actual_preview_height = Column(Integer)
            sample_url = Column(String(918))
            sample_width = Column(Integer)
            sample_height = Column(Integer)
            sample_file_size = Column(Integer)
            jpeg_url = Column(String(918))
            jpeg_width = Column(Integer)
            jpeg_height = Column(Integer)
            jpeg_file_size = Column(Integer)
            rating = Column(String(1))
            is_rating_locked = Column(Boolean)
            has_children = Column(Boolean)
            parent_id = Column(Integer, nullable=True)
            status = Column(String(16))
            is_pending = Column(Boolean)
            width = Column(Integer)
            height = Column(Integer)
            is_held = Column(Boolean)
            frames_pending_string = Column(String(918), nullable=True)
            frames_pending = Column(String(918), nullable=True)
            frames_string = Column(String(918), nullable=True)
            frames = Column(String(918), nullable=True)
            is_note_locked = Column(Boolean)
            last_noted_at = Column(Integer)
            last_commented_at = Column(Integer)

        return DynamicModel

    def query(
        self,
        page: int = 1,
        page_size: int = 20,
        tags: Optional[str] = None,
        rating: Optional[str] = None,
        author: Optional[str] = None,
        min_width: Optional[int] = None,
        max_width: Optional[int] = None,
        min_height: Optional[int] = None,
        max_height: Optional[int] = None,
        min_file_size: Optional[int] = None,
        max_file_size: Optional[int] = None,
        file_type: Optional[str] = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> Tuple[List[dict], int]:
        Model = self._get_model()
        query_stmt = select(Model)
        count_stmt = select(func.count()).select_from(Model)

        if tags:
            tags_filter = tags.replace(" AND ", " ").replace(" OR ", " ").split()
            for tag in tags_filter:
                if tag.startswith("-"):
                    query_stmt = query_stmt.filter(~Model.tags.contains(tag[1:]))
                else:
                    query_stmt = query_stmt.filter(Model.tags.contains(tag))

        if author:
            query_stmt = query_stmt.filter(Model.author == author)

        if rating and rating != "All":
            rating_map = {
                "Safe": "s",
                "Questionable": "q",
                "Explicit": "e",
                "s": "s",
                "q": "q",
                "e": "e",
            }
            rating_val = rating_map.get(rating, rating)
            query_stmt = query_stmt.filter(Model.rating == rating_val)

        if min_width:
            query_stmt = query_stmt.filter(Model.width >= min_width)
        if max_width:
            query_stmt = query_stmt.filter(Model.width <= max_width)
        if min_height:
            query_stmt = query_stmt.filter(Model.height >= min_height)
        if max_height:
            query_stmt = query_stmt.filter(Model.height <= max_height)

        if min_file_size:
            query_stmt = query_stmt.filter(Model.file_size >= min_file_size * 1024)
        if max_file_size:
            query_stmt = query_stmt.filter(Model.file_size <= max_file_size * 1024)

        if file_type:
            query_stmt = query_stmt.filter(Model.file_ext == file_type.lower())

        sort_column = getattr(Model, sort_by, Model.id)
        if sort_order.lower() == "desc":
            query_stmt = query_stmt.order_by(sort_column.desc())
        else:
            query_stmt = query_stmt.order_by(sort_column.asc())

        offset = (page - 1) * page_size
        query_stmt = query_stmt.offset(offset).limit(page_size)

        results = self.session.execute(query_stmt).scalars().all()
        total = self.session.execute(count_stmt).scalar() or 0

        rating_display_map = {"s": "Safe", "q": "Questionable", "e": "Explicit"}
        images = []
        for row in results:
            tags_list = row.tags.split() if row.tags else []
            rating_display = (
                rating_display_map.get(row.rating, row.rating) if row.rating else "Safe"
            )
            file_ext = row.file_ext or "jpg"

            local_preview = _check_local_file(row.id, file_ext, "preview")
            local_original = _check_local_file(row.id, file_ext, "original")

            images.append(
                {
                    "id": row.id,
                    "tags": tags_list,
                    "width": row.width or 0,
                    "height": row.height or 0,
                    "rating": rating_display,
                    "file_url": row.file_url or "",
                    "preview_url": row.preview_url or "",
                    "sample_url": None,
                    "file_size": row.file_size or 0,
                    "file_ext": file_ext,
                    "author": row.author or "",
                    "created_at": str(row.created_at) if row.created_at else "",
                    "md5": row.md5 or "",
                    "score": row.score,
                    "is_downloaded": True,
                    "local_preview_path": local_preview,
                    "local_file_path": local_original,
                }
            )

        return images, total

    def get_by_id(self, image_id: int) -> Optional[dict]:
        Model = self._get_model()
        stmt = select(Model).filter_by(id=image_id)
        row = self.session.execute(stmt).scalar_one_or_none()
        if not row:
            return None

        rating_display_map = {"s": "Safe", "q": "Questionable", "e": "Explicit"}
        tags_list = row.tags.split() if row.tags else []
        rating_display = (
            rating_display_map.get(row.rating, row.rating) if row.rating else "Safe"
        )
        file_ext = row.file_ext or "jpg"

        local_preview = _check_local_file(row.id, file_ext, "preview")
        local_original = _check_local_file(row.id, file_ext, "original")

        return {
            "id": row.id,
            "tags": tags_list,
            "width": row.width or 0,
            "height": row.height or 0,
            "rating": rating_display,
            "file_url": row.file_url or "",
            "preview_url": row.preview_url or "",
            "sample_url": None,
            "file_size": row.file_size or 0,
            "file_ext": file_ext,
            "author": row.author or "",
            "created_at": str(row.created_at) if row.created_at else "",
            "md5": row.md5 or "",
            "score": row.score,
            "is_downloaded": True,
            "local_preview_path": local_preview,
            "local_file_path": local_original,
        }

    def insert(self, data: dict) -> bool:
        Model = self._get_model()
        try:
            record = Model(**data)
            self.session.add(record)
            self.session.commit()
            return True
        except Exception:
            self.session.rollback()
            return False

    def check_exists(self, image_id: int) -> bool:
        Model = self._get_model()
        stmt = select(Model.id).filter_by(id=image_id)
        return self.session.execute(stmt).scalar_one_or_none() is not None
