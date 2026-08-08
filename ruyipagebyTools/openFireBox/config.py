# -*- coding: utf-8 -*-
"""浏览器配置与创建"""

from dataclasses import dataclass
import random
import time
from ruyipage import FirefoxOptions, FirefoxPage


@dataclass
class Settings:
    browser_path: str = r"D:\EXED\10_brower\firefox-155.0a1.en-US.win64-20260801\firefox\firefox.exe"
    port: int = 12000
    headless: bool = False
    width: int = 1440
    height: int = 900
    human_algorithm: str = "windmouse"
    proxy: str = "http://127.0.0.1:7897"
    action_visual: bool = False
    private_mode: bool = True
    close_on_exit: bool = False


def create_page(oneProxy ,settings: Settings = None) -> FirefoxPage:
    """根据配置创建 FirefoxPage 并打开注册页。返回 ready 的 page 对象。"""
    if settings is None:
        settings = Settings()

    opts = (FirefoxOptions()
            .set_browser_path(settings.browser_path)
            .set_port(settings.port)
            .set_random_port()
            .headless(settings.headless)
            .set_window_size(settings.width, settings.height)
            .set_human_algorithm(settings.human_algorithm)
            .private_mode(settings.private_mode)
            .close_on_exit(settings.close_on_exit)
            .enable_action_visual(settings.action_visual))

    print(f"oneProxy=>http://{oneProxy}")
    if oneProxy:
        opts.set_proxy(f"http://{oneProxy}")

    page = FirefoxPage(opts)
    page.get("", wait="complete")
    page.wait(random.uniform(0.6, 1.0))
    return page

proxyArr = [
"4419993-3f4ec64982:09b8882739-US-69671306@gate.kookeey.info:1000"]

for item in proxyArr:
    create_page(item)