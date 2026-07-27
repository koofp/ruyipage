# -*- coding: utf-8 -*-
"""浏览器配置与创建"""

from dataclasses import dataclass
import random
import time
from ruyipage import FirefoxOptions, FirefoxPage


@dataclass
class Settings:
    browser_path: str = r"D:\EXED\10_brower\firefox\firefox.exe"
    port: int = 12000
    headless: bool = False
    width: int = 1440
    height: int = 900
    human_algorithm: str = "windmouse"
    proxy: str = "http://127.0.0.1:7897"
    action_visual: bool = True
    close_on_exit: bool = False


def create_page(settings: Settings = None) -> FirefoxPage:
    """根据配置创建 FirefoxPage 并打开注册页。返回 ready 的 page 对象。"""
    if settings is None:
        settings = Settings()
    # print(f"setting:{settings}")
    opts = (FirefoxOptions()
            .set_browser_path(settings.browser_path)
            .set_port(settings.port)
            .headless(settings.headless)
            .set_window_size(settings.width, settings.height)
            .set_human_algorithm(settings.human_algorithm)
            .set_proxy(settings.proxy)
            .close_on_exit(settings.close_on_exit)
            .enable_action_visual(settings.action_visual))

    page = FirefoxPage(opts)
    page.get("https://signup.live.com/", wait="complete")
    page.wait(random.uniform(0.6, 1.0))
    return page
