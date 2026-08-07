# Windows 客户端（NSIS 安装器）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把当前 FastAPI + Vue 单端口 Web 应用打包成 Windows NSIS 安装器（PyWebView + PyInstaller），用户双击安装、双击运行，免装 Python/Docker，支持 SQLite 零配置和系统托盘常驻。

**Architecture:** 三层流水线 — (1) PyInstaller 把 backend + frontend/dist 打成 `_internal/` 资源目录；(2) PyWebView 主程序启动并守护 uvicorn subprocess；(3) NSIS 安装器把产物包成 `YandeSpider-Setup-vX.Y.Z.exe`，把 SQLite 数据库和下载目录默认放在安装目录下、把 `config.yaml` 放在 `%APPDATA%\yande-spider\config\`，并提供下载路径选择向导。

**Tech Stack:** Python 3.12、FastAPI、Vue 3 (Vite)、PyWebView 5.x、pystray、Pillow、PyInstaller 6.x、NSIS 3.x、appdirs。

## 全局约束（来自 spec 与已确认决策）

- **打包形态**：NSIS 安装器（per-user 安装，免管理员权限）。原因：避免文件散落、提供卸载程序、升级友好。
- **目录隔离**：
  - 安装目录 `C:\Program Files\Yande Spider\`（只读）：`yande-spider.exe`、`_internal\`、`data\yande_data.db`、`downloads\`（默认，可改）、`uninstall.exe`、图标
  - 用户配置目录 `%APPDATA%\yande-spider\config\config.yaml`（读写，可漫游）
- **数据库**：**SQLite 零配置**默认（`database.enable=False`），MariaDB 模式保留但仅在配置 UI 内手动启用。
- **代理**：与原版一致（关闭 / 自定义 / 系统代理三态，UI 可改，热生效需重启）。
- **进程模型**：uvicorn 通过 subprocess 守护，主进程崩溃自动重启。
- **凭据红线**（AGENTS.md 红线）：
  - 打包资源内 `config.yaml` 必须 `password: ""`、`proxy_enable: False`
  - 发布前执行密钥扫描，命中真实密码立即停止
- **路径抽象**：所有运行路径走 `appdirs.user_data_dir()` + 安装目录探测；`Path(__file__)` 在 PyInstaller frozen 环境下失效，必须改写。
  - **路径读取约定**（Task 1 implementer 发现）：所有代码读"安装目录/数据/下载/日志/配置"必须通过 `path_constant.install_dir` / `path_constant.user_config_dir` / `path_constant.config_file` / `path_constant.port_file` 或 `resolve_install_dir()`，**禁止直接读 `PathConstant.base_dir`**（dev mode 等于仓库根，frozen mode 是错的开发路径）。
  - **pytest 命令约定**：所有 `pytest` 命令必须以 `cd backend && PYTHONPATH=.` 开头；裸 `cd backend && uv run pytest` 会因根 `conftest.py` 的 `from src.common.constant import path_constant` 找不到 `src` 而失败。
- **端口**：uvicorn 默认 `127.0.0.1:0`（OS 自动分配空闲端口），端口写到 `%APPDATA%\yande-spider\port`。
- **首次启动**：**不弹额外配置框**（SQLite 零配置 + 代理走 UI 设置）。NSIS 安装向导可选下载目录。
- **非范围**：跨平台（macOS/Linux）、自动更新（electron-updater 风格）、代码签名证书、Microsoft Store / MSIX、移动端 Capacitor、Cloud Sync。

---

## 文件结构总览（先于任务清单锁定）

### 新增文件
| 路径 | 职责 |
|------|------|
| `desktop/main.py` | PyWebView 启动入口；守护 uvicorn subprocess；端口发现；单实例锁 |
| `desktop/tray.py` | pystray 系统托盘（打开主界面/暂停调度/退出）；Windows 资源路径封装 |
| `desktop/single_instance.py` | 基于 `socket` + `msvcrt`/`flock` 的单实例锁（避免重复启动） |
| `desktop/icon.ico` | Windows 应用图标（用于 .exe、托盘、NSIS） |
| `desktop/version.txt` | NSIS 读取的版本号（打包时从 `AppConfig.version` 拷贝） |
| `desktop/nsis/installer.nsi` | NSIS 安装脚本（向导页面、文件安装、注册表、卸载程序） |
| `desktop/nsis/header.bmp` / `sidebar.bmp` | NSIS 向导装饰图（可选） |
| `desktop/build/build_exe.py` | PyInstaller 构建脚本（一键生成 `dist/_internal/` + `yande-spider.exe`） |
| `desktop/build/build_installer.py` | 调用 `makensis` 生成 `YandeSpider-Setup-vX.Y.Z.exe` |
| `desktop/requirements.txt` | 桌面专属依赖（pywebview、pystray、pyinstaller、appdirs、Pillow） |
| `desktop/tests/test_paths.py` | `PathConstant` 客户端模式路径解析单测 |
| `desktop/tests/test_subprocess.py` | uvicorn subprocess 启动/健康检查/重启单测 |
| `docs/superpowers/specs/2026-08-05-windows-client-design.md` | 本设计/实施文档 |

### 修改文件
| 路径 | 改动概要 |
|------|---------|
| `backend/src/common/constant.py` | `PathConstant` 增加 `install_dir`、`user_config_dir`、`port_file` 字段；`base_dir` 增加客户端探测 fallback；路径全部基于 `install_dir` / `user_config_dir` |
| `backend/service.py` | `uvicorn.run` 端口参数化（CLI/env 读取，默认 `127.0.0.1:0`） |
| `backend/src/__init__.py` | `_get_git_sha` 在 frozen 环境读取 `version.txt`，无文件时降级 `unknown`；`work_dir_setup` 创建新目录 |
| `backend/src/middleware/frontend_static.py` | 客户端模式下从 `_MEIPASS` 或 `install_dir/_internal/frontend/dist` 读取 dist |
| `backend/src/common/settings.py` | `load_config` / `save_config` 默认走 `user_config_dir/config/config.yaml`；首启写入 placeholder（`password=""`, `proxy_enable=False`） |
| `config/config.yaml`（占位符） | `password: ""`、`proxy_enable: False`（仅作为打包时的内置默认值；运行时仍以 `%APPDATA%` 配置覆盖） |
| `pyproject.toml` | 不直接改；额外依赖放 `desktop/requirements.txt` |
| `frontend/package.json` | 不改；版本号同步留给版本 bump 流程 |
| `.gitignore` | 增加 `_internal/`、`build/`、`*.exe`、`YandeSpider-Setup-*.exe` 忽略规则 |
| `README.md` | 远期计划项改写为「已规划」并指向本设计文档 |

---

## Task 1: 路径抽象层（PathConstant 客户端感知）

**Files:**
- Modify: `backend/src/common/constant.py:29-40`
- Create: `backend/src/common/path_resolver.py`
- Test: `backend/tests/test_path_resolver.py`

**Interfaces:**
- Consumes: `appdirs.user_data_dir()` 派生用户配置目录；`sys.frozen`、`sys._MEIPASS` 探测 frozen 环境
- Produces:
  - `PathConstant.install_dir: Path` — 安装目录（frozen 时取 `sys._MEIPASS` 的父目录；否则取 `base_dir`）
  - `PathConstant.user_config_dir: Path` — `%APPDATA%\yande-spider\config`（Windows）或 `~/.config/yande-spider`（其他平台，开发模式）
  - `PathConstant.port_file: Path` — `user_config_dir.parent / "port"`（同层）
  - `PathConstant.config_file: Path` — `user_config_dir / "config.yaml"`
  - 其余路径（download_dir、data_dir、log_dir）改为基于 `install_dir`

### Step 1: 写失败测试

```python
# backend/tests/test_path_resolver.py
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from src.common.path_resolver import resolve_install_dir, resolve_user_config_dir, is_frozen


def test_is_frozen_false_in_dev():
    with patch.object(sys, "frozen", "", create=True):
        assert is_frozen() is False


def test_is_frozen_true_in_pyinstaller():
    with patch.object(sys, "frozen", "true", create=True):
        with patch.object(sys, "_MEIPASS", "/tmp/_MEIPASS", create=True):
            assert is_frozen() is True


def test_resolve_install_dir_dev_mode(tmp_path):
    """开发模式：install_dir = base_dir（仓库根）"""
    fake_repo = tmp_path / "repo"
    fake_src = fake_repo / "backend" / "src" / "common"
    fake_src.mkdir(parents=True)
    fake_file = fake_src / "constant.py"
    fake_file.touch()

    with patch("src.common.path_resolver.PathConstant.base_dir", fake_repo):
        assert resolve_install_dir() == fake_repo


def test_resolve_install_dir_frozen(tmp_path):
    """PyInstaller 环境：install_dir = sys._MEIPASS 的父目录"""
    fake_mei = tmp_path / "_MEIPASS"
    fake_mei.mkdir()
    fake_exe_parent = fake_mei.parent

    with patch.object(sys, "frozen", "true", create=True):
        with patch.object(sys, "_MEIPASS", str(fake_mei), create=True):
            assert resolve_install_dir() == fake_exe_parent


def test_resolve_user_config_dir_windows(tmp_path):
    """Windows：%APPDATA%\\yande-spider"""
    fake_appdata = tmp_path / "AppData" / "Roaming"
    with patch("os.name", "nt"):
        with patch.dict(os.environ, {"APPDATA": str(fake_appdata)}):
            result = resolve_user_config_dir()
            assert result == fake_appdata / "yande-spider"


def test_resolve_user_config_dir_posix(tmp_path):
    """POSIX 开发模式：~/.config/yande-spider"""
    fake_home = tmp_path / "home"
    with patch("os.name", "posix"):
        with patch.dict(os.environ, {"HOME": str(fake_home)}):
            result = resolve_user_config_dir()
            assert result == fake_home / ".config" / "yande-spider"
```

### Step 2: 运行测试确认失败

Run:
```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_path_resolver.py -v
```
Expected: FAIL `ModuleNotFoundError: No module named 'src.common.path_resolver'`

### Step 3: 实现 `path_resolver.py`

```python
# backend/src/common/path_resolver.py
"""客户端/开发模式路径解析。

核心规则：
- 开发模式（未 freeze）：install_dir = 仓库根；user_config_dir = ~/.config/yande-spider
- PyInstaller frozen：install_dir = sys._MEIPASS 父目录（即 _internal/ 的上一层）
- 客户端配置（config.yaml）始终在 user_config_dir 下；其余数据/下载在 install_dir 下
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


_APP_NAME = "yande-spider"


def is_frozen() -> bool:
    """是否处于 PyInstaller frozen 环境。"""
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


def resolve_install_dir() -> Path:
    """安装目录。

    - 开发模式：PathConstant.base_dir（即仓库根）
    - PyInstaller frozen：sys._MEIPASS 的父目录（C:\\Program Files\\Yande Spider\\）
    """
    if is_frozen():
        return Path(sys._MEIPASS).resolve().parent
    from src.common.constant import PathConstant
    return PathConstant.base_dir


def resolve_user_config_dir() -> Path:
    """用户配置目录（持久、可漫游）。

    - Windows: %APPDATA%\\yande-spider
    - POSIX 开发模式: ~/.config/yande-spider
    """
    if os.name == "nt":
        appdata = os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))
        return Path(appdata) / _APP_NAME
    return Path.home() / ".config" / _APP_NAME
```

### Step 4: 修改 `PathConstant` 注入新字段

```python
# backend/src/common/constant.py:29-40
from src.common.path_resolver import resolve_install_dir, resolve_user_config_dir


class PathConstant(ConstantModel):
    # 客户端感知：动态计算
    install_dir: Path = Path(__file__).parent.parent.parent
    user_config_dir: Path = Path.home() / ".config" / "yande-spider"

    # 数据/下载/日志：跟随安装目录
    download_dir: Path = install_dir / "downloads"
    previews_dir: Path = download_dir / "previews"
    originals_dir: Path = download_dir / "originals"
    data_dir: Path = install_dir / "data"
    sqlite_file: Path = data_dir / "yande_data.db"
    log_dir: Path = install_dir / "logs"

    # 配置：用户目录
    config_dir: Path = user_config_dir / "config"
    config_file: Path = config_dir / "config.yaml"

    # 端口文件：与 config 同层
    port_file: Path = user_config_dir / "port"

    # 前端 dist：frozen 时在 _internal/frontend/dist，dev 时在仓库 frontend/dist
    frontend_dist: Path = install_dir / "frontend" / "dist"


# 冻结后用解析函数覆盖（避免 pydantic frozen 限制，使用 module-level 单例）
def _resolve_paths() -> None:
    """在模块导入后被 init_app 调用，把动态解析值写入全局单例。"""
    install = resolve_install_dir()
    user_cfg = resolve_user_config_dir()
    global path_constant
    path_constant = PathConstant(
        install_dir=install,
        user_config_dir=user_cfg,
        download_dir=install / "downloads",
        previews_dir=install / "downloads" / "previews",
        originals_dir=install / "downloads" / "originals",
        data_dir=install / "data",
        sqlite_file=install / "data" / "yande_data.db",
        log_dir=install / "logs",
        config_dir=user_cfg / "config",
        config_file=user_cfg / "config" / "config.yaml",
        port_file=user_cfg / "port",
        frontend_dist=install / "frontend" / "dist",
    )


path_constant = PathConstant()  # 默认值；init_app 时会被覆盖
```

### Step 5: 在 `init_app` 调用 `_resolve_paths`

```python
# backend/src/__init__.py 顶部追加
from src.common.constant import _resolve_paths, path_constant  # 同时在 __init__.py 重新导出 _resolve_paths，供 service.py 复用
__all__ = ["init_app", "app_config", "path_constant", "_resolve_paths"]

def init_app(app: FastAPI) -> FastAPI:
    _resolve_paths()  # 必须在任何中间件读 path_constant 之前
    app.add_middleware(...)  # 既有代码
    work_dir_setup()  # 既有代码
    ...
```

### Step 6: 运行全部测试确认通过

Run:
```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_path_resolver.py -v
cd backend && PYTHONPATH=. uv run pytest tests/ -v  # 确保无回归
```
Expected: 全部 PASS

### Step 7: 手动验证（开发模式）

```bash
cd backend && uv run uvicorn service:main_app --port 8000
# 期望 banner 打印 Data dir = <repo>/data, Log dir = <repo>/logs
# （开发模式 install_dir = 仓库根）
```
Expected: banner 输出仓库根下的目录，未崩溃。

### Step 8: 手动验证（frozen 模拟）

```bash
cd backend && uv run python -c "
import sys
sys.frozen = True
sys._MEIPASS = '/tmp/_MEIPASS_TEST/_internal'
from src.common.path_resolver import resolve_install_dir
print(resolve_install_dir())  # 应输出 /tmp/_MEIPASS_TEST
"
```
Expected: 输出 `/tmp/_MEIPASS_TEST`。

### Step 9: Commit

```bash
git add backend/src/common/constant.py backend/src/common/path_resolver.py \
  backend/src/__init__.py backend/tests/test_path_resolver.py
git commit -m "feat(client): path abstraction layer for client-aware PathConstant"
```

---

## Task 2: uvicorn 端口参数化 + 端口文件协议

**Files:**
- Modify: `backend/service.py`
- Modify: `backend/src/__init__.py`
- Create: `backend/src/common/port_manager.py`
- Test: `backend/tests/test_port_manager.py`

**Interfaces:**
- Produces: `write_port_file(port: int)` / `read_port_file() -> int | None` / `find_free_port() -> int`
- Consumes: `path_constant.port_file`

### Step 1: 写失败测试

```python
# backend/tests/test_port_manager.py
import socket
from pathlib import Path

from src.common.port_manager import find_free_port, write_port_file, read_port_file


def test_find_free_port_returns_int():
    port = find_free_port()
    assert isinstance(port, int)
    assert 1024 < port < 65536


def test_port_file_roundtrip(tmp_path):
    port_file = tmp_path / "port"
    write_port_file(port_file, 12345)
    assert read_port_file(port_file) == 12345


def test_read_port_file_missing(tmp_path):
    assert read_port_file(tmp_path / "missing") is None


def test_read_port_file_corrupted(tmp_path):
    port_file = tmp_path / "port"
    port_file.write_text("not a number")
    assert read_port_file(port_file) is None
```

### Step 2: 运行测试确认失败

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_port_manager.py -v
```
Expected: FAIL `ModuleNotFoundError: No module named 'src.common.port_manager'`

### Step 3: 实现 `port_manager.py`

```python
# backend/src/common/port_manager.py
"""uvicorn 端口发现与端口文件协议。

PyWebView 主进程启动 uvicorn subprocess 时：
1. 主进程 find_free_port() → 端口号
2. 主进程 write_port_file(port_file, port)  → %APPDATA%/yande-spider/port
3. 启动 uvicorn subprocess，参数 --port <port>
4. uvicorn 健康检查通过后，主进程从 port_file 读端口，构造 PyWebView URL

uvicorn 自己不需要写端口文件（subprocess 启动参数已明确），但提供 helper
供测试和未来场景使用。
"""
from __future__ import annotations

import socket
from pathlib import Path
from typing import Optional


def find_free_port() -> int:
    """让 OS 分配一个空闲端口。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def write_port_file(port_file: Path, port: int) -> None:
    """写入端口号到端口文件。原子写：先临时文件后 rename。"""
    port_file.parent.mkdir(parents=True, exist_ok=True)
    tmp = port_file.with_suffix(port_file.suffix + ".tmp")
    tmp.write_text(str(port), encoding="utf-8")
    tmp.replace(port_file)


def read_port_file(port_file: Path) -> Optional[int]:
    """读取端口号。文件不存在或内容无效返回 None。"""
    if not port_file.exists():
        return None
    try:
        return int(port_file.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        return None
```

### Step 4: 修改 `service.py` 支持 CLI/env 端口

```python
# backend/service.py
import os
import sys

import uvicorn
from fastapi import FastAPI

from src import init_app, app_config, _resolve_paths

if "uvicorn" in sys.argv[0]:
    _resolve_paths()  # frozen 环境必须先解析路径
    main_app = FastAPI(**app_config.model_dump())
    init_app(main_app)


if __name__ == "__main__":
    _resolve_paths()
    main_app = FastAPI(docs_url="/docs", redoc_url="/redoc")
    main_app = init_app(main_app)
    host = os.environ.get("YANDE_HOST", "127.0.0.1")
    port = int(os.environ.get("YANDE_PORT", "0"))  # 0 = OS 自动分配
    uvicorn.run(main_app, host=host, port=port)
```

### Step 5: 运行测试确认通过

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_port_manager.py -v
```
Expected: PASS

### Step 6: 手动验证

```bash
cd backend && YANDE_PORT=0 uv run python service.py
# 期望：uvicorn 启动并打印 "Uvicorn running on http://127.0.0.1:<随机端口>"
```
Expected: 进程不退出，端口为随机空闲端口。

### Step 7: Commit

```bash
git add backend/service.py backend/src/common/port_manager.py backend/tests/test_port_manager.py
git commit -m "feat(client): uvicorn port parametrization + port file protocol"
```

---

## Task 3: `frontend_dist` frozen 适配 + `version.txt` 注入

**Files:**
- Modify: `backend/src/middleware/frontend_static.py:14-24`
- Modify: `backend/src/__init__.py:35-49`
- Create: `backend/src/__version__.py`
- Test: `backend/tests/test_frontend_dist_resolver.py`

### Step 1: 写失败测试

```python
# backend/tests/test_frontend_dist_resolver.py
from pathlib import Path
from unittest.mock import patch

from src.middleware.frontend_static import resolve_frontend_dist


def test_resolve_frontend_dist_dev_mode():
    fake = Path("/repo/frontend/dist")
    with patch("src.middleware.frontend_static.path_constant") as mock_pc:
        mock_pc.frontend_dist = fake
        assert resolve_frontend_dist() == fake


def test_resolve_frontend_dist_frozen():
    """frozen 时从 _MEIPASS/_internal/frontend/dist 读取。"""
    with patch("sys.frozen", "true", create=True):
        with patch("sys._MEIPASS", "/install/_internal", create=True):
            result = resolve_frontend_dist()
            assert result == Path("/install/_internal/frontend/dist")
```

### Step 2: 运行测试确认失败

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_frontend_dist_resolver.py -v
```
Expected: FAIL `ImportError`

### Step 3: 实现 frontend_dist 解析

```python
# backend/src/middleware/frontend_static.py
import sys
from pathlib import Path

from fastapi import FastAPI
from loguru import logger
from starlette.responses import FileResponse
from starlette.staticfiles import StaticFiles

from src import path_constant
from src.common.constant import ErrMsg
from src.middleware.errors import APIException
from src.models.response.base_response import BaseResponse


def resolve_frontend_dist() -> Path:
    """解析前端 dist 路径：
    - frozen: sys._MEIPASS/frontend/dist
    - dev: path_constant.frontend_dist
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "frontend" / "dist"
    return path_constant.frontend_dist


class FrontendStaticLoader:
    @staticmethod
    def init_app(app: FastAPI) -> None:
        frontend_dist = resolve_frontend_dist()
        if not frontend_dist.exists():
            logger.info(f"No frontend file found at {frontend_dist}.")
            return

        logger.info(f"Frontend file load: {frontend_dist}")
        assets_dir = frontend_dist / "assets"
        if assets_dir.exists():
            app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")
        app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="root")
        logger.info("WebServer application initialized for web server")

        @app.get("/health", tags=["系统"])
        async def health_check():
            return BaseResponse()

        @app.get("/{path:path}", include_in_schema=False)
        async def serve_spa(path: str):
            index_path = frontend_dist / "index.html"
            if index_path.exists():
                return FileResponse(index_path)
            raise APIException(ErrMsg.NOT_FOUND_ERROR)
```

### Step 4: 修改 `_get_git_sha` 支持 frozen 读 `version.txt`

```python
# backend/src/__init__.py:35-49
import shutil
import subprocess
import sys
from pathlib import Path


def _get_git_sha() -> str:
    """获取当前 git commit short SHA。

    优先级：
    1. frozen 环境：读取 _MEIPASS/version.txt（NSIS 打包时注入）
    2. 开发模式：subprocess 调用 git rev-parse
    3. 都不可用：返回 "unknown"
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        version_txt = Path(sys._MEIPASS) / "version.txt"
        if version_txt.exists():
            return version_txt.read_text(encoding="utf-8").strip() or "unknown"
    if not shutil.which("git"):
        return "unknown"
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=2, check=False,
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"
    except Exception:
        return "unknown"
```

### Step 5: 添加 `__version__.py`

```python
# backend/src/__version__.py
"""单一版本源。NSIS 打包时把此版本号写入 desktop/version.txt（同时也作为 banner 显示）。"""
__version__ = "1.1.9"
```

### Step 6: 运行测试确认通过

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_frontend_dist_resolver.py -v
cd backend && PYTHONPATH=. uv run pytest tests/ -v  # 无回归
```
Expected: 全部 PASS

### Step 7: Commit

```bash
git add backend/src/middleware/frontend_static.py backend/src/__init__.py \
  backend/src/__version__.py backend/tests/test_frontend_dist_resolver.py
git commit -m "feat(client): frontend_dist frozen resolver + version.txt injection"
```

---

## Task 4: 配置模块用户目录化 + 打包 placeholder

**Files:**
- Modify: `backend/src/common/settings.py:104-128`
- Modify: `config/config.yaml`（打包专用 placeholder）
- Create: `backend/src/common/config_bootstrap.py`
- Test: `backend/tests/test_config_bootstrap.py`

### Step 1: 写失败测试

```python
# backend/tests/test_config_bootstrap.py
from pathlib import Path

from src.common.config_bootstrap import write_default_user_config


def test_write_default_user_config_creates_file(tmp_path):
    target = tmp_path / "config.yaml"
    write_default_user_config(target)
    content = target.read_text(encoding="utf-8")
    assert "password: ''" in content
    assert "proxy_enable: false" in content
    assert "yande_api" in content
    assert "downloader" in content


def test_write_default_user_config_idempotent(tmp_path):
    """已存在时不覆盖（保留用户修改）。"""
    target = tmp_path / "config.yaml"
    target.write_text("database:\n  enable: true\n", encoding="utf-8")
    write_default_user_config(target)
    assert target.read_text(encoding="utf-8") == "database:\n  enable: true\n"
```

### Step 2: 运行测试确认失败

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_config_bootstrap.py -v
```
Expected: FAIL `ModuleNotFoundError`

### Step 3: 实现 `config_bootstrap.py`

```python
# backend/src/common/config_bootstrap.py
"""用户配置首次写入。

首启行为：
- 用户配置目录不存在 → 创建目录并写入 placeholder（password='', proxy_enable=False）
- 文件已存在 → 不覆盖（保留用户修改）

打包内置的 config/config.yaml 永远是 placeholder（不入 git 敏感数据）。
"""
from __future__ import annotations

from pathlib import Path

import yaml
from loguru import logger
from pydantic import SecretStr

from src.common.settings import Config, DatabaseConfig, ApiConfig, DownloaderConfig, SchedulerConfig


DEFAULT_PLACEHOLDER_YAML = """\
# 默认配置（首启生成）。请通过 UI 修改，敏感字段请勿手改。
database:
  enable: false
  host: localhost
  port: 3306
  user: root
  password: ''
  schema_name: Pictures
yande_api:
  proxy_enable: false
  timeout: 30
  retry: 3
  proxies:
    http: ''
    https: ''
downloader:
  thread_num: 4
  max_concurrent_tasks: 3
  chunk_size: 10240
  split_size: 52428800
  retry_times: 3
scheduler:
  max_concurrent_schedules: 2
  max_images_per_run_default: 800
  per_page_limit: 100
app:
  debug: false
"""


def write_default_user_config(target: Path) -> None:
    """写入默认配置到目标路径。已存在则跳过。"""
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        logger.info(f"Config already exists at {target}, skip bootstrap.")
        return
    target.write_text(DEFAULT_PLACEHOLDER_YAML, encoding="utf-8")
    logger.info(f"Default config written to {target}.")
```

### Step 4: 在 `load_config` 中调用 bootstrap

```python
# backend/src/common/settings.py:104-115
def load_config(config_path: Path = Path("config.yaml")) -> Config:
    # 首启生成 placeholder
    from src.common.config_bootstrap import write_default_user_config
    write_default_user_config(config_path)

    if config_path.exists():
        try:
            data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            if data is None:
                data = {}
            return Config.model_validate(data)
        except Exception as e:
            logger.warning(f"load config err: {e}")

    default_config = Config()
    save_config(default_config, config_path)
    return default_config
```

### Step 5: 替换打包专用 `config/config.yaml`

```yaml
# config/config.yaml（打包专用 placeholder，远端仓库内此文件**不包含任何真实凭据**）
# 真实运行时配置从 %APPDATA%\yande-spider\config\config.yaml 读取；此文件仅在 PyInstaller frozen 资源中作为兜底
database:
  enable: false
  host: localhost
  port: 3306
  user: root
  password: ""
  schema_name: Pictures
yande_api:
  proxy_enable: false
  timeout: 30
  retry: 3
  proxies:
    http: ""
    https: ""
downloader:
  thread_num: 4
  max_concurrent_tasks: 3
  chunk_size: 10240
  split_size: 52428800
  retry_times: 3
scheduler:
  max_concurrent_schedules: 2
  max_images_per_run_default: 800
  per_page_limit: 100
app:
  debug: false
```

### Step 6: 运行测试确认通过

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_config_bootstrap.py -v
cd backend && PYTHONPATH=. uv run pytest tests/ -v  # 无回归
```
Expected: 全部 PASS

### Step 7: 凭据扫描（强制）

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev
git diff origin/next..HEAD -- config/config.yaml \
  | grep -iE '(password|secret|token|api[_-]?key)\s*[:=]\s*["\x27][^"\x27]+["\x27]' \
  | grep -vE '""|null|<YOUR_|<CHANGE_'
# 期望：无输出
```

### Step 8: Commit

```bash
git add backend/src/common/settings.py backend/src/common/config_bootstrap.py \
  backend/tests/test_config_bootstrap.py config/config.yaml
git commit -m "feat(client): config bootstrap with safe placeholder + frozen resource defaults"
```

---

## Task 5: 下载器预分配降级 + 50MB 提示

**Files:**
- Modify: `backend/src/infrastructure/downloader.py:142-192`
- Test: `backend/tests/test_downloader_fallocate.py`

### Step 1: 写失败测试

```python
# backend/tests/test_downloader_fallocate.py
from pathlib import Path

from src.infrastructure.downloader import file_writer


def test_file_writer_fallback_on_disk_full(tmp_path, monkeypatch):
    """磁盘不足时降级为流式写入，不抛 IOError。"""
    target = tmp_path / "out.bin"

    def fake_seek(*args, **kwargs):
        raise OSError("No space left on device")

    monkeypatch.setattr(Path, "seek", fake_seek)

    chunks = [b"hello", b"world"]
    file_writer(str(target), chunks, file_size=1024 * 1024 * 1024)  # 1GB 请求
    # 期望：文件存在，size > 0，未抛异常
    assert target.exists()
    assert target.stat().st_size >= len(b"helloworld")
```

### Step 2: 运行测试确认失败

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_downloader_fallocate.py -v
```
Expected: FAIL `OSError: No space left on device`

### Step 3: 修改 `file_writer` 预分配降级

```python
# backend/src/infrastructure/downloader.py (替换 142-192 行的预分配逻辑)
def _try_preallocate(target: Path, file_size: int) -> bool:
    """预分配整个文件以减少磁盘碎片。失败时返回 False（降级为流式）。"""
    try:
        with target.open("wb") as f:
            f.seek(file_size - 1)
            f.write(CommonConstant.file_write_placeholder)
        return True
    except OSError as e:
        logger.warning(
            f"Preallocate {file_size} bytes for {target} failed: {e}. "
            "Falling back to streaming write."
        )
        return False


def file_writer(file_path: str, chunks: list[bytes], file_size: int) -> None:
    target = Path(file_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lock = FileLock(str(target) + ".lock")

    with lock:
        preallocated = _try_preallocate(target, file_size)
        if not preallocated:
            # 降级：流式拼接 chunks
            with target.open("wb") as f:
                for chunk in chunks:
                    f.write(chunk)
            logger.info(f"Streamed write complete: {target} ({target.stat().st_size} bytes)")
            return

        # 预分配成功：用 Range 写入对应切片
        with target.open("r+b") as f:
            offset = 0
            for chunk in chunks:
                f.seek(offset)
                f.write(chunk)
                offset += len(chunk)
```

### Step 4: 运行测试确认通过

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_downloader_fallocate.py -v
```
Expected: PASS

### Step 5: Commit

```bash
git add backend/src/infrastructure/downloader.py backend/tests/test_downloader_fallocate.py
git commit -m "feat(client): downloader preallocate fallback for low-disk environments"
```

---

## Task 6: PyWebView 启动器（桌面入口）

**Files:**
- Create: `desktop/main.py`
- Create: `desktop/single_instance.py`
- Create: `desktop/tray.py`
- Create: `desktop/icon.ico`（占位 16x16 ICO，NSIS 阶段替换为正式图标）
- Create: `desktop/tests/test_main.py`

### Step 1: 写失败测试（subprocess 启动）

```python
# desktop/tests/test_main.py
import time
from pathlib import Path

import requests

from desktop.main import wait_for_health


def test_wait_for_health_success(tmp_path):
    """健康检查在超时内成功。"""
    port_file = tmp_path / "port"
    port_file.write_text("18000", encoding="utf-8")  # 假设 18000 上有服务（测试中 mock）

    # 用一个临时 http server mock /health
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, *args, **kwargs):
            pass

    server = HTTPServer(("127.0.0.1", 18000), Handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()

    try:
        result = wait_for_health(port_file, timeout=3.0)
        assert result is True
    finally:
        server.shutdown()


def test_wait_for_health_timeout(tmp_path):
    """健康检查超时返回 False。"""
    port_file = tmp_path / "port"
    port_file.write_text("1", encoding="utf-8")  # 端口 1 几乎不会监听
    result = wait_for_health(port_file, timeout=1.0)
    assert result is False
```

### Step 2: 运行测试确认失败

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev
uv run --with pytest pytest desktop/tests/test_main.py -v
```
Expected: FAIL `ModuleNotFoundError: No module named 'desktop.main'`

### Step 3: 实现 `desktop/single_instance.py`

```python
# desktop/single_instance.py
"""Windows 单实例锁（避免重复启动托盘）。"""
import socket
from pathlib import Path


class SingleInstanceError(RuntimeError):
    pass


def acquire_lock(lock_port: int = 47299) -> socket.socket:
    """尝试绑定 lock_port；失败说明已有实例在运行。"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(("127.0.0.1", lock_port))
        sock.listen(1)
        return sock
    except OSError as e:
        sock.close()
        raise SingleInstanceError(
            f"Another instance is already running (lock port {lock_port} busy)."
        ) from e
```

### Step 4: 实现 `desktop/tray.py`

```python
# desktop/tray.py
"""系统托盘（pystray）。"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable, Optional

import webview
from loguru import logger
from pystray import Icon, Menu, MenuItem
from PIL import Image


class SystemTray:
    def __init__(
        self,
        icon_path: Path,
        title: str,
        url: str,
        on_quit: Callable[[], None],
        window: Optional[webview.Window] = None,
    ):
        self.icon_path = icon_path
        self.title = title
        self.url = url
        self.on_quit = on_quit
        self.window = window
        self._icon: Optional[Icon] = None
        self._thread: Optional[threading.Thread] = None

    def _show_window(self) -> None:
        if self.window:
            try:
                self.window.show()
            except Exception as e:
                logger.warning(f"Show window failed: {e}")

    def _open_browser(self) -> None:
        import webbrowser
        webbrowser.open(self.url)

    def _quit(self) -> None:
        self.on_quit()
        if self._icon:
            self._icon.stop()

    def start(self) -> None:
        image = Image.open(self.icon_path)
        menu = Menu(
            MenuItem("打开主界面", self._show_window, default=True),
            MenuItem("浏览器打开", self._open_browser),
            MenuItem("退出", self._quit),
        )
        self._icon = Icon(self.title, image, self.title, menu)
        self._thread = threading.Thread(target=self._icon.run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._icon:
            self._icon.stop()
```

### Step 5: 实现 `desktop/main.py`

```python
# desktop/main.py
"""PyWebView 主入口。

启动序列：
1. 单实例锁
2. 加载 icon
3. 启动 uvicorn subprocess（注入 YANDE_PORT 环境变量）
4. 等待 /health 通过
5. 创建 PyWebView 窗口加载 http://127.0.0.1:<port>/
6. 启动系统托盘
7. 阻塞运行
8. 退出：关闭托盘 → 终止 subprocess
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

import requests
import webview
from loguru import logger

from desktop.paths import get_install_dir, get_user_config_dir, get_icon_path
from desktop.single_instance import SingleInstanceError, acquire_lock
from desktop.tray import SystemTray


HEALTH_TIMEOUT = 30.0
HEALTH_INTERVAL = 0.2


def wait_for_health(port_file: Path, timeout: float = HEALTH_TIMEOUT) -> bool:
    """阻塞等待 uvicorn /health 通过。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if port_file.exists():
            try:
                port = int(port_file.read_text(encoding="utf-8").strip())
                resp = requests.get(f"http://127.0.0.1:{port}/health", timeout=1.0)
                if resp.status_code == 200:
                    logger.info(f"Health check passed on port {port}")
                    return True
            except (ValueError, requests.RequestException):
                pass
        time.sleep(HEALTH_INTERVAL)
    return False


def start_uvicorn_subprocess(install_dir: Path) -> subprocess.Popen:
    """启动 uvicorn subprocess，端口由 OS 分配。"""
    env = os.environ.copy()
    env["YANDE_HOST"] = "127.0.0.1"
    env["YANDE_PORT"] = "0"  # OS auto-allocate
    env["PYTHONPATH"] = str(install_dir / "_internal" / "backend")

    if getattr(sys, "frozen", False):
        # frozen: yande-spider.exe 与 _internal/ 同级，python 解释器在 _internal/python.exe
        python_exe = install_dir / "_internal" / "python.exe"
        service_module = "service"
        cwd = install_dir / "_internal" / "backend"
    else:
        python_exe = sys.executable
        service_module = "service"
        cwd = Path(__file__).resolve().parent.parent / "backend"

    cmd = [str(python_exe), "-m", "uvicorn", f"{service_module}:main_app"]
    logger.info(f"Starting uvicorn: {cmd} (cwd={cwd})")
    return subprocess.Popen(
        cmd,
        cwd=str(cwd),
        env=env,
        stdout=subprocess.DEVNULL,  # 由 loguru 接管；这里只关心进程存活
        stderr=subprocess.PIPE,
    )


def main() -> int:
    # 1. 单实例
    try:
        lock = acquire_lock()
    except SingleInstanceError as e:
        logger.error(str(e))
        return 1

    install_dir = get_install_dir()
    user_config_dir = get_user_config_dir()
    user_config_dir.mkdir(parents=True, exist_ok=True)
    port_file = user_config_dir / "port"

    # 2. 启动 uvicorn
    proc = start_uvicorn_subprocess(install_dir)

    # 3. 等待健康检查
    if not wait_for_health(port_file):
        logger.error("Uvicorn failed to start within timeout.")
        proc.terminate()
        return 2

    port = int(port_file.read_text(encoding="utf-8").strip())
    url = f"http://127.0.0.1:{port}"

    # 4. PyWebView 窗口
    icon_path = get_icon_path(install_dir)
    window = webview.create_window(
        title="Yande Spider",
        url=url,
        width=1280,
        height=800,
        resizable=True,
    )

    # 5. 退出回调
    def on_closing() -> None:
        logger.info("PyWebView closing, terminating uvicorn.")
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

    window.events.closing += on_closing

    # 6. 启动系统托盘（PyWebView 启动后）
    def run_webview() -> None:
        webview.start()

    tray: Optional[SystemTray] = None

    def on_tray_quit() -> None:
        window.destroy()

    try:
        tray = SystemTray(
            icon_path=icon_path,
            title="Yande Spider",
            url=url,
            on_quit=on_tray_quit,
            window=window,
        )
        tray.start()
        run_webview()
    finally:
        if tray:
            tray.stop()
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()

    return 0


if __name__ == "__main__":
    signal.signal(signal.SIGINT, lambda *_: sys.exit(0))
    sys.exit(main())
```

### Step 6: 实现 `desktop/paths.py`

```python
# desktop/paths.py
"""桌面端路径解析（独立于 backend，避免循环依赖）。"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def get_install_dir() -> Path:
    """安装目录。frozen 时取 sys._MEIPASS 父目录。"""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS).resolve().parent
    return Path(__file__).resolve().parent.parent


def get_user_config_dir() -> Path:
    """用户配置目录。Windows: %APPDATA%/yande-spider。"""
    if os.name == "nt":
        appdata = os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))
        return Path(appdata) / "yande-spider"
    return Path.home() / ".config" / "yande-spider"


def get_icon_path(install_dir: Path) -> Path:
    """图标路径。"""
    if getattr(sys, "frozen", False):
        return install_dir / "_internal" / "desktop" / "icon.ico"
    return Path(__file__).resolve().parent / "icon.ico"
```

### Step 7: 运行测试确认通过

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev
uv run --with pytest --with requests --with pywebview --with pystray \
  pytest desktop/tests/test_main.py -v
```
Expected: PASS

### Step 8: 开发模式手动验证

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev
# 终端 1：先手动启动 uvicorn 模拟 frozen 行为
cd backend && YANDE_PORT=0 uv run python service.py &
# 终端 2：等 uvicorn 启动后，写入端口文件模拟 main 行为
uv run --with pywebview --with pystray python -c "
from pathlib import Path
from desktop.main import wait_for_health
wait_for_health(Path.home() / '.config' / 'yande-spider' / 'port', timeout=5.0)
"
```
Expected: 子进程运行不崩溃。

### Step 9: Commit

```bash
git add desktop/main.py desktop/paths.py desktop/single_instance.py \
  desktop/tray.py desktop/icon.ico desktop/tests/test_main.py
git commit -m "feat(client): PyWebView launcher with subprocess guardian and system tray"
```

---

## Task 7: PyInstaller 构建脚本

**Files:**
- Create: `desktop/build/build_exe.py`
- Create: `desktop/yande-spider.spec`（可选，build_exe.py 生成）
- Create: `desktop/requirements.txt`

### Step 1: 写 `requirements.txt`

```text
# desktop/requirements.txt
pywebview>=5.7,<6
pystray>=0.19.5
appdirs>=1.4.4
Pillow>=10.0.0
pyinstaller>=6.0
pywin32>=306; sys_platform == "win32"
```

### Step 2: 写 `build_exe.py`

```python
# desktop/build/build_exe.py
"""PyInstaller 构建脚本。

运行：
    cd /home/exa160/opencode/yande.re-spider-next-dev
    uv run --with pyinstaller python desktop/build/build_exe.py

产出（PyInstaller 默认 dist/）：
    dist/yande-spider/_internal/
        backend/                  # 整个后端源码
        desktop/                  # 桌面入口与托盘
        frontend/dist/            # Vite 构建产物
        version.txt               # 当前版本号
        python.exe                # PyInstaller 嵌入的 Python 解释器
        ...
    dist/yande-spider/yande-spider.exe
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BUILD_DIR = REPO_ROOT / "desktop" / "build"
DIST_DIR = REPO_ROOT / "dist"


def build_frontend() -> None:
    """先构建前端（如果 dist 不存在或过期）。"""
    frontend_dist = REPO_ROOT / "frontend" / "dist"
    if frontend_dist.exists():
        print(f"Frontend dist already exists at {frontend_dist}, skipping build.")
        return
    print("Building frontend...")
    subprocess.run(
        ["npm", "run", "build"],
        cwd=str(REPO_ROOT / "frontend"),
        check=True,
    )


def write_version_file() -> Path:
    """把 AppConfig.version 写入 desktop/version.txt（frozen 环境读取用）。"""
    version_file = BUILD_DIR / "version.txt"
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    # 从 AppConfig 读取
    sys.path.insert(0, str(REPO_ROOT / "backend"))
    from src import app_config  # noqa: E402
    version_file.write_text(app_config.version, encoding="utf-8")
    print(f"Version file written: {version_file} ({app_config.version})")
    return version_file


def clean_dist() -> None:
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
    print(f"Cleaned {DIST_DIR}")


def run_pyinstaller(version_file: Path) -> None:
    """调用 PyInstaller。"""
    entry = REPO_ROOT / "desktop" / "main.py"
    spec_args = [
        "--noconfirm",
        "--name=yande-spider",
        "--onedir",  # NSIS 安装器打包友好（不用 onefile，体积更小、启动更快）
        "--windowed",  # 无控制台窗口
        f"--add-data={REPO_ROOT / 'frontend' / 'dist'};frontend/dist",
        f"--add-data={version_file};.",
        f"--add-data={REPO_ROOT / 'backend'};backend",
        f"--add-data={REPO_ROOT / 'config' / 'config.yaml'};config",
        f"--add-data={REPO_ROOT / 'desktop' / 'icon.ico'};desktop",
        "--hidden-import=uvicorn",
        "--hidden-import=uvicorn.logging",
        "--hidden-import=uvicorn.loops",
        "--hidden-import=uvicorn.loops.auto",
        "--hidden-import=uvicorn.protocols",
        "--hidden-import=uvicorn.protocols.http",
        "--hidden-import=uvicorn.protocols.http.auto",
        "--hidden-import=uvicorn.protocols.websockets",
        "--hidden-import=uvicorn.protocols.websockets.auto",
        "--hidden-import=uvicorn.lifespan",
        "--hidden-import=uvicorn.lifespan.on",
        "--hidden-import=sqlalchemy.dialects.sqlite",
        "--hidden-import=apscheduler.jobstores.sqlalchemy",
        "--collect-all=loguru",
        "--collect-all=pystray",
        str(entry),
    ]

    print("Running PyInstaller...")
    subprocess.run(
        ["pyinstaller", *spec_args],
        cwd=str(REPO_ROOT),
        check=True,
    )


def main() -> None:
    build_frontend()
    version_file = write_version_file()
    clean_dist()
    run_pyinstaller(version_file)
    print(f"Build complete. Output: {DIST_DIR / 'yande-spider'}")


if __name__ == "__main__":
    main()
```

### Step 3: 在干净 Windows VM 跑构建（手动）

> **说明**：PyInstaller 不支持跨平台交叉编译，必须在 Windows 上运行。

```cmd
:: Windows PowerShell
cd C:\path\to\yande.re-spider-next-dev
uv sync
cd frontend && npm install && npm run build && cd ..
python desktop\build\build_exe.py
:: 期望：dist\yande-spider\_internal\ 与 dist\yande-spider\yande-spider.exe 生成
```

Expected: `dist\yande-spider\yande-spider.exe` 存在；双击能弹窗（即使端口冲突也会快速退出）。

### Step 4: Commit

```bash
git add desktop/build/build_exe.py desktop/requirements.txt
git commit -m "feat(client): PyInstaller build script for Windows onedir distribution"
```

---

## Task 8: NSIS 安装器脚本

**Files:**
- Create: `desktop/nsis/installer.nsi`
- Create: `desktop/nsis/header.bmp`（150x57 占位，可后续替换）
- Create: `desktop/nsis/sidebar.bmp`（164x314 占位）
- Create: `desktop/build/build_installer.py`

### Step 1: 写 `installer.nsi`

```nsis
; desktop/nsis/installer.nsi
; NSIS 安装脚本 - Yande Spider

!include "MUI2.nsh"
!include "FileFunc.nsh"
!include "x64.nsh"

!define APP_NAME "Yande Spider"
!define APP_EXE "yande-spider.exe"
!define APP_UNINSTALL "uninstall.exe"
!define APP_VERSION "1.1.9"
!define APP_PUBLISHER "exa160"
!define APP_COPYRIGHT "MIT License"
!define MUI_ABORTWARNING

; 默认安装目录（per-user，无需管理员）
InstallDir "$LOCALAPPDATA\Programs\${APP_NAME}"
InstallDirRegKey HKCU "Software\${APP_NAME}" "InstallDir"

Name "${APP_NAME} ${APP_VERSION}"
OutFile "YandeSpider-Setup-v${APP_VERSION}.exe"
RequestExecutionLevel user

; MUI 设置
!define MUI_HEADERIMAGE
!define MUI_HEADERIMAGE_BITMAP "${NSISDIR}\Contrib\Graphics\Header\nsis3-branding\win.bmp"
!define MUI_WELCOMEFINISHPAGE_BITMAP "${NSISDIR}\Contrib\Graphics\Wizard\win.bmp"
!define MUI_WELCOMEPAGE_TITLE "${APP_NAME} 安装向导"
!define MUI_FINISHPAGE_TITLE "${APP_NAME} 安装完成"
!define MUI_FINISHPAGE_RUN "${APP_EXE}"
!define MUI_FINISHPAGE_RUN_TEXT "立即启动 ${APP_NAME}"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "license.txt"
Page custom DownloadPathPage DownloadPathPageLeave
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_LANGUAGE "SimpChinese"

Var DownloadPath

; 下载路径选择页
Function DownloadPathPage
  ; 默认下载路径：安装目录下的 downloads
  StrCpy $DownloadPath "$INSTDIR\downloads"

  nsDialogs::Create /NOUNLOAD 1018
  Pop $0
  ${If} $0 == error
    Abort
  ${EndIf}

  nsDialogs::CreateControl /NOUNLOAD "STATIC" 0 0 0 100% 12u "下载目录（默认在安装目录下，建议改到大容量磁盘）"
  nsDialogs::CreateControl /NOUNLOAD "EDIT" 0 0 14u 100% 12u "$DownloadPath"
  Pop $1
  nsDialogs::CreateControl /NOUNLOAD "BUTTON" 0 75% 30u 25% 12u "浏览..."
  Pop $2
  nsDialogs::Show
FunctionEnd

Function DownloadPathPageLeave
  nsDialogs::GetControlText $1 $DownloadPath
  ; 简单校验：路径必须非空
  ${If} $DownloadPath == ""
    MessageBox MB_ICONSTOP "下载路径不能为空"
    Abort
  ${EndIf}
FunctionEnd

; 安装前检查
Function .onInit
  ; 检查是否已有实例在运行（通过 lock 端口 47299）
  nsExec::ExecToLog 'netstat -ano | findstr :47299'
  Pop $0
  ${If} $0 == 0
    MessageBox MB_ICONSTOP "检测到 ${APP_NAME} 正在运行，请先关闭后再安装。"
    Abort
  ${EndIf}
FunctionEnd

Section "主程序" SecMain
  SectionIn RO
  SetOutPath "$INSTDIR"
  ; 复制 PyInstaller 产物
  File /r "dist\yande-spider\_internal"
  File "dist\yande-spider\${APP_EXE}"

  ; 写下载路径到注册表（首次启动时读取）
  WriteRegStr HKCU "Software\${APP_NAME}" "DownloadPath" "$DownloadPath"
  WriteRegStr HKCU "Software\${APP_NAME}" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "Software\${APP_NAME}" "Version" "${APP_VERSION}"

  ; 写卸载程序
  WriteUninstaller "$INSTDIR\${APP_UNINSTALL}"
SectionEnd

Section "开始菜单快捷方式"
  CreateDirectory "$SMPROGRAMS\${APP_NAME}"
  CreateShortcut "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}"
  CreateShortcut "$SMPROGRAMS\${APP_NAME}\卸载.lnk" "$INSTDIR\${APP_UNINSTALL}"
SectionEnd

Section "桌面快捷方式"
  CreateShortcut "$DESKTOP\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}"
SectionEnd

Section "Uninstall"
  ; 询问是否保留用户数据
  MessageBox MB_YESNO|MB_ICONQUESTION "是否同时删除用户数据目录（%APPDATA%\yande-spider）和下载目录？$\r$\n选否则保留。" IDNO skip_data
    RMDir /r "$APPDATA\yande-spider"
    RMDir /r "$DownloadPath"
  skip_data:
  ; 删除应用目录
  RMDir /r "$INSTDIR"
  ; 清理注册表
  DeleteRegKey HKCU "Software\${APP_NAME}"
  DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "DisplayName"
  ; 删除快捷方式
  RMDir /r "$SMPROGRAMS\${APP_NAME}"
  Delete "$DESKTOP\${APP_NAME}.lnk"
SectionEnd
```

### Step 2: 写 `build_installer.py`

```python
# desktop/build/build_installer.py
"""调用 makensis 生成安装器。

需要：
- Windows 上安装 NSIS 3.x（https://nsis.sourceforge.io/）
- 把 makensis.exe 加到 PATH

运行：
    python desktop/build/build_installer.py
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DESKTOP = REPO_ROOT / "desktop"
NSI = DESKTOP / "nsis" / "installer.nsi"
DIST = REPO_ROOT / "dist"
OUTPUT = REPO_ROOT / "YandeSpider-Setup-v1.1.9.exe"


def main() -> None:
    if not NSI.exists():
        raise FileNotFoundError(f"NSI not found: {NSI}")
    if shutil.which("makensis") is None:
        raise RuntimeError("makensis not found in PATH. Install NSIS 3.x and add to PATH.")

    cmd = [
        "makensis",
        f"/DREPO_ROOT={REPO_ROOT}",
        f"/DOUTPUT={OUTPUT}",
        str(NSI),
    ]
    print(f"Running: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)
    print(f"Installer built: {OUTPUT}")


if __name__ == "__main__":
    main()
```

### Step 3: 在 Windows 上跑构建

```cmd
:: PowerShell
cd C:\path\to\yande.re-spider-next-dev
:: 先确保 Task 7 已经产出 dist\yande-spider\
python desktop\build\build_installer.py
:: 期望：仓库根目录出现 YandeSpider-Setup-v1.1.9.exe（约 100MB）
```

Expected: `YandeSpider-Setup-v1.1.9.exe` 生成。

### Step 4: 端到端验证（干净 Windows 10 VM）

```cmd
:: 在全新 Windows 10 虚拟机（无 Python、无 git、无代理）：
1. 双击 YandeSpider-Setup-v1.1.9.exe
2. 安装向导：接受许可 → 下载目录选 D:\Pictures\yande-spider → 安装 → 完成
3. 勾选"立即启动 Yande Spider"
4. 期望：托盘图标出现；PyWebView 窗口弹出并展示主界面
5. 关闭 PyWebView 窗口
6. 验证：
   - %APPDATA%\yande-spider\config\config.yaml 存在
   - %APPDATA%\yande-spider\port 存在（端口号）
   - 安装目录\data\yande_data.db 已创建
   - D:\Pictures\yande-spider\ 已创建
7. 通过 UI 关闭代理（默认已关闭），刷新主页能正常加载
8. 触发一次下载任务，确认文件落到 D:\Pictures\yande-spider\
9. 右键托盘 → 退出；进程干净退出，端口释放
10. 控制面板卸载；勾选"删除数据"；验证安装目录、用户目录、下载目录均已清理
```

Expected: 全部 10 步通过。

### Step 5: Commit

```bash
git add desktop/nsis/installer.nsi desktop/nsis/header.bmp desktop/nsis/sidebar.bmp \
  desktop/build/build_installer.py
git commit -m "feat(client): NSIS installer with download path wizard and clean uninstall"
```

---

## Task 9: 凭据红线 + 文档同步

**Files:**
- Modify: `README.md`（远期计划 → 已规划 / 链接到本设计文档）
- Modify: `docs/spec.md`（需求 2.2.2 状态更新）
- Modify: `docs/tasks.md`（§8 任务状态更新）
- Modify: `docs/design.md`（架构图注脚更新）

### Step 1: 修改 README 远期计划

```markdown
<!-- README.md 开发计划 → 远期计划段 -->

### 远期计划
- [x] **Windows 桌面客户端**（NSIS 安装器，已规划；详见 [Windows 客户端设计文档](docs/superpowers/specs/2026-08-05-windows-client-design.md)）
- [ ] 跨平台桌面客户端（macOS / Linux，二期）
- [ ] 移动端适配优化
```

### Step 2: 修改 `docs/spec.md` 需求 2.2.2

```markdown
<!-- docs/spec.md 第 133-143 行 -->

### 2.2.2 桌面客户端支持（P1）

**实现状态**：✅ 规划完成，进入实施阶段（Windows NSIS 安装器）。
详见实施文档 [docs/superpowers/specs/2026-08-05-windows-client-design.md]。

首期范围：
- [x] Windows 10/11 单文件安装器
- [x] SQLite 零配置
- [x] 系统托盘常驻（pystray）
- [x] 下载目录可配置（NSIS 向导）
- [x] 配置文件独立于安装目录（%APPDATA%）
- [ ] macOS / Linux（**不在首期范围**）
- [ ] 自动更新（**不在首期范围**，手动下载）
- [ ] 代码签名（**不在首期范围**，首期可不签名）
```

### Step 3: 修改 `docs/tasks.md` §8 任务

```markdown
<!-- docs/tasks.md §8 顶部 -->

## 第 8 章 Windows 桌面客户端开发（P1） ✅ 已规划，进入实施

> **规划完成于 2026-08-05**，详见实施文档
> [docs/superpowers/specs/2026-08-05-windows-client-design.md](docs/superpowers/specs/2026-08-05-windows-client-design.md)。
>
> 实施将按 8 个原子任务逐步合入 `feature/desktop-client` 分支 → MR 到 `next_dev`。
>
> **首期非范围**：macOS/Linux、自动更新、代码签名。

### 8.0 验收清单（首期）

- [ ] Task 1 路径抽象层（合并入 `next_dev` 后勾选）
- [ ] Task 2 端口参数化（合并入 `next_dev` 后勾选）
- [ ] Task 3 frozen frontend dist 适配
- [ ] Task 4 配置 bootstrap + 占位符
- [ ] Task 5 下载器预分配降级
- [ ] Task 6 PyWebView 启动器
- [ ] Task 7 PyInstaller 构建脚本
- [ ] Task 8 NSIS 安装器
- [ ] Task 9 文档同步 + 凭据红线（**强制**）

<!-- §8.1/§8.2/§8.3 旧内容保留作为参考，但顶部加注 "详见上方实施文档" -->
```

### Step 4: 修改 `docs/design.md` 第 1.1 节架构图注脚

```markdown
<!-- docs/design.md 架构图 "Electron 桌面客户端" 节点 -->

**架构图修订（2026-08-05）**：
原"Electron 桌面客户端(远期规划)"节点已升级为 **Windows 客户端(NSIS)**，
技术栈由 Electron 改为 PyWebView + PyInstaller + NSIS。
详见实施文档 [docs/superpowers/specs/2026-08-05-windows-client-design.md](docs/superpowers/specs/2026-08-05-windows-client-design.md)。
```

### Step 5: 凭据强制扫描

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev
git diff origin/next..HEAD \
  | grep -iE '(password|secret|token|api[_-]?key)\s*[:=]\s*["\x27][^"\x27]+["\x27]' \
  | grep -vE '""|null|<YOUR_|<CHANGE_'
# 期望：无输出
```

如果命中真实凭据：**立即停止推送**，把真密钥替换为占位符（`""` 或 `<YOUR_DB_PASSWORD>`）后再推送（这是 `AGENTS.md` 红线规则）。

### Step 6: Commit

```bash
git add README.md docs/spec.md docs/tasks.md docs/design.md
git commit -m "docs(client): Windows client design integrated into spec/design/tasks"
```

---

## 风险登记与缓解

| 风险 | 等级 | 缓解 |
|------|------|------|
| PyInstaller 漏抓 hidden import | 高 | Task 7 列出 `uvicorn.protocols.*` / `apscheduler.jobstores.sqlalchemy` 等；端到端 Task 8 步骤 4 验证关键路径 |
| `_internal/` 体积 200MB+ | 中 | NSIS 用 LZMA 压缩；提供 `desktop/requirements.txt` 精简 pywebview/pystray 依赖 |
| uvicorn subprocess 崩溃 | 中 | Task 6 main.py 在 PyWebView 退出时 terminate+kill；托盘菜单显示进程状态（**二期扩展**） |
| 单实例锁被绕过 | 中 | Task 6 端口 47299 锁；NSIS 安装前 `.onInit` 也会校验 |
| 端口冲突 | 低 | OS 自动分配空闲端口 |
| Windows Defender 误报 PyInstaller | 中 | 后续可提交微软 MAPP；首期文档说明"如被拦截请添加信任" |
| 凭据泄露到 git | **红线** | Task 4 强制 placeholder + Task 9 强制扫描；扫描不通过禁止推送 |
| 用户数据目录迁移 | 中 | 首期不支持迁移；后续版本提供「导入旧数据」UI |
| APScheduler 定时任务被 OS 休眠跳过 | 中 | 文档明确"应用须保持运行（托盘常驻）"；二期可接 Windows Task Scheduler |
| mariadb C 扩展打包失败 | 中 | Task 1 默认 SQLite（`database.enable=False`）；MariaDB 仅作 UI 高级选项 |

## 自检清单（执行前最后一遍）

- [ ] 所有 Task 的 Step 代码完整无占位符
- [ ] 所有 Task 的 Step 命令可在 Windows / Linux 任一平台运行（已标注）
- [ ] 文件路径与 §"文件结构总览"一致
- [ ] 函数签名一致（`write_default_user_config`、`wait_for_health`、`start_uvicorn_subprocess` 在前后 Task 中同名同参）
- [ ] 凭据红线在 Task 4、Task 9 各执行一次
- [ ] 测试套件覆盖：路径解析、端口管理、前端 dist、配置 bootstrap、下载器降级、主启动器

---

## 执行交接

计划已完成并保存至 `docs/superpowers/specs/2026-08-05-windows-client-design.md`。

两种执行方式：

**1. Subagent-Driven (推荐)** — 每个 Task 派遣独立 subagent，Task 间评审，快速迭代
**2. Inline Execution** — 当前会话直接执行 executing-plans，批量执行 + 检查点

你希望用哪种方式推进？