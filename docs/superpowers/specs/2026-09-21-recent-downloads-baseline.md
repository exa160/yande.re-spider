# 最近下载功能 — 集成验证基线

**记录时间**：2026-09-21（改动开始前）
**环境**：仓库根 `.venv`（`../.venv/bin/python`），Python 3.12

## 后端 pytest 基线

| 运行方式 | 改动前 | 改动后 |
|---|---|---|
| `cd backend && ../.venv/bin/python -m pytest -q` | **4 failed, 168 passed** | **240 passed（0 failed）** |
| `../.venv/bin/python -m pytest unit_test -q` | 158 passed | 226 passed |
| `../.venv/bin/python -m pytest tests -q` | 14 passed | 14 passed |

### 改动前存在的 4 个失败 —— 已在本次一并修复（根因修复）

预先存在的失败用例：

- `unit_test/api/v1/test_download_states_route.py::test_states_endpoint_maps_error_to_4xx`
- `unit_test/api/v1/test_favorite_local_count_route.py::test_local_count_404_for_missing_folder`
- `unit_test/api/v1/test_favorite_online_count_ttl.py::test_route_returns_error_when_refresh_fails`
- `unit_test/api/v1/test_my_favorites_route.py::test_add_my_favorite_returns_404_for_nonexistent`

**症状**：`unit_test/` 与 `tests/` 单独跑各自全绿，全量跑才失败。报错
`TypeError: Object of type ErrMsg is not JSON serializable`。

**根因**（二分定位到 `tests/test_path_constant.py::test_path_constant_module_singleton_reflects_env`）：

1. 该用例用 `importlib.reload(constant_mod)` 让模块级 `path_constant` 单例按 env 重建。
2. `reload` **就地重建** `src.common.constant` 里的所有类，含 `ErrMsg` 枚举。
3. 其他模块（`api/v1/*.py`、`middleware/errors.py`）的 `from src.common.constant import ErrMsg`
   仍持有**旧类对象**。
4. `APIException.__init__` 用 `isinstance(err_msg, ErrMsg)` 判定 → **失配为 False** →
   走 else 分支 → `http_status` 停留在初始值 `HTTPStatus.OK`、`err_code` 退化为 `'0000'`
   → **错误响应被静默降级成 200**，`err_msg` 变成整个枚举的 repr 元组，
   最终在 JSON 序列化处抛 `ErrMsg is not JSON serializable`。

**修复**（`src/middleware/errors.py`）：把判定从「类身份」改为「值特征」，
与类身份解耦，reload 后依然成立：

```python
is_err_msg_enum = (
    not isinstance(err_msg, str)
    and hasattr(err_msg, "code") and hasattr(err_msg, "msg")
    and hasattr(err_msg, "http_status")
)
```

> 这不只是测试问题：任何运行时 `importlib.reload` 都会让错误响应降级为 200。
> 属框架级脆弱点，修复后错误状态码恢复正确。

**附带修复**：`tests/test_path_constant.py` 的 `reload_constant` 夹具增加
teardown 二次 reload，让 reload 对进程内其他模块透明。

## 前端测试

| 命令 | 改动前 | 改动后 |
|---|---|---|
| `cd frontend && npx vitest run` | 16 files / 293 tests | **17 files / 336 tests 全通过** |

## 备注

- `backend/` 下原本**没有** DAO/Service 层测试先例，本次新建
- 无 `conftest.py` / `pytest.ini`，pytest 配置为默认
- `backend/unit_test/api/v1/test_recent_downloads_route.py` 的夹具挂载了
  `ErrorHandleMiddleware.init_app(app)`，使断言状态码的用例可靠

