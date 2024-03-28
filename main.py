import Quartz
from PIL import Image
import wx
import time
import os
import subprocess
import platform
import yaml
import glob
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
import appdirs
from enum import Enum

app_name = "pointer-cc"
app_author = "smatting"

Command = Enum('Command', ['QUIT', 'CHANGE_MIDI_CHANNEL', 'UPDATE_WINDOW'])

def datadir():
    return appdirs.user_data_dir(app_name, app_author)

def userfile(p):
    return os.path.join(datadir(), p)

def initialize_config():
    os.makedirs(datadir(), exist_ok=True)

class Box:
    def __init__(self, xmin, xmax, ymin, ymax):
        self.xmin = xmin
        self.xmax = xmax
        self.ymin = ymin
        self.ymax = ymax

    def __eq__(self, other):
        return self.totuple() == other.totuple()

    def totuple(self):
        return (self.xmin, self.xmax, self.ymin, self.ymax)

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


class Controller:
    def __init__(self, i, x, y, speed_multiplier=None):
        self.i = i
        self.x = x
        self.y = y
        self.speed_multiplier = speed_multiplier

class Instrument:
    def __init__(self, pattern, box, controllers):
        self.pattern = pattern
        self.box = box
        self.controllers = controllers

    @staticmethod
    def load(path):
        with open(path, 'r') as f:
            d = yaml.safe_load(f.read())
        dim = d["dimensions"]
        box = Box(0, dim["width"], 0, dim["height"])
        controllers = []
        for g in d["controllers"]:
            mspeed = g.get('speed')
            if mspeed is not None:
                speed = int(mspeed)
            else:
                speed = None
            c = Controller(int(g['i']), int(g["x"]), int(g["y"]), speed)
            controllers.append(c)
        pattern = d['window_title_pattern']
        return Instrument(pattern, box, controllers)

    def find_closest_controller(self, mx, my):
        c_best = None
        d_best = math.inf
        for c in self.controllers:
            d = math.pow(c.x - mx, 2.0) + math.pow(c.y - my, 2.0)
            if d < d_best:
                c_best = c
                d_best = d
        return c_best

def analyze(filename, marker_color=(255, 0, 255, 255)):
    im = Image.open(filename)
    def f(i, p):
        x, y = p
        return {"i": i, "x": x, "y": y}

    controllers = [f(i, b.center()) for i, b in enumerate(find_markings(im, marker_color))]
    b = make_box(0, 0, im.width, im.height) 
    d = {
        "dimensions" : {
            "width": im.width,
            "height": im.height
        },
        "controllers": controllers
    }
    return d
    # return Model(b, markings)

def fmt_hex(i):
    s = hex(i)[2:].upper()
    prefix = "".join(((2 - len(s)) * ["0"]))
    return prefix + hex(i)[2:].upper()

class Dispatcher(threading.Thread):
    def __init__(self, midiin, queue, frame, instruments, config):
        super(Dispatcher, self).__init__()
        self.midiin = midiin
        self.queue = queue
        self.frame = frame
        self.midi_channel = None
        self.instruments = instruments
        self.controllers = {}
        self.config = config

        if len(self.instruments) == 0:
            self.frame.set_window_text("No instruments configured, please read the docs")

    def fmt_message(self, message, prefix):
        input = (' '.join([fmt_hex(b) for b in message]))
        input_dec = ' '.join([str(b) for b in message])
        # chn = self.channels[self.current_channel]
        # state = f'chn:{(chn.chn+1):02d} [{chn.instrument.name}] p:{chn.current_page}'
        return (prefix + input + " dec: " + input_dec)

    def get_active_controller(self):
        if len(self.controllers) == 0:
            return None

        elif len(self.controllers) == 1:
            return list(self.controllers.values())[0]

        else:
            # return leftmost; TODO: find the one with center closest to pointer
            cbest = None
            xmin = math.inf
            for c in self.controllers.values():
                if c.window.box.xmin < xmin:
                    xmin = c.window.box.xmin
                    cbest = c
            return cbest

    def __call__(self, event, data=None):
        try:
            message, deltatime = event

            ch = message[0] & 0x0f
            ignore = False
            if self.midi_channel is not None:
                if ch != self.midi_channel:
                    return
    
            controller = self.get_active_controller()

            midi_msg_text = self.fmt_message(message, "")

            cc_text = ""
            if controller:
                if controller.current_controller is None:
                    cc_text = ""
                else:
                    ms = controller.current_controller.speed_multiplier
                    if ms is not None:
                        s = f', speed: {ms}'
                    else:
                        s = ''
                    cc_text = str(f"i: {controller.current_controller.i}" + s)

            wx.CallAfter(self.frame.update_view, midi_msg_text, cc_text)

            # note off(?)
            if message[0] & 0xf0 == 0x80:
                pass

            if controller:
                # midi cc
                if message[0] & 0xf0 == 0xb0:
                    if message[1] == self.config.pan_x_cc:
                        x_normed = message[2] / 127.0
                        controller.pan_x(x_normed)

                    if message[1] == self.config.pan_y_cc:
                        y_normed = message[2] / 127.0
                        controller.pan_y(y_normed)

                    if message[1] == self.config.control_cc:
                        cc_value = message[2]
                        controller.turn(cc_value)
                        if not controller.freewheeling:
                            self.frame.set_freewheel_text('')

                    if message[1] == self.config.freewheel_cc:
                        self.frame.set_freewheel_text('freewheeling')
                        controller.freewheel()

        except Exception as e:
            traceback.print_exception(e)

    def run(self):
        self.midiin.set_callback(self)
        running = True
        while running:
            item = self.queue.get()
            cmd = item[0]
            if cmd == Command.QUIT:
                running = False
            elif cmd == Command.CHANGE_MIDI_CHANNEL:
                if item[1] == 0:
                    self.midi_channel = None
                else:
                    self.midi_channel = item[1] - 1
            elif cmd == Command.UPDATE_WINDOW:
                name = item[1]
                window = item[2]
                if window is None:
                    if name in self.controllers:
                        del self.controllers[name]
                else:
                    self.controllers[name] = MouseController(self.instruments[window.pattern], window)

                c = self.get_active_controller()
                if c is None:
                    self.frame.set_window_text('No window found')
                else:
                    self.frame.set_window_text(c.window.name)


def main_analyze():
    return analyze("instruments/tal-jupiter.png")


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
    def __init__(self, model, window):
        self.model = model
        self.set_window(window)

        self.mx = 0.0
        self.my = 0.0

        self.freewheeling = False
        self.freewheeling_direction = None
        self.cc_last = None
        self.current_controller = None

        self.last_controller_turned = None
        self.last_controller_accum = 0.0

    def set_window(self, window):
        window_box = window.box
        t = window_to_model(window_box, self.model.box)
        s2w = screen_to_window(window_box)
        t.multiply_right(s2w)
        self.screen_to_model = t
        self.model_to_screen = self.screen_to_model.inverse()
        self.window = window

    def pan_x(self, x_normed):
        self.mx = self.model.box.width * x_normed
        self.current_controller = self.move_mouse()

    def pan_y(self, y_normed):
        invert = True
        if invert:
            y_normed = 1.0 - y_normed
        self.my = self.model.box.height * y_normed
        self.current_controller = self.move_mouse()

    def turn(self, cc_value):
        val = cc_value

        if self.last_controller_turned is not None:
            if self.current_controller is not None:
                if self.last_controller_turned.i != self.current_controller.i:
                    self.last_controller_accum = 0.0

        if self.cc_last is not None:
            delta = val - self.cc_last
            # print(delta)

            if self.freewheeling:
                if self.freewheeling_direction is None:
                    self.freewheeling_direction = delta > 0
                elif self.freewheeling_direction != (delta > 0):
                    self.freewheeling = False
                    self.freewheeling_direction = None

            if not self.freewheeling:
                speed = 1.46

                if self.current_controller is not None:
                    k = self.current_controller.speed_multiplier
                    if k is not None:
                        speed *= k / 100.0

                self.last_controller_accum += delta * speed
                k_whole = int(self.last_controller_accum)
                self.last_controller_accum -= k_whole
                mouse.wheel(k_whole)

        if self.last_controller_turned is None:
            self.last_controller_turned = self.current_controller

        self.cc_last = val

    def freewheel(self):
        self.freewheeling = True
        self.freewheeling_direction = None

    def move_mouse(self):
        c = self.model.find_closest_controller(self.mx, self.my)
        x, y = self.model_to_screen.apply(c.x, c.y)
        mouse.move(int(x), int(y))
        return c



class MainWindow(wx.Frame):
    def __init__(self, parent, title, q, ports, midiin):
        wx.Frame.__init__(self, parent, title=title, size=(200, -1))
        self.queue = q
        self.midiin = midiin

        self.button = wx.Button(self, label="Quit")
        self.Bind(
            wx.EVT_BUTTON, self.handle_button_click, self.button
        )

        self.ports = ports
        self.port_dropdown = wx.ComboBox(self, id=wx.ID_ANY, choices=self.ports, style=wx.CB_READONLY)

        self.connect_button = wx.Button(self, label="Connect")
        self.Bind(
            wx.EVT_BUTTON, self.handle_connect_click, self.connect_button
        )

        channel_choices = ["All"] + [f"Ch. {i}" for i in range(1, 17)]
        self.channel_dropdown = wx.ComboBox(self, id=wx.ID_ANY, choices=channel_choices, style=wx.CB_READONLY)
        self.Bind(wx.EVT_COMBOBOX, self.handle_channel_choice, self.channel_dropdown)

        self.window_text = wx.StaticText(self, label="", style=wx.ALIGN_CENTER)

        self.cc_text = wx.StaticText(self, label="", style=wx.ALIGN_CENTER)

        self.freewheel_text = wx.StaticText(self, label="", style=wx.ALIGN_CENTER)

        self.midi_msg_text = wx.StaticText(self, label="<no MIDI received yet>", style=wx.ALIGN_CENTER)

        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.sizer.Add(self.port_dropdown)
        self.sizer.Add(self.connect_button)
        self.sizer.Add(self.channel_dropdown)
        self.sizer.Add(self.button)
        self.sizer.Add(self.window_text)
        self.sizer.Add(self.freewheel_text)
        self.sizer.Add(self.cc_text)
        self.sizer.Add(self.midi_msg_text)

        self.SetSizer(self.sizer)
        self.SetAutoLayout(True)
        self.Show()

    def update_view(self, midi_msg, cc_text):
        self.midi_msg_text.SetLabel(midi_msg)
        self.cc_text.SetLabel(cc_text)

    def set_window_text(self, text):
        self.window_text.SetLabel(text)

    def set_freewheel_text(self, text):
        self.freewheel_text.SetLabel(text)

    def handle_button_click(self, event):
        self.queue.put((Command.QUIT, None))
        self.Close()
        wx.GetApp().ExitMainLoop()

    def handle_connect_click(self, event):
        v = self.port_dropdown.GetValue()
        if v is not None:
            try:
                i = self.ports.index(v)
                self.midiin.open_port(i)
            except ValueError:
                pass

    def handle_channel_choice(self, event):
        i = event.GetInt()
        self.queue.put((Command.CHANGE_MIDI_CHANNEL, i))


def matches_name(window, name_pattern):
    name = window.get(Quartz.kCGWindowName)
    if name is None:
        return False
    else:
        for pattern in name_patterns:
            if name.find(pattern) > -1:
            # if re.search(pattern, name):
                return True
        return False

class Window:
    def __init__(self, pattern, name, box):
        self.pattern = pattern
        self.name = name
        self.box = box

    def totuple(self):
        return (self.pattern, self.name, self.box)

    def __eq__(self, other):
        if other is None:
            return False
        else:
            return self.totuple() == other.totuple()

def get_windows_mac(name_patterns=["TAL-J-8"]):
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

class WindowPolling(threading.Thread):
    def __init__(self, queue, patterns):
        super(WindowPolling, self).__init__()
        self.patterns = patterns
        self.queue = queue

        self.event = threading.Event()
        self.windows = {}

    def run(self):
        running = True
        while running:
            windows = get_windows_mac(self.patterns)
            for name, window in windows.items():
                if self.windows.get(name) != windows[name]:
                    self.queue.put((Command.UPDATE_WINDOW, name, windows[name]))
                    self.windows[name] = windows[name]

            todelete = []
            for name in self.windows:
                if windows.get(name) is None:
                    self.queue.put((Command.UPDATE_WINDOW, name, None))
                    todelete.append(name)

            for name in todelete:
                del self.windows[name]

            time.sleep(1)
            if self.event.is_set():
                running = False

class Config:
    def __init__(self, pan_x_cc, pan_y_cc, control_cc, freewheel_cc):
        self.pan_x_cc = pan_x_cc
        self.pan_y_cc = pan_y_cc
        self.control_cc = control_cc
        self.freewheel_cc = freewheel_cc

    @staticmethod
    def load(path):
        with open(path, 'r') as f:
            d = yaml.safe_load(f.read())
        pan_x_cc = d['pan_x']['cc']
        pan_y_cc = d['pan_y']['cc']
        control_cc = d['control']['cc']
        freewheel_cc = d['freewheel']['cc']
        return Config(pan_x_cc, pan_y_cc, control_cc, freewheel_cc)

def main_2():
    d = main_analyze()
    print(yaml.dump(d, sort_keys=False))

def load_instruments():
    root_dir = datadir()
    filenames = glob.glob('inst-*.yaml', root_dir=root_dir)
    d = {}
    for filename in filenames:
        p = os.path.join(root_dir, filename)
        inst = Instrument.load(p)
        d[inst.pattern] = inst
    return d

def open_directory(path):
    if platform.system() == "Windows":
        os.startfile(path)
    elif platform.system() == "Darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])

def main():
    initialize_config()

    config = Config.load(userfile('config.yaml'))

    q = queue.Queue()

    app = wx.App(False)

    midiin = rtmidi.MidiIn()
    ports = midiin.get_ports()

    frame = MainWindow(None, "pointer-cc", q, ports, midiin)

    instruments = load_instruments()

    polling = WindowPolling(q, list(instruments.keys()))
    polling.start()

    dispatcher = Dispatcher(midiin, q, frame, instruments, config)
    dispatcher.start()

    app.MainLoop()

    polling.event.set()
    polling.join()

    dispatcher.join()

if __name__ == '__main__':
    main()
