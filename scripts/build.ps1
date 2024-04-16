if (Test-Path -Path build -PathType Container) {
  Remove-Item -Force -Recurse build
}

if (Test-Path -Path dist -PathType Container) {
  Remove-Item -Force -Recurse dist
}

# pyinstaller --name pointer-cc --icon ./resources/icon.icns --windowed main.py
.\venv\bin\pyinstaller --name pointer-cc --windowed main.py
