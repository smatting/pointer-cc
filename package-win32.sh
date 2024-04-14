#!/usr/bin/env bash

set -eo pipefail

rm -rf build dist Output
pyinstaller --name pointer-cc --icon ./resources/icon.icns --windowed main.py
ISCC ./setup.iss
