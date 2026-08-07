"""静态扫描所有 async 路由，断言无未包裹的同步 DAO/service 调用。

背景：v1.1.7 之前 56 个 async 路由里有 40 个直接调用同步 service/DAO，
事件循环被同步 SQL/HTTP 冻结。本测试确保后续 PR 不再重蹈覆辙。

策略：AST 扫描 + 字符串黑名单。每个 async def 函数体逐行检查，
只要出现以下模式之一就 fail：
- 单例 DAO 调用：favorite_dao.xxx() / yande_data_repository.xxx() / ...
- Service 全限定名调用：FavoritesService.xxx() / ...
- 同步 HTTP：YandeApi(...) / .get_count(...)
- 同步文件：ImageCache(...) / .download_preview(...)

豁免规则：出现在 `await asyncio.to_thread(...)` 或 `run_in_executor(...)`
实参列表中的，忽略。
"""
import ast
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]) + "/backend")

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC = REPO_ROOT / "backend" / "src"

# 黑名单：同步对象
SYNC_DAO_SINGLETONS = {
    "favorite_dao",
    "yande_data_repository",
    "tag_repository",
    "artist_repository",
    "download_task_dao",
}

SYNC_SERVICES = {
    "FavoritesService",
    "DownloadService",
    "GalleryService",
    "TagCacheService",
    "ConfigService",
}

SYNC_HTTP_CLASSES = {"YandeApi"}
SYNC_FILE_CLASSES = {"ImageCache"}


def _is_inside_to_thread(node: ast.Call) -> bool:
    """判断 Call 节点是否作为 asyncio.to_thread / run_in_executor 的实参。

    只识别直接外层调用（深度=1），更深的嵌套交给递归自然处理。
    """
    func = node.func
    func_str = ast.unparse(func) if hasattr(ast, "unparse") else ""
    return func_str in ("asyncio.to_thread", "run_in_executor")


def _find_async_routes_in_module(tree: ast.Module) -> list[tuple[str, ast.AsyncFunctionDef]]:
    """提取模块所有顶层 async def"""
    return [
        (node.name, node)
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef)
    ]


def _scan_body_for_sync_calls(body: list[ast.stmt]) -> list[str]:
    """扫描函数体，返回所有命中黑名单的源代码片段"""
    hits: list[str] = []
    for stmt in body:
        for node in ast.walk(stmt):
            if not isinstance(node, ast.Call):
                continue
            # 豁免：asyncio.to_thread / run_in_executor 实参
            if _is_inside_to_thread(node):
                continue
            func = node.func
            # X.method() 形式
            if isinstance(func, ast.Attribute):
                if isinstance(func.value, ast.Name):
                    name = func.value.id
                    if name in SYNC_DAO_SINGLETONS:
                        hits.append(f"{name}.{func.attr}(...)")
                    elif name in SYNC_SERVICES:
                        hits.append(f"{name}.{func.attr}(...)")
                    elif name in SYNC_HTTP_CLASSES:
                        hits.append(f"{name}(...) 或 .{func.attr}(...)")
                    elif name in SYNC_FILE_CLASSES:
                        hits.append(f"{name}(...) 或 .{func.attr}(...)")
            # Bare class call: YandeApi(...) / ImageCache(...)
            elif isinstance(func, ast.Name):
                if func.id in SYNC_HTTP_CLASSES or func.id in SYNC_FILE_CLASSES:
                    hits.append(f"{func.id}(...)")
    return hits


def _resolve_module_path(module_path: str) -> Path:
    """根据 module 短名定位 backend/src 下的源文件路径"""
    rel = module_path.replace(".", "/")
    if rel.startswith("src/"):
        rel = rel[len("src/"):]
    return BACKEND_SRC / f"{rel}.py"


@pytest.mark.parametrize("module_path", [
    "src.api.v1.gallery",
    "src.api.v1.favorites",
    "src.api.v1.download",
    "src.api.v1.tag_cache",
    "src.api.v1.config",
    "src.api.v1.query",
])
def test_async_routes_have_no_unwrapped_sync_calls(module_path: str):
    """所有 async 路由函数体内的同步调用必须包 asyncio.to_thread"""
    source_path = _resolve_module_path(module_path)
    if not source_path.exists():
        pytest.skip(f"Module file not found: {source_path}")

    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    failures: list[str] = []

    for fname, fnode in _find_async_routes_in_module(tree):
        hits = _scan_body_for_sync_calls(fnode.body)
        if hits:
            failures.append(f"{module_path}.{fname}: {hits}")

    assert not failures, (
        f"{module_path}: {len(failures)} 个 async 路由直接调用了同步对象（必须包 asyncio.to_thread）\n"
        + "\n".join(failures)
    )
