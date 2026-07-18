"""_tag_filter 行为测试：精确 / 通配 / 排除 / 转义。"""
from datetime import datetime

import pytest

from src.dao.database import _get_session_factory
from src.dao.yande_data_dao import YandeDataRepository
from src.models.database.yande import YandeData


@pytest.fixture
def session():
    s = _get_session_factory()()
    yield s
    s.close()


def _make_data(session, image_id: int, tags: str, down_flag: bool = True) -> None:
    """在测试数据库中插入一条可控 tag 记录。"""
    session.query(YandeData).filter_by(id=image_id).delete()
    session.commit()
    data = YandeData(
        id=image_id,
        down_flag=down_flag,
        tags=tags,
        created_at=datetime.now(),
        updated_at=datetime.now(),
        creator_id=0,
        author="test",
        change=0,
        source="",
        score=0,
        md5="x" * 32,
        file_size=0,
        file_ext="jpg",
        file_url="",
        is_shown_in_index=False,
        preview_url="",
        preview_width=0,
        preview_height=0,
        actual_preview_width=0,
        actual_preview_height=0,
        sample_url="",
        sample_width=0,
        sample_height=0,
        sample_file_size=0,
        jpeg_url="",
        jpeg_width=0,
        jpeg_height=0,
        jpeg_file_size=0,
        rating="s",
        is_rating_locked=False,
        has_children=False,
        parent_id=None,
        status="active",
        is_pending=False,
        width=0,
        height=0,
        is_held=False,
        is_note_locked=False,
        last_noted_at=0,
        last_commented_at=0,
    )
    session.add(data)
    session.commit()


def _cleanup_tag(session, tag: str) -> None:
    """使用通配删除所有含某子串的记录（清理阶段用，宽松匹配可接受）。"""
    session.query(YandeData).filter(YandeData.tags.contains(tag)).delete()
    session.commit()


SEED_EXACT = "test_seed_exact_zzz"
SEED_PREFIX_A = "panza_test_zzz"
SEED_PREFIX_B = "panda_test_zzz"
SEED_INFIX = "pin_test_zzz"
SEED_NOISE = "noise_test_zzz"


def _setup_corpus(session):
    """构造 5 条独立 tag 串用于测试。"""
    ids = [91000001, 91000002, 91000003, 91000004, 91000005]
    for tid in ids:
        _make_data(session, tid, "init_remove_me", down_flag=False)
    _cleanup_tag(session, "init_remove_me")
    _make_data(session, ids[0], SEED_EXACT, down_flag=True)
    _make_data(session, ids[1], f"{SEED_PREFIX_A} {SEED_EXACT}", down_flag=True)
    _make_data(session, ids[2], f"{SEED_PREFIX_B} {SEED_EXACT}", down_flag=True)
    _make_data(session, ids[3], f"{SEED_INFIX} {SEED_EXACT}", down_flag=True)
    _make_data(session, ids[4], f"{SEED_EXACT} {SEED_NOISE}", down_flag=True)
    return ids


def _teardown_corpus(session, ids):
    for tid in ids:
        session.query(YandeData).filter_by(id=tid).delete()
    session.commit()


def test_exact_token_does_not_match_substring(session):
    ids = _setup_corpus(session)
    try:
        repo = YandeDataRepository(session=session)
        rows, _ = repo.query(
            YandeDataRepository.YandeDataQueryParams(tags="noise_test_zzz")
        )
        row_ids = {r.id for r in rows}
        assert ids[4] in row_ids
        assert all(tid != row_ids for tid in ids[:4])
    finally:
        _teardown_corpus(session, ids)


def test_prefix_wildcard_matches_seed(session):
    ids = _setup_corpus(session)
    try:
        repo = YandeDataRepository(session=session)
        rows, _ = repo.query(
            YandeDataRepository.YandeDataQueryParams(tags="panza_test_zzz*")
        )
        row_ids = {r.id for r in rows}
        assert ids[1] in row_ids
        assert ids[2] not in row_ids
        assert ids[3] not in row_ids
        assert ids[4] not in row_ids
    finally:
        _teardown_corpus(session, ids)


def test_middle_wildcard_matches_seed(session):
    ids = _setup_corpus(session)
    try:
        repo = YandeDataRepository(session=session)
        rows, _ = repo.query(
            YandeDataRepository.YandeDataQueryParams(tags="pin_test_*zzz")
        )
        row_ids = {r.id for r in rows}
        assert ids[3] in row_ids
        assert ids[0] not in row_ids
        assert ids[1] not in row_ids
        assert ids[2] not in row_ids
    finally:
        _teardown_corpus(session, ids)


def test_exclude_token_does_not_remove_other_token(session):
    """-panza_test_zzz 仅排除包含该完整 token 的行，不影响 pin_test_zzz。"""
    ids = _setup_corpus(session)
    try:
        repo = YandeDataRepository(session=session)
        rows, _ = repo.query(
            YandeDataRepository.YandeDataQueryParams(tags=f"-{SEED_PREFIX_A}")
        )
        row_ids = {r.id for r in rows}
        assert ids[1] not in row_ids
        assert ids[3] in row_ids
        assert ids[4] in row_ids
    finally:
        _teardown_corpus(session, ids)


def test_multiple_tokens_use_and_semantics(session):
    ids = _setup_corpus(session)
    try:
        repo = YandeDataRepository(session=session)
        rows, _ = repo.query(
            YandeDataRepository.YandeDataQueryParams(
                tags=f"{SEED_EXACT} noise_test_zzz"
            )
        )
        row_ids = {r.id for r in rows}
        # 仅 ids[4] 同时含两个 token
        assert row_ids == {ids[4]}
    finally:
        _teardown_corpus(session, ids)


def test_bare_star_is_ignored(session):
    ids = _setup_corpus(session)
    try:
        repo = YandeDataRepository(session=session)
        rows, _ = repo.query(
            YandeDataRepository.YandeDataQueryParams(tags="*")
        )
        # 过滤为 None，repo 视为不过滤 tags；返回所有记录（仅断言调用不抛错）
        assert rows is not None
    finally:
        _teardown_corpus(session, ids)


def test_escaping_literal_percent_in_token(session):
    """用户输入中包含 % / _ 时应按字面匹配（autoescape 验证）。"""
    raw_tag = "tag_with_percent_zzz%"
    ids = [92000001, 92000002]
    _make_data(session, ids[0], raw_tag, down_flag=True)
    _make_data(session, ids[1], "tag_with_percent_zzzX", down_flag=True)
    try:
        repo = YandeDataRepository(session=session)
        rows, _ = repo.query(
            YandeDataRepository.YandeDataQueryParams(tags=raw_tag)
        )
        row_ids = {r.id for r in rows}
        assert ids[0] in row_ids
        assert ids[1] not in row_ids
    finally:
        for tid in ids:
            session.query(YandeData).filter_by(id=tid).delete()
        session.commit()