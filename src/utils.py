import win32gui
import re
import random
import string


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