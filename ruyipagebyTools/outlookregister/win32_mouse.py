# -*- coding: utf-8 -*-
"""Win32 native mouse input (OS-level, bypasses BiDi cross-origin restriction)."""
import ctypes
from ctypes import wintypes


user32 = ctypes.windll.user32
INPUT_MOUSE = 0
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG), ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t),
    ]


class INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("union", INPUTUNION)]


def _send_mouse(flags: int):
    event = INPUT()
    event.type = INPUT_MOUSE
    event.union.mi = MOUSEINPUT(0, 0, 0, flags, 0, 0)
    return user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(INPUT))


def screen_coords(btn_cx: float, btn_cy: float,
                  px_off: dict, hu_off: dict, vs: dict,
                  skip_px_offset: bool = True) -> tuple[int, int]:
    """hitbox 中心点 → 视口 → 屏幕绝对坐标。
       skip_px_offset=True 时只用 hu_off，False 时叠加 px_off + hu_off。"""
    if skip_px_offset:
        vx = btn_cx + hu_off["x"]
        vy = btn_cy + hu_off["y"]
    else:
        vx = btn_cx + px_off["x"] + hu_off["x"]
        vy = btn_cy + px_off["y"] + hu_off["y"]
    sx = int(vs["x"] + vx)
    sy = int(vs["y"] + vy)
    return sx, sy


def native_hold(sx: int, sy: int, hold_seconds: float = 11.0,
                jitter_px: int = 2):
    """在 (sx, sy) 按住左键 hold_seconds 秒，期间随机微抖。"""
    import random
    import time

    if not user32.SetCursorPos(sx, sy):
        raise ctypes.WinError(ctypes.get_last_error())
    time.sleep(0.15)

    if _send_mouse(MOUSEEVENTF_LEFTDOWN) != 1:
        raise ctypes.WinError(ctypes.get_last_error())

    hold_until = time.time() + hold_seconds
    while time.time() < hold_until:
        user32.SetCursorPos(
            sx + random.randint(-jitter_px, jitter_px),
            sy + random.randint(-jitter_px, jitter_px),
        )
        time.sleep(random.uniform(0.08, 0.35))

    _send_mouse(MOUSEEVENTF_LEFTUP)
