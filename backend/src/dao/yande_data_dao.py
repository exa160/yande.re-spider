from enum import Enum
from typing import List, Optional, Tuple

from loguru import logger
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, select, func, or_
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from src.common import config
from src.common.constant import Rating
from src.common.utils import check_local_file
from src.dao.database import BaseDAO
from src.models.database.yande import YandeData


_LIKE_ESCAPE = "\\"


def _to_like_pattern(token: str) -> str:
    """把 yande DSL 的通配形式翻译为 SQL LIKE 模式：
    - `*` 替换为 `%`
    - 字面 `%`、`_`、`\\` 加转义符，避免被解释为通配/转义
    """
    out = []
    for ch in token.replace("*", "%"):
        if ch in ("%", "_", _LIKE_ESCAPE):
            out.append(_LIKE_ESCAPE)
        out.append(ch)
    return "".join(out)


class SortBy(str, Enum):
    """排序字段枚举"""
    ID = "id"
    CREATED_AT = "created_at"
    RATING = "rating"
    FILE_SIZE = "file_size"
    WIDTH = "width"
    HEIGHT = "height"


class SortOrder(str, Enum):
    """排序方向枚举"""

    ASC = "asc"
    DESC = "desc"


class YandeDataRepository(BaseDAO):
    class YandeDataQueryParams(BaseModel):
        """高级查询参数"""

        tags: Optional[str] = Field(
            None,
            description="标签表达式，空格分隔；无 * 表精确 token 匹配，前缀 - 表排除；含 *（如 pan* / p*n）表前缀/中间通配",
        )
        min_width: Optional[int] = Field(None, ge=0, description="最小宽度")
        max_width: Optional[int] = Field(None, ge=0, description="最大宽度")
        min_height: Optional[int] = Field(None, ge=0, description="最小高度")
        max_height: Optional[int] = Field(None, ge=0, description="最大高度")
        rating: Optional[list[Rating]] = Field(None, description="评分过滤")
        min_file_size: Optional[int] = Field(None, ge=0, description="最小文件大小(KB)")
        max_file_size: Optional[int] = Field(None, ge=0, description="最大文件大小(KB)")
        file_types:  Optional[List[str]] = Field(None, description="文件类型列表")
        author: Optional[str] = Field(None, max_length=100, description="作者名称")
        sort_by: Optional[SortBy] = Field(SortBy.CREATED_AT, description="排序字段")
        sort_order: Optional[SortOrder] = Field(SortOrder.DESC, description="排序方向")
        page: int = Field(1, ge=1, description="页码")
        page_size: int = Field(20, ge=1, le=100, description="每页数量")

        model_config = ConfigDict(from_attributes=True)

    @staticmethod
    def _tag_filter(tags: str):
        """本地 tag 过滤。

        规则：
          - 无 * -> 精确 token 匹配（按空格分词）
          - 含 * -> 走 LIKE 通配，与 yande.re DSL 一致；用户输入 * 翻译为 SQL %
          - 前缀 - -> 排除语义（取反）
          - 纯 * 或空 token -> 静默忽略
        多 token 之间为 AND 关系（与历史行为一致）。
        """
        if not tags:
            return None
        parts = [t for t in tags.split() if t.strip()]
        filters = []
        for raw in parts:
            negated = raw.startswith("-")
            token = raw[1:] if negated else raw
            if not token or token == "*":
                continue

            if "*" in token:
                pattern = _to_like_pattern(token)
                cond = or_(
                    YandeData.tags.like(pattern, escape=_LIKE_ESCAPE),
                    YandeData.tags.like(f"% {pattern}", escape=_LIKE_ESCAPE),
                )
            else:
                cond = or_(
                    YandeData.tags == token,
                    YandeData.tags.like(f"{token} %", escape=_LIKE_ESCAPE),
                    YandeData.tags.like(f"% {token}", escape=_LIKE_ESCAPE),
                    YandeData.tags.like(f"% {token} %", escape=_LIKE_ESCAPE),
                )

            filters.append(~cond if negated else cond)

        if not filters:
            return None
        return and_(*filters)

    @staticmethod
    def _build_upsert_stmt(yande_items: list, returning: bool = False):
        use_mariadb = config.database.enable and config.database.host

        if use_mariadb:
            stmt = mysql_insert(YandeData).values(yande_items)
            update_cols = {
                k: stmt.inserted[k]
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

    def query(
        self, query_params: YandeDataQueryParams, downloaded_only: bool = None
        ) -> Tuple[List[YandeData], int]:
        filter_funcs = []

        # 过滤器映射字典
        filter_mappings = {
            "tags": lambda v: self._tag_filter(v),
            "rating": lambda v: YandeData.rating.in_(v),
            "file_types": lambda v: YandeData.file_ext.in_(v),
            "min_width": lambda v: YandeData.width >= v,
            "max_width": lambda v: YandeData.width <= v,
            "min_height": lambda v: YandeData.height >= v,
            "max_height": lambda v: YandeData.height <= v,
            "min_file_size": lambda v: YandeData.file_size >= v * 1024,
            "max_file_size": lambda v: YandeData.file_size <= v * 1024,
            "author": lambda v: YandeData.author.contains(v),
        }
        if not query_params.rating or len(query_params.rating) == len(Rating):
            query_params.rating = None  # 全部评分不需要过滤
        if downloaded_only is not None:
            filter_funcs.append(YandeData.down_flag == downloaded_only)
        # 应用简单过滤器
        for param_name, filter_func in filter_mappings.items():
            param_value = getattr(query_params, param_name, None)
            if param_value is not None:
                filter_funcs.append(filter_func(param_value))

        count_stmt = select(func.count()).select_from(YandeData).filter(*filter_funcs)
        query_stmt = select(YandeData).filter(*filter_funcs)

        offset = (query_params.page - 1) * query_params.page_size
        query_stmt = query_stmt.offset(offset).limit(query_params.page_size)

        sort_column = getattr(YandeData, query_params.sort_by, YandeData.id)
        if query_params.sort_order == "desc":
            query_stmt = query_stmt.order_by(sort_column.desc())
        elif query_params.sort_order == "asc":
            query_stmt = query_stmt.order_by(sort_column.asc())
        else:
            query_stmt = query_stmt.order_by(sort_column.desc())

        results = self.session.execute(query_stmt).scalars().all()
        total = self.session.execute(count_stmt).scalar() or 0

        return results, total

    def get_by_id(self, image_id: int) -> Optional[YandeData]:
        stmt = select(YandeData).filter_by(id=image_id)
        return self.session.execute(stmt).scalar_one_or_none()

    def get_max_id_for_tags(self, tags: str) -> Optional[int]:
        """返回匹配 tags 且已下载的最大图片 ID。仅作为增量模式首次运行的兜底起点。"""
        if not tags or not tags.strip():
            return None
        filter_funcs = [
            self._tag_filter(tags),
            YandeData.down_flag.is_(True),
        ]
        stmt = select(func.max(YandeData.id)).filter(*filter_funcs)
        return self.session.execute(stmt).scalar_one_or_none()

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

    def get_downloaded_ids(self) -> set[int]:
        """查询所有已下载原图的 image_id（单次 SQL，仅取 id 字段）

        Returns:
            set[int]: down_flag=True 的 image_id 集合
        """
        stmt = select(YandeData.id).where(YandeData.down_flag.is_(True))
        rows = self.session.execute(stmt).scalars().all()
        return set(rows)

    def get_file_ext(self, image_id: int) -> Optional[str]:
        """只查询 file_ext，轻量级方法"""
        stmt = select(YandeData.file_ext).filter_by(id=image_id)
        result = self.session.execute(stmt).scalar_one_or_none()
        return result if result else "jpg"

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

    def upsert_batch_with_down_flags(self, yande_items: list) -> Optional[List[YandeData]]:
        if not yande_items:
            return None

        try:
            stmt = self._build_upsert_stmt(yande_items, returning=True)
            result = self.session.execute(stmt)
            rows = result.scalars().all()
            return rows
        except Exception as e:
            logger.warning(f"Upsert batch with returning failed: {e}")
            self.session.rollback()

        try:
            # 回退方案：不使用 returning，直接查询更新后的 down_flag
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
            raise e

    def upsert(self, yande_item) -> bool:
        if hasattr(yande_item, '__dict__'):
            yande_item = {k: v for k, v in yande_item.__dict__.items() if not k.startswith('_')}
        result = self.upsert_batch([yande_item])
        return result > 0


yande_data_repository = YandeDataRepository()