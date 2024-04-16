Remove-Item -Force -Recurse build
Remove-Item -Force -Recurse dist 
Remove-Item -Force -Recurse output
Remove-Item -Force -Recurse Output
$ErrorActionPreference = 'Stop'
# pyinstaller --name pointer-cc --icon ./resources/icon.icns --windowed main.py
pyinstaller --name pointer-cc --windowed main.py
