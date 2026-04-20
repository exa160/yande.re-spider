"""
Yande.re 数据仓库

提供图片、标签、艺术家的数据访问接口。
使用新的 DatabaseManager 进行会话管理和事务控制。
"""

from sqlalchemy import select, func, or_
from sqlalchemy.orm import Session
from typing import List, Optional, Tuple

from backend.src.model.database import DatabaseManager, get_session_factory
from backend.src.model.database.models import YandeTag, YandeArtist, YandeData
from loguru import logger
import os


def get_table_name() -> str:
    """获取当前配置的表名（MariaDB 模式下有效）"""
    from backend.config.settings import config

    return config.database.datatable if config.database.enable else "yande_data"


# 缓存引擎和表名（向后兼容）
_cached_engine = None
_cached_table_name = None


def get_engine():
    """获取数据库引擎（向后兼容）"""
    global _cached_engine, _cached_table_name
    current_table_name = get_table_name()
    if _cached_engine is None or _cached_table_name != current_table_name:
        _cached_engine = DatabaseManager.get_engine()
        _cached_table_name = current_table_name
    return _cached_engine


def refresh_engine():
    """刷新引擎（向后兼容）"""
    global _cached_engine, _cached_table_name
    _cached_engine = None
    _cached_table_name = None


def _get_local_file_base() -> str:
    """获取本地文件基础目录"""
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "downloads"
    )


def _check_local_file(image_id: int, file_ext: str, file_type: str) -> Optional[str]:
    """检查本地文件是否存在"""
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
    """
    Yande 图片数据仓库

    使用新的 DatabaseManager 进行会话管理。
    """

    def __init__(self, session: Session = None):
        self._session = session
        self._session_owns = session is None

    def __enter__(self):
        if self._session is None:
            self._session = get_session_factory()()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._session and self._session_owns:
            if exc_type is not None:
                self._session.rollback()
            else:
                try:
                    self._session.commit()
                except Exception as e:
                    logger.error(f"Database commit error: {e}")
                    self._session.rollback()
                    raise
            self._session.close()
        return False

    @property
    def session(self) -> Session:
        if self._session is None:
            self._session = get_session_factory()()
        return self._session

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
        """查询图片列表"""
        Model = YandeData
        query_stmt = select(Model)
        count_stmt = select(func.count()).select_from(Model)

        if tags:
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
            rating_val = row.rating
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
        """根据ID获取图片详情"""
        Model = YandeData
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
        """插入图片数据"""
        try:
            record = YandeData(**data)
            self.session.add(record)
            self.session.commit()
            return True
        except Exception as e:
            logger.warning(f"Insert yande data error: {e}")
            self.session.rollback()
            return False

    def check_exists(self, image_id: int) -> bool:
        """检查图片是否存在"""
        stmt = select(YandeData.id).filter_by(id=image_id)
        return self.session.execute(stmt).scalar_one_or_none() is not None

    def check_downloaded(self, image_id: int) -> bool:
        """检查图片是否已下载（记录存在且 down_flag=True）"""
        stmt = select(YandeData.id).filter_by(id=image_id, down_flag=True)
        return self.session.execute(stmt).scalar_one_or_none() is not None


class TagRepository:
    """
    标签缓存仓库

    使用新的 DatabaseManager 进行会话管理。
    """

    def __init__(self, session: Session = None):
        self._session = session
        self._session_owns = session is None

    def __enter__(self):
        if self._session is None:
            self._session = get_session_factory()()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._session and self._session_owns:
            if exc_type is not None:
                self._session.rollback()
            else:
                try:
                    self._session.commit()
                except Exception as e:
                    logger.error(f"Database commit error: {e}")
                    self._session.rollback()
                    raise
            self._session.close()
        return False

    @property
    def session(self) -> Session:
        if self._session is None:
            self._session = get_session_factory()()
        return self._session

    def upsert_tags(self, tags: List[dict]) -> int:
        """批量插入或更新标签，返回成功更新的数量"""
        from datetime import datetime

        count = 0
        for tag_data in tags:
            try:
                stmt = select(YandeTag).filter_by(id=tag_data.get("id"))
                existing = self.session.execute(stmt).scalar_one_or_none()
                if existing:
                    existing.name = tag_data.get("name", existing.name)
                    existing.count = tag_data.get("count", existing.count)
                    existing.type = tag_data.get("type", existing.type)
                    existing.ambiguous = tag_data.get("ambiguous", existing.ambiguous)
                    existing.updated_at = datetime.now()
                else:
                    new_tag = YandeTag(
                        id=tag_data["id"],
                        name=tag_data.get("name", ""),
                        count=tag_data.get("count", 0),
                        type=tag_data.get("type", 0),
                        ambiguous=tag_data.get("ambiguous", False),
                        updated_at=datetime.now(),
                    )
                    self.session.add(new_tag)
                count += 1
            except Exception as e:
                logger.warning(f"Upsert tag error: {e}")
        self.session.commit()
        return count

    def get_tag_by_id(self, tag_id: int) -> Optional[dict]:
        """根据ID获取标签"""
        stmt = select(YandeTag).filter_by(id=tag_id)
        tag = self.session.execute(stmt).scalar_one_or_none()
        if tag:
            return {
                "id": tag.id,
                "name": tag.name,
                "count": tag.count,
                "type": tag.type,
                "ambiguous": tag.ambiguous,
            }
        return None

    def get_tag_count(self) -> int:
        """获取缓存的标签总数"""
        stmt = select(func.count(YandeTag.id))
        return self.session.execute(stmt).scalar() or 0

    def get_max_id(self) -> int:
        """获取缓存中标签的最大ID"""
        stmt = select(func.max(YandeTag.id))
        result = self.session.execute(stmt).scalar()
        return result or 0

    def clear_all_tags(self):
        """清空所有标签缓存"""
        self.session.query(YandeTag).delete()
        self.session.commit()

    def search_tags(self, keyword: str, limit: int = 20) -> List[dict]:
        """搜索标签"""
        stmt = (
            select(YandeTag)
            .filter(YandeTag.name.like(f"%{keyword}%"))
            .order_by(YandeTag.count.desc())
            .limit(limit)
        )
        results = self.session.execute(stmt).scalars().all()
        return [
            {
                "id": t.id,
                "name": t.name,
                "count": t.count,
                "type": t.type,
                "ambiguous": t.ambiguous,
            }
            for t in results
        ]


class ArtistRepository:
    """
    艺术家缓存仓库

    使用新的 DatabaseManager 进行会话管理。
    """

    def __init__(self, session: Session = None):
        self._session = session
        self._session_owns = session is None

    def __enter__(self):
        if self._session is None:
            self._session = get_session_factory()()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._session and self._session_owns:
            if exc_type is not None:
                self._session.rollback()
            else:
                try:
                    self._session.commit()
                except Exception as e:
                    logger.error(f"Database commit error: {e}")
                    self._session.rollback()
                    raise
            self._session.close()
        return False

    @property
    def session(self) -> Session:
        if self._session is None:
            self._session = get_session_factory()()
        return self._session

    def upsert_artists(self, artists: List[dict]) -> int:
        """批量插入或更新艺术家，返回成功更新的数量"""
        from datetime import datetime
        import json

        count = 0
        for artist_data in artists:
            try:
                stmt = select(YandeArtist).filter_by(id=artist_data.get("id"))
                existing = self.session.execute(stmt).scalar_one_or_none()
                urls_json = json.dumps(artist_data.get("urls", []))
                if existing:
                    existing.name = artist_data.get("name", existing.name)
                    existing.alias_id = artist_data.get("alias_id")
                    existing.group_id = artist_data.get("group_id")
                    existing.urls = urls_json
                    existing.updated_at = datetime.now()
                else:
                    new_artist = YandeArtist(
                        id=artist_data["id"],
                        name=artist_data.get("name", ""),
                        alias_id=artist_data.get("alias_id"),
                        group_id=artist_data.get("group_id"),
                        urls=urls_json,
                        updated_at=datetime.now(),
                    )
                    self.session.add(new_artist)
                count += 1
            except Exception as e:
                logger.warning(f"Upsert artist error: {e}")
        self.session.commit()
        return count

    def get_artist_by_id(self, artist_id: int) -> Optional[dict]:
        """根据ID获取艺术家"""
        import json

        stmt = select(YandeArtist).filter_by(id=artist_id)
        artist = self.session.execute(stmt).scalar_one_or_none()
        if artist:
            return {
                "id": artist.id,
                "name": artist.name,
                "alias_id": artist.alias_id,
                "group_id": artist.group_id,
                "urls": json.loads(artist.urls) if artist.urls else [],
            }
        return None

    def get_artist_count(self) -> int:
        """获取缓存的艺术家总数"""
        stmt = select(func.count(YandeArtist.id))
        return self.session.execute(stmt).scalar() or 0

    def search_artists(self, keyword: str, limit: int = 20) -> List[dict]:
        """搜索艺术家"""
        import json

        stmt = (
            select(YandeArtist)
            .filter(YandeArtist.name.like(f"%{keyword}%"))
            .limit(limit)
        )
        results = self.session.execute(stmt).scalars().all()
        return [
            {
                "id": t.id,
                "name": t.name,
                "alias_id": t.alias_id,
                "group_id": t.group_id,
                "urls": json.loads(t.urls) if t.urls else [],
            }
            for t in results
        ]
