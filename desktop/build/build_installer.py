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
