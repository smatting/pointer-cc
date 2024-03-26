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

def find_boxes(im, marker_color=(255, 0, 255, 255)):
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

def analyze(filename):
    im = Image.open(filename)
    points = [b.center() for b in find_boxes(im)]
    return im.width, im.height, points



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

        while True:
            time.sleep(1)
            # item = self.queue.get()
            #
            # if item is None:
            #     print('message empty')
            #     continue
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


def main_mapper():
    NOVA_PORT = 'Launch Control XL'
    midiin, port = open_midiport(NOVA_PORT, "input")

    dispatcher = Dispatcher(midiin)
    dispatcher.start()
    while True:
        time.sleep(1)

def main_analyze():
    return analyze("instruments/tal-jupiter.png")
    

def main():
    main_mapper()

if __name__ == '__main__':
    main()
