import json
from datetime import datetime
from sqlalchemy import select, func
from typing import List, Optional

from src.dao.database import BaseDAO
from src.models.database.yande import YandeArtist
from loguru import logger


class ArtistRepository(BaseDAO):

    def upsert_artists(self, artists: List[dict]) -> int:
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
        return count

    def get_artist_by_id(self, artist_id: int) -> Optional[dict]:
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
        stmt = select(func.count(YandeArtist.id))
        return self.session.execute(stmt).scalar() or 0

    def search_artists(self, keyword: str, limit: int = 20) -> List[dict]:
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


artist_repository = ArtistRepository()