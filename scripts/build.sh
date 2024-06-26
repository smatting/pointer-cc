#!/usr/bin/env bash

set -eo pipefail

rm -rf dist build Output

# when installing with --target (arm64) venv/bin doesnt get the binaries
PATH="venv/lib/python3.10/site-packages/bin":$PATH

python setup.py put_version
pyinstaller \
    --name pointer-cc \
    --target-arch "${TARGET_ARCH:-x86_64}" \
    --icon ./resources/icon.icns \
    --add-data "./pointercc/resources/logo-small.png:./pointercc/resources/" \
    --windowed main.py
