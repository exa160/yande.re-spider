"""``YandeApi.search_trans`` 的 ``order:`` meta-tag 生成测试。

背景（设计文档 §5.3.1 / §5.3.2）：旧实现用字符串拼接
``f"order:{sort_by}_{order}"``，但 yande.re 各字段的后缀规则**不一致**：

    id      升序 order:id         降序 order:id_desc
    score   升序 order:score_asc  降序 order:score
    mpixels 升序 order:mpixels_asc 降序 order:mpixels

后果是「在线浏览 + 按 ID 升序」静默失效 —— ``sort_by="id"`` + ``sort_order="asc"``
拼出服务端不认的 ``order:id_asc``，退化为默认排序。默认路径是 ``desc``
（恰好合法），所以平时无感。

现在改为查 ``yande_api.ORDER_TOKENS`` 显式映射表；**未登记**字段
（landscape / portrait / vote）仍沿用历史拼接行为（保守回退，行为不变）。

纯函数测试：不发 HTTP、不碰数据库。
"""
import pytest

from src.infrastructure.yande_api import ORDER_TOKENS, YandeApi
from src.models.request.yande import YandeSearchTags


def _trans(sort_by=None, sort_order=None, **kwargs) -> str:
    """便捷调用：用给定 sort 参数构造 YandeSearchTags 并转换。"""
    tags = YandeSearchTags(sort_by=sort_by, sort_order=sort_order, **kwargs)
    return YandeApi.search_trans(tags)


def _order_tokens(result: str) -> list[str]:
    """从转换结果中挑出所有 order: token。"""
    return [p for p in result.split() if p.startswith("order:")]


# --------------------------------------------------------------------------
# 1~6：已登记字段的 asc/desc 必须映射到各自合法的 token
# --------------------------------------------------------------------------

def test_id_asc_is_bare_order_id():
    """核心回归用例：sort_by=id + asc → order:id（**不能**是 order:id_asc）。"""
    result = _trans(sort_by="id", sort_order="asc")
    assert _order_tokens(result) == ["order:id"]
    assert "order:id_asc" not in result


def test_id_desc_is_order_id_desc():
    result = _trans(sort_by="id", sort_order="desc")
    assert _order_tokens(result) == ["order:id_desc"]


def test_score_asc_is_order_score_asc():
    result = _trans(sort_by="score", sort_order="asc")
    assert _order_tokens(result) == ["order:score_asc"]


def test_score_desc_is_bare_order_score():
    """与 id 相反：score 降序才是「无后缀」形式。"""
    result = _trans(sort_by="score", sort_order="desc")
    assert _order_tokens(result) == ["order:score"]
    assert "order:score_desc" not in result


def test_mpixels_asc_is_order_mpixels_asc():
    result = _trans(sort_by="mpixels", sort_order="asc")
    assert _order_tokens(result) == ["order:mpixels_asc"]


def test_mpixels_desc_is_bare_order_mpixels():
    result = _trans(sort_by="mpixels", sort_order="desc")
    assert _order_tokens(result) == ["order:mpixels"]


# --------------------------------------------------------------------------
# 7：sort_order 缺失 / 非法 → 一律按 desc 处理
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "bad_order",
    [None, "", "ASC", "ascending", "descending", "desc ", "DESC"],
)
def test_invalid_sort_order_falls_back_to_desc(bad_order):
    result = _trans(sort_by="id", sort_order=bad_order)
    assert _order_tokens(result) == ["order:id_desc"]


@pytest.mark.parametrize(
    "sort_by, expected",
    [("id", "order:id_desc"), ("score", "order:score"), ("mpixels", "order:mpixels")],
)
def test_missing_sort_order_desc_token_per_field(sort_by, expected):
    """默认 desc 下三个字段各是不同写法，不能一刀切拼 ``_desc``。"""
    result = _trans(sort_by=sort_by, sort_order=None)
    assert _order_tokens(result) == [expected]


# --------------------------------------------------------------------------
# 8：sort_by 缺失 → 查询串里不得出现任何 order: token
# --------------------------------------------------------------------------

@pytest.mark.parametrize("empty_sort_by", [None, ""])
def test_no_sort_by_emits_no_order_token(empty_sort_by):
    assert _order_tokens(_trans(sort_by=empty_sort_by, sort_order="asc")) == []


def test_sort_by_none_keeps_other_filters_intact():
    """只跳过 order 部分，其余过滤条件照常生成。"""
    result = _trans(sort_by=None, sort_order="desc", tags="foo", min_id=100)
    assert _order_tokens(result) == []
    assert "foo" in result
    assert "id:>=100" in result


# --------------------------------------------------------------------------
# 9：未登记字段 → 回退到历史拼接行为（锁定「行为不变」这个取舍）
# --------------------------------------------------------------------------

@pytest.mark.parametrize("sort_by", ["vote", "landscape", "portrait"])
def test_unregistered_field_keeps_legacy_concat(sort_by):
    result = _trans(sort_by=sort_by, sort_order="desc")
    assert _order_tokens(result) == [f"order:{sort_by}_desc"]

    result_asc = _trans(sort_by=sort_by, sort_order="asc")
    assert _order_tokens(result_asc) == [f"order:{sort_by}_asc"]


def test_unregistered_field_not_in_order_tokens_table():
    """保守回退的前提：这些字段确实没有登记映射。"""
    for field in ("vote", "landscape", "portrait"):
        assert field not in ORDER_TOKENS


# --------------------------------------------------------------------------
# 10：完整查询串里不得出现任何非法 token
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "sort_by, sort_order",
    [
        ("id", "asc"),
        ("id", "desc"),
        ("score", "asc"),
        ("score", "desc"),
        ("mpixels", "asc"),
        ("mpixels", "desc"),
        ("vote", "asc"),
        ("vote", "desc"),
        (None, "asc"),
    ],
)
def test_no_invalid_order_token_in_full_query_string(sort_by, sort_order):
    result = _trans(
        sort_by=sort_by,
        sort_order=sort_order,
        tags="hatsune_miku",
        min_score=50,
        parent_none=True,
    )
    assert "order:id_asc" not in result
    assert "order:score_desc" not in result
    assert "order:mpixels_desc" not in result


def test_order_token_appears_alongside_other_filters():
    """与其它 token 共存时，order 仍是唯一且正确的那一个。

    只用 ``min_id`` —— ``search_trans`` 的 ``range_mappings`` 循环对
    ``max_*`` 字段存在一个**独立的既有缺陷**（会产出 ``id:>=`` 而非 ``id:<=``，
    见 §5.3.2 同区域），不属于本 PR 范围，故不在此断言 max_* 行为。
    """
    result = _trans(sort_by="id", sort_order="asc", tags="foo", min_id=100, parent_none=True)
    assert _order_tokens(result) == ["order:id"]
    assert "foo" in result
    assert "id:>=100" in result
    assert "parent:none" in result
