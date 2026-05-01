"""
YandeData DAO - 兼容层

此文件已重构，功能已拆分到独立文件：
- yande_data_dao.py: YandeDataRepository
- tag_dao.py: TagRepository
- artist_dao.py: ArtistRepository
"""

from src.dao.yande_data_dao import YandeDataRepository, yande_data_repository
from src.dao.tag_dao import TagRepository, tag_repository
from src.dao.artist_dao import ArtistRepository, artist_repository

__all__ = [
    "YandeDataRepository",
    "yande_data_repository",
    "TagRepository",
    "tag_repository",
    "ArtistRepository",
    "artist_repository",
]