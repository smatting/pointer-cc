#!/usr/bin/env bash

set -eo pipefail

rm -rf dist build Output
pyinstaller --name pointer-cc --icon ./resources/icon.icns --windowed main.py
