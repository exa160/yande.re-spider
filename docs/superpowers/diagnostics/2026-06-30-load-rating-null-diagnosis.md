# 预览图清理 UI — `/load` 接口 `rating=None` 崩溃：诊断与修复方案

**日期**：2026-06-30
**状态**：诊断完成，待用户审批修复方案
**作者**：Sisyphus
**范围**：仅诊断 + 修复方案，**不动代码**

---

## 1. 错误回顾

```text
ERROR  | src.middleware.errors:global_exception_handler:85 -
        Unhandled Exception: object NoneType can't be used in 'await' expression

ERROR  | src.middleware.errors:global_exception_handler:86 -
pydantic_core._pydantic_core.ValidationError:
    1 validation error for GalleryLoadResponse
    data.0.rating
        Input should be 's', 'q' or 'e' [type=enum,
        input_value=None, input_type=NoneType]
```

**触发入口**：`POST /load` API（`backend/src/api/v1/gallery.py:26`）
**抛出点**：`GalleryLoadResponse(data=images, ...)` （第 36 行）— Pydantic 序列化阶段
**报错字段**：`data[0].rating` 期望枚举，实际 `None`

---

## 2. Root Cause（已锁定）

### 2.1 调用链

```
load_gallery (api/v1/gallery.py:26)
    └─ asyncio.to_thread(GalleryService.query_local_database, request)
        └─ YandeDataRepository().query(query_params)
            └─ session.execute(select(YandeData)...)  ← ORM YandeData.__tablename__='yande_data'
                └─ returns List[YandeData]              ← 第一行 row.rating = None
    └─ GalleryLoadResponse(data=images, ...)            ← Pydantic 校验失败
        └─ ValidationError: rating=None, expects 's'/'q'/'e'
```

### 2.2 数据契约落差（关键）

**DB 侧**：
- 列定义 `rating VARCHAR(1)`，**`nullable=True`**（SQLAlchemy `Column` 未显式 nullable=False → 默认 nullable）
- 实际表 `yande_data` 中存在 1 条 `rating IS NULL` 的记录：`id=100, created_at='2024-01-01', down_flag=1, rating=NULL`

**ORM 侧**：
```python
# backend/src/models/database/yande.py:45
rating = Column(Enum(Rating, values_callable=lambda x: [e.value for e in x]),
                index=True, comment="图片评级")
# 没有 nullable=False  ← 源头 1：schema 允许 NULL
```

**Pydantic 侧**：
```python
# backend/src/models/response/gallery.py:25
class ImageDetail(BaseModel):
    rating: Rating = Field(description="图片评级，如 S/R18")
                                       # ← 没有 default / Optional  ← 源头 2：应用层强制枚举
```

**Enum 定义**：
```python
# backend/src/common/constant.py:89
class Rating(str, Enum):
    S   = "s"
    R15 = "q"   # R15 对应 'q' (Questionable)
    R18 = "e"
```

### 2.3 直接 Root Cause（一句话）

**`backend/data/yande_data.db` 中 `yande_data` 表残留 1 条 `id=100` 记录，rating 字段为 NULL；ORM 严格按 `Rating` 枚举校验，NULL 不属于 `'s'/'q'/'e'`，所以 Pydantic 序列化时崩溃。**

数据来源推论：id=100 / created_at=2024-01-01 / score=NULL / change=NULL / preview_width=NULL 等大量字段为 NULL，明显是**手工测试数据残留**（2024 年初 schema 测试时插入，未清理；后续 `Base.metadata.create_all()` 也不会清理既有数据）。

### 2.4 顺带发现（次级 Root Cause — 当前未触发但潜藏）

`backend/data/yande_data.db` 实际存在**两个图片表**：

| 表 | 行数 | rating 分布 | 是否被 ORM 映射 | 备注 |
|---|---|---|---|---|
| `yande_data` | 1 | NULL | ✅（当前 `YandeData` ORM 指向这个表） | 旧 schema 残留，42 列（含 `site`, `source_id`） |
| `image_data` | 3034 | ('e':627, 'q':1501, 's':906) | ❌（生产数据实际在这表，但 ORM 不映射） | 新 schema，43 列（含 `down_flag`） |

git log 显示历史上有过完整重命名：
- `3d7533f feat(db): rename yande_data to image_data with site field`
- `12a4d74 refactor(dao): rename YandeDataRepository to ImageDataRepository with site param`

但 `feature` 分支当前的 ORM 仍是旧版 `YandeData`（42 列、有 `site` / `source_id` 字段），仍映射 `yande_data` 表。这两个 rename commits 在 `next_dev` 分支不在 `feature` 分支的 git 历史中。

**这不是导致当前 bug 的原因**（用户实际报错来自 ORM 读到的那 1 行），但是**潜在的下一次 bug**（一旦生产线真有 NULL rating 数据落库，相同路径还会爆）。修复方案必须顺手指出。

---

## 3. 漏洞面（暴露面）扫描

包含 `Rating` 枚举字段且 **未做 nullable 兼容** 的 Pydantic 模型：

| 文件:行 | 字段 | 是否 Optional | 风险 |
|---|---|---|---|
| `models/response/gallery.py:25` | `ImageDetail.rating: Rating` | ❌ | **本 bug 源头** |
| `models/response/yande.py:49` | `YandePostData.YandePostItem.rating: Rating` | ❌ | 仅在 infrastructure 层解析远端 API 时使用，远端数据格式固定为 's'/'q'/'e'，**无外部数据风险**，但同样脆弱 |
| `models/response/yande.py:52` | `parent_id: Optional[int]` | ✅ | OK |
| `models/response/gallery.py:33` | `ImageDetail.score: Optional[int]` | ✅ | OK |

**当前确实受影响的 API**：
1. `POST /api/v1/gallery/load`（本 bug，source=local 时）
2. `GET /api/v1/gallery/image/{id}`（同样读 `YandeData`，如果命中 id=100 会同样爆）
3. `POST /api/v1/gallery/load`（source=remote 时不读 ORM，但 `YandePostData.rating: Rating` 同模式，仅外部数据固定时不触发）

`POST /api/v1/gallery/load`（source=local）→ 当前 100% 必爆（DB 里那条 id=100 是仅有的 `yande_data` 行）。

---

## 4. 修复方案（4 选 1，按代价从低到高）

### 方案 A：**数据层清理**（最小侵入，不动 schema）

直接删 / 更新 DB 里的脏数据：

```sql
-- 选项 1：直接删除（推荐 — id=100 显然是测试残留）
DELETE FROM yande_data WHERE id = 100;

-- 选项 2：兜底为 'q'（Questionable，最安全评级）
UPDATE yande_data SET rating = 'q' WHERE rating IS NULL OR rating = '';

-- 选项 3：兜底为 'q' + 加 NOT NULL 约束（防止未来再次 NULL）
UPDATE yande_data SET rating = 'q' WHERE rating IS NULL;
-- SQLite 不能 ALTER COLUMN，需要重建表才能加 NOT NULL，复杂性提升
```

**优点**：
- 5 秒修复，最小代价
- 不动代码、不动 schema、可回滚（备份数据可以恢复）
- 立即解决 /load 报错

**缺点**：
- 治标不治本：未来如果再有 NULL rating 写入，仍会爆
- 没有强制约束，下次 regression

**回滚**：`data/yande_data.db.pre-migration-20260621.bak` 等 3 个备份可直接恢复

**验证**：
```bash
sqlite3 -readonly backend/data/yande_data.db \
  "SELECT COUNT(*) FROM yande_data WHERE rating IS NULL; -- expected 0"
```
然后重启 backend，调 `/load` 返回 200。

---

### 方案 B：**Pydantic 兜底**（应用层 defense in depth，推荐与 A 联用）

修改 `backend/src/models/response/gallery.py:25`：

```python
class ImageDetail(BaseModel):
    rating: Optional[Rating] = Field(
        default=None,
        description="图片评级（s=Safe, q=Questionable, e=Explicit），缺失时为 None",
    )

    @field_validator('rating', mode='before')
    @classmethod
    def coerce_rating(cls, v):
        """兼容 DB 中 NULL/空字符串/未知值的脏数据。

        1) None / '' / NoneType → None（保持 Optional 语义）
        2) 's' / 'q' / 'e' → 对应 Rating 枚举
        3) 未知值 → 兜底为 Rating.R15 (q)，不报错
        """
        if v is None or v == '':
            return None
        if isinstance(v, Rating):
            return v
        try:
            return Rating(v)
        except ValueError:
            logger.warning(f"Unknown rating value: {v!r}, defaulting to R15 (q)")
            return Rating.R15
```

**优点**：
- 治标也治本：未来 DB 落 NULL rating，API 仍能正常返回
- 兜底值是 `Rating.R15 ('q')` — yande.re 站点的中间评级，最安全的兜底

**缺点**：
- 改动了 3 处代码（含 `@field_validator` 装饰器 import）
- 静默兜底可能掩盖未来 schema 不一致（建议加 logger.warning）

**额外回报**：前端 Gallery/Vue 的 rating 展示不会因为 DB 脏数据 crash，但前端需要相应处理 `null`（目前直接 `{rating}` 会渲染 "null"，需要 `{rating || 'q'}` 或 `{rating ?? 'q'}`）。

---

### 方案 C：**DB schema NOT NULL + DB migration 系统**（治本 + 治根）

1. 引入 Alembic（项目目前 `alembic/versions/` 空目录，无 alembic.ini）
2. 写第一个 migration：
   ```python
   def upgrade():
       # 1) 兜底数据
       op.execute("UPDATE yande_data SET rating = 'q' WHERE rating IS NULL")
       # 2) 重建表加 NOT NULL（SQLite ALTER 限制 → CREATE NEW + COPY + DROP + RENAME）
       # 详细步骤见 Alembic SQLite 文档
   ```
3. ORM 同步：`Column(Enum(Rating, ...), nullable=False, server_default='q')`

**优点**：
- 一劳永逸
- 未来 schema 变更走标准 migration 流程

**缺点**：
- 工作量大（3-5 天）
- 引入 Alembic 是项目级决策（项目目前 `_auto_migrate` workaround）
- 重建表涉及 `image_data` 表（同样 nullable=True）— 范围扩大

**不推荐**作为单独方案，应在用户明确希望"做完整 migration 体系建设"时再做。

---

### 方案 D：**合并 next_dev 的 ORM rename + 数据迁移**（治根）

合并 `3d7533f feat(db): rename yande_data to image_data` + `12a4d74 refactor(dao): rename YandeDataRepository...`，让 ORM 真正映射 `image_data` 表：

**优点**：
- 与 production 主线对齐
- 消除两表并存的混乱（yande_data 是僵尸）

**缺点**：
- 重大 schema 变更，跨多文件（DAO + ORM + middleware + services + api），需要全回归测试
- 是 release-blocking 级别的 PR
- 不解决 /load crash（因为 production 数据已合规）

**不推荐**针对本 bug。但应在后续 sprint 单独排期。

---

## 5. 推荐方案：**A + B 组合**

| 步骤 | 行动 | 风险 |
|---|---|---|
| 1 | **B**: 改 `ImageDetail.rating` 为 `Optional` + 加 `field_validator` 兜底（defense in depth） | 低 — 改动隔离在 `response/gallery.py`，加 5 行代码 + 1 个 decorator import |
| 2 | **A**: 删 / 兜底 yande_data id=100 那条脏数据 | 极低 — 一条 SQL，可 rollback |
| 3 | **回归测试**：写 failing test 模拟 NULL rating 落库 → /load 仍能返回 200 | 0 — TDD 验证 |
| 4 | （可选）`/load` source=remote 路径也加相同兜底，防止远端 API 改格式时 crash | 低 |

**理由**：
- A 立即止血（5 秒）
- B 防止未来回归（minute 级）
- C/D 是项目级治理，超出"修这个 bug"的范围

**总改动预估**：
- `backend/src/models/response/gallery.py` ±8 行
- `backend/src/models/response/yande.py`（可选）±8 行
- `backend/unit_test/api/v1/test_preview_cleanup_routes.py`（或新建 `test_gallery_load.py`）+30 行新增测试
- **无需动 ORM / DAO / service**

---

## 6. 验证步骤（修复后必须全部跑通）

1. **静态验证**：pydantic model 改完后 `grep -rn "rating: Rating" src/` 只剩 yande.py 那个外部数据契约（这是合理的）
2. **后端单元测试**：`pytest unit_test/dao/test_yande_data_dao_downloaded_ids.py unit_test/infrastructure/test_image_cache_cleanup.py unit_test/services/test_gallery_cleanup.py unit_test/api/v1/test_preview_cleanup_routes.py -v` 23 个原测试全过 + 新增 rating=NULL 测试通过
3. **新增测试**（建议）：
   ```python
   def test_image_detail_accepts_null_rating():
       detail = ImageDetail(rating=None, ...)
       assert detail.rating is None
       
   def test_image_detail_coerces_unknown_rating():
       detail = ImageDetail(rating='x', ...)
       assert detail.rating == Rating.R15  # 兜底
       
   def test_load_gallery_with_null_rating_row():
       # INSERT 一条 rating=NULL 的 yande_data 记录
       # 调 POST /load -> 期望 200, data 含该条记录（rating 字段为 None）
   ```
4. **真实环境**（用户手动）：
   - 重启 backend
   - `curl -X POST http://localhost:8000/api/v1/gallery/load -d '{"source":"local","page":1,"page_size":20}'`
   - 期望 HTTP 200，返回 JSON `code:"0000"`

---

## 7. 不在本次范围（先记录）

- 项目级 Alembic 迁移体系（方案 C）
- 合并 next_dev 的 ORM rename（方案 D）
- 前端 Gallery.vue 对 `rating: null` 的展示兼容（虽然 B 方案后 API 返回的是 `None`，前端原 `{rating}` 会渲染成字符串 "null"，需要 `v-if="rating"` 守卫）
- image_data 表的同等 rating 防御（虽然 3034 行数据当前合规，但 nullable=True 风险持续存在）

---

## 8. 修复执行时间线（如果用户批准 A+B）

| 阶段 | 工时估算 | 步骤 |
|---|---|---|
| 修复代码 | ~20 分钟 | 改 `response/gallery.py` + 加测试 |
| 清理脏数据 | ~1 分钟 | 1 条 SQL |
| 验证 | ~10 分钟 | pytest + curl |
| commit | ~5 分钟 | 1-2 commit |
| **总计** | **~40 分钟** | |

---

**请审阅**: 选哪套方案？最推荐 A+B。
- ✅ **A+B**：组合修复（推荐）
- ⚠️ **A only**：临时止血（生产先回滚，治本做后续）
- ⚠️ **B only**：只改应用层（不动 DB，但生产 /load 仍 500）
- ❌ **C / D**：需要更大变更窗口，建议排期而非临时修

确认后我开始实施。
