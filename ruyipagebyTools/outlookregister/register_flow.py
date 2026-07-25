# -*- coding: utf-8 -*-
"""注册表单填写"""

import random
import time
from ruyipage import FirefoxPage


def fill_form(page: FirefoxPage, email: str, password: str,
              first_name: str, last_name: str,
              birth_month_idx: int, birth_day_idx: int, birth_year: str):
    """填完整个微软注册表单并走到最后一步（触发 PX 验证）。"""

    # ── email ──
    page.actions.human_move(
        page.ele("#floatingLabelInput4"), algorithm="windmouse"
    ).human_click().human_type(email).perform()
    page.wait(random.uniform(0.4, 0.8))

    account_next = page.ele("xpath://button[@data-testid=\"primaryButton\"]")
    page.actions.human_move(account_next, algorithm="windmouse").human_click().perform()
    page.wait(random.uniform(0.5, 0.9))

    # ── password ──
    password_btn = page.ele("xpath://*[@id=\"floatingLabelInput13\"]")
    page.actions.human_move(password_btn, algorithm="windmouse").human_click().human_type(password).perform()
    page.wait(random.uniform(0.6, 1.0))

    account_next = page.ele("xpath://button[@data-testid=\"primaryButton\"]")
    page.actions.human_move(account_next, algorithm="windmouse").human_click().perform()
    page.wait(random.uniform(0.4, 0.8))

    # ── birth month ──
    mouth = page.ele("xpath://*[@id=\"BirthMonthDropdown\"]")
    page.actions.human_move(mouth, algorithm="windmouse").human_click().perform()
    page.wait(random.uniform(0.4, 0.8))

    options = page.eles("xpath://div[@role=\"option\"]")
    page.actions.human_move(options[birth_month_idx], algorithm="windmouse").human_click().perform()
    page.wait(random.uniform(0.3, 0.7))

    # ── birth day ──
    day = page.ele("xpath://*[@id=\"BirthDayDropdown\"]")
    page.actions.human_move(day, algorithm="windmouse").human_click().perform()
    page.wait(random.uniform(0.5, 0.9))

    options = page.eles("xpath://div[@role=\"option\"]")
    page.actions.human_move(options[birth_day_idx], algorithm="windmouse").human_click().perform()
    page.wait(random.uniform(0.4, 0.8))

    # ── birth year ──
    year = page.ele("xpath://*[@id=\"floatingLabelInput24\"]")
    page.actions.human_move(year, algorithm="windmouse").human_click().human_type(birth_year).perform()
    page.wait(random.uniform(0.6, 1.0))

    role_next = page.ele("xpath://button[@data-testid=\"primaryButton\"]")
    page.actions.human_move(role_next, algorithm="windmouse").human_click().perform()
    page.wait(random.uniform(0.4, 0.8))

    # ── first name ──
    first_el = page.ele("xpath://*[@id=\"firstNameInput\"]")
    page.actions.human_move(first_el, algorithm="windmouse").human_click().human_type(first_name).perform()
    page.wait(random.uniform(0.6, 1.0))

    # ── last name ──
    last_el = page.ele("xpath://div[1]/div[2]/div[1]/span[1]")
    page.actions.human_move(last_el, algorithm="windmouse").human_click().human_type(last_name).perform()

    name_next = page.ele("xpath://button[@data-testid=\"primaryButton\"]")
    page.actions.human_move(name_next, algorithm="windmouse").human_click().perform()
    page.wait(2)
