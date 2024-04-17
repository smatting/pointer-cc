if (Test-Path -Path build -PathType Container) {
  Remove-Item -Force -Recurse build
}

if (Test-Path -Path dist -PathType Container) {
  Remove-Item -Force -Recurse dist
}

pyinstaller --name pointer-cc --icon ./resources/icons.ico --windowed main.py
