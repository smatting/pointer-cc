python="/Library/Frameworks/Python.framework/Versions/3.10/Resources/Python.app/Contents/MacOS/Python"
rm -rf venv
"$python" --version
"$python" -m venv venv
source venv/bin/activate
command -v python3
python3 --version
pip install -r requirements.txt
pip install -r requirements-stage2.txt
