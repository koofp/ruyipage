"""串行批量注册 Outlook 账号。每次注册一个，完成后清理再起下一个。"""
import time

from config import Settings, create_page
from utils import (generate_strong_password, random_email,
                   randomDayAndMonthAndYear, generate_name)
from register_flow import fill_form
from px_captcha import handle_captcha
from getAccountData import save_account_data


# ── 配置 ──
BATCH_SIZE = 2                 # 本次注册数量
PROXY = "http://127.0.0.1:7897"
WAIT_BETWEEN = 10              # 两次注册间隔（秒）—— 避免代理/微软风控
FIREFOX_QUIT_WAIT = 3          # quit 后等 Firefox 释放端口

for i in range(1, BATCH_SIZE + 1):
    email = f"{random_email()}@outlook.com"
    password = generate_strong_password()
    first_name, last_name = generate_name()
    birth_month = randomDayAndMonthAndYear("month")
    birth_day = randomDayAndMonthAndYear("day")
    birth_year = str(randomDayAndMonthAndYear("year"))

    print(f"\n{'='*60}")
    print(f"  第 {i}/{BATCH_SIZE} 次  {email}")
    print(f"{'='*60}")

    settings = Settings(proxy=PROXY)
    page = create_page(settings)

    try:
        fill_form(page, email, password, first_name, last_name,
                  birth_month, birth_day, birth_year)

        if handle_captcha(page):
            result = save_account_data(page, email, password, proxy=PROXY)
            print(f"  ✅ 成功: {result['record_file']}")
        else:
            print(f"  ❌ PX 验证失败，跳过账号保存")
    except Exception as exc:
        print(f"  💥 异常: {type(exc).__name__}: {exc}")
    finally:
        try:
            page.quit()
        except Exception:
            pass
        time.sleep(FIREFOX_QUIT_WAIT)

    if i < BATCH_SIZE:
        print(f"  等待 {WAIT_BETWEEN} 秒...")
        time.sleep(WAIT_BETWEEN)

print(f"\n{'='*60}")
print(f"  完成 {BATCH_SIZE} 次注册")
print(f"{'='*60}")
