## Installation

You can find **downloads** for Mac and Windows in the [releases page](https://github.com/smatting/pointer-cc/releases). If you've got a newer Mac with a M chip, then download the `.dmg`  file that ends with`-arm64`. Otherwise download the `.dmg` file that ends with `-x86_x64` . You can find out which one you got in the `About My Mac` menu.

When yourun the Window installer there will be a warning that the installer comes from "Unknown Publisher". This is because I don't want to spend the 300 eur per year for obtaining a verified certificate. You can optionally add the [StefanMattingCA.cer](https://raw.githubusercontent.com/smatting/pointer-cc/main/certs/StefanMattingCA.cer) certificate to the trusted root certificates of your user to ger rid of the warning.

## Using pointer-cc

When you run pointer-cc the first time on Mac it will ask permissions to for both "Screen Recording" and "Accessability". pointer-cc needs these permissions in order to be able to move the both ("Accessability" permission) as well as recognizing the instruments location and size ("Screen recording"). Please navigate to "Security & Privacy" and make sure you've manually added a checkmark for categories. Please restart the app! It can be that pointer-cc doesn't ask for all permission the first time. In that case you need to restart pointer-cc **twice**.

![permissions needed for pointer-cc](docs/mac-permissions.gif) 

<img title="" src="docs/main-window-unconfigured-win32.png" alt="" width="293">

At the bottom of the main window you can select yor MIDI device and channel. You should see MIDI messages flashing at the bottom if it works correctly.



In order to start using pointer-cc you need add instrument configurations. To add a new instrument follow these steps

1. Take a screenshot of your instrument. Make sure you crop to the exact contents of the window, omit the window bar or borders.
2. Use a paint program (e.g. online [jspaint.app](https://jspaint.app), MS Paint or [GIMP](https://www.gimp.org/)) to mark all the controls with points or rectangles in the same color. Choose a color for that doesn't occur in the screenshot otherwise. Make sure you note down the exact RGB color code, e.g. `#ff00ff0` or `R = 255, G = 0, B = 255` if you chose a pink like in the screenshot. Feel free to omit any controls that you are not interested in. It could look like this:
   ![controls marked with pink dots](docs/obxd-marked.jpg)
   Save the marked screenshot as a PNG file.
3. In pointer-cc select `Add Instrument` from the menu and follow the instructions.

After adding the instruments choose `Open Config Dir`. The configuration directory of pointer-cc contains two kinds of files

- `config.txt` - The main configuration file

- `inst-{some name}.txt`- Instrument configuration files. These have to start with `inst-` and and with `.txt`. Files named differently will be ignored.

The **main confguration** file `config.txt` looks like this

```
[bindings]
[bindings.1]
command = "pan-x"
cc = 77

[bindings.2]
command = "pan-y"
cc = 78

[bindings.3]
command = "adjust-control"
cc = 79

[bindings.4]
command = "freewheel"
cc = 80

[midi]
port = "Launch Control XL 0"
channel = 0

```

In the `[bindings]` section you add mappings of your midi control knobs to commands for pointer-cc. To determin the correct value for the  `cc` field turn the knob you want to use and note down the control number atthe MIDI status barat the bottom of the pointer-cc window and change `cc` field to it.

The `command` field determines what happens when you adust the midi controller.

- `pan-x` pan the cursor horizontally. A CC value `0` pans the pointer all the way left

- `pan-x-inv` pan the cursor horizonally. A CC value of `127` pans the pointer  all the way left

- `pan-y` pan the cursor vertically. A CC value `0` pans the pointer all the way up 

- `pan-y-inv` pan the cursor vertically. A CC value `127` pans the pointer all the way up

- `adjust-control` adjust the current control. What mouse pointer action is simulated depends on the configuration of current control element (See instrument configuration below)

- `freewheel` start freewheeling. While freewheeling you can turn the adjustment knob (knob mapped to `adjust-control`) in one direction without it having any effect. When you turn the adjustment knob in the other direction freewheeling stops and the adjustment knob has its effect again.

The `[midi]` section is automatically updated when you change the MIDI settings in the window, there is no need to edit this part manually.

The instrument file that is generated in the "Add Instrument" window. To tune it to your needs you need to edit it with a text editor. A typical **instrument configuration** file, e.g. `inst-jupiter8.txt` looks like this

```
[window]
contains = "TAL-J-8"

[default]
type = "wheel"

[default.drag]
speed = 1.0

[default.wheel]
speed = 0.3
time_resolution = 50

[dimensions]
width = 1439
height = 736

[controls]
[controls.c1]
x = 1074
y = 172
m = 1.0

[controls.c2]
type = "click"
x = 1033
y = 177
m = 1.0

...

```





- `window.contains` is used by pointer-cc to find the instrument window. Pick a string here that is contained in the window title of the instrument. It's usually the name of the instrument. Note that the case has to also match (comparison is case-sensitive).

- `default.type` the default type of pointer control used by all controls if not explicity `type` is defined. Valid values are `drag`, `wheel`, `click` (see below)

- `default.drag.speed` default setting for`speed` for controls that are of type `drag`

- `default.wheel.speed` default setting for`speed` for controls that are of type `wheel`

- `default.wheel.time_resolution` default setting for `time_resolution` for controls that are of type `wheel`. This settings controls how many times per second a wheel event is send to the instrument window. If this is too high then the operating system (seen on Windows only) might drop wheel events when you turn the adjustment knob fast. Setting it too low results in too choppy updates. Try to experiment with this value to find a sweet spot. `50` (times per second) seems to be good starting point.

- `controls` The `controls.c1`, `controls.c2`, ... sections correspond to the control elements that you marked in the screenshots. You can see the `c?` number that belongs to acontrol element in the pointer-cc window when you select .

- `controls.c1.x`: x coordinate of the control element (was extracted from screenshot)

- `controls.c1.y`: y coordinate of the control element (was extracted from screenshot)

- `controls.c1.type` (optional). Determines the type of mouse pointer action that is simulated by pointer-cc when the adjustment knob is turned while on control `c1`. Valid values are
  
  - `drag` the mouse pointer is dragged up or down
  
  - `wheel` the mouse pointer's wheel is turned up or down
  
  - `click` the mouse pointer simulates a click. To trigger a click turn the adjustment knob quickly down and then up again
  
  If you don't specify a `type` for a control element then `default.type` is used.

- `control.c1.m` (optional) Speed multiplier for (only relevant for `wheel` and `drag`). Values smaller than `1.0` result in less dragging or wheeling while values greater than `1.0` result in more dragging and wheeling. Use this to tune the speed of the control relative to the rest. The overall speed that the controller `speed * m`.
  If you don't specify a `m` then `1.0` is used.

- `control.c1.speed` (optional) Speed for the control element. Unless you have a good reason don't set it. It's better to set `default.drag.speed` abd `defautlt.wheel.speed` to have consistent base speeds for all knobs and use `control.c1.m` to modify relative to the base speed

- `dimensions.width` and `dimensions.height`. Defines the dimensions of the whole instruments. All `x` and `y` coordinates of control elements relative to it. This is the resolution of the screenshot image.
