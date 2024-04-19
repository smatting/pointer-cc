## Installation

You can find **downloads** for Mac and Windows in the [releases page](https://github.com/smatting/pointer-cc/releases). If you've got a newer Mac with a M1 or M2 chip, then download the `.dmg`  file that `-arm64` in the name. If you've got a Mac with a Silicon chip choose the one with `-x86_x64` in the name. You can find out which one you got in the `About My Mac` menu.

When you try run the Window installer there will be warning that the installer comes from "Unknown Publisher". This is because I don't want to spend the 300 eur per year of obtaining a verified certificate. You can optionally add the [StefanMattingCA.cer](https://raw.githubusercontent.com/smatting/pointer-cc/main/certs/StefanMattingCA.cer) certificate to the trusted root certificates of your user to ger rid of this error message.

## Using pointer-cc

When you run pointer-cc the first time on Mac it will ask permissions to for both "Screen Recording" and "Accessability". pointer-cc needs these permissions in order to be able to move the both ("Accessability" permission) as well as recognizing the instruments location and size ("Screen recording"). Please navigate to "Security & Privacy" and make sure you've manually added a checkmark for categories. Please restart the app! It can be that pointer-cc doesn't ask for all permission the first time. In that case you need to restart pointer-cc *twice*.

![permissions needed for pointer-cc](docs/mac-permissions.gif)



<img src="docs/main-window-unconfigured-win32.png" title="" alt="" width="230">



You add instruments before you are able to use pointer-cc.

1. Take a screenshot of your instrument. Make sure you crop to the exact contents of the window, omit the window bar or borders.
2. Use a paint program (e.g. Paint or [GIMP](https://www.gimp.org/)) to mark all the controls with dots. Choose a color that doesn't occur in the screenshot other. Make sure you note down the color RGB values, e.g. `#ff00ff0` or `R = 255, G = 0, B = 255` for a pink color. For example
   ![controls marked with pink dots](docs/obxd-marked.jpg)
   Save the marked screenshot as a PNG file.
