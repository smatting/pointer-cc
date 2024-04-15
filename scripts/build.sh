#!/usr/bin/env bash

set -eo pipefail

pyinstaller --name pointer-cc --icon ./resources/icon.icns --windowed main.py
