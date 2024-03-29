#!/usr/bin/env bash

rm -f dist/pointer-cc.app.zip
zip -r dist/pointer-cc.app.zip dist/pointer-cc.app
scp dist/pointer-cc.app.zip "sefan:pointer-cc.app.$(date +%Y%m%d%H%M%S).zip"
