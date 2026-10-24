from collections import Counter
from datetime import datetime
from typing import List, Optional, Tuple

from loguru import logger
from sqlalchemy import select, func
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from src.common import config
from src.dao.database import BaseDAO
from src.models.database.yande import YandeData, YandeTag, TagLocalStats


class TagRepository(BaseDAO):

    @staticmethod
    def _chunked(iterable, chunk_size: int):
        """将列表切分成指定大小的子列表"""
        for i in range(0, len(iterable), chunk_size):
            yield iterable[i:i + chunk_size]

    def upsert_tags(self, tags: List[dict]) -> int:
        if not tags:
            return 0

        use_mariadb = config.database.enable and config.database.host

        normalized_tags = [
            {
                "id": t["id"],
                "name": t.get("name", ""),
                "count": t.get("count", 0),
                "type": t.get("type", 0),
                "ambiguous": t.get("ambiguous", False),
                "updated_at": datetime.now(),
            }
            for t in tags
        ]

        chunk_size = 5000
        total_inserted = 0
        for chunk in self._chunked(normalized_tags, chunk_size):
            try:
                if use_mariadb:
                    stmt = mysql_insert(YandeTag).values(chunk)
                    update_cols = {
                        k: stmt.inserted[k]
                        for k in ["name", "count", "type", "ambiguous", "updated_at"]
                    }
                    stmt = stmt.on_duplicate_key_update(**update_cols)
                else:
                    stmt = sqlite_insert(YandeTag).values(chunk)
                    stmt = stmt.on_conflict_do_update(
                        index_elements=[YandeTag.id],
                        set_={
                            "name": stmt.excluded.name,
                            "count": stmt.excluded.count,
                            "type": stmt.excluded.type,
                            "ambiguous": stmt.excluded.ambiguous,
                            "updated_at": stmt.excluded.updated_at,
                        },
                    )

                self.session.execute(stmt)
                total_inserted += len(chunk)

            except Exception as e:
                logger.warning(f"Upsert tags chunk error: {e}")
                self.session.rollback()
        return total_inserted


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

    def get_local_stats_last_calculated(self) -> Optional[datetime]:
        """全量本地统计的最后计算时间。

        ``calculate_local_stats`` 会把所有行刷成同一时刻，之后
        ``adjust_local_stats`` 只会更新被触及的行，因此 MIN 仍代表「上次全量」
        时间，可用于判断是否还有必要重算。
        """
        return self.session.execute(
            select(func.min(TagLocalStats.last_calculated))
        ).scalar()

    def calculate_local_stats(self) -> int:
        """全量重算本地标签统计（只统计已下载图片，且只落库已缓存标签）。

        性能要点（2026-10-25 优化）：
        - 流式读取 tags（yield_per），避免一次性把 3 万+ 标签字符串全部读入内存；
        - 写回改为 chunked ``INSERT ... ON CONFLICT DO UPDATE``，不再构造/追踪
          上万个 ORM 对象（此前 mutate + flush 是全流程最大开销）。
        """
        tag_counter: Counter = Counter()

        with self.session.no_autoflush:
            stmt = (
                select(YandeData.tags)
                .where(YandeData.down_flag == True)  # noqa: E712
                .execution_options(yield_per=2000)
            )
            for tags_str in self.session.execute(stmt).scalars():
                if tags_str:
                    tag_counter.update(tags_str.split())

        if not tag_counter:
            return 0

        tag_names = list(tag_counter.keys())
        tags_stmt = select(YandeTag).filter(YandeTag.name.in_(tag_names))
        tag_objs = {t.name: t for t in self.session.execute(tags_stmt).scalars().all()}
        if not tag_objs:
            return 0

        now = datetime.now()
        rows = [
            {
                "tag_id": tag_objs[name].id,
                "local_count": local_count,
                "last_calculated": now,
            }
            for name, local_count in tag_counter.items()
            if name in tag_objs
        ]
        if not rows:
            return 0

        # 注意：必须把参数列表传给 execute（DBAPI executemany），不能把 rows
        # 拼进 .values() 生成超大单条 INSERT —— 后者每 1000 行要让 SQLAlchemy
        # 重新编译一次 3000 参数的语句，实测比 executemany 慢一个数量级。
        use_mariadb = config.database.enable and config.database.host
        if use_mariadb:
            insert_stmt = mysql_insert(TagLocalStats)
            stmt = insert_stmt.on_duplicate_key_update(
                local_count=insert_stmt.inserted.local_count,
                last_calculated=insert_stmt.inserted.last_calculated,
            )
        else:
            insert_stmt = sqlite_insert(TagLocalStats)
            stmt = insert_stmt.on_conflict_do_update(
                index_elements=[TagLocalStats.tag_id],
                set_={
                    "local_count": insert_stmt.excluded.local_count,
                    "last_calculated": insert_stmt.excluded.last_calculated,
                },
            )

        for chunk in self._chunked(rows, 500):
            self.session.execute(stmt, chunk)

        return len(rows)

    def adjust_local_stats(self, added: List[str], removed: List[str]) -> int:
        """按单张图片的标签增减量更新本地统计。

        只处理已存在于 ``YandeTag`` 缓存中的标签：缓存里没有的新标签无法拿到
        tag_id，等下一次标签缓存刷新 + 全量重算时再补。负值钳到 0，避免历史
        数据不一致时把计数打成负数。
        """
        deltas: Counter = Counter()
        for name in added:
            deltas[name] += 1
        for name in removed:
            deltas[name] -= 1
        deltas = {name: delta for name, delta in deltas.items() if delta}

        if not deltas:
            return 0

        tags_stmt = select(YandeTag).filter(YandeTag.name.in_(list(deltas)))
        tag_by_name = {
            tag.name: tag
            for tag in self.session.execute(tags_stmt).scalars().all()
        }
        if not tag_by_name:
            return 0

        stats_stmt = select(TagLocalStats).filter(
            TagLocalStats.tag_id.in_([tag.id for tag in tag_by_name.values()])
        )
        stats_by_id = {
            stat.tag_id: stat
            for stat in self.session.execute(stats_stmt).scalars().all()
        }

        now = datetime.now()
        updated = 0
        for name, delta in deltas.items():
            tag = tag_by_name.get(name)
            if tag is None:
                continue
            stat = stats_by_id.get(tag.id)
            if stat is not None:
                stat.local_count = max(0, (stat.local_count or 0) + delta)
                stat.last_calculated = now
                updated += 1
            elif delta > 0:
                self.session.add(
                    TagLocalStats(
                        tag_id=tag.id,
                        local_count=delta,
                        last_calculated=now,
                    )
                )
                updated += 1

        return updated

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