from config import Settings, create_page
from utils import generate_strong_password, random_email, randomDayAndMonthAndYear, generate_name
from register_flow import fill_form
from px_captcha import handle_captcha
from getAccountData import save_account_data
import sys


def run_once(proxy="http://127.0.0.1:7897"):
    """执行一次完整的 Outlook 注册流程。返回 (ok, record_file) 元组。"""
    email = f"{random_email()}@outlook.com"
    password = generate_strong_password()
    first_name, last_name = generate_name()
    birth_month = randomDayAndMonthAndYear("month")
    birth_day = randomDayAndMonthAndYear("day")
    birth_year = str(randomDayAndMonthAndYear("year"))

    print(f"=== 开始注册: {email} ===")
    settings = Settings(proxy=proxy)
    page = create_page(settings)

    try:
        fill_form(page, email, password, first_name, last_name,
                  birth_month, birth_day, birth_year)
        if not handle_captcha(page):
            print(f"❌ PX 验证失败: {email}")
            return False, None
        result = save_account_data(page, email, password, proxy=proxy)
        print(f"✅ 成功: {result['record_file']}")
        return True, result['record_file']
    finally:
        try:
            page.quit()
        except Exception:
            pass


if __name__ == "__main__":
    ok, record = run_once(proxy="http://127.0.0.1:7897")
    sys.exit(0 if ok else 1)
