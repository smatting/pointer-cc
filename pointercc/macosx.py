import Quartz
from pointercc.core import Window, Box, make_box

def request_access():
    Quartz.CGRequestPostEventAccess()
    Quartz.CGRequestScreenCaptureAccess()
    Quartz.CGPreflightScreenCaptureAccess()

def get_windows(name_patterns):
    windows = Quartz.CGWindowListCopyWindowInfo(0, Quartz.kCGNullWindowID)
    result = {}
    for w in windows:
        bounds = w.get(Quartz.kCGWindowBounds)
        name = str(w.get(Quartz.kCGWindowName))
        if name is None or bounds is None:
            continue

        for pattern in name_patterns:
            if name.find(pattern) > -1:
                box = make_box(int(bounds['X']), int(bounds['Y']), int(bounds['Width']), int(bounds['Height']))
                window = Window(pattern, name, box)
                result[name] = window
    return result

def init():
    request_access()
