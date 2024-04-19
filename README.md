## Installation

You can find **downloads** for Mac and Windows in the [releases page](https://github.com/smatting/pointer-cc/releases). If you've got a newer Mac with a M chip, then download the `.dmg`  file that ends with`-arm64`. Otherwise download the `.dmg` file that ends with `-x86_x64` . You can find out which one you got in the `About My Mac` menu.

When yourun the Window installer there will be a warning that the installer comes from "Unknown Publisher". This is because I don't want to spend the 300 eur per year for obtaining a verified certificate. You can optionally add the [StefanMattingCA.cer](https://raw.githubusercontent.com/smatting/pointer-cc/main/certs/StefanMattingCA.cer) certificate to the trusted root certificates of your user to ger rid of the warning.

## Using pointer-cc

When you run pointer-cc the first time on Mac it will ask permissions to for both "Screen Recording" and "Accessability". pointer-cc needs these permissions in order to be able to move the both ("Accessability" permission) as well as recognizing the instruments location and size ("Screen recording"). Please navigate to "Security & Privacy" and make sure you've manually added a checkmark for categories. Please restart the app! It can be that pointer-cc doesn't ask for all permission the first time. In that case you need to restart pointer-cc **twice**.

![permissions needed for pointer-cc](docs/mac-permissions.gif) 

<img title="" src="docs/main-window-unconfigured-win32.png" alt="" width="293">

At the bottom of the main window you can select yor MIDI device and channel. You should see MIDI message flashing at the bottom if it works correctly.



In order to start using pointer-cc you need add instrument configurations. To add a new instrument follow these steps

1. Take a screenshot of your instrument. Make sure you crop to the exact contents of the window, omit the window bar or borders.
2. Use a paint program (e.g. Paint or [GIMP](https://www.gimp.org/)) to mark all the controls with dots. Choose a color for the dots that doesn't occur in the screenshot otherwise. Make sure you note down the exact RGB color code, e.g. `#ff00ff0` or `R = 255, G = 0, B = 255` if you chose a pink like in the screenshot. Feel free to omit any controls that you are not interested in. For example it could look like this:
   ![controls marked with pink dots](docs/obxd-marked.jpg)
   Save the marked screenshot as a PNG file.
3. In pointer-cc select `Add Instrument` from the menu and follow the instructions.

After adding the instruments choose `Open Config Dir`. The configuration directory of pointer-cc contains two kinds of files

- `config.txt` - The main configuration file

- `inst-{some name}.txt`- Instrument configuration files. These have to start with `inst-` and and with `.txt`. Files named differently will be ignored.

The `config.txt` by default looks like this

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

- `adjust-control` adjust the control. What mouse pointer action is simulated depends on the instrument configuration of the current instrument (see below)

The `[midi]` section is automatically updated when you change the MIDI settings in the window, there is no need to edit this part manually.
