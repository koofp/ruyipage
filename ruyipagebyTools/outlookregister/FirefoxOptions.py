import random
import time
import ctypes
from ctypes import wintypes

from config import Settings, create_page
from utils import generate_strong_password, random_email, randomDayAndMonthAndYear, generate_name
from register_flow import fill_form
from px_captcha import handle_captcha
from getAccountData import save_account_data


# ── 配置 ──
REG_EMAIL = f"{random_email()}@outlook.com"
REG_PASSWORD = generate_strong_password()
PROXY = "http://127.0.0.1:7897"

_birth_month = randomDayAndMonthAndYear("month")
_birth_day = randomDayAndMonthAndYear("day")
_birth_year = str(randomDayAndMonthAndYear("year"))
first_name, last_name = generate_name()

# ── 启动浏览器 ──
settings = Settings(proxy=PROXY)
page = create_page(settings)

try:
    # ── 注册流程 ──
    fill_form(page, REG_EMAIL, REG_PASSWORD,
              first_name, last_name, _birth_month, _birth_day, _birth_year)

    # ── PX 人机验证 ──
    handle_captcha(page)

    # ── 保存账号数据 ──
    result = save_account_data(page, REG_EMAIL, REG_PASSWORD, proxy=PROXY)
    print(f"[FirefoxOptions] 账号保存结果: {result}")
finally:
    try:
        page.quit()
    except Exception as exc:
        print(f"[FirefoxOptions] page.quit failed: {type(exc).__name__}: {exc}")
