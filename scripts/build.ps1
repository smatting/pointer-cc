if (Test-Path -Path build -PathType Container) {
  Remove-Item -Force -Recurse build
}

if (Test-Path -Path dist -PathType Container) {
  Remove-Item -Force -Recurse dist
}

pyinstaller --name pointer-cc `
  --icon ./resources/icons.ico `
  --add-data "./pointercc/resources/logo-small.png:./pointercc/resources/" `
  --windowed main.py
