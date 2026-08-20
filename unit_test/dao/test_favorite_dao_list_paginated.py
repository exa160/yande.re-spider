"""测试 FavoriteDao.list_paginated 分页逻辑

背景：favorite_dao 是模块级单例，BaseDAO 在严格模式下要求
`RequestSessionMiddleware` 提供 session。无 HTTP 请求上下文时，
必须用 `with favorite_dao as dao:` 显式打开 session，__exit__ 会
自动 commit 并清空 _session 让下一次 with 重新建立。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]) + "/backend")

from src.dao.favorite_dao import favorite_dao
from src.models.database.yande import FavoriteFolder


def _seed_via_dao(n: int) -> None:
    """使用 favorite_dao 单例创建 n 个收藏夹，sort_order = i"""
    with favorite_dao as dao:
        dao.session.query(FavoriteFolder).delete()
        for i in range(n):
            dao.create(name=f"folder_{i}", sort_order=i)


def test_list_paginated_returns_total():
    _seed_via_dao(15)
    with favorite_dao as dao:
        items, total = dao.list_paginated(page=1, page_size=10)
    assert total == 15
    assert len(items) == 10


def test_list_paginated_ordered_by_sort_order():
    _seed_via_dao(5)
    with favorite_dao as dao:
        items, _ = dao.list_paginated(page=1, page_size=10)
    assert [f.sort_order for f in items] == [0, 1, 2, 3, 4]


def test_list_paginated_second_page():
    _seed_via_dao(15)
    with favorite_dao as dao:
        items, total = dao.list_paginated(page=2, page_size=10)
    assert total == 15
    assert len(items) == 5
    assert items[0].sort_order == 10


def test_list_paginated_empty_when_no_data():
    with favorite_dao as dao:
        dao.session.query(FavoriteFolder).delete()
        items, total = dao.list_paginated(page=1, page_size=10)
    assert items == []
    assert total == 0
