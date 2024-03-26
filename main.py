import Quartz
from PIL import Image

import time
import rtmidi
import traceback
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
    def __init__(self, midiin):
        super(Dispatcher, self).__init__()
        self.midiin = midiin
        self.queue = queue.Queue()

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
                print("midi_cc")

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

def main_mapper():
    NOVA_PORT = 'Launch Control XL'
    midiin, port = open_midiport(NOVA_PORT, "input")

    dispatcher = Dispatcher(midiin)
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

def screen_to_window(x, y, window_box):
    b = window_box
    return x - b.xmin, y - b.ymin

def window_to_screen(x, y, window_box):
    b = window_box
    return x + b.xmin, y + b.ymin

def window_to_model(x, y, window_box, model_box):
    pass

def main():
    print('analyzing..', end='')
    model = main_analyze()
    print('done.')
    main_mapper()

if __name__ == '__main__':
    main()
