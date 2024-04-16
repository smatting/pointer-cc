$ErrorActionPreference = 'Stop'

# export PATH="/c/Program Files (x86)/Inno Setup 6":$PATH
# export PATH="C:\Program Files (x86)\Windows Kits\10\bin\10.0.18362.0\x64":$PATH


python --version
Remove-Item -Force -Recurse -ErrorAction SilentlyContinue venv
python -m venv venv
cd .\venv\Scripts
./Activate.ps1
cd ..\..\

pip install --upgrade pip
pip install -r requirements.txt
pip install -r requirements-stage2.txt
