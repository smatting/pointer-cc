from PIL import Image
import wx
import wx.lib.delayedresult
import requests
import time
import importlib.resources
import datetime
import http.client
import urllib
import semver
import textwrap
import pyperclip
import traceback
import os
import time
import webbrowser
import subprocess
import platform
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
from pointercc.core import Window, Box, make_box
from pointercc.version import version
if sys.platform == "win32":
    import pointercc.win32 as core_platform
elif sys.platform == "darwin":
    import pointercc.darwin as core_platform
else:
    raise NotImplemnted(f'Platform {sys.platform} not supported')

app_name = "pointer-cc"
app_author = "smatting"
app_url = "https://github.com/smatting/pointer-cc/"
app_email = "pointer-cc@posteo.com"
url_latest = "https://raw.githubusercontent.com/smatting/pointer-cc/main/latest_release.txt"

InternalCommand = Enum('InternalCommand', ['QUIT', 'CHANGE_MIDI_PORT',  'CHANGE_MIDI_CHANNEL', 'UPDATE_WINDOW', 'RELOAD_ALL_CONFIGS'])

class Bijection:
    def __init__(self, a_name, b_name, atob_pairs):
        self._d_atob = dict(atob_pairs)
        self._d_btoa = dict([(b, a) for (a, b) in atob_pairs])

        setattr(self, a_name, self._a)
        setattr(self, b_name, self._b)

    def _a(self, b):
        return self._d_btoa.get(b)

    def _b(self, a):
        return self._d_atob.get(a)

def datadir():
    return appdirs.user_data_dir(app_name, app_author)

def userfile(p):
    return os.path.join(datadir(), p)

def configfile():
    return userfile('config.txt')

def initialize_config():
    os.makedirs(datadir(), exist_ok=True)
    cf = configfile()
    if not os.path.exists(cf):
        with open(cf, 'w') as f:
            conf = default_config_toml()
            f.write(conf.as_string())

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

def squared_dist(p1, p2):
    x1, y1 = p1
    x2, y2 = p2
    return (x1 - x2)**2 + (y1 - y2)**2

class Control:
    def __init__(self, type_, i, x, y, speed, m, time_resolution):
        self.type_ = type_
        self.i = i
        self.x = x
        self.y = y
        self.speed = speed
        self.m = m
        self.time_resolution = time_resolution

    def __eq__(self, other):
        return self.i == other.i

    def __str__(self):
        type_str = control_type_bij.str(self.type_)
        return f'{self.i}({type_str})'

    @staticmethod
    def parse(d, i, default, context):
        try:
            x_s = expect_value(d, "x")
            x = expect_int(x_s, "x")

            y_s = expect_value(d, "y")
            y = expect_int(y_s, "y")

            default_type = control_type_bij.enum(default['type'])
            type_= maybe(d.get('type'), control_type_bij.enum, default_type)
        
            m = maybe(d.get('m'), lambda s: expect_float(s, 'm'), 1.0)

            if type_ == ControlType.WHEEL:
                d = default['wheel']
                default_speed = d['speed']
                default_time_resolution = d['time_resolution']
            else:
                d = default['drag']
                default_speed = d['speed']
                default_time_resolution = 100

            time_resolution = maybe(d.get('time_resolution'), lambda s: expect_int(s, 'time_resolution'), default_time_resolution)
            speed = maybe(d.get('speed'), lambda s: expect_float(s, 'speed'), default_speed)

            return Control(type_, i, x, y, speed, m, time_resolution)

        except ConfigError as ce:
            ce.msg = ce.msg + f", {context}"
            raise ce

def maybe(mv, f, default):
    if mv is None:
        return default
    else:
        return f(mv)

class Instrument:
    def __init__(self, pattern, box, controls):
        self.pattern = pattern
        self.box = box
        self.controls = controls

    @staticmethod
    def load(path, instrument_context):
        try:
            controls = []

            with open(path, 'r') as f:
                d = tomlkit.load(f)

            dimensions = expect_value(d, 'dimensions')
            width_s = expect_value(dimensions, 'width', 'dimensions')
            width = expect_int(width_s, 'dimensions.width')
            height_s = expect_value(dimensions, 'height', 'dimensions')
            height = expect_int(height_s, 'dimensions.height')

            box = Box(0, width, 0, height)

            default = expect_value(d, 'default')
            type_s = expect_value(default, 'type', 'default')

            default_wheel = expect_value(default, 'wheel', 'default')
            expect_value(default_wheel, 'speed', 'default.wheel')
            expect_value(default_wheel, 'time_resolution', 'default.wheel')

            default_drag = expect_value(default, 'drag', 'default')
            expect_value(default_drag, 'speed', 'default.drag')

            controls_unparsed = expect_value(d, 'controls')
            for control_id, v in controls_unparsed.items():
                context = f"in control \"{control_id}\""
                c = Control.parse(v, control_id, default, context)
                controls.append(c)

            window = expect_value(d, 'window')
            pattern = expect_value(window, 'contains', 'window')

            return Instrument(pattern, box, controls)

        except tomlkit.exceptions.TOMLKitError as tk:
            msg = f'Not a valid TOML file: {tk}'
            raise ConfigError(msg + f" in \"{instrument_context}\"")

        except ConfigError as ce:
            raise ConfigError(ce.msg + f" in \"{instrument_context}\"")


    def find_closest_control(self, mx, my):
        c_best = None
        d_best = math.inf
        for c in self.controls:
            d = math.pow(c.x - mx, 2.0) + math.pow(c.y - my, 2.0)
            if d < d_best:
                c_best = c
                d_best = d
        return c_best

def overlaps(p1, p2):
    if p1[0] > p2[0]:
        p1, p2 = p2, p1
    return p2[0] <= p1[1]

def find_overlapping(spans, p):
    for p_span in spans:
        if overlaps(p_span, p):
            return spans[p_span]
    return None

def color_diff(c1, c2):
    return max(abs(c1[0] - c2[0]), abs(c1[1] - c2[1]), abs(c1[2] - c2[2]))

def find_markings(im, marker_color, threshold, update_percent):
    boxes = []
    spans_last = {}
    for y in range(0, im.height):
        update_percent(int(100*y//im.height))
        xmin = None
        xmax = None
        spans = {}
        for x in range(0, im.width):
            color = im.getpixel((x, y))
            diff = color_diff(marker_color, color)
            in_marker = diff <= threshold
            if in_marker:
                if xmin is None:
                    xmin = x
                xmax = x

            if (not in_marker and xmax is not None) or (in_marker and x == im.width - 1):
                b = find_overlapping(spans_last, (xmin, xmax))
                if b is not None:
                    b.ymax = y
                    b.xmin = min(b.xmin, xmin)
                    b.xmax = max(b.xmax, xmax)
                else:
                    b = Box(xmin, xmax, y, y)
                    boxes.append(b)
                spans[(xmin, xmax)] = b
                xmin = None
                xmax = None
        spans_last = spans
    return boxes

def analyze(self, filename, marker_color, threshold):
    d = {}
    im = Image.open(filename)

    dimensions = {}
    d['dimensions'] = dimensions
    dimensions['width'] = im.width
    dimensions['height'] = im.height

    def update_percent(i):
        wx.CallAfter(self.update_progress, i)

    controls = {}
    d['controls'] = controls
    markings = find_markings(im, marker_color, threshold, update_percent)
    for i, box in enumerate(markings):
        c = {}
        x, y = box.center()
        c['x'] = x
        c['y'] = y
        controls[f'c{i+1}'] = c
    return d

def toml_instrument_config(extract_result, window_contains, control_type):
    doc = tomlkit.document()
    doc.add(tomlkit.comment(f'The is pointer-cc instrument configuration file. Please edit it to change it, then pick "Reload Config" from the menu for your changes to take effect. See the pointer-cc documentation for details: {app_url}.'))

    window = tomlkit.table()
    window.add('contains', window_contains)
    doc.add('window', window)

    dimensions = tomlkit.table()
    dimensions.add('width', extract_result['dimensions']['width'])
    dimensions.add('height', extract_result['dimensions']['height'])
    doc.add('dimensions', dimensions)

    default_control = tomlkit.table()
    default_control.add('type', control_type)

    default_drag = tomlkit.table()
    default_drag.add('speed', 1.0)
    default_control.add('drag', default_drag)

    default_wheel = tomlkit.table()
    default_wheel.add('speed', 1.0)
    default_wheel.add('time_resolution', 100)
    default_control.add('wheel', default_wheel)

    doc.add('default', default_control)

    controls = tomlkit.table()
    for cid, c in extract_result['controls'].items():
        control = tomlkit.table()
        control.add('x', c['x'])
        control.add('y', c['y'])
        control.add('m', 1.0)
        controls.add(cid, control)
    doc.add('controls', controls)
    return doc

midi_type_bij = Bijection('midi', 'display', [(0x80, "NOTEOFF"), (0x90, "NOTEON"), (0xA0, "KPRESS"), (0xB0, "CC"), (0xC0, "PROG"), (0xC0, "PROG"), (0xD0, "CHPRESS"), (0xE0, "PBEND"), (0xF0, "SYSEX")])

def fmt_hex(i):
    s = hex(i)[2:].upper()
    prefix = "".join(((2 - len(s)) * ["0"]))
    return prefix + s

def fmt_midi(msg):
    if len(msg) == 0:
        return None
    else:
        parts = []
        t = midi_type_bij.display(msg[0] & 0xf0)
        if t is not None:
            chan = (msg[0] & 0x0f) + 1
            parts.append(f'Ch.{chan}')
            parts.append(t)
        else:
            parts.append(fmt_hex(msg[0]))
        parts = parts + [str(i) for i in msg[1:]]
        return ' '.join(parts)

class Dispatcher(threading.Thread):
    def __init__(self, midiin, queue, frame):
        super(Dispatcher, self).__init__()
        self.midiin = midiin
        self.queue = queue
        self.frame = frame
        self.port_name = None
        self.midi_channel= 0
        self.controllers = {}
        self.polling = None
        self.config = default_config()
        self.instruments = {}
        self.reload_all_configs()

    def reload_all_configs(self):
        try:
            config = load_config()
        except ConfigError as e:
            msg = f'Configuration error: {e}'
            wx.CallAfter(self.frame.show_error, msg)
        else:
            instruments, inst_exceptions = load_instruments()

            self.config = config
            self.set_instruments(instruments)

            if config.preferred_midi_port is not None:
                self.queue.put((InternalCommand.CHANGE_MIDI_PORT, config.preferred_midi_port, False))

            if config.preferred_midi_channel is not None:
                self.queue.put((InternalCommand.CHANGE_MIDI_CHANNEL, config.preferred_midi_channel))

            self.stop_window_polling()
            self.start_window_polling()

            if len(inst_exceptions) > 0:
                msgs = []
                for e in inst_exceptions:
                    msgs.append(str(e))
                msg = 'Configuration error: ' + ' '.join(msgs)
                wx.CallAfter(self.frame.show_error, msg)

    def get_active_controller(self):
        if len(self.controllers) == 0:
            return None

        elif len(self.controllers) == 1:
            return list(self.controllers.values())[0]

        else:

            x, y = mouse.get_position()

            def sort_key(controller):
                box = controller.window.box
                key_contains = 0 if box.contains_point(x, y) else 1
                key_distance = squared_dist(box.center(), (x, y))
                tpl = (key_contains, key_distance)
                return tpl

            controllers = list(self.controllers.values())
            controllers.sort(key=sort_key)
            if len(controllers) > 0:
                return controllers[0]

    def __call__(self, event, data=None):
        try:
            message, deltatime = event

            ch = message[0] & 0x0f
            ignore = False
            if self.midi_channel != 0:
                if ch != self.midi_channel - 1:
                    return
    
            controller = self.get_active_controller()

            midi_msg_text_parts = []
            m = fmt_midi(message)
            if m is not None:
                midi_msg_text_parts.append(m)

            # note off(?)
            if message[0] & 0xf0 == 0x80:
                pass

            ctrl_info_parts = []
            if controller:
                if controller.current_control is not None:
                    ctrl_info_parts.append(str(controller.current_control))

                if controller.freewheeling:
                    ctrl_info_parts.append('(freewheeling)')

                if message[0] & 0xf0 == 0xb0:
                    for binding in self.config.bindings:
                        if binding.cc == message[1]:

                            c = cmd_str.str(binding.command)
                            midi_msg_text_parts.append(f'({c})')

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
                                status = controller.turn(cc)
                                if status is not None:
                                    ctrl_info_parts.append(status)

                            elif binding.command == Command.FREEWHEEL:
                                controller.freewheel()

            ctrl_info = ' '.join(ctrl_info_parts)
            midi_msg_text = ' '.join(midi_msg_text_parts)
            wx.CallAfter(self.frame.update_view, midi_msg_text, ctrl_info)

        except Exception as e:
            traceback.print_exception(e)
    
    def set_instruments(self, instruments):
        if len(instruments) == 0:
            msg = "No instruments configured, please read the docs"
        else:
            msg = f'{len(instruments)} instruments configured' 

        self.instruments = instruments
        wx.CallAfter(self.frame.set_window_text, msg)

    def start_window_polling(self):
        self.polling = WindowPolling(self.queue, list(self.instruments.keys()))
        self.polling.start()

    def stop_window_polling(self):
        if self.polling:
            self.polling.event.set()
            self.polling.join()

    def run(self):
        self.midiin.set_callback(self)

        running = True
        while running:
            item = self.queue.get()
            cmd = item[0]
            if cmd == InternalCommand.QUIT:
                running = False
                self.stop_window_polling()

            elif cmd == InternalCommand.CHANGE_MIDI_CHANNEL:
                self.midi_channel = item[1]
                if self.midiin.is_port_open() and self.port_name is not None:
                    self.config.set_preferred_midi(self.port_name, self.midi_channel)

            elif cmd == InternalCommand.CHANGE_MIDI_PORT:
                port_name = item[1]
                triggered_by_user = item[2]
                (success, exc) = open_midi_port(self.midiin, port_name)
                if success:
                    self.port_name = port_name
                    self.config.set_preferred_midi(port_name, self.midi_channel)
                    self.midiin.set_callback(self)
                    wx.CallAfter(self.frame.set_midi_selection, self.port_name, self.midi_channel)
                else:
                    if triggered_by_user:
                        msg = f"Could not open MIDI port \"{port_name}\""
                        wx.CallAfter(self.frame.show_error, msg)
                        # TODO:
                        # wx.CallAfter(self.frame.set_midi_selection, None, None)

            elif cmd == InternalCommand.UPDATE_WINDOW:
                name = item[1]
                window = item[2]
                if window is None:
                    if name in self.controllers:
                        del self.controllers[name]
                else:
                    self.controllers[name] = InstrumentController(self.instruments[window.pattern], window)

                c = self.get_active_controller()
                if c is None:
                    self.frame.set_window_text('No window found')
                else:
                    self.frame.set_window_text(c.window.name)

            elif cmd == InternalCommand.RELOAD_ALL_CONFIGS:
                self.reload_all_configs()

def unit_affine():
    return Affine(1.0, 1.0, 0.0, 0.0)

# affine transform that can be scaling and translation
class Affine:
    def __init__(self, sx, sy, dx, dy):
        self.sx = sx
        self.sy = sy
        self.dx = dx
        self.dy = dy

    def inverse(self):
        small = 1e-2
        if abs(self.sx) < small or abs(self.sy) < small:
            return unit_affine()
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
    if model_box.width == 0 or model_box.height == 0:
        return unit_affine()
    sx = window_box.width / model_box.width
    sy = window_box.height / model_box.height
    s = min(sx, sy)
    excess_x = window_box.width - s * model_box.width
    excess_y = window_box.height - s * model_box.height
    return Affine(s, s, excess_x / 2.0, excess_y)

def window_to_model(window_box, model_box):
    return model_to_window(window_box, model_box).inverse()

class InstrumentController:
    def __init__(self, instrument, window):
        self.instrument = instrument
        self.set_window(window)

        self.mx = 0.0
        self.my = 0.0
        self.current_control = None

        self.freewheeling = False
        self.freewheeling_direction = None

        self.last_cc = None
        self.last_control = None
        self.last_control_accum = 0.0
        self.last_t = None
        self.dragging = False
        
        self.click_sm = ClickStateMachine(1.0, 2)
        
    def set_window(self, window):
        window_box = window.box
        t = window_to_model(window_box, self.instrument.box)
        s2w = screen_to_window(window_box)
        t.multiply_right(s2w)
        self.screen_to_instrument = t
        self.instrument_to_screen = self.screen_to_instrument.inverse()
        self.window = window

    def pan_x(self, x_normed):
        self.mx = self.instrument.box.width * x_normed
        self.current_control = self.move_pointer_to_closest()

    def pan_y(self, y_normed):
        self.my = self.instrument.box.height * y_normed
        self.current_control = self.move_pointer_to_closest()

    def turn(self, cc):
        status = None

        screen_x, screen_y = mouse.get_position()
        if not self.dragging:
            self.mx, self.my = self.screen_to_instrument.apply(screen_x, screen_y)

        self.current_control = self.instrument.find_closest_control(self.mx, self.my)
        
        if self.last_control is not None:
            if self.current_control != self.last_control:
                self.click_sm.reset()
                self.last_cc = cc
                self.last_control_accum = 0.0
                self.last_t = None

        if self.last_cc is None:
            self.last_cc = cc

        delta = cc - self.last_cc
        t = time.time()

        if self.freewheeling:
            if self.freewheeling_direction is None:
                self.freewheeling_direction = delta > 0
            elif self.freewheeling_direction != (delta > 0):
                self.freewheeling = False
                self.freewheeling_direction = None

        else:
            if self.current_control is not None:
                m = self.current_control.m
                speed = self.current_control.speed * self.current_control.m

            self.last_control_accum += delta * speed

            if self.current_control.type_ == ControlType.WHEEL:
                if self.last_t is None:
                    self.last_t = t
                else:
                    time_delta = t - self.last_t
                    time_delta_res = 1.0 / self.current_control.time_resolution
                    if time_delta > time_delta_res:
                        if time_delta < 5 * time_delta_res:
                            mouse.wheel(self.last_control_accum)
                            status = f'wheel! {"+" if self.last_control_accum > 0 else ""}{self.last_control_accum:.2f} (x{speed:.2f})'
                        self.last_control_accum = 0
                        self.last_t = t
            elif  self.current_control.type_ == ControlType.DRAG:
                if self.dragging:
                    pass
                else:
                    mouse.press()
                    self.dragging = True
                k_whole = int(self.last_control_accum)
                mouse.move(screen_x, screen_y - k_whole)
                status = f'drag! {"+" if k_whole > 0 else ""}{k_whole} (x{speed:.2f})'
                self.last_control_accum -= k_whole
            elif self.current_control.type_ == ControlType.CLICK:
                is_click = self.click_sm.on_cc(cc, time.time())
                if is_click:
                    mouse.click()
                    status = f'click! (x{speed:.2f})'

        self.last_control = self.current_control
        self.last_cc = cc
        return status

    def freewheel(self):
        self.freewheeling = True
        self.freewheeling_direction = None

    def move_pointer_to_closest(self):
        c = self.instrument.find_closest_control(self.mx, self.my)
        if self.dragging:
            mouse.release()
            self.dragging = False
        x, y = self.instrument_to_screen.apply(c.x, c.y)
        mouse.move(int(x), int(y))
        return c

class AddInstrumentDialog(wx.Dialog):
    def __init__(self, parent, title, queue):
        wx.Frame.__init__(self, parent, title=title)
        self.queue = queue
       
        self.extract_result = None
        topbottommargin = 25
        intermargin = 25
        smallmargin = 4
        horizontal_margin = 20

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.AddSpacer(topbottommargin)

        introText = wx.StaticText(self)
        t = textwrap.dedent('''\
        Here you can create a instrument configuration .txt file for your VST / Software Instrument. 
        After you've created it you need to edit the .txt file with a text editor to change the details
        of each control, e.g. speed multiplier etc. Please read the pointer documentation on how to do this.
        ''')
        introText.SetLabelMarkup(t)
        sizer.Add(introText, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, border=horizontal_margin)

        controlPosLabel = wx.StaticText(self) 
        controlPosLabel.SetLabelMarkup('<b>Control positions</b>')
        controlPosDescr = wx.StaticText(self) 
        controlPosDescr.SetLabelMarkup('<i>Take a screenshot of the instrument window. Crop the screen to contents, but\nexclude all window decoration, e.g. the window title bar or borders.\nThen mark the controls by drawing rectangles in the marker color with any image app (e.g. GIMP).</i>')
        # cpLabel = wx.StaticText(self, label="Marker color #FF00FF, rgb(255,0,255)")
        self.cpLabel = wx.StaticText(self)
        self.colorPickerCtrl = wx.ColourPickerCtrl(self)
        self.colorPickerCtrl.SetColour(wx.Colour(255, 0, 255))
        self.colorPickerCtrl.Bind(wx.EVT_COLOURPICKER_CHANGED, self.on_color_changed)

        self.set_color_text()
        cpSizer = wx.BoxSizer(wx.HORIZONTAL)
        cpSizer.Add(self.colorPickerCtrl, 0)
        cpSizer.Add(self.cpLabel, wx.SizerFlags().Bottom().Border(wx.LEFT, borderinpixels=smallmargin))
        sizer.Add(controlPosLabel, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, border=horizontal_margin)
        sizer.AddSpacer(smallmargin)
        sizer.Add(controlPosDescr, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, border=horizontal_margin)
        sizer.AddSpacer(smallmargin)
        sizer.Add(cpSizer, 0, wx.LEFT | wx.RIGHT, border=horizontal_margin)
        sizer.AddSpacer(smallmargin)


        self.colorThreshold = wx.TextCtrl(self, value="30")
        colorThresholdSizer = wx.BoxSizer(wx.HORIZONTAL)
        colorThresholdSizer.Add(self.colorThreshold)

        thresholdLabel = wx.StaticText(self, label="Marker color threshold (0-255)")
        colorThresholdSizer.Add(thresholdLabel, 0, wx.LEFT, border=smallmargin)
        sizer.Add(colorThresholdSizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, border=horizontal_margin)

        self.selectScreenshot = wx.FilePickerCtrl(self, style=wx.FLP_OPEN, message="Select a cropped screenshot of instrument", wildcard="*.png")
        self.selectScreenshot.Bind(wx.EVT_FILEPICKER_CHANGED, self.on_screenshot_selected)
        filepicker_set_button_label(self.selectScreenshot, 'Analyze Screenshot')


        self.analyzeText = wx.StaticText(self, label="(no positions extracted yet)")
        analyzeSizer = wx.BoxSizer(wx.HORIZONTAL)
        analyzeSizer.Add(self.selectScreenshot)
        analyzeSizer.Add(self.analyzeText, 0, wx.LEFT, border=smallmargin)
        sizer.Add(analyzeSizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, border=horizontal_margin)

        sizer.AddSpacer(intermargin)

        windowPatternLabel = wx.StaticText(self) 
        windowPatternLabel.SetLabelMarkup('<b>Window Pattern</b>')
        windowPatternDescr = wx.StaticText(self, style=wx.LB_MULTIPLE)  
        windowPatternDescr.SetLabelMarkup('<i>What string is always contained in the instrument\'s window title (usually the name)? This is needed to detect its window.</i>')
        self.window_pattern_ctrl = wx.TextCtrl(self)
        sizer.Add(windowPatternLabel, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, border=horizontal_margin)
        sizer.AddSpacer(smallmargin)
        sizer.Add(windowPatternDescr, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, border=horizontal_margin)
        sizer.AddSpacer(smallmargin)
        sizer.Add(self.window_pattern_ctrl, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, border=horizontal_margin)

        sizer.AddSpacer(intermargin)

        mouseControlLabel = wx.StaticText(self) 
        mouseControlLabel.SetLabelMarkup('<b>Mouse control</b>')
        mouseControlDescr = wx.StaticText(self) 
        mouseControlDescr.SetLabelMarkup('<i>How does the mouse adjust controls?</i>')
        sizer.Add(mouseControlLabel, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, border=horizontal_margin)
        sizer.AddSpacer(smallmargin)
        sizer.Add(mouseControlDescr, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, border=horizontal_margin)
        sizer.AddSpacer(smallmargin)
        choices = [
            "mouse drag up and down",
            "mouse wheel"
        ]
        self.mousectrl_combo = wx.ComboBox(self, id=wx.ID_ANY, value="mouse wheel", choices=choices, style=wx.CB_READONLY)
        sizer.Add(self.mousectrl_combo, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, border=horizontal_margin)

        sizer.AddSpacer(intermargin)

        filenameDescr = wx.StaticText(self)
        filenameDescr.SetLabelMarkup('<i>Choose instrument configuration save file. The filename must start with "inst-" and end with ".txt".</i>')
        self.chooseSaveFile = wx.FilePickerCtrl(self, style=wx.FLP_SAVE, message="Save instrument text file")
        filepicker_set_button_label(self.chooseSaveFile, 'Save Instrument')
        self.chooseSaveFile.SetInitialDirectory(datadir())
        self.chooseSaveFile.SetPath(userfile('inst-renameme.txt'))
        self.chooseSaveFile.Bind(wx.EVT_FILEPICKER_CHANGED, self.on_save_file_picked)

        sizer.Add(filenameDescr, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, border=horizontal_margin)
        sizer.AddSpacer(smallmargin)
        sizer.Add(self.chooseSaveFile, 0, wx.CENTER | wx.LEFT | wx.RIGHT, border=horizontal_margin)
        sizer.AddSpacer(topbottommargin)

        self.progress = None

        self.SetSizer(sizer)
        self.Fit()

    def on_color_changed(self, _):
        self.set_color_text()

    def set_color_text(self):
        c = self.colorPickerCtrl.GetColour()
        r, g, b, _ = c.Get()
        msg = 'Marker color: #' + fmt_hex(r) + fmt_hex(g) + fmt_hex(b) + ", " + f'rgb({r},{g},{b})'
        self.cpLabel.SetLabel(msg)

    def on_extract_done(self, delayed_result, **kwargs):
        if self.progress:
            self.progress.Destroy()
            self.progress = None
        self.set_extract_result(delayed_result.get(), kwargs['path'])

    def update_progress(self, i):
        if self.progress:
            self.progress.Update(i)

    def on_screenshot_selected(self, event):
        v = self.colorThreshold.GetValue()
        msg = None
        try:
            v_int = int(v)
        except Exception as e:
            msg = f'Color threshold {v} is not an integer'
        if not (0 <= v_int and v_int <= 255):
            msg = f'Color threshold {v} is not in range 0-255'
        if msg:
            wx.CallAfter(self.frame.show_error, msg)
            return

        path = self.selectScreenshot.GetPath()
        marker_color = self.colorPickerCtrl.GetColour().Get()
        self.progress = wx.ProgressDialog("In Progress", message="Analyzing screenshot...")
        wx.lib.delayedresult.startWorker(self.on_extract_done, workerFn=analyze, ckwargs=dict(path=path), wargs=[self, path, marker_color, v_int])

    def set_extract_result(self, extract_result, path):
        self.extract_result = extract_result
        dim = extract_result['dimensions']
        width = dim['width']
        height = dim['height']
        n = len(extract_result['controls'])
        filename = os.path.basename(path)
        msg = f'{n} controls found in {filename}, {width}x{height}.'
        self.analyzeText.SetLabel(msg)

    def on_save_file_picked(self, event):
        path = self.chooseSaveFile.GetPath()

        problems = []
        if os.path.dirname(path) != datadir():
            problems.append('Instrument file is not chosen in the configuration directory')

        if not re.match('^inst-(.*)\.txt$', os.path.basename(path)):
            problems.append('Instrument file is not named in format inst-{name}.txt . It must start with "inst-" and end in ".txt".')

        if self.extract_result is None:
            problems.append('Screenshot analysis is missing')

        window_contains = self.window_pattern_ctrl.GetValue()
        if len(window_contains) == 0:
            problems.append('Window title pattern is missing')

        if len(problems) > 0:
            message = "Did not save the instrument because:\n"
            message += '\n'.join([f"{i+1}: {p}" for i, p in enumerate(problems)])
            dlg = wx.MessageDialog(None, message, 'Instrument not saved', wx.OK | wx.ICON_ERROR)
            dlg.ShowModal()
            dlg.Destroy()
            return

        mouse_control = control_type_bij.str([ControlType.DRAG, ControlType.WHEEL][self.mousectrl_combo.GetCurrentSelection()])
        doc = toml_instrument_config(self.extract_result, window_contains, mouse_control)
        with open(path, 'w') as f:
            f.write(doc.as_string())

        self.queue.put((InternalCommand.RELOAD_ALL_CONFIGS, None))

        message = f'"{os.path.basename(path)}" was successfully saved to the configuration directory.\nTo further adjust it you need to open it with a text editor.\nPlease read the documentation on the details of the instrument configuration file. Please "Reload Config" in the menu after you\'ve changed config files to take effect.'
        dlg = wx.MessageDialog(None, message, f'Instrument successfully saved', wx.OK | wx.CANCEL)
        dlg.SetOKLabel("Open configuration directory")
        response = dlg.ShowModal()
        dlg.Destroy()

        if response == wx.ID_OK:
            open_directory(datadir())

        self.EndModal(0)

class AboutWindow(wx.Frame):
    def __init__(self, parent):
        super(AboutWindow, self).__init__(parent)
        msg = f'pointer-cc, Version {version}\nby Stefan Matting\nPlease send feedback to pointer-cc@posteo.com or the github site.'

        sizer = wx.BoxSizer(wx.VERTICAL)

        margin_outside = 20

        sizer.AddSpacer(40)

        self.version_label = wx.StaticText(self, label=msg, style=wx.ALIGN_CENTRE_HORIZONTAL)
        sizer.Add(self.version_label, 0, wx.LEFT | wx.RIGHT, margin_outside)

        sizer.AddSpacer(10)

        self.go_website = wx.Button(self, label='Go to website')
        self.go_website.Bind(wx.EVT_BUTTON, self.on_go_website)
        sizer.Add(self.go_website, 0, wx.LEFT | wx.RIGHT, margin_outside)

        sizer.AddSpacer(10)

        self.copy_email = wx.Button(self, label='Copy email address to clipboard')
        self.copy_email.Bind(wx.EVT_BUTTON, self.on_copy_email)
        sizer.Add(self.copy_email, 0, wx.LEFT | wx.RIGHT, margin_outside)

        sizer.AddSpacer(10)

        self.close_button = wx.Button(self, label='Close window')
        self.close_button.Bind(wx.EVT_BUTTON, self.on_close)
        sizer.Add(self.close_button, 0, wx.LEFT | wx.RIGHT, margin_outside)

        sizer.AddSpacer(40)

        self.SetSizer(sizer)
        sizer.SetMinSize((300, 0))
        sizer.Fit(self)
    
    def on_go_website(self, event):
        webbrowser.open(app_url)

    def on_copy_email(self, event):
        pyperclip.copy(app_email)

    def on_close(self, event):
        self.Destroy()


class MainWindow(wx.Frame):
    def __init__(self, parent, title, q, ports):
        wx.Frame.__init__(self, parent, title=title)

        self.panel = wx.Panel(self, wx.ID_ANY)

        self.Bind(wx.EVT_CLOSE, self.on_close)

        self.queue = q

        self.ports = ports

        files = importlib.resources.files('pointercc')
        with files.joinpath('resources/logo-small.png').open('rb') as f:
            png = wx.Image(f, wx.BITMAP_TYPE_ANY).ConvertToBitmap()
            logo = wx.StaticBitmap(self.panel, -1, png, (10, 10), (png.GetWidth(), png.GetHeight()))

        self.version_label = wx.StaticText(self.panel, label=f'', style=wx.ALIGN_CENTRE_HORIZONTAL)

        value = ""
        self.port_dropdown = wx.ComboBox(self.panel, id=wx.ID_ANY, value=value, choices=self.ports, style=wx.CB_READONLY)
        self.Bind(wx.EVT_COMBOBOX, self.handle_midi_port_choice, self.port_dropdown)

        channel_choices = ["All"] + [f"Ch. {i}" for i in range(1, 17)]
        value = ""
        # value = channel_choices[config.preferred_midi_channel]
        self.channel_dropdown = wx.ComboBox(self.panel, id=wx.ID_ANY, value=value, choices=channel_choices, style=wx.CB_READONLY)
        self.Bind(wx.EVT_COMBOBOX, self.handle_midi_channel_choice, self.channel_dropdown)

        self.window_text_ctrl = wx.TextCtrl(self.panel, style=wx.TE_READONLY)

        self.ctrlinfo_text_ctrl = wx.TextCtrl(self.panel, style=wx.TE_READONLY)

        # self.midi_msg_text = wx.StaticText(self.panel, label="<no MIDI received yet>", style=wx.ALIGN_CENTER)

        filemenu= wx.Menu()


        about = filemenu.Append(wx.ID_ABOUT, "&About"," Information about this program")
        self.Bind(wx.EVT_MENU, self.on_about, about)

        create_instrument = filemenu.Append(wx.ID_ANY, "&Add Instrument"," Add instrument configuration")
        self.Bind(wx.EVT_MENU, self.on_create_instrument, create_instrument)

        open_config = filemenu.Append(wx.ID_ANY, "&Open Config Dir"," Open configuartion directory")
        self.Bind(wx.EVT_MENU, self.on_open_config, open_config)

        reload_config = filemenu.Append(wx.ID_ANY, "&Reload config"," Reload all configuration")
        self.Bind(wx.EVT_MENU, self.reload_config, reload_config)

        exitMenutItem = filemenu.Append(wx.ID_EXIT,"E&xit"," Terminate the program")
        self.Bind(wx.EVT_MENU, self.on_exit, exitMenutItem)

        helpmenu = wx.Menu()
        get_help = helpmenu.Append(wx.ID_HELP, "Open Documentation", "Documentation")
        self.Bind(wx.EVT_MENU, self.on_help, get_help)

        menuBar = wx.MenuBar()
        menuBar.Append(filemenu,"&File") # Adding the "filemenu" to the MenuBar
        menuBar.Append(helpmenu,"&Help") # Adding the "filemenu" to the MenuBar
        self.SetMenuBar(menuBar)  # Adding the MenuBar to the Frame content.

        midiChoice = wx.BoxSizer(wx.HORIZONTAL)
        midiChoice.Add(self.port_dropdown, 0, wx.ALL, 0)
        midiChoice.Add(self.channel_dropdown, 0, wx.ALL, 0)

        self.midi_msg_ctrl = wx.TextCtrl(self.panel, style=wx.TE_READONLY)

        horizontal_margin = 20
        topbottommargin = 25
        intermargin = 10

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.AddSpacer(topbottommargin)
        sizer.Add(logo, 0, wx.EXPAND)
        sizer.AddSpacer(intermargin)
        sizer.Add(self.version_label, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, border=horizontal_margin)
        sizer.AddSpacer(intermargin)
        sizer.Add(self.window_text_ctrl, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, border=horizontal_margin)
        sizer.AddSpacer(intermargin)
        sizer.Add(self.ctrlinfo_text_ctrl,  0, wx.EXPAND | wx.LEFT | wx.RIGHT, border=horizontal_margin)
        sizer.AddSpacer(intermargin)
        sizer.Add(midiChoice, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, border=horizontal_margin)
        sizer.Add(self.midi_msg_ctrl, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, border=horizontal_margin)
        sizer.AddSpacer(topbottommargin)

        # TODO:maybe 
        self.sizer = sizer

        self.panel.SetSizer(sizer)
        sizer.SetMinSize((300, 0))
        sizer.Fit(self)

        self.update_view('(no MIDI received yet)', '')

        self.Show()

    def on_help(self, event):
        webbrowser.open(app_url)

    def on_about(self, event):
        about_window = AboutWindow(self)
        about_window.Show()

    def reload_config(self, event):
        self.queue.put((InternalCommand.RELOAD_ALL_CONFIGS, None))

    def on_open_config(self, event):
        open_directory(datadir())

    def on_create_instrument(self, event):
        w = AddInstrumentDialog(None, "Create Instrument", self.queue)
        w.ShowModal()

    def on_close(self, event):
        self.queue.put((InternalCommand.QUIT, None))
        wx.GetApp().ExitMainLoop()
        event.Skip()

    def update_view(self, midi, ctrlinfo):
        self.midi_msg_ctrl.SetLabel(midi)
        self.ctrlinfo_text_ctrl.SetLabel(ctrlinfo)

    def set_window_text(self, text):
        self.window_text_ctrl.SetLabel(text)

    def on_exit(self, event):
        self.Close()

    def handle_midi_port_choice(self, event):
        v = self.port_dropdown.GetValue()
        self.queue.put((InternalCommand.CHANGE_MIDI_PORT, v, True))

    def set_version_label(self, msg):
        self.version_label.SetLabel(msg)
        self.sizer.Layout()

    def handle_midi_channel_choice(self, event):
        i = event.GetInt()
        self.queue.put((InternalCommand.CHANGE_MIDI_CHANNEL, i))

    def show_error(self, msg):
        dlg = wx.MessageDialog(None, msg, 'Error', wx.OK | wx.ICON_ERROR)
        dlg.ShowModal()
        dlg.Destroy()

    def set_midi_selection(self, port_name, port_number):
        self.port_dropdown.SetValue(port_name)
        self.channel_dropdown.SetSelection(port_number)


def matches_name(window, name_pattern):
    name = window.get(Quartz.kCGWindowName)
    if name is None:
        return False
    else:
        for pattern in name_patterns:
            if name.find(pattern) > -1:
                return True
        return False

class WindowPolling(threading.Thread):
    def __init__(self, queue, patterns):
        super(WindowPolling, self).__init__()
        self.queue = queue

        self.event = threading.Event()
        self.windows = {}
        self.set_patterns(patterns)

    def set_patterns(self, patterns):
        self.patterns = patterns
        self.windows = {}

    def run(self):
        running = True
        while running:
            windows = core_platform.get_windows(self.patterns)
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

def default_config_toml():
    doc = tomlkit.document()

    doc.add(tomlkit.comment(f'The is pointer-cc configuration file. Please edit it to change configuration, then pick "Reload Config" from the menu for your changes to take effect. See the pointer-cc documentation for details: {app_url}.'))

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

def default_config():
    d = default_config_toml()
    path = userfile('config.txt')
    return Config.parse(d, path)

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
            if cc_value < self.down_cc:
                self.down_cc = cc_value

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
            cc = expect_int(cc_s, 'cc')
            return Binding(cmd, cc)
        except ConfigError as ce:
            ce.msg = ce.msg + f", {context}"
            raise ce

def expect_value(d, k, context=''):
    v = d.get(k)
    if v is not None:
        return v
    else:
        msg = f'Missing key: \"{k}\"'
        if context != '':
            msg += f' in "{context}"'
        raise ConfigError(msg)

def expect_float(v, context=''):
    try:
        return float(v)
    except:
        raise ConfigError(f'Not a float: \"{str(v)}\" in \"{context}\"')

def expect_int(s, context):
    try:
        return int(s)
    except:
        raise ConfigError(f"Not a decimal: \"{s}\" in \"{context}\"")

class Config:
    def __init__(self, config_path, bindings, preferred_midi_port, preferred_midi_channel):
        self.config_path = config_path
        self.bindings = bindings
        self.preferred_midi_port = preferred_midi_port 
        self.preferred_midi_channel = preferred_midi_channel

    def set_preferred_midi(self, midi_port, midi_channel):
        with open(self.config_path, 'r') as f:
            d = tomlkit.load(f)

        midi = tomlkit.table()
        if midi_port is not None:
            midi.add('port', midi_port)

        if midi_channel is not None:
            midi.add('channel', midi_channel)

        d['midi'] = midi

        with open(self.config_path, 'w') as f:
            f.write(d.as_string())

    @staticmethod
    def parse(d, path):
        bindings_cfg = expect_value(d, 'bindings')

        midi = d.get('midi')
        preferred_midi_port = None
        preferred_midi_channel = None
        if midi is not None:
            preferred_midi_port = midi.get('port')
            preferred_midi_channel = midi.get('channel')

        bindings = []
        for bi, b in bindings_cfg.items():
            bing = Binding.parse(b, f'parsing binding \"{bi}\"')
            bindings.append(bing)

        return Config(path, bindings, preferred_midi_port, preferred_midi_channel)

    @staticmethod
    def load(path):
        with open(path, 'r') as f:
            d = tomlkit.load(f)
            return Config.parse(d, path)

def load_instruments():
    root_dir = datadir()
    filenames = glob.glob('inst-*.txt', root_dir=root_dir)
    d = {}
    exceptions = []
    for filename in filenames:
        p = os.path.join(root_dir, filename)
        try:
            inst = Instrument.load(p, filename)
        except ConfigError as e:
            exceptions.append(e)
        else:
            d[inst.pattern] = inst
    return d, exceptions

def load_config():
    return Config.load(userfile('config.txt'))

def open_directory(path):
    if sys.platform == "win32":
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])

def open_midi_port(midiin, port_name):
    try:
        if midiin.is_port_open():
            midiin.close_port()
        ports = midiin.get_ports()
        i = ports.index(port_name)
        midiin.open_port(i)
        return (True, None)
    except Exception as e:
        return (False, e)

def filepicker_set_button_label(picker, label):
    buttons = list(filter(lambda c: isinstance(c, wx.Button), picker.GetChildren()))
    if len(buttons) == 1:
        button = buttons[0]
        button.SetLabel(label)
        button.SetMinSize(button.GetBestSize())


def https_get(url):
    res = requests.get(url)

    # try:
    url_parts = urllib.parse.urlparse(url)
    connection = http.client.HTTPSConnection(url_parts.netloc)
    connection.request("GET", url_parts.path)
    response = connection.getresponse()
    data = response.read().decode("utf-8")
    return data
    # except Exception as e:
    #     return None


class UpdateCheck(threading.Thread):
    def __init__(self, frame):
        super(UpdateCheck, self).__init__()
        self.frame = frame
        self.event = threading.Event()

    def run(self):
        running = True
        t_last = None
        time.sleep(2)
        while running:

            do_check = False
            t = datetime.datetime.now()
            if t_last is None:
                do_check = True
            else:
                if t - t_last > datetime.timedelta(hours=24):
                    do_check = True
            t_last = t

            if do_check:
                newer_version = self.check_latest_bigger_version()
                if newer_version is not None:
                    msg = f'Newer version {newer_version} is available!'
                    wx.CallAfter(self.frame.set_version_label, msg)

            if self.event.is_set():
                running = False

            time.sleep(0.5)

    def check_latest_bigger_version(self):
        if version == "0.0.0":
            return
        latest_version = None
        try:
            r = requests.get(url_latest)
            assert r.status_code == 200
            latest_version = r.text.strip()
        except Exception:
            pass

        if latest_version is not None:
           try:
               if semver.compare(version, latest_version) < 0:
                   return latest_version
           except:
               pass

def main():
    app = wx.App(True)
    polling = None
    dispatcher = None
    update_check = None
    try:
        initialize_config()

        core_platform.init()

        q = queue.Queue()

        midiin = rtmidi.MidiIn()
        ports = midiin.get_ports()

        frame = MainWindow(None, "pointer-cc", q, ports)

        dispatcher = Dispatcher(midiin, q, frame)
        dispatcher.start()

        update_check = UpdateCheck(frame)
        update_check.start()


    except Exception as e:
        traceback.print_exc()

    app.MainLoop()

    if update_check:
        update_check.event.set()
        update_check.join()

    if dispatcher:
        dispatcher.join()

def main2():
    q = queue.Queue()
    polling = WindowPolling(q, [ "TAL-J-8", "Prophet-5 V"])
    polling.start()

if __name__ == '__main__':
    main()
