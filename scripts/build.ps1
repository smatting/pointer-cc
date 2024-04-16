$ErrorActionPreference = 'Stop'
Remove-Item -Force -Recurse -ErrorAction SilentlyContinue dist
Remove-Item -Force -Recurse -ErrorAction SilentlyContinue output
Remove-Item -Force -Recurse -ErrorAction SilentlyContinue Output
pyinstaller --name pointer-cc --icon ./resources/icon.icns --windowed main.py
