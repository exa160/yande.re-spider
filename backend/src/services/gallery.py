"""
图库业务逻辑层
"""

import time
from typing import List, Optional

import requests
from loguru import logger
from PIL import Image
from sqlalchemy import func, select


from src.common.constant import CleanupMode
from src.common.constant import ErrMsg
from src.common.constant import Rating
from src.common.constant import TaskStatus
from src.common.constant import path_constant
from src.common.settings import config
from src.common.utils import get_error_type_from_exception
from src.dao.yande_data_dao import SortBy, YandeDataRepository
from src.infrastructure.image_cache import ImageCache
from src.infrastructure.yande_api import YandeApi
from src.middleware.errors import APIException
from src.middleware.session import RequestSessionMiddleware
from src.models.database.my_favorite import MyFavorite
from src.models.database.yande import DownloadTask, YandeData
from src.models.request.gallery import GalleryLoadRequest
from src.models.request.yande import YandeSearchTags
from src.models.response.gallery import ImageDetail


class GalleryService:
    """图库服务类"""

    @staticmethod
    def _favorite_status_enabled(include_flag: Optional[bool]) -> bool:
        """我的最爱总开关双判断（binding constraint）。

        effective_include_favorite = include_favorite_status
                                      AND config.favorites.enable_my_favorites

        前端只在 enableMyFavorites=true 时才发该参数；后端再独立判一次总开关，
        保证总开关关闭时任何路径都不会查 my_favorite（零 DB 开销）。
        本地（LEFT JOIN）与在线（IN 批量查询）两条路径共用此判定，避免出现第三份副本。
        """
        return bool(
            include_flag and getattr(config.favorites, "enable_my_favorites", False)
        )

    @staticmethod
    def _attach_favorite_status(session, images: list) -> None:
        """一次 IN 批量查询给图片挂 is_favorited 运行时属性（True/False）。

        用于在线浏览与 include_online 合并路径：这些图片来自 upsert，不带
        LEFT JOIN 结果，只能按 id 批量查一次 my_favorite。走 image_id UNIQUE
        索引，比本地那条 LEFT JOIN 更轻。

        依赖 expire_on_commit=False（dao/database.py）：调用点在 with 块内，
        属性为 transient，不会被 SQLAlchemy 当作脏字段写回。
        """
        ids = [img.id for img in images]
        if not ids:
            return
        favorited = set(
            session.execute(
                select(MyFavorite.image_id).where(MyFavorite.image_id.in_(ids))
            )
            .scalars()
            .all()
        )
        for img in images:
            img.is_favorited = img.id in favorited  # type: ignore[attr-defined]

    @staticmethod
    def query_local_database(
        params: GalleryLoadRequest,
        include_favorite_status: Optional[bool] = None,
        random: Optional[bool] = None,
    ) -> tuple[List[YandeData], int]:
        """
        查询本地数据库。

        双判断 (binding constraint)：
            effective_include_favorite = (req.include_favorite_status
                                          AND config.favorites.enable_my_favorites)
            只有两者都为 True 才会 LEFT JOIN my_favorite；其它情况保持原行为。

        第三条分流：``sort_by == SortBy.DOWNLOADED_AT``（最近下载）也必须走
        ``_query_local_with_options``，因为该排序依赖 download_task 子查询 + JOIN，
        ``YandeDataRepository.query()`` 里的 ``getattr(YandeData, sort_by)`` 拿不到该列
        （yande_data 没有 downloaded_at 列），会静默退化成按 id 排序。

        Args:
            params: GalleryLoadRequest（含 include_favorite_status / random 字段）
            include_favorite_status: 覆盖 request.include_favorite_status（None=沿用 request）
            random: 覆盖 request.random（None=沿用 request）

        Returns:
            (图片列表, 总数)；effective_include_favorite=True 时每个
            YandeData 实例会附加运行时属性 is_favorited (True/False)
        """
        req_include = (
            include_favorite_status
            if include_favorite_status is not None
            else params.include_favorite_status
        )
        req_random = random if random is not None else params.random
        effective_include_favorite = bool(
            req_include and getattr(config.favorites, "enable_my_favorites", False)
        )
        sort_by_downloaded_at = params.sort_by == SortBy.DOWNLOADED_AT

        if not effective_include_favorite and not req_random and not sort_by_downloaded_at:
            with YandeDataRepository() as repo:
                repo.YandeDataQueryParams.model_validate(params)
                images, total = repo.query(
                    query_params=params,
                    downloaded_only=True,
                )
            return images, total

        with YandeDataRepository() as repo:
            repo.YandeDataQueryParams.model_validate(params)
            images, total = GalleryService._query_local_with_options(
                repo=repo,
                params=params,
                effective_include_favorite=effective_include_favorite,
                random=req_random,
            )
        return images, total

    @staticmethod
    def _build_latest_download_subquery():
        """「最近下载」子查询：每张图最近一次**完成**下载的时间。

        ``SELECT image_id, MAX(completed_at) AS latest_at FROM download_tasks
          WHERE status='completed' AND completed_at IS NOT NULL
          GROUP BY image_id``

        两个 WHERE 条件缺一不可（与 download_task_dao 的 4 个「最近下载」方法同口径）：
        - ``status='completed'`` 排除 pending/downloading/paused/failed/cancelled
        - ``completed_at IS NOT NULL`` 排除「文件已存在、跳过下载」分支产生的 NULL
          （否则 MAX() 会把 NULL 组的时间整体拖成 NULL，排序失去意义）

        GROUP BY image_id 顺带完成「同一张图重复下载只出现一次」的去重。
        """
        return (
            select(
                DownloadTask.image_id.label("image_id"),
                func.max(DownloadTask.completed_at).label("latest_at"),
            )
            .where(
                DownloadTask.status == TaskStatus.COMPLETED,
                DownloadTask.completed_at.isnot(None),
            )
            .group_by(DownloadTask.image_id)
            .subquery()
        )

    @staticmethod
    def _query_local_with_options(
        repo: YandeDataRepository,
        params: GalleryLoadRequest,
        effective_include_favorite: bool,
        random: bool,
    ) -> tuple[List[YandeData], int]:
        """自构 SQL：LEFT JOIN my_favorite + 可选 ORDER BY RANDOM() + DISTINCT。

        与 YandeDataRepository.query() 共用同一套 filter_funcs，保证 tags / rating /
        file_types / size / author 等过滤条件一致。

        三条分支互不干扰、可自由组合：
        1. ``effective_include_favorite`` → LEFT JOIN my_favorite 带出 is_favorited
        2. ``random`` → ORDER BY RANDOM() + DISTINCT（优先级高于排序键）
        3. ``sort_by == SortBy.DOWNLOADED_AT`` → INNER JOIN download_task 子查询，
           按 MAX(completed_at) 排序（yande_data 无该列，只能走 JOIN，见 §3.4）
        """
        session = repo.session
        qp = repo.YandeDataQueryParams.model_validate(params)

        filter_funcs = []
        if qp.rating and len(qp.rating) != len(Rating):
            filter_funcs.append(YandeData.rating.in_(qp.rating))
        filter_funcs.append(YandeData.down_flag.is_(True))
        for param_name in (
            "tags",
            "file_types",
            "min_width",
            "max_width",
            "min_height",
            "max_height",
            "min_file_size",
            "max_file_size",
            "author",
        ):
            v = getattr(qp, param_name, None)
            if v is None:
                continue
            if param_name == "tags":
                cond = repo._tag_filter(v)
                if cond is not None:
                    filter_funcs.append(cond)
            elif param_name == "file_types":
                filter_funcs.append(YandeData.file_ext.in_(v))
            elif param_name == "min_width":
                filter_funcs.append(YandeData.width >= v)
            elif param_name == "max_width":
                filter_funcs.append(YandeData.width <= v)
            elif param_name == "min_height":
                filter_funcs.append(YandeData.height >= v)
            elif param_name == "max_height":
                filter_funcs.append(YandeData.height <= v)
            elif param_name == "min_file_size":
                filter_funcs.append(YandeData.file_size >= v * 1024)
            elif param_name == "max_file_size":
                filter_funcs.append(YandeData.file_size <= v * 1024)
            elif param_name == "author":
                filter_funcs.append(YandeData.author.contains(v))

        offset = (qp.page - 1) * qp.page_size

        # 「最近下载」排序：必须 JOIN 子查询取 MAX(completed_at)，
        # 不可用 getattr(YandeData, "downloaded_at")（该列不存在）
        sort_by_downloaded_at = qp.sort_by == SortBy.DOWNLOADED_AT
        latest_subq = (
            GalleryService._build_latest_download_subquery()
            if sort_by_downloaded_at
            else None
        )

        if effective_include_favorite:
            stmt = (
                select(YandeData, MyFavorite.id)
                .outerjoin(MyFavorite, MyFavorite.image_id == YandeData.id)
            )
        else:
            stmt = select(YandeData)

        if latest_subq is not None:
            # join_from 显式指定左表，避免与上面的 outerjoin 抢隐式左连接对象
            stmt = stmt.join_from(
                YandeData, latest_subq, latest_subq.c.image_id == YandeData.id
            )

        stmt = stmt.filter(*filter_funcs)

        if random:
            # 用 .distinct() 而非 .distinct(YandeData.id)：后者编译为 PostgreSQL 专属
            # DISTINCT ON (col)，在 SQLite/MariaDB 上会被静默忽略。
            stmt = stmt.order_by(func.random()).distinct()
        elif latest_subq is not None:
            sort_column = latest_subq.c.latest_at
            # 第二排序键 YandeData.id：同秒完成时给出确定性顺序，避免翻页抖动
            if qp.sort_order == "asc":
                stmt = stmt.order_by(sort_column.asc(), YandeData.id.asc())
            else:
                stmt = stmt.order_by(sort_column.desc(), YandeData.id.desc())
        else:
            sort_column = getattr(YandeData, qp.sort_by, YandeData.id)
            if qp.sort_order == "desc":
                stmt = stmt.order_by(sort_column.desc())
            elif qp.sort_order == "asc":
                stmt = stmt.order_by(sort_column.asc())
            else:
                stmt = stmt.order_by(sort_column.desc())

        stmt = stmt.offset(offset).limit(qp.page_size)

        rows = session.execute(stmt).all()

        if effective_include_favorite:
            images: List[YandeData] = []
            for yande, fav_id in rows:
                yande.is_favorited = fav_id is not None  # type: ignore[attr-defined]
                images.append(yande)
        else:
            images = [row[0] for row in rows]

        count_stmt = select(func.count()).select_from(YandeData).filter(*filter_funcs)
        if latest_subq is not None:
            # count 必须走同一条 JOIN，否则 total 会把「无 completed 任务的图片」也算进去
            count_stmt = count_stmt.join_from(
                YandeData, latest_subq, latest_subq.c.image_id == YandeData.id
            )
        total = session.execute(count_stmt).scalar() or 0
        return images, total

    @staticmethod
    def query_yande_api(params: GalleryLoadRequest) -> tuple[List[dict], int]:
        """
        查询 yande.re API 并同步到本地数据库

        Args:
            params: 查询参数字典

        Returns:
            (图片列表, 总数)
        """
        yande_api = YandeApi()
        search_tags = YandeSearchTags.model_validate(params)

        try:
            yande_data = yande_api.get_ranking(
                query_params=YandeApi.PostRankQueryParams(
                    page=params.page,
                    limit=params.page_size,
                    tags=params.tags,
                    search_tags=search_tags
                )
            )
        except requests.RequestException as e:
            err_msg, detail = get_error_type_from_exception(e)
            raise APIException(err_msg=err_msg, data={"detail": detail})

        yande_items = list(yande_data.root)
        if not yande_items:
            return [], 0

        with YandeDataRepository() as repo:
            # 批量 upsert（一次数据库操作），并返回当前记录
            images = repo.upsert_batch_with_down_flags(yande_data.model_dump())
            # 在线浏览同样需要收藏状态：upsert 走的是 on_conflict_do_update，
            # 不会带出 my_favorite 信息，必须按 id 补查一次
            if GalleryService._favorite_status_enabled(params.include_favorite_status):
                GalleryService._attach_favorite_status(repo.session, images)
        return images, len(images)

    @staticmethod
    def get_image_by_id(image_id: int, source: str = "local") -> Optional[dict]:
        """
        根据 ID 获取图片详情

        Args:
            image_id: 图片 ID
            source: 数据源 (local/yande)

        Returns:
            图片信息字典，不存在返回 None
        """
        if source == "local":
            images, _ = GalleryService.query_local_database({"page": 1, "page_size": 1})
        else:
            images, _ = GalleryService.query_yande_api({"page": 1, "page_size": 100})

        for img in images:
            if img["id"] == image_id:
                return img
        return None

    @staticmethod
    def get_image_detail(
        image_id: int, include_favorite_status: bool = False
    ) -> Optional[ImageDetail]:
        """
        根据 ID 获取单张图片详情（双判断 include_favorite_status）。

        双判断 (binding constraint)：
            effective_include_favorite = (include_favorite_status
                                          AND config.favorites.enable_my_favorites)
            只有两者都为 True 时才会查 my_favorite 表；其它情况
            is_favorited 保持 None。

        与 /gallery/load 的 query_local_database 行为一致：本接口
        也强制双重判断，保证总开关关闭时不查表。

        Args:
            image_id: 图片 ID
            include_favorite_status: 是否附带收藏状态（仍受总开关约束）

        Returns:
            ImageDetail 实例（包含 is_favorited），不存在返回 None
        """
        session = RequestSessionMiddleware.get_session()
        yande = session.query(YandeData).filter(YandeData.id == image_id).first()
        if not yande:
            return None

        is_favorited: Optional[bool] = None
        effective = bool(
            include_favorite_status
            and getattr(config.favorites, "enable_my_favorites", False)
        )
        if effective:
            is_favorited = (
                session.query(MyFavorite)
                .filter(MyFavorite.image_id == image_id)
                .first()
                is not None
            )

        return ImageDetail.model_validate(yande).model_copy(
            update={"is_favorited": is_favorited}
        )

    @staticmethod
    def get_statistics(source: str = "local") -> dict:
        """
        获取图库统计信息

        Args:
            source: 数据源 (local/yande)

        Returns:
            统计信息字典
        """
        if source == "local":
            images, total = GalleryService.query_local_database(
                {"page": 1, "page_size": 10000}
            )
            downloaded = total
        else:
            images = []
            total = 0
            downloaded = 0

        rating_distribution = {"Safe": 0, "Questionable": 0, "Explicit": 0}
        for img in images:
            rating = img.get("rating", "Safe")
            if rating in rating_distribution:
                rating_distribution[rating] += 1

        return {
            "total_images": total,
            "downloaded_images": downloaded,
            "rating_distribution": rating_distribution,
            "file_type_distribution": {},
        }

    @staticmethod
    def get_preview_path(filename: str):
        """获取预览图路径"""
        return path_constant.previews_dir / filename

    @staticmethod
    def get_original_path(filename: str):
        """获取原图路径"""
        return path_constant.originals_dir / filename

    @staticmethod
    def generate_preview(image_id: int, file_ext: str = "jpg"):
        cache = ImageCache()
        preview_path = cache.get_preview_path(image_id, "jpg")

        if preview_path.exists():
            return preview_path

        original_path = cache.get_original_path(image_id, file_ext)
        if not original_path.exists():
            logger.warning(f"Original image {image_id} not found for preview generation")
            return None

        try:
            img = Image.open(str(original_path))
            img.thumbnail(
                (600, 600), Image.Resampling.LANCZOS
            )
            if img.mode == "RGBA":
                img = img.convert("RGB")
            img.save(str(preview_path), "JPEG", quality=85)
            return preview_path if preview_path.exists() else None
        except Exception:
            logger.error(f"Failed to generate preview for image {image_id}", exc_info=True)
            return None

    @staticmethod
    def fetch_and_cache_preview(image_id: int):
        """
        从远程获取并缓存预览图,如果本地已存在则直接返回(默认jpg格式，有修改需适配preview_url)

        Args:
            image_id: 图片 ID

        Returns:
            预览图路径，失败抛出 APIException

        Raises:
            APIException: 获取或缓存失败时抛出
        """

        cache = ImageCache()
        preview_path = cache.get_preview_path(image_id, "jpg")

        if preview_path.exists():
            return preview_path

        with YandeDataRepository() as repo:
            image_data = repo.get_by_id(image_id)

        if not image_data:
            logger.warning(f"Image {image_id} not found in database")
            raise APIException(ErrMsg.NOT_FOUND, data={"image_id": image_id})

        preview_url = image_data.preview_url
        if not preview_url:
            logger.warning(f"Image {image_id} has no preview_url")
            raise APIException(ErrMsg.LOAD_PREVIEW_DATA_ERROR, e=Exception(f"ID: {image_id} has no preview URL available"))

        try:
            return cache.download_preview(preview_url, image_id, "jpg")
        except requests.RequestException as e:
            logger.error(f"Request error for image {image_id}: {e}")
            raise APIException(ErrMsg.LOAD_PREVIEW_DATA_ERROR, e=e)
        except IOError as e:
            logger.error(f"IO error saving preview {image_id}: {e}")
            raise APIException(ErrMsg.SAVE_PREVIEW_DATA_ERROR, e=e)
        except Exception as e:
            logger.error(f"Unexpected error fetching preview {image_id}: {e}")
            raise APIException(ErrMsg.LOAD_PREVIEW_DATA_ERROR, e=e)

    @staticmethod
    def get_preview_for_local(image_id: int):
        cache = ImageCache()
        preview_path = cache.get_preview_path(image_id, "jpg")

        if preview_path.exists():
            return preview_path

        with YandeDataRepository() as repo:
            actual_file_ext = repo.get_file_ext(image_id)

        original_path = cache.get_original_path(image_id, actual_file_ext)
        if original_path.exists():
            return GalleryService.generate_preview(image_id, actual_file_ext)

        return None

    @staticmethod
    def cleanup_previews(mode: CleanupMode, dry_run: bool) -> dict:
        """清理 preview 缩略图

        Args:
            mode: 清理模式（CLEAN_LOCAL_PREVIEWS 仅删 down_flag=True 的；
                  CLEAN_ALL_PREVIEWS 清空整个 previews/ 目录）
            dry_run: True 仅评估不删除，False 实际删除

        Returns:
            dict: 包含 mode / dry_run / matched / deleted / failed /
                  total_bytes / duration_ms 的结果

        Raises:
            APIException: 数据库查询失败时（仅 CLEAN_LOCAL_PREVIEWS 模式）
        """
        cache = ImageCache()
        previews_dir = path_constant.previews_dir
        start = time.monotonic()

        if not previews_dir.exists():
            return _empty_cleanup_result(mode, dry_run)

        all_previews = cache.list_preview_files()

        if mode == CleanupMode.CLEAN_LOCAL_PREVIEWS:
            try:
                with YandeDataRepository() as repo:
                    downloaded_ids = repo.get_downloaded_ids()
            except Exception as e:
                raise APIException(ErrMsg.QUERY_ERROR, e=e)

            targets = []
            for p in all_previews:
                image_id = GalleryService._parse_image_id(p.name)
                if image_id is not None and image_id in downloaded_ids:
                    targets.append(p)
        else:
            targets = all_previews

        matched = len(targets)
        total_bytes = 0
        for p in targets:
            try:
                total_bytes += p.stat().st_size
            except OSError:
                continue

        deleted, failed = 0, 0
        if not dry_run:
            for p in targets:
                if cache.safe_unlink(p):
                    deleted += 1
                else:
                    failed += 1

        duration_ms = int((time.monotonic() - start) * 1000)
        return {
            "mode": mode.value,
            "dry_run": dry_run,
            "matched": matched,
            "deleted": deleted,
            "failed": failed,
            "total_bytes": total_bytes,
            "duration_ms": duration_ms,
        }

    @staticmethod
    def _parse_image_id(filename: str) -> Optional[int]:
        """从 preview 文件名解析 image_id。约定：{id}.{ext}"""
        if filename.startswith("."):
            return None
        stem = filename.rsplit(".", 1)[0] if "." in filename else filename
        try:
            return int(stem)
        except ValueError:
            return None


def _empty_cleanup_result(mode: CleanupMode, dry_run: bool) -> dict:
    """previews 目录不存在时的零结果"""
    return {
        "mode": mode.value,
        "dry_run": dry_run,
        "matched": 0,
        "deleted": 0,
        "failed": 0,
        "total_bytes": 0,
        "duration_ms": 0,
    }
