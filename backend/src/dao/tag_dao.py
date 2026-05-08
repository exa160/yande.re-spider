from collections import Counter
from datetime import datetime
from typing import List, Optional, Tuple

from loguru import logger
from sqlalchemy import select, func

from src.dao.database import BaseDAO
from src.models.database.yande import YandeData, YandeTag, TagLocalStats


class TagRepository(BaseDAO):

    def upsert_tags(self, tags: List[dict]) -> int:
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
        return count

    def get_tag_by_id(self, tag_id: int) -> Optional[dict]:
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
        stmt = select(func.count(YandeTag.id))
        return self.session.execute(stmt).scalar() or 0

    def get_max_id(self) -> int:
        stmt = select(func.max(YandeTag.id))
        result = self.session.execute(stmt).scalar()
        return result or 0

    def clear_all_tags(self):
        self.session.query(YandeTag).delete()

    def search_tags(self, keyword: str, limit: int = 20) -> List[dict]:
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

    def calculate_local_stats(self) -> int:
        tag_counter: Counter = Counter()

        with self.session.no_autoflush:
            stmt = select(YandeData.tags).where(YandeData.down_flag == True)
            results = self.session.execute(stmt).scalars().all()

            for tags_str in results:
                if tags_str:
                    tag_counter.update(tags_str.split())

        if not tag_counter:
            return 0

        now = datetime.now()

        tag_names = list(tag_counter.keys())
        tags_stmt = select(YandeTag).filter(YandeTag.name.in_(tag_names))
        tag_objs = {t.name: t for t in self.session.execute(tags_stmt).scalars().all()}

        tag_ids = [t.id for t in tag_objs.values()]
        if not tag_ids:
            return 0

        stats_stmt = select(TagLocalStats).filter(TagLocalStats.tag_id.in_(tag_ids))
        existing_stats = {s.tag_id: s for s in self.session.execute(stats_stmt).scalars().all()}

        to_update = []
        to_insert = []

        for tag_name, local_count in tag_counter.items():
            tag_obj = tag_objs.get(tag_name)
            if not tag_obj:
                continue

            if tag_obj.id in existing_stats:
                to_update.append((existing_stats[tag_obj.id], local_count))
            else:
                to_insert.append({
                    'tag_id': tag_obj.id,
                    'local_count': local_count,
                    'last_calculated': now,
                })

        for stats_obj, local_count in to_update:
            stats_obj.local_count = local_count
            stats_obj.last_calculated = now

        if to_insert:
            for data in to_insert:
                self.session.add(TagLocalStats(**data))

        return len(tag_counter)

    def get_tags_with_stats(
        self,
        tag_type: Optional[int] = None,
        search_keyword: Optional[str] = None,
        limit: int = 100,
        has_local_only: bool = False,
    ) -> Tuple[List[dict], int]:
        stmt = select(YandeTag)
        count_stmt = select(func.count(YandeTag.id))

        if tag_type is not None:
            stmt = stmt.filter(YandeTag.type == tag_type)
            count_stmt = count_stmt.filter(YandeTag.type == tag_type)

        if search_keyword:
            stmt = stmt.filter(YandeTag.name.like(f"%{search_keyword}%"))
            count_stmt = count_stmt.filter(YandeTag.name.like(f"%{search_keyword}%"))

        if has_local_only:
            stmt = stmt.join(TagLocalStats, YandeTag.id == TagLocalStats.tag_id)
            count_stmt = count_stmt.join(TagLocalStats, YandeTag.id == TagLocalStats.tag_id)

        stmt = stmt.order_by(YandeTag.count.desc()).limit(limit)
        results = self.session.execute(stmt).scalars().all()
        total = self.session.execute(count_stmt).scalar() or 0

        tag_ids = [t.id for t in results]
        local_stats_map = {}
        if tag_ids:
            stats_stmt = select(TagLocalStats).filter(TagLocalStats.tag_id.in_(tag_ids))
            local_stats = self.session.execute(stats_stmt).scalars().all()
            local_stats_map = {s.tag_id: s.local_count for s in local_stats}

        tags = []
        for t in results:
            tags.append({
                "id": t.id,
                "name": t.name,
                "count": t.count,
                "type": t.type,
                "ambiguous": t.ambiguous,
                "local_count": local_stats_map.get(t.id, 0),
            })

        return tags, total

    def get_tags_by_names(self, names: List[str]) -> dict:
        stmt = select(YandeTag).filter(YandeTag.name.in_(names))
        results = self.session.execute(stmt).scalars().all()
        return {t.name: t.type for t in results}


tag_repository = TagRepository()