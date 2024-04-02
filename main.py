import Quartz
from PIL import Image
import wx
import time
import os
import time
import webbrowser
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
import tomlkit
import copy
import sys
import re
import appdirs
from enum import Enum

app_name = "pointer-cc"
app_author = "smatting"
app_url = "https://github.com/smatting/pointer-cc/"

InternalCommand = Enum('InternalCommand', ['QUIT', 'CHANGE_MIDI_CHANNEL', 'UPDATE_WINDOW'])

class Bijection:
    def __init__(self, a_name, b_name, atob_pairs):
        self._d_atob = dict(atob_pairs)
        self._d_btoa = dict([(b, a) for (a, b) in atob_pairs])

        setattr(self, a_name, self._a)
        setattr(self, b_name, self._b)

    def _a(self, b):
        v = self._d_btoa[b]
        if v is None:
            knowns = ", ".join([f"\"{str(k)}\"" for k in self._d_btoa.keys()])
            msg = f'Unknown value "{str(b)}", known values are: {knowns}.' 
            raise ConfigError(msg)
        return v

    def _b(self, a):
        v = self._d_atob[a]
        if v is None:
            knowns = ", ".join([f"\"{str(k)}\"" for k in self._d_atob.keys()])
            msg = f'Unknown value "{str(a)}", known values are: {knowns}.' 
            raise ConfigError(msg)
        return v

def datadir():
    return appdirs.user_data_dir(app_name, app_author)

def userfile(p):
    import tomlkit
    return os.path.join(datadir(), p)

def configfile():
    return userfile('config.txt')

def initialize_config():
    os.makedirs(datadir(), exist_ok=True)
    cf = configfile()
    if not os.path.exists(cf):
        with open(cf, 'w') as f:
            conf = default_config()
            f.write(conf.as_string())

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

ControlType = Enum('ControlType', ['WHEEL', 'DRAG','CLICK'])


class ConfigError(Exception):
    def __init__(self, msg):
        self.msg = msg
        super(ConfigError, self).__init__(self.msg)

def in_context(f, context):
    try:
        return f()
    except ConfigError as ce:
        ce.msg = ce.msg + f", {context}"
        raise ce

control_type_bij = Bijection('str', 'enum', [('wheel', ControlType.WHEEL), ('drag', ControlType.DRAG), ('click', ControlType.CLICK)])


#TODO: rename Control
class Controller:
    def __init__(self, type_, i, x, y, speed, m):
        self.type_ = type_
        self.i = i
        self.x = x
        self.y = y
        self.speed = speed
        self.m = m

    def __eq__(self, other):
        return self.i == other.i

    @staticmethod
    def parse(d, i, default_wheel_speed, default_drag_speed, default_type, context):
        try:
            x_s = expect_value(d, "x")
            x = expect_decimal(x_s)

            y_s = expect_value(d, "y")
            y = expect_decimal(y_s)

            type_= maybe(d.get('type'), control_type_bij.enum, default_type)
        
            m = maybe(d.get('m'), expect_float, 1.0)

            if type_ == ControlType.WHEEL:
                speed = default_wheel_speed
            else:
                speed = default_drag_speed

            return Controller(type_, i, x, y, speed, m)

        except ConfigError as ce:
            ce.msg = ce.msg + f", {context}"
            raise ce

def maybe(mv, f, default):
    if mv is None:
        return default
    else:
        return f(mv)

class Instrument:
    def __init__(self, pattern, box, controllers):
        self.pattern = pattern
        self.box = box
        self.controllers = controllers

    @staticmethod
    def load(path, context):
        try:
            controls = []

            with open(path, 'r') as f:
                d = tomlkit.load(f)

            dimensions = expect_value(d, 'dimensions')
            width_s = expect_value(dimensions, 'width')
            width = expect_decimal(width_s)
            height_s = expect_value(dimensions, 'height')
            height = expect_decimal(height_s)

            box = Box(0, width, 0, height)

            dc = expect_value(d, 'default_control')
            type_s = expect_value(dc, "type")
            default_type = control_type_bij.enum(type_s)

            wheel_speed_s = expect_value(dc, "wheel_speed")
            default_wheel_speed = in_context(lambda: expect_float(wheel_speed_s), 'wheel_speed')

            drag_speed_s = expect_value(dc, "drag_speed")
            default_drag_speed = in_context(lambda: expect_float(drag_speed_s), 'drag_speed')

            controls_unparsed = expect_value(d, 'controls')
            for control_id, v in controls_unparsed.items():
                context = "for control {control_id}"
                c = Controller.parse(v, control_id, default_wheel_speed, default_drag_speed, default_type, context)
                controls.append(c)

            window = expect_value(d, 'window')
            pattern = expect_value(window, 'contains')

            return Instrument(pattern, box, controls)

        except ConfigError as ce:
            raise ConfigError(ce.msg + f", {context}")


    def find_closest_controller(self, mx, my):
        c_best = None
        d_best = math.inf
        for c in self.controllers:
            d = math.pow(c.x - mx, 2.0) + math.pow(c.y - my, 2.0)
            if d < d_best:
                c_best = c
                d_best = d
        return c_best

def analyze(doc, filename, marker_color=(255, 0, 255, 255)):
    im = Image.open(filename)

    dimensions = tomlkit.table()
    dimensions.add('width', im.width)
    dimensions.add('height', im.height)
    doc.add('dimensions', dimensions)

    controls = tomlkit.table()
    for i, box in enumerate(find_markings(im, marker_color)):
        x, y = box.center()
        c = tomlkit.table() 
        c.add('x', x)
        c.add('y', y)
        c.add('m', 1.0)
        controls.add(f'c{i+1}', c)

    doc.add('controls', controls)

    return doc

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
                    ms = controller.current_controller.m
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
                if message[0] & 0xf0 == 0xb0:
                    for binding in self.config.bindings:
                        if binding.cc == message[1]:
                            if binding.command == Command.PAN_X:
                                x_normed = message[2] / 127.0
                                controller.pan_x(x_normed)

                            elif binding.command == Command.PAN_X_INV:
                                x_normed = message[2] / 127.0
                                controller.pan_x(1.0 - x_normed)

                            elif binding.command == Command.PAN_Y:
                                y_normed = message[2] / 127.0
                                controller.pan_y(y_normed)

                            elif binding.command == Command.PAN_Y_INV:
                                y_normed = message[2] / 127.0
                                controller.pan_y(1.0 - y_normed)

                            elif binding.command == Command.ADJUST_CONTROL:
                                cc = message[2]
                                controller.turn(cc)

                            elif binding.command == Command.FREEWHEEL:
                                controller.freewheel()

        except Exception as e:
            traceback.print_exception(e)

    def run(self):
        self.midiin.set_callback(self)
        running = True
        while running:
            item = self.queue.get()
            cmd = item[0]
            if cmd == InternalCommand.QUIT:
                running = False
            elif cmd == InternalCommand.CHANGE_MIDI_CHANNEL:
                if item[1] == 0:
                    self.midi_channel = None
                else:
                    self.midi_channel = item[1] - 1
            elif cmd == InternalCommand.UPDATE_WINDOW:
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


def generate_instrument(outfile, screenshot_file, window_contains, control_type_s):
    doc = tomlkit.document()

    doc.add(tomlkit.comment('This instrument configuration file is of TOML format (https://toml.io). See the pointer-cc documentation for details.'))

    window = tomlkit.table()
    window.add('contains', window_contains)

    doc.add('window', window)

    default_control = tomlkit.table()
    default_control.add('type', control_type_s)
    default_control.add('wheel_speed', 1.0)
    default_control.add('drag_speed', 1.0)
    doc.add('default_control', default_control)

    analyze(doc, screenshot_file)

    with open(outfile, 'w') as f:
        f.write(doc.as_string())

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
        self.current_controller = None

        self.freewheeling = False
        self.freewheeling_direction = None

        self.last_controller_turned = None
        self.last_cc = None
        self.last_controller_accum = 0.0
        self.dragging = False
        
        self.click_sm = ClickStateMachine(0.5, 2)
        
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
        self.current_controller = self.move_pointer_to_closest()

    def pan_y(self, y_normed):
        self.my = self.model.box.height * y_normed
        self.current_controller = self.move_pointer_to_closest()

    def turn(self, cc):
        screen_x, screen_y = mouse.get_position()
        if not self.dragging:
            self.mx, self.my = self.screen_to_model.apply(screen_x, screen_y)

        self.current_controller = self.model.find_closest_controller(self.mx, self.my)
        
        if self.last_controller_turned is not None:
            if self.last_controller_turned != self.current_controller:
                self.click_sm.reset()
                self.last_cc = cc
                self.last_controller_accum = 0.0

        if self.last_cc is None:
            self.last_cc = cc

        delta = cc - self.last_cc

        if self.freewheeling:
            if self.freewheeling_direction is None:
                self.freewheeling_direction = delta > 0
            elif self.freewheeling_direction != (delta > 0):
                self.freewheeling = False
                self.freewheeling_direction = None

        else:
            if self.current_controller is not None:
                m = self.current_controller.m
                speed = self.current_controller.speed * self.current_controller.m

            self.last_controller_accum += delta * speed
            k_whole = int(self.last_controller_accum)
            self.last_controller_accum -= k_whole

            if self.current_controller.type_ == ControlType.WHEEL:
                mouse.wheel(k_whole)
            elif  self.current_controller.type_ == ControlType.DRAG:
                if self.dragging:
                    pass
                else:
                    mouse.press()
                    self.dragging = True
                mouse.move(screen_x, screen_y - k_whole)
            elif self.current_controller.type_ == ControlType.CLICK:
                is_click = self.click_sm.on_cc(cc, time.time())
                print('is_click', is_click, repr(self.click_sm))


        self.last_controller_turned = self.current_controller
        self.last_cc = cc

    def freewheel(self):
        self.freewheeling = True
        self.freewheeling_direction = None

    def move_pointer_to_closest(self):
        c = self.model.find_closest_controller(self.mx, self.my)
        #
        # if self.last_controller_turned is not None:
        #     if c != self.last_controller_turned:

        if self.dragging:
            mouse.release()
            self.dragging = False

        x, y = self.model_to_screen.apply(c.x, c.y)
        mouse.move(int(x), int(y))
        return c



class MainWindow(wx.Frame):
    def __init__(self, parent, title, q, ports, midiin):
        wx.Frame.__init__(self, parent, title=title, size=(200, -1))

        self.Bind(wx.EVT_CLOSE, self.on_close)


        self.queue = q
        self.midiin = midiin

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

        filemenu= wx.Menu()

        about = filemenu.Append(wx.ID_ABOUT, "&About"," Information about this program")
        self.Bind(wx.EVT_MENU, self.on_help, about)

        open_config = filemenu.Append(wx.ID_ANY, "&Open Config Dir"," Open configuartion directory")
        self.Bind(wx.EVT_MENU, self.on_open_config, open_config)

        exitMenutItem = filemenu.Append(wx.ID_EXIT,"E&xit"," Terminate the program")
        self.Bind(wx.EVT_MENU, self.on_exit, exitMenutItem)

        helpmenu = wx.Menu()
        get_help = helpmenu.Append(wx.ID_HELP, "Get &Help", "Get Help")
        self.Bind(wx.EVT_MENU, self.on_help, get_help)

        menuBar = wx.MenuBar()
        menuBar.Append(filemenu,"&File") # Adding the "filemenu" to the MenuBar
        menuBar.Append(helpmenu,"&Help") # Adding the "filemenu" to the MenuBar
        self.SetMenuBar(menuBar)  # Adding the MenuBar to the Frame content.

        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.sizer.Add(self.port_dropdown)
        self.sizer.Add(self.connect_button)
        self.sizer.Add(self.channel_dropdown)
        self.sizer.Add(self.window_text)
        self.sizer.Add(self.freewheel_text)
        self.sizer.Add(self.cc_text)
        self.sizer.Add(self.midi_msg_text)

        self.SetSizer(self.sizer)
        self.SetAutoLayout(True)
        self.Show()

    def on_help(self, event):
        webbrowser.open(app_url)

    def on_open_config(self, event):
        open_directory(datadir())

    def on_close(self, event):
        self.queue.put((InternalCommand.QUIT, None))
        wx.GetApp().ExitMainLoop()
        event.Skip()

    def update_view(self, midi_msg, cc_text):
        self.midi_msg_text.SetLabel(midi_msg)
        self.cc_text.SetLabel(cc_text)

    def set_window_text(self, text):
        self.window_text.SetLabel(text)

    def set_freewheel_text(self, text):
        self.freewheel_text.SetLabel(text)

    def on_exit(self, event):
        self.Close()

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
        self.queue.put((InternalCommand.CHANGE_MIDI_CHANNEL, i))


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
                    self.queue.put((InternalCommand.UPDATE_WINDOW, name, windows[name]))
                    self.windows[name] = windows[name]

            todelete = []
            for name in self.windows:
                if windows.get(name) is None:
                    self.queue.put((InternalCommand.UPDATE_WINDOW, name, None))
                    todelete.append(name)

            for name in todelete:
                del self.windows[name]

            time.sleep(1)
            if self.event.is_set():
                running = False


def default_config():
    doc = tomlkit.document()

    doc.add(tomlkit.comment('The pointer-cc configuration file is of TOML format (https://toml.io). See the pointer-cc documentation for details.'))

    bindings = tomlkit.table()

    t1 = tomlkit.table()
    t1.add('command', 'pan-x')
    t1.add('cc', 77)
    bindings.add('1', t1)

    t2 = tomlkit.table()
    t2.add('command', 'pan-y')
    t2.add('cc', 78)
    bindings.add('2', t2)

    t3 = tomlkit.table()
    t3.add('command', 'adjust-control')
    t3.add('cc', 79)
    bindings.add('3', t3)

    t4 = tomlkit.table()
    t4.add('command', 'freewheel')
    t4.add('cc', 80)
    bindings.add('4', t4)

    doc.add('bindings', bindings)
    return doc

Command = Enum('Command', ['PAN_X', 'PAN_X_INV', 'PAN_Y', 'PAN_Y_INV', 'ADJUST_CONTROL', 'FREEWHEEL'])

cmd_str = Bijection('command', 'str', [(Command.PAN_X, 'pan-x'),
                                       (Command.PAN_X_INV, 'pan-x-inv'),
                                       (Command.PAN_Y, 'pan-y'),
                                       (Command.PAN_Y_INV, 'pan-y-inv'),
                                       (Command.ADJUST_CONTROL, 'adjust-control'),
                                       (Command.FREEWHEEL, 'freewheel')
                                       ])

class ClickStateMachine:
    def __init__(self, timeout_secs, delta_cc):
        self.setting_timeout_secs = timeout_secs
        self.setting_delta_cc = delta_cc

        self.start_cc = None
        self.start_t = None
        self.down_cc = None
        self.isdown = False


    def __repr__(self):
        return str((self.start_cc, self.start_t, self.down_cc, self.isdown))

    def on_time(self, t):
        return self.on_cc(None, t)

    def reset(self):
        self.start_cc = None
        self.start_t = None
        self.down_cc = None
        self.isdown = False

    def on_cc(self, cc_value, t):
        '''
        cc_value may be empty
        '''
        event_start = False
        event_timeout = False
        event_moveup = False
        event_movedown = False
        event_click = False

        # self.start_cc state machine
        if self.start_cc is None:
            if cc_value is not None:
                event_start = True
                self.start_cc = cc_value
                self.start_t = t
        else:
            if t - self.start_t > self.setting_timeout_secs:
                self.start_cc = None
                event_timeout = True
            if self.start_cc is not None:
                if cc_value is not None:
                    if cc_value <= self.start_cc - self.setting_delta_cc:
                        event_movedown = True

        # self.down_cc state machine
        if self.down_cc is None:
            if event_movedown and cc_value is not None:
                self.down_cc = cc_value
        else:
            if event_timeout:
                self.down_cc = None
            if cc_value is not None and self.down_cc is not None:
                if cc_value >= self.down_cc + self.setting_delta_cc:
                    event_moveup = True

        # self.isup state machine
        if not self.isdown:
            if event_movedown:
                self.isdown = True
        else:
            if event_moveup:
                event_click = True
            if event_timeout:
                self.isown = False

        if event_click:
            self.reset()

        return event_click

class Binding:
    def __init__(self, command, cc):
        self.command = command
        self.cc = cc

    @staticmethod
    def parse(d, context):
        try:
            command_name = expect_value(d, 'command')
            cmd = cmd_str.command(command_name)
            cc_s = expect_value(d, 'cc')
            cc = expect_decimal(cc_s)
            return Binding(cmd, cc)
        except ConfigError as ce:
            ce.msg = ce.msg + f", {context}"
            raise ce

def expect_value(d, k):
    v = d.get(k)
    if v is not None:
        return v
    else:
        raise ConfigError(f'Expected key: \"{k}\"')

def expect_float(v):
    try:
        return float(v)
    except:
        raise ConfigError(f'Not a float: \"{str(v)}\"')

def expect_decimal(s):
    try:
        return int(s)
    except:
        raise ConfigError(f"Not a decimal: \"{s}\"")

class Config:
    def __init__(self, bindings):
        self.bindings = bindings

    @staticmethod
    def load(path):
        result = []
        with open(path, 'r') as f:
            d = tomlkit.load(f)
            bindings = expect_value(d, 'bindings')
            for bi, b in bindings.items():
                bing = Binding.parse(b, f'parsing binding \"{bi}\"')
                result.append(bing)
            return Config(result)

def load_instruments():
    root_dir = datadir()
    filenames = glob.glob('inst-*.txt', root_dir=root_dir)
    d = {}
    for filename in filenames:
        p = os.path.join(root_dir, filename)
        inst = Instrument.load(p, filename)
        d[inst.pattern] = inst
    return d

def open_directory(path):
    if platform.system() == "Windows":
        os.startfile(path)
    elif platform.system() == "Darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])

def request_access():
    Quartz.CGRequestPostEventAccess()
    Quartz.CGRequestScreenCaptureAccess()

def main():
    initialize_config()

    config = Config.load(userfile('config.txt'))

    request_access()
    Quartz.CGPreflightScreenCaptureAccess()

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

def main_analyze():
    generate_instrument('instruments/inst-tal-j-8.txt', 'instruments/tal-jupiter.png', 'TAL-J-8', 'wheel')
    generate_instrument('instruments/inst-prophet-5-v.txt', 'instruments/prophet-5-v-marked.png', 'Prophet-5 V', 'drag')

if __name__ == '__main__':
    # main_analyze()
    main()
