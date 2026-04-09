from sqlalchemy import (
    select,
    func,
    Column,
    Integer,
    String,
    Boolean,
    DateTime,
    create_engine,
    or_,
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
    from backend.dao.database import get_db_engine as _get_db_engine

    global _cached_engine, _cached_table_name
    current_table_name = get_table_name()
    if _cached_engine is None or _cached_table_name != current_table_name:
        _cached_engine = _get_db_engine()
        _cached_table_name = current_table_name
    return _cached_engine


def refresh_engine():
    global _cached_engine, _cached_table_name
    _cached_engine = None
    _cached_table_name = None


def _get_local_file_base():
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "downloads"
    )


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
        from backend.dao.database import YandeData

        self._session = session
        self._Model = YandeData

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._session:
            self._session.close()
        return False

    @property
    def session(self) -> Session:
        if self._session is None:
            self._session = Session(bind=get_engine())
        return self._session

    def _get_model(self):
        return self._Model

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
        downloaded_only: bool = False,
    ) -> Tuple[List[dict], int]:
        Model = self._get_model()
        query_stmt = select(Model)
        count_stmt = select(func.count()).select_from(Model)

        if tags:
            # 强制 AND 逻辑：忽略 OR，只保留 AND 语义
            # 先把 OR 替换成 AND，再统一处理
            tags_normalized = tags.upper().replace(" OR ", " AND ")
            tags_filter = [t for t in tags_normalized.split(" AND ") if t.strip()]
            for tag in tags_filter:
                tag = tag.strip()
                if tag.startswith("-"):
                    query_stmt = query_stmt.filter(~Model.tags.contains(tag[1:]))
                    count_stmt = count_stmt.filter(~Model.tags.contains(tag[1:]))
                else:
                    query_stmt = query_stmt.filter(Model.tags.contains(tag))
                    count_stmt = count_stmt.filter(Model.tags.contains(tag))

        if author:
            query_stmt = query_stmt.filter(Model.author == author)
            count_stmt = count_stmt.filter(Model.author == author)

        if rating and rating != "All":
            rating_map = {
                "Safe": "s",
                "Questionable": "q",
                "Explicit": "e",
                "s": "s",
                "q": "q",
                "e": "e",
            }
            rating_values = []
            for r in rating.split(","):
                r = r.strip()
                if r:
                    mapped = rating_map.get(r, r)
                    if mapped:
                        rating_values.append(mapped)

            if rating_values:
                if len(rating_values) == 1:
                    query_stmt = query_stmt.filter(Model.rating == rating_values[0])
                    count_stmt = count_stmt.filter(Model.rating == rating_values[0])
                else:
                    rating_filters = [Model.rating == rv for rv in rating_values]
                    query_stmt = query_stmt.filter(or_(*rating_filters))
                    count_stmt = count_stmt.filter(or_(*rating_filters))

        if min_width:
            query_stmt = query_stmt.filter(Model.width >= min_width)
            count_stmt = count_stmt.filter(Model.width >= min_width)
        if max_width:
            query_stmt = query_stmt.filter(Model.width <= max_width)
            count_stmt = count_stmt.filter(Model.width <= max_width)
        if min_height:
            query_stmt = query_stmt.filter(Model.height >= min_height)
            count_stmt = count_stmt.filter(Model.height >= min_height)
        if max_height:
            query_stmt = query_stmt.filter(Model.height <= max_height)
            count_stmt = count_stmt.filter(Model.height <= max_height)

        if min_file_size:
            query_stmt = query_stmt.filter(Model.file_size >= min_file_size * 1024)
            count_stmt = count_stmt.filter(Model.file_size >= min_file_size * 1024)
        if max_file_size:
            query_stmt = query_stmt.filter(Model.file_size <= max_file_size * 1024)
            count_stmt = count_stmt.filter(Model.file_size <= max_file_size * 1024)

        if file_type:
            ext_values = [
                ext.strip().lower() for ext in file_type.split(",") if ext.strip()
            ]
            if len(ext_values) == 1:
                query_stmt = query_stmt.filter(Model.file_ext == ext_values[0])
                count_stmt = count_stmt.filter(Model.file_ext == ext_values[0])
            elif len(ext_values) > 1:
                ext_filters = [Model.file_ext == ext for ext in ext_values]
                query_stmt = query_stmt.filter(or_(*ext_filters))
                count_stmt = count_stmt.filter(or_(*ext_filters))

        if downloaded_only:
            query_stmt = query_stmt.filter(Model.down_flag == True)
            count_stmt = count_stmt.filter(Model.down_flag == True)

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
            rating_val = (
                row.rating.value if hasattr(row.rating, "value") else row.rating
            )
            rating_display = (
                rating_display_map.get(rating_val, rating_val) if rating_val else "Safe"
            )
            file_ext = row.file_ext or "jpg"

            local_preview = _check_local_file(row.id, file_ext, "preview")
            local_original = _check_local_file(row.id, file_ext, "original")
            is_downloaded = row.down_flag if hasattr(row, "down_flag") else True

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
                    "is_downloaded": is_downloaded,
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

    def check_downloaded(self, image_id: int) -> bool:
        """检查图片是否已下载（记录存在且 down_flag=True）"""
        Model = self._get_model()
        stmt = select(Model.id).filter_by(id=image_id, down_flag=True)
        return self.session.execute(stmt).scalar_one_or_none() is not None
