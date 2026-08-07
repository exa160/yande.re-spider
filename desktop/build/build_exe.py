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
