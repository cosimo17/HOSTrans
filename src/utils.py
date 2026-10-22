import base64
import io
import win32gui
import re
import random
import string
from typing import Tuple
import pyautogui


def switch_window(window_title):
    def enum_windows_proc(hwnd, window_title):
        if win32gui.IsWindow(hwnd) and win32gui.IsWindowEnabled(hwnd) and win32gui.IsWindowVisible(hwnd):
            window_text = win32gui.GetWindowText(hwnd)
            if window_text.startswith(window_title):
                win32gui.SetForegroundWindow(hwnd)
                return False
        return True

    win32gui.EnumWindows(enum_windows_proc, window_title)


def window_exists(window_title):
    found = False

    def enum_windows_proc(hwnd, _):
        nonlocal found
        if win32gui.IsWindow(hwnd) and win32gui.IsWindowEnabled(hwnd) and win32gui.IsWindowVisible(hwnd):
            window_text = win32gui.GetWindowText(hwnd)
            if window_text.startswith(window_title):
                found = True
                return False
        return True  # 必须显式返回 True 以继续枚举

    win32gui.EnumWindows(enum_windows_proc, None)

    return found


def contains_korean(text):
    korean_pattern = re.compile('[\uAC00-\uD7AF\u3130-\u318F\u1100-\u11FF]')
    return bool(korean_pattern.search(text))


def generate_random_string(length):
    return ''.join(random.choices(string.digits, k=length))


def capture_chat_region_base64(ratios: Tuple[float, float, float, float]) -> str:
    """根据相对屏幕分辨率的硬编码偏移比例截取局部屏幕，并返回 PNG 的 Base64 字符串"""
    screen_w, screen_h = pyautogui.size()
    x_ratio, y_ratio, w_ratio, h_ratio = ratios
    left = max(0, int(screen_w * x_ratio))
    top = max(0, int(screen_h * y_ratio))
    width = max(1, int(screen_w * w_ratio))
    height = max(1, int(screen_h * h_ratio))

    screenshot = pyautogui.screenshot(region=(left, top, width, height))
    buffer = io.BytesIO()
    screenshot.save(buffer, format='PNG')
    return base64.b64encode(buffer.getvalue()).decode('utf-8')
