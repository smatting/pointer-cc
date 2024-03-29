#!/usr/bin/env bash

set -eo pipefail


# build=dev
build=prod

# Requisite: Install Python from this link https://www.python.org/downloads/release/python-31011/
python="/Library/Frameworks/Python.framework/Versions/3.10/Resources/Python.app/Contents/MacOS/Python"

rm -rf venv_native 
$python -m venv venv_native
source ./venv_native/bin/activate
pip install -r requirements.txt
pip install https://github.com/boppreh/mouse/archive/7b773393ed58824b1adf055963a2f9e379f52cc3.zip
if [ "$build" = "dev" ]; then
    rm -rf build dist && python setup.py py2app -A
else
    rm -rf build dist && python setup.py py2app
fi
