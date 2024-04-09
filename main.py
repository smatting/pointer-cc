import Quartz
from PIL import Image
import wx
import wx.lib.delayedresult
import time
import textwrap
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

app_name = "pointer-cc"
app_author = "smatting"
app_url = "https://github.com/smatting/pointer-cc/"

InternalCommand = Enum('InternalCommand', ['QUIT', 'CHANGE_MIDI_PORT',  'CHANGE_MIDI_CHANNEL', 'UPDATE_WINDOW'])

class Bijection:
    def __init__(self, a_name, b_name, atob_pairs):
        self._d_atob = dict(atob_pairs)
        self._d_btoa = dict([(b, a) for (a, b) in atob_pairs])

        setattr(self, a_name, self._a)
        setattr(self, b_name, self._b)

    def _a(self, b):
        return self._d_btoa.get(b)
        # TODO: raise / handle config errors at call site
        # if v is None:
        #     knowns = ", ".join([f"\"{str(k)}\"" for k in self._d_btoa.keys()])
        #     msg = f'Unknown value "{str(b)}", known values are: {knowns}.' 
        #     raise ConfigError(msg)
        return v

    def _b(self, a):
        return self._d_atob.get(a)
        # if v is None:
        #     knowns = ", ".join([f"\"{str(k)}\"" for k in self._d_atob.keys()])
        #     msg = f'Unknown value "{str(a)}", known values are: {knowns}.' 
        #     raise ConfigError(msg)

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

def find_markings(im, marker_color, update_percent):
    boxes = []
    spans_last = {}
    for y in range(0, im.height):
        update_percent(int(100*y//im.height))
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

    def __str__(self):
        type_str = control_type_bij.str(self.type_)
        return f'{self.i}({type_str})'

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

def analyze(self, filename, marker_color=(255, 0, 255, 255)):
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
    markings = find_markings(im, marker_color, update_percent)
    for i, box in enumerate(markings):
        c = {}
        x, y = box.center()
        c['x'] = x
        c['y'] = y
        controls[f'c{i+1}'] = c
    return d

def toml_instrument_config(extract_result, window_contains, control_type):
    doc = tomlkit.document()
    doc.add(tomlkit.comment('The pointer-cc configuration file is of TOML format (https://toml.io). See the pointer-cc documentation for details.'))

    window = tomlkit.table()
    window.add('contains', window_contains)
    doc.add('window', window)

    dimensions = tomlkit.table()
    dimensions.add('width', extract_result['dimensions']['width'])
    dimensions.add('height', extract_result['dimensions']['height'])
    doc.add('dimensions', dimensions)

    default_control = tomlkit.table()
    default_control.add('type', control_type)
    default_control.add('wheel_speed', 1.0)
    default_control.add('drag_speed', 1.0)
    doc.add('default_control', default_control)

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
    def __init__(self, midiin, queue, frame, instruments, config):
        super(Dispatcher, self).__init__()
        self.midiin = midiin
        self.queue = queue
        self.frame = frame

        midi_channel= 0
        if config.preferred_midi_channel is not None:
            midi_channel = config.preferred_midi_channel
        self.midi_channel = midi_channel

        self.instruments = instruments
        self.controllers = {}
        self.config = config

        if len(self.instruments) == 0:
            self.frame.set_window_text("No instruments configured, please read the docs")

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
                if controller.current_controller is not None:
                    ctrl_info_parts.append(str(controller.current_controller))

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

    def run(self):
        self.midiin.set_callback(self)

        running = True
        while running:
            item = self.queue.get()
            cmd = item[0]
            if cmd == InternalCommand.QUIT:
                running = False

            elif cmd == InternalCommand.CHANGE_MIDI_CHANNEL:
                self.midi_channel = item[1]

            elif cmd == InternalCommand.CHANGE_MIDI_PORT:
                ports = self.midiin.get_ports()
                port_name = item[1]

                port_index = None
                try:
                    port_index = ports.index(port_name)
                except ValueError:
                    pass

                if port_index is not None:

                    if self.midiin.is_port_open():
                        self.midiin.close_port()
                    self.midiin.open_port(port_index)
                    self.midiin.set_callback(self)

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
        
        self.click_sm = ClickStateMachine(1.0, 2)
        
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
        status = None

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
                status = f'wheel! {"+" if k_whole > 0 else ""} (x{speed:.2f})'
            elif  self.current_controller.type_ == ControlType.DRAG:
                if self.dragging:
                    pass
                else:
                    mouse.press()
                    self.dragging = True
                mouse.move(screen_x, screen_y - k_whole)
                status = f'drag! {"+" if k_whole > 0 else ""}{k_whole} (x{speed:.2f})'
            elif self.current_controller.type_ == ControlType.CLICK:
                is_click = self.click_sm.on_cc(cc, time.time())
                if is_click:
                    mouse.click()
                    status = f'click! (x{speed:.2f})'

        self.last_controller_turned = self.current_controller
        self.last_cc = cc
        return status

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

class CreateInstWindow(wx.Frame):
    def __init__(self, parent, title):
        wx.Frame.__init__(self, parent, title=title)
       
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
        self.selectScreenshot = wx.FilePickerCtrl(self, style=wx.FLP_OPEN, message="Select a cropped screenshot of instrument", wildcard=".png")
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
            "mouse drag (up and down)",
            "mouse wheel (prefer this if both are supported)"
        ]
        self.mousectrl_combo = wx.ComboBox(self, id=wx.ID_ANY, choices=choices, style=wx.CB_READONLY)
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
        path = self.selectScreenshot.GetPath()
        marker_color = self.colorPickerCtrl.GetColour().Get()
        self.progress = wx.ProgressDialog("In Progress", message="Analyzing screenshot...")
        wx.lib.delayedresult.startWorker(self.on_extract_done, workerFn=analyze, ckwargs=dict(path=path), wargs=[self, path, marker_color])

    def set_extract_result(self, extract_result, path):
        self.extract_result = extract_result
        dim = extract_result['dimensions']
        width = dim['width']
        height = dim['height']
        n = len(extract_result['controls'])
        filename = os.path.basename(path)
        msg = f'{width}x{height}, {n} controls ({filename}).'
        self.analyzeText.SetLabel(msg)

    def on_save_file_picked(self, event):
        path = self.chooseSaveFile.GetPath()

        problems = []
        if os.path.dirname(path) != datadir():
            problems.append('Instrument file is not chosen in the configuration directory')

        if not re.match('^inst-(.*)\.txt$', os.path.basename(path)):
            problems.append('Instrument file is not named in format inst-changeme.txt')

        if self.extract_result is None:
            problems.append('Screenshot analysis is missing')

        window_contains = self.window_pattern_ctrl.GetValue()
        if len(window_contains) == 0:
            problems.append('Window title pattern is missing')

        if len(problems) > 0:
            message = "Did not safe the instrument because:\n"
            message += '\n'.join([f"{i+1}: {p}" for i, p in enumerate(problems)])
            dlg = wx.MessageDialog(None, message, 'Instrument not saved', wx.OK | wx.ICON_ERROR)
            dlg.ShowModal()
            dlg.Destroy()
            return

        mouse_control = control_type_bij.str([ControlType.DRAG, ControlType.WHEEL][self.mousectrl_combo.GetCurrentSelection()])
        doc = toml_instrument_config(self.extract_result, window_contains, mouse_control)
        with open(path, 'w') as f:
            f.write(doc.as_string())


class MainWindow(wx.Frame):
    def __init__(self, parent, title, q, ports, config, instruments):
        wx.Frame.__init__(self, parent, title=title)

        self.panel = wx.Panel(self, wx.ID_ANY)

        self.config = config

        self.Bind(wx.EVT_CLOSE, self.on_close)

        self.queue = q

        self.ports = ports

        value = ""
        if config.preferred_midi_port is not None:
            value = config.preferred_midi_port
        self.port_dropdown = wx.ComboBox(self.panel, id=wx.ID_ANY, value=value, choices=self.ports, style=wx.CB_READONLY)
        self.Bind(
            wx.EVT_COMBOBOX, self.handle_midi_port_choice, self.port_dropdown
        )

        channel_choices = ["All"] + [f"Ch. {i}" for i in range(1, 17)]
        value = ""
        if config.preferred_midi_channel is not None:
            if 0 <= config.preferred_midi_channel and config.preferred_midi_channel < len(channel_choices):
                value = channel_choices[config.preferred_midi_channel]

        self.channel_dropdown = wx.ComboBox(self.panel, id=wx.ID_ANY, value=value, choices=channel_choices, style=wx.CB_READONLY)
        self.Bind(wx.EVT_COMBOBOX, self.handle_midi_channel_choice, self.channel_dropdown)

        self.window_text_ctrl = wx.TextCtrl(self.panel, style=wx.TE_READONLY)

        self.ctrlinfo_text_ctrl = wx.TextCtrl(self.panel, style=wx.TE_READONLY)

        # self.midi_msg_text = wx.StaticText(self.panel, label="<no MIDI received yet>", style=wx.ALIGN_CENTER)

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

        midiSizer = wx.BoxSizer(wx.HORIZONTAL)
        midiSizer.Add(self.port_dropdown, 0, wx.ALL, 0)
        midiSizer.Add(self.channel_dropdown, 0, wx.ALL, 0)

        self.midi_msg_ctrl = wx.TextCtrl(self.panel, style=wx.TE_READONLY)

        sizer = wx.BoxSizer(wx.VERTICAL)
        # sizer.Add(self.port_dropdown)
        # sizer.Add(self.channel_dropdown)
        sizer.Add(self.window_text_ctrl, 0, wx.EXPAND)
        sizer.Add(self.ctrlinfo_text_ctrl,  0, wx.EXPAND)
        sizer.Add(midiSizer)
        sizer.Add(self.midi_msg_ctrl, 0, wx.EXPAND)

        self.panel.SetSizer(sizer)
        sizer.Fit(self)

        self.update_view('(no MIDI received yet)', '')

        if len(instruments) == 0:
            msg_inital_msg = 'no instruments configured, please read docs'
        else:
            msg_inital_msg = f'{len(instruments)} instruments configured' 
        self.set_window_text(msg_inital_msg)

        self.Show()

    def on_help(self, event):
        webbrowser.open(app_url)

    def on_open_config(self, event):
        open_directory(datadir())

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

    def save_preferred_midi(self):
        midi_port = None
        midi_port_selected = self.port_dropdown.GetValue()
        if midi_port_selected != "":
            midi_port = midi_port_selected

        channel_selection = self.channel_dropdown.GetSelection()
        channel = None
        if channel_selection != wx.NOT_FOUND:
            channel = channel_selection

        self.config.set_preferred_midi(midi_port, channel)

    def handle_midi_port_choice(self, event):
        v = self.port_dropdown.GetValue()
        self.queue.put((InternalCommand.CHANGE_MIDI_PORT, v))
        self.save_preferred_midi()

    def handle_midi_channel_choice(self, event):
        i = event.GetInt()
        self.queue.put((InternalCommand.CHANGE_MIDI_CHANNEL, i))
        self.save_preferred_midi()


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
    def load(path):
        with open(path, 'r') as f:
            d = tomlkit.load(f)
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
    Quartz.CGPreflightScreenCaptureAccess()

def connect_to_port(midiin, port_name):
    ports = midiin.get_ports()
    try:
        i = ports.index(port_name)
        midiin.open_port(i)
        return True
    except ValueError:
        return False

def filepicker_set_button_label(picker, label):
    buttons = list(filter(lambda c: isinstance(c, wx.Button), picker.GetChildren()))
    if len(buttons) == 1:
        button = buttons[0]
        button.SetLabel(label)
        button.SetMinSize(button.GetBestSize())

def main():
    app = wx.App(True)
    try:
        initialize_config()

        config = Config.load(userfile('config.txt'))

        request_access()

        q = queue.Queue()

        midiin = rtmidi.MidiIn()
        ports = midiin.get_ports()
        if config.preferred_midi_port is not None:
            c = connect_to_port(midiin, config.preferred_midi_port)

        instruments = load_instruments()

        frame = MainWindow(None, "pointer-cc", q, ports, config, instruments)

        w = CreateInstWindow(None, "Create Instrument")
        w.Show()

        polling = WindowPolling(q, list(instruments.keys()))
        polling.start()

        dispatcher = Dispatcher(midiin, q, frame, instruments, config)
        dispatcher.start()
    except Exception as e:
        traceback.print_exc()

    app.MainLoop()

    polling.event.set()
    polling.join()

    dispatcher.join()

if __name__ == '__main__':
    # main_analyze()
    main()
