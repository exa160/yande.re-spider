from sqlalchemy import select, func, or_
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from typing import List, Optional, Tuple

from src.common.utils import check_local_file
from src.common import config
from src.dao.database import BaseDAO
from src.models.database.yande import YandeData
from loguru import logger


class YandeDataRepository(BaseDAO):
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
        query_stmt = select(YandeData)
        count_stmt = select(func.count()).select_from(YandeData)

        if tags:
            tags_normalized = tags.upper().replace(" OR ", " AND ")
            tags_filter = [t for t in tags_normalized.split(" AND ") if t.strip()]
            for tag in tags_filter:
                tag = tag.strip()
                if tag.startswith("-"):
                    query_stmt = query_stmt.filter(~YandeData.tags.contains(tag[1:]))
                    count_stmt = count_stmt.filter(~YandeData.tags.contains(tag[1:]))
                else:
                    query_stmt = query_stmt.filter(YandeData.tags.contains(tag))
                    count_stmt = count_stmt.filter(YandeData.tags.contains(tag))

        if author:
            query_stmt = query_stmt.filter(YandeData.author == author)
            count_stmt = count_stmt.filter(YandeData.author == author)

        if rating and rating != "All":
            rating_map = {
                "Safe": "s", "Questionable": "q", "Explicit": "e",
                "s": "s", "q": "q", "e": "e",
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
                    query_stmt = query_stmt.filter(YandeData.rating == rating_values[0])
                    count_stmt = count_stmt.filter(YandeData.rating == rating_values[0])
                else:
                    rating_filters = [YandeData.rating == rv for rv in rating_values]
                    query_stmt = query_stmt.filter(or_(*rating_filters))
                    count_stmt = count_stmt.filter(or_(*rating_filters))

        if min_width:
            query_stmt = query_stmt.filter(YandeData.width >= min_width)
            count_stmt = count_stmt.filter(YandeData.width >= min_width)
        if max_width:
            query_stmt = query_stmt.filter(YandeData.width <= max_width)
            count_stmt = count_stmt.filter(YandeData.width <= max_width)
        if min_height:
            query_stmt = query_stmt.filter(YandeData.height >= min_height)
            count_stmt = count_stmt.filter(YandeData.height >= min_height)
        if max_height:
            query_stmt = query_stmt.filter(YandeData.height <= max_height)
            count_stmt = count_stmt.filter(YandeData.height <= max_height)

        if min_file_size:
            query_stmt = query_stmt.filter(YandeData.file_size >= min_file_size * 1024)
            count_stmt = count_stmt.filter(YandeData.file_size >= min_file_size * 1024)
        if max_file_size:
            query_stmt = query_stmt.filter(YandeData.file_size <= max_file_size * 1024)
            count_stmt = count_stmt.filter(YandeData.file_size <= max_file_size * 1024)

        if file_type:
            ext_values = [ext.strip().lower() for ext in file_type.split(",") if ext.strip()]
            if len(ext_values) == 1:
                query_stmt = query_stmt.filter(YandeData.file_ext == ext_values[0])
                count_stmt = count_stmt.filter(YandeData.file_ext == ext_values[0])
            elif len(ext_values) > 1:
                ext_filters = [YandeData.file_ext == ext for ext in ext_values]
                query_stmt = query_stmt.filter(or_(*ext_filters))
                count_stmt = count_stmt.filter(or_(*ext_filters))

        if downloaded_only:
            query_stmt = query_stmt.filter(YandeData.down_flag == True)
            count_stmt = count_stmt.filter(YandeData.down_flag == True)

        sort_column = getattr(YandeData, sort_by, YandeData.id)
        if sort_order.lower() == "desc":
            query_stmt = query_stmt.order_by(sort_column.desc())
        else:
            query_stmt = query_stmt.order_by(sort_column.asc())

        offset = (page - 1) * page_size
        query_stmt = query_stmt.offset(offset).limit(page_size)

        results = self.session.execute(query_stmt).scalars().all()
        total = self.session.execute(count_stmt).scalar() or 0

        # rating_display_map = {"s": "Safe", "q": "Questionable", "e": "Explicit"}
        # images = []
        # for row in results:
        #     tags_list = row.tags.split() if row.tags else []
        #     rating_val = row.rating.value if hasattr(row.rating, "value") else row.rating
        #     rating_display = rating_display_map.get(rating_val, rating_val) if rating_val else "Safe"
        #     file_ext = row.file_ext or "jpg"

        #     local_preview = check_local_file(row.id, file_ext, "preview")
        #     local_original = check_local_file(row.id, file_ext, "original")
        #     is_downloaded = row.down_flag if hasattr(row, "down_flag") else True

        #     images.append({
        #         "id": row.id,
        #         "tags": tags_list,
        #         "width": row.width or 0,
        #         "height": row.height or 0,
        #         "rating": rating_display,
        #         "file_url": row.file_url or "",
        #         "preview_url": row.preview_url or "",
        #         "sample_url": None,
        #         "file_size": row.file_size or 0,
        #         "file_ext": file_ext,
        #         "author": row.author or "",
        #         "created_at": str(row.created_at) if row.created_at else "",
        #         "md5": row.md5 or "",
        #         "score": row.score,
        #         "is_downloaded": is_downloaded,
        #         "local_preview_path": local_preview,
        #         "local_file_path": local_original,
        #     })

        return results, total

    def get_by_id(self, image_id: int) -> Optional[dict]:
        stmt = select(YandeData).filter_by(id=image_id)
        row = self.session.execute(stmt).scalar_one_or_none()
        if not row:
            return None

        rating_display_map = {"s": "Safe", "q": "Questionable", "e": "Explicit"}
        tags_list = row.tags.split() if row.tags else []
        rating_display = rating_display_map.get(row.rating, row.rating) if row.rating else "Safe"
        file_ext = row.file_ext or "jpg"

        local_preview = check_local_file(row.id, file_ext, "preview")
        local_original = check_local_file(row.id, file_ext, "original")

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
        try:
            record = YandeData(**data)
            self.session.add(record)
            return True
        except Exception:
            return False

    def check_exists(self, image_id: int) -> bool:
        stmt = select(YandeData.id).filter_by(id=image_id)
        return self.session.execute(stmt).scalar_one_or_none() is not None

    def check_downloaded(self, image_id: int) -> bool:
        stmt = select(YandeData.id).filter_by(id=image_id, down_flag=True)
        return self.session.execute(stmt).scalar_one_or_none() is not None

    def update_down_flag(self, image_id: int, down_flag: bool = True) -> bool:
        try:
            stmt = select(YandeData).filter_by(id=image_id)
            record = self.session.execute(stmt).scalar_one_or_none()

            if record:
                record.down_flag = down_flag
                return True
            return False
        except Exception as e:
            logger.warning(f"Update down_flag error: {e}")
            return False

    def _build_upsert_stmt(self, yande_items: list, returning: bool = False):
        use_mariadb = config.database.enable and config.database.host

        if use_mariadb:
            stmt = mysql_insert(YandeData).values(yande_items)
            update_cols = {
                k: stmt.excluded[k]
                for k in yande_items[0].keys()
                if k not in ("id", "down_flag")
            }
            update_cols["down_flag"] = YandeData.down_flag
            stmt = stmt.on_duplicate_key_update(**update_cols)
        else:
            stmt = sqlite_insert(YandeData).values(yande_items)
            stmt = stmt.on_conflict_do_update(
                index_elements=[YandeData.id],
                set_={
                    k: stmt.excluded[k]
                    for k in yande_items[0].keys()
                    if k != "id"
                },
            )

        if returning:
            stmt = stmt.returning(YandeData)

        return stmt

    def upsert_batch(self, yande_items: list) -> int:
        if not yande_items:
            return 0

        try:
            stmt = self._build_upsert_stmt(yande_items)
            self.session.execute(stmt)
            return len(yande_items)
        except Exception as e:
            logger.warning(f"Upsert batch error: {e}")
            self.session.rollback()
            return 0

    def upsert_batch_with_down_flags(self, yande_items: list) -> dict:
        if not yande_items:
            return {}

        try:
            stmt = self._build_upsert_stmt(yande_items, returning=True)
            result = self.session.execute(stmt)
            rows = result.scalars().all()
            return rows
        except Exception as e:
            logger.warning(f"Upsert batch with returning failed: {e}")
            self.session.rollback()

        try:
            stmt = self._build_upsert_stmt(yande_items)
            self.session.execute(stmt)
            existing_ids = [r["id"] for r in yande_items]
            existing_stmt = select(YandeData).where(
                YandeData.id.in_(existing_ids)
            )
            rows = self.session.execute(existing_stmt).scalars().all()
            return rows
        except Exception as e:
            logger.warning(f"Fallback down_flag query failed: {e}")
            self.session.rollback()
            return {}

    def upsert(self, yande_item) -> bool:
        result = self.upsert_batch([yande_item])
        return result > 0


yande_data_repository = YandeDataRepository()