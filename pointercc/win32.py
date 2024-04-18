import win32gui
from pointercc.core import Window, Box

def get_windows(name_patterns):
    result = {}
    def f(hwnd, r):
        title = win32gui.GetWindowText(hwnd)

        if not win32gui.IsWindowVisible(hwnd):
            return

        if title is None:
            return

        for pattern in name_patterns:
            if title.find(pattern) > -1:
                (xmin, ymin, xmax, ymax) = win32gui.GetWindowRect(hwnd)
                box = Box(xmin, xmax, ymin, ymax)
                window = Window(pattern, title, box)
                result[title] = window
    win32gui.EnumWindows(f, result)
    return result

def init():
    pass
