"""系统托盘（pystray）。"""
from __future__ import annotations

import threading
import webbrowser
from pathlib import Path
from typing import Callable, Optional

import webview
from loguru import logger
from PIL import Image
from pystray import Icon, Menu, MenuItem


class SystemTray:
    """封装 pystray 图标，提供「打开主界面 / 浏览器打开 / 退出」菜单。"""

    def __init__(
        self,
        icon_path: Path,
        title: str,
        url: str,
        on_quit: Callable[[], None],
        window: Optional[webview.Window] = None,
    ) -> None:
        self.icon_path = icon_path
        self.title = title
        self.url = url
        self.on_quit = on_quit
        self.window = window
        self._icon: Optional[Icon] = None
        self._thread: Optional[threading.Thread] = None

    def _show_window(self) -> None:
        if self.window is None:
            return
        try:
            self.window.show()
        except Exception as e:
            logger.warning(f"Show window failed: {e}")

    def _open_browser(self) -> None:
        webbrowser.open(self.url)

    def _quit(self) -> None:
        try:
            self.on_quit()
        finally:
            if self._icon is not None:
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
        if self._icon is not None:
            try:
                self._icon.stop()
            except Exception as e:
                logger.warning(f"Tray stop failed: {e}")