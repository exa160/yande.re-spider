"""我的最爱 业务逻辑服务

提供：
- add                : 加入我的最爱 + 条件触发自动下载
- remove             : 取消我的最爱（幂等）
- list_paginated     : 分页列出我的最爱（MyFavoritesListItem）
- count              : 我的最爱总数
- get_preview        : 我的最爱预览图元数据（MyFavoritePreviewImage）

分层约束：api → services → dao；本文件仅编排 DAO / Repository / DownloadService，
不直接拼 SQL。

Session 管理：通过 YandeDataRepository 上下文管理器获取 session，再传递给
MyFavoriteDao 的 static 方法。这样：
- 在 HTTP 请求中：会复用 RequestSessionMiddleware 的 session（同一事务）
- 在后台任务 / 测试中：自己创建独立 session（with 退出时自动 commit/rollback）

DAO 调用约定：MyFavoriteDao 是纯 static 类，必须显式传入 session。
"""
from typing import List, Tuple

from loguru import logger

from src.common.settings import config
from src.dao.my_favorite_dao import MyFavoriteDao
from src.dao.yande_data_dao import YandeDataRepository
from src.models.response.my_favorites import (
    MyFavoritePreviewImage,
    MyFavoritesListItem,
)
from src.services.download import DownloadService


class MyFavoritesService:
    """我的最爱业务编排。"""

    @staticmethod
    async def add(image_id: int) -> None:
        """加入我的最爱；满足条件时异步触发下载。

        业务规则：
        1. 图片必须在 yande_data 中存在（否则 raise ValueError）
        2. 写入 my_favorite（UNIQUE 约束保证幂等）
        3. 仅当 ``not yande_data.down_flag AND config.favorites.enable_favorite_autodownload``
           时才触发下载；下载失败不回滚收藏（已 commit），仅记录 warning

        Raises:
            ValueError: image_id 不存在于 yande_data
        """
        with YandeDataRepository() as repo:
            yande_data = repo.get_by_id(image_id)
            if not yande_data:
                raise ValueError(f"Image {image_id} not found in database")
            MyFavoriteDao.add(repo.session, image_id=image_id)
            # 退出 with 块时 YandeDataRepository.__exit__ 会 commit，收藏已落库
            # 此处保存 down_flag 用于上下文退出后再决策是否触发下载
            should_download = (
                not yande_data.down_flag
                and config.favorites.enable_favorite_autodownload
            )

        if should_download:
            try:
                await DownloadService.create_task(image_id)
                logger.info(f"My favorite auto-download triggered for {image_id}")
            except Exception as e:
                # 收藏已提交，下载失败不影响数据一致性
                logger.warning(f"Auto-download failed for {image_id}: {e}")

    @staticmethod
    def remove(image_id: int) -> None:
        """取消我的最爱（幂等）。不存在不报错。"""
        with YandeDataRepository() as repo:
            MyFavoriteDao.remove(repo.session, image_id=image_id)

    @staticmethod
    def list_paginated(
        page: int = 1, page_size: int = 20
    ) -> Tuple[List[MyFavoritesListItem], int]:
        """分页列出我的最爱（含元数据），按收藏时间倒序。

        Returns:
            (items, total) — items 已 ORM→Pydantic 转换，total 为全表总数
        """
        with YandeDataRepository() as repo:
            records = MyFavoriteDao.list_paginated(
                repo.session, page=page, page_size=page_size
            )
            total = MyFavoriteDao.count(repo.session)
        # ORM DateTime 必须显式 isoformat()，Pydantic 不会自动转 str
        items = [
            MyFavoritesListItem(
                id=mf.id,
                image_id=mf.image_id,
                created_at=mf.created_at.isoformat(),
            )
            for mf in records
        ]
        return items, total

    @staticmethod
    def count() -> int:
        """我的最爱总数。"""
        with YandeDataRepository() as repo:
            return MyFavoriteDao.count(repo.session)

    @staticmethod
    def get_preview(limit: int = 20) -> List[MyFavoritePreviewImage]:
        """我的最爱预览图元数据，按收藏时间倒序。

        DAO 已 JOIN yande_data；此处需把 Rating enum 规范化为 str（Pydantic 不会
        自动把 ORM 返回的 Enum 列转为 str，否则 ValidationError）。
        """
        with YandeDataRepository() as repo:
            rows = MyFavoriteDao.get_preview(repo.session, limit=limit)
        return [
            MyFavoritePreviewImage(
                id=row["id"],
                preview_url=row.get("preview_url"),
                tags=row.get("tags", ""),
                rating=str(row["rating"]) if row.get("rating") is not None else "",
            )
            for row in rows
        ]