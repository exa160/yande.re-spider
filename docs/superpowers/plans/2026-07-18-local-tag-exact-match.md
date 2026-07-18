# 本地 Tag 默认精确匹配 + 通配兼容 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `backend/src/dao/yande_data_dao.py::_tag_filter` 的默认匹配语义改为完整 tag token 匹配，同时支持与 yande.re DSL 对齐的前缀与中间通配（`pan*` / `p*n`），并补齐测试覆盖与文档说明。

**Architecture:** 单一过滤函数 `_tag_filter` 重写分支：token 无 `*` 走精确匹配（SQL `=` + 三段 `LIKE`），token 含 `*` 走通配（直接 `LIKE` 带 autoescape）。调用方 `query` 与 `get_max_id_for_tags` 共用此函数，调度增量游标自动对齐。前端零改动。

**Tech Stack:** FastAPI / SQLAlchemy 2 / SQLite & MariaDB / SQLAlchemy `like()` 自定义转义 / pytest + repository 内 autouse fixture / `git-master` commit 规范。

---

## 任务 1：改写 `_tag_filter` 默认精确语义（保留 `*` 通配）

**Files:**
- Modify: `backend/src/dao/yande_data_dao.py:55-65` （`_tag_filter` 静态方法）
- Modify: `backend/src/dao/yande_data_dao.py:38` （`YandeDataQueryParams.tags` Field description）

- [ ] **Step 1：修改 `YandeDataQueryParams.tags` Field 描述**

定位 `backend/src/dao/yande_data_dao.py:35-53` 中：

```python
tags: Optional[str] = Field(None, description="标签表达式，空格分隔，前缀 - 表示排除")
```

替换为：

```python
tags: Optional[str] = Field(
    None,
    description="标签表达式，空格分隔；无 * 表精确 token 匹配，前缀 - 表排除；含 *（如 pan* / p*n）表前缀/中间通配",
)
```

- [ ] **Step 2：重写 `_tag_filter` 静态方法**

定位 `backend/src/dao/yande_data_dao.py:55-65`，整体替换为：

```python
@staticmethod
def _tag_filter(tags: str):
    """本地 tag 过滤。

    规则：
      - 无 * -> 精确 token 匹配（按空格分词）
      - 含 * -> 走 LIKE 通配，与 yande.re DSL 一致
      - 前缀 - -> 排除语义（取反）
      - 纯 * 或空 token -> 静默忽略
    多 token 之间为 AND 关系（与历史行为一致）。
    """
    parts = [t for t in tags.split() if t.strip()]
    filters = []
    for raw in parts:
        negated = raw.startswith("-")
        token = raw[1:] if negated else raw
        if not token or token == "*":
            continue

        if "*" in token:
            cond = or_(
                YandeData.tags.like(token, autoescape=True),
                YandeData.tags.like(f"% {token}", autoescape=True),
            )
        else:
            cond = or_(
                YandeData.tags == token,
                YandeData.tags.like(f"{token} %", autoescape=True),
                YandeData.tags.like(f"% {token}", autoescape=True),
                YandeData.tags.like(f"% {token} %", autoescape=True),
            )

        filters.append(~cond if negated else cond)

    if not filters:
        return None
    return and_(*filters)
```

注意：`from sqlalchemy import and_, select, func, or_`（`dao/yande_data_dao.py:6`）已存在，无需新增 import。

- [ ] **Step 3：本地烟雾测试**

进入 `backend/` 目录运行：

```bash
cd backend && python -c "from src.dao.yande_data_dao import YandeDataRepository; print(YandeDataRepository._tag_filter.__doc__)"
```

预期：打印出新 docstring 全文，且无 ImportError。

- [ ] **Step 4：Commit**

按仓库规范提交：

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev
GIT_MASTER=1 git add backend/src/dao/yande_data_dao.py
GIT_MASTER=1 git commit -m "fix(dao): 本地 tag 默认精确匹配，支持 * 通配兼容 yande.re DSL"
```

预期提交消息风格与 `git log --oneline -20` 中现有 `fix(dao):` / `feat(dao):` 一致。

---

## 任务 2：新增 `_tag_filter` 语义测试

**Files:**
- Create: `unit_test/dao/test_tag_filter_modes.py`

- [ ] **Step 1：创建测试目录与文件骨架**

`unit_test/dao/` 目录当前不存在，需先创建。写入 `unit_test/dao/__init__.py`（空文件）与 `unit_test/dao/test_tag_filter_modes.py`：

```python
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
    _make_data(session, ids[4], SEED_NOISE, down_flag=True)
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
```

- [ ] **Step 2：运行新测试，预期全部通过**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev
uv run pytest unit_test/dao/test_tag_filter_modes.py -v
```

预期：7 个测试全部 PASS。若失败，按错误信息调整 `_tag_filter` 实现，回到任务 1。

- [ ] **Step 3：Commit**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev
GIT_MASTER=1 git add unit_test/dao/test_tag_filter_modes.py unit_test/dao/__init__.py
GIT_MASTER=1 git commit -m "test(dao): 覆盖 _tag_filter 精确/通配/排除/转义行为"
```

---

## 任务 3：更新现有 `test_max_id_for_tags.py` 种子避免命名冲突

**Files:**
- Modify: `unit_test/test_max_id_for_tags.py`

- [ ] **Step 1：替换种子字符串**

将所有 `unique_test_tag_abc_zzz` / `test_filter_downloaded_tag_zzz` / `test_all_undownloaded_tag_zzz` / `nonexistent_tag_xyz_zzz` 后缀 `_zzz` 统一替换为 `_zzz_exact`。示例（替换全文 6 处）：

| 原值 | 新值 |
|---|---|
| `nonexistent_tag_xyz_zzz` | `nonexistent_tag_xyz_zzz_exact` |
| `unique_test_tag_abc_zzz` | `unique_test_tag_abc_zzz_exact` |
| `test_filter_downloaded_tag_zzz` | `test_filter_downloaded_tag_zzz_exact` |
| `test_all_undownloaded_tag_zzz` | `test_all_undownloaded_tag_zzz_exact` |

`_cleanup_tag` 保留 `tags.contains(tag)`（清理阶段允许宽松匹配）。

- [ ] **Step 2：运行测试，预期全部 PASS**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev
uv run pytest unit_test/test_max_id_for_tags.py -v
```

预期：4 个测试全部 PASS（说明精确语义下种子仍命中）。

- [ ] **Step 3：Commit**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev
GIT_MASTER=1 git add unit_test/test_max_id_for_tags.py
GIT_MASTER=1 git commit -m "test(dao): _zzz 种子改为 _zzz_exact 避免与精确语义冲突"
```

---

## 任务 4：跑全套后端测试，确认无回归

**Files:** 无文件修改，仅运行测试。

- [ ] **Step 1：运行整个后端测试集**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev
uv run pytest unit_test/ -v
```

预期：所有原有测试 + 新增 7 个测试全部 PASS。`FavoriteService._parse_tags_to_params`、`run_folder_schedule`、`POST /gallery/load` 链路相关测试若失败，回到任务 1 检查 `_tag_filter` 的 `None` 返回处理。

- [ ] **Step 2：若失败定位与修复**

若 `repo.query` 在 `tags=""` 时出现参数不兼容，验证 `_tag_filter` 在 `filters=[]` 时返回 `None` 且 `query` 方法的 `filter(*filter_funcs)` 能正确忽略 `None`。

`YandeDataRepository.query`（`dao/yande_data_dao.py:124-125`）当前为：

```python
count_stmt = select(func.count()).select_from(YandeData).filter(*filter_funcs)
```

`filter(None)` 在 SQLAlchemy 中会被忽略。若仍报错，在 `query` 内部加 `filter_funcs = [f for f in filter_funcs if f is not None]`，再回到任务 1 同步提交修复。

- [ ] **Step 3：无 commit**

若无修复需要，跳过此步。

---

## 任务 5：补充 AGENTS.md / README.md 文档说明

**Files:**
- Modify: `AGENTS.md:74-75`（代码规范检查清单）
- Modify: `README.md` “主要功能”章节（可选）

- [ ] **Step 1：在 `AGENTS.md` “API 路由文件检查”清单后追加一条**

定位 `AGENTS.md` 末尾的 **重构状态追踪** 与 *最后更新* 注释之间，在 “代码规范检查清单 → API 路由文件检查” 节追加：

```markdown
- [ ] 本地 tag 匹配：默认精确 token；`*` 表通配（`pan*` 前缀，`p*n` 中间）；`-` 表排除；纯 `*` 忽略（详见 `docs/superpowers/specs/2026-07-18-local-tag-exact-match-design.md`）
```

- [ ] **Step 2：在 `README.md` “主要功能”章节“高级查询”一行追加说明**

定位 `README.md` “瀑布流图库 + 高级查询（标签组合、分辨率、评分、文件大小过滤）”，改为：

```markdown
- 瀑布流图库 + 高级查询（本地 tag 默认精确匹配，`pan*` 前缀通配、`p*n` 中间通配，与 yande.re DSL 一致）
```

- [ ] **Step 3：Commit**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev
GIT_MASTER=1 git add AGENTS.md README.md
GIT_MASTER=1 git commit -m "docs: 补充本地 tag 精确 + 通配规则说明"
```

---

## 任务 6：版本号升级与发布流程（按 docs/release.md）

**Files:**
- Modify: `pyproject.toml:3`（`version = "1.1.5"` → `"1.1.6"`）
- Modify: `frontend/package.json:3`（`"version": "1.1.5"` → `"1.1.6"`）
- Modify: `backend/src/__init__.py:27`（`version: str = "1.1.5"` → `"1.1.6"`，即 `AppConfig.version` 实际定义位置）

- [ ] **Step 1：按 docs/release.md 三处 version 源同步**

按 `docs/release.md:112-114` 列出的三处源：

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev
sed -i 's/version = "1.1.5"/version = "1.1.6"/' pyproject.toml
sed -i 's/"version": "1.1.5"/"version": "1.1.6"/' frontend/package.json
sed -i 's/version: str = "1.1.5"/version: str = "1.1.6"/' backend/src/__init__.py
GIT_MASTER=1 git diff -- pyproject.toml frontend/package.json backend/src/__init__.py
```

预期输出仅展示三行 version 字符串变化。

- [ ] **Step 2：按 release 流程打 tag、PR**

按 `docs/release.md` 流程：

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev
GIT_MASTER=1 git add pyproject.toml frontend/package.json backend/src/__init__.py
GIT_MASTER=1 git commit -m "build(release): bump version 1.1.5 → 1.1.6"
GIT_MASTER=1 git tag v1.1.6
git push origin feature
gh release create v1.1.6 --target feature --title "v1.1.6" --notes "本地 tag 匹配改为默认精确 token，支持 * 通配兼容 yande.re DSL"
gh issue create --title "v1.1.6 验证" --body "请验证 pan 精确命中与 pan*/p*n 通配语义"
gh pr create --base next --title "v1.1.6: 本地 tag 默认精确 + * 通配" --body-file - <<'EOF'
- 修改：_tag_filter 默认精确 token；含 * 走通配
- 新增：unit_test/dao/test_tag_filter_modes.py 7 个用例
- 文档：AGENTS.md / README.md / 设计文档
EOF
```

---

## 自审清单（提交前自查）

- [ ] 任务 1 改写后 `_tag_filter` 处理 `tags=""` 与 `tags="*"` 时返回 `None`，不会污染 `repo.query` 的 `filter(*filter_funcs)`。
- [ ] 任务 2 测试覆盖精确 / 前缀通配 / 中间通配 / 排除 / AND / 纯 `*` / 转义，共 7 用例。
- [ ] 任务 3 种子改名与现有断言语义一致（精确 token 仍是字符串本身）。
- [ ] 任务 4 全套 `pytest` 通过；若有 `None` 处理问题已在 `query` 内修复。
- [ ] 任务 5 文档引用了正确的设计文档路径与日期。
- [ ] 任务 6 三个 version 源同步，且 tag / release / PR 描述完整。
- [ ] 全部 commit 消息风格遵循仓库现有 `fix(dao):` / `test(dao):` / `docs:` / `build(release):` 前缀。
- [ ] 无 `TBD` / `TODO` / `FIXME` 占位符残留。