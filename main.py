import Quartz
from PIL import Image

import time
import rtmidi
import math
import traceback
import mouse
from rtmidi.midiutil import open_midiport
import threading
import queue
import copy
import sys
import re

class Box:
    def __init__(self, xmin, xmax, ymin, ymax):
        self.xmin = xmin
        self.xmax = xmax
        self.ymin = ymin
        self.ymax = ymax

    def center(self):
        x = self.xmin + (self.xmax - self.xmin) // 2
        y = self.ymin + (self.ymax - self.ymin) // 2
        return (x, y)

    @property
    def width(self):
        return self.xmax - self.xmin

    @property
    def height(self):
        return self.ymax - self.ymin

def make_box(x, y, width, height):
    return Box(x, x + width, y, y + height)

def find_markings(im, marker_color):
    boxes = []
    spans_last = {}
    for y in range(0, im.height):
        xmin = None
        xmax = None
        spans = {}
        for x in range(0, im.width):
            in_marker = im.getpixel((x, y)) == marker_color
            if in_marker:
                if xmin is None:
                    xmin = x
                xmax = x

            if (not in_marker and xmax is not None) or (in_marker and x == im.width - 1):
                b = spans_last.get((xmin, xmax))
                if b is not None:
                    b.ymax = y
                else:
                    b = Box(xmin, xmax, y, y)
                    boxes.append(b)
                spans[(xmin, xmax)] = b
                xmin = None
                xmax = None
        spans_last = spans
    return boxes

class Model:
    def __init__(self, box, markings):
        self.box = box
        self.markings = markings

def analyze(filename, marker_color=(255, 0, 255, 255)):
    im = Image.open(filename)
    markings = [b.center() for b in find_markings(im, marker_color)]
    b = make_box(0, 0, im.width, im.height) 
    return Model(b, markings)

def fmt_hex(i):
    s = hex(i)[2:].upper()
    prefix = "".join(((2 - len(s)) * ["0"]))
    return prefix + hex(i)[2:].upper()

class Dispatcher(threading.Thread):
    def __init__(self, midiin, mouse_controller):
        super(Dispatcher, self).__init__()
        self.midiin = midiin
        self.queue = queue.Queue()
        self.mouse_controller = mouse_controller

    def fmt_message(self, message, prefix):
        input = (' '.join([fmt_hex(b) for b in message]))
        input_dec = ' '.join([str(b) for b in message])
        # chn = self.channels[self.current_channel]
        # state = f'chn:{(chn.chn+1):02d} [{chn.instrument.name}] p:{chn.current_page}'
        return (prefix + input + " dec: " + input_dec)

    def __call__(self, event, data=None):
        try:
            message, deltatime = event
            print(self.fmt_message(message, '<     '))

            # note on(?)
            if message[0] & 0xf0 == 0x90:
                if message[1] == 0x3c:
                    print('aha!')
                    self.queue.put(42)
                pass

            # note off(?)
            if message[0] & 0xf0 == 0x80:
                pass

            # midi cc
            if message[0] & 0xf0 == 0xb0:
                if message[1] == 0x31:
                    x_normed = message[2] / 127.0
                    self.mouse_controller.pan_x(x_normed)
                if message[1] == 0x32:
                    y_normed = message[2] / 127.0
                    self.mouse_controller.pan_y(y_normed)

        except Exception as e:
            traceback.print_exception(e)
            # print('Exception in handler: ' + repr(e))

    def run(self):
        self.midiin.set_callback(self)

        running = True
        while running:
            item = self.queue.get()

            print('got item!')
            sys.stdout.flush()
            running = False

            #
            # dst, message = item
            #
            # sys.stdout.flush()
            # if dst == 'nova':
            #     self.nova_midiout.send_message(message)
            # elif dst == 'out':
            #     self.mapped_midiout.send_message(message)
            #     print(self.fmt_message(message, f'>{dst.ljust(4)} '))
            # else:
            #     raise ValueError(dst)
        print('done?')


class Window:
    def __init__(self, title, box):
        self.title = title
        self.box = box

def main():
    print('analyzing..', end='')
    model = main_analyze()
    print('done.')
    window = get_windows_mac()[0]
    NOVA_PORT = 'Launch Control XL'
    midiin, port = open_midiport(NOVA_PORT, "input")
    mouse_controller = MouseController(window, model)
    dispatcher = Dispatcher(midiin, mouse_controller)
    dispatcher.start()
    dispatcher.join()

def main_analyze():
    return analyze("instruments/tal-jupiter.png")

def matches_any(window, name_patterns):
    name = window.get(Quartz.kCGWindowName)
    if name is None:
        return False
    else:
        for pattern in name_patterns:
            if re.search(pattern, name):
                return True
        return False
    
def get_windows_mac(name_patterns=["TAL-J-8"]):
    windows = Quartz.CGWindowListCopyWindowInfo(0, Quartz.kCGNullWindowID)
    result = []
    for w in filter(lambda w: matches_any(w, name_patterns), windows):
        bounds = w.get(Quartz.kCGWindowBounds)
        if bounds:
            b = make_box(int(bounds['X']), int(bounds['Y']), int(bounds['Width']), int(bounds['Height']))
            title = w[Quartz.kCGWindowName]
            window = Window(title, b)
            result.append(window)
    return result


# affine transform that can be scaling and translation
class Affine:
    def __init__(self, sx, sy, dx, dy):
        self.sx = sx
        self.sy = sy
        self.dx = dx
        self.dy = dy

    def inverse(self):
        sx_inv = 1.0 / self.sx
        sy_inv = 1.0 / self.sy
        return Affine(sx_inv, sy_inv, - sx_inv * self.dx, - sy_inv * self.dy)

    def multiply_right(self, other):
        sx = self.sx * other.sx
        sy = self.sy * other.sy
        dx = sx * other.dx + self.dx
        dy = sy * other.dy + self.dy
        self.sx = sx
        self.sy = sy
        self.dx = dx
        self.dy = dy

    def apply(self, x, y):
        x_ = self.sx * x + self.dx
        y_ = self.sy * y + self.dy
        return (x_, y_)

def screen_to_window(window_box):
    b = window_box
    return Affine(1.0, 1.0, -b.xmin, -b.ymin)

def window_to_screen(window_box):
    return screen_to_window(window_box).inverse()

def model_to_window(window_box, model_box):
    sx = window_box.width / model_box.width
    sy = window_box.height / model_box.height
    s = min(sx, sy)
    excess_x = window_box.width - s * model_box.width
    excess_y = window_box.height - s * model_box.height
    return Affine(s, s, excess_x / 2.0, excess_y)

def window_to_model(window_box, model_box):
    return model_to_window(window_box, model_box).inverse()

class MouseController:
    def __init__(self, window, model):
        self.window = window
        self.model = model

        t = window_to_model(window.box, model.box)
        s2w = screen_to_window(window.box)
        t.multiply_right(s2w)

        self.screen_to_model = t
        self.model_to_screen = self.screen_to_model.inverse()

        self.mx = 0.0
        self.my = 0.0

    def pan_x(self, x_normed):
        self.mx = self.model.box.width * x_normed
        self.move_mouse()

    def pan_y(self, y_normed):
        self.my = self.model.box.height * y_normed
        self.move_mouse()

    def move_mouse(self):
        mx, my = self.find_closest_marker(self.mx, self.my)
        # mx, my = self.mx, self.my

        x, y = self.model_to_screen.apply(mx, my)
        mouse.move(int(x), int(y))

    def find_closest_marker(self, mx, my):
        d_best = math.inf
        i_best = 0
        for i, (x, y) in enumerate(self.model.markings):
            d = math.pow(x - mx, 2.0) + math.pow(y - my, 2.0)
            if d < d_best:
                i_best = i
                d_best = d
        return self.model.markings[i_best]

if __name__ == '__main__':
    main()
