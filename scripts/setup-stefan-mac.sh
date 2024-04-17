python="/Library/Frameworks/Python.framework/Versions/3.10/Resources/Python.app/Contents/MacOS/Python"
rm -rf venv
"$python" --version
"$python" -m venv venv
source venv/bin/activate
command -v python3
python3 --version

if [ "$TARGET_ARCH" = "x86_64" ]; then
    # --no-deps: prevent wxpython from pulling numpy
    pip install --no-deps -r requirements.txt
    pip install -r requirements-stage2.txt
else
    # --no-deps: prevent wxpython from pulling numpy
    # --no-deps also required when specifying platform
    pip install --platform macosx_11_0_arm64 --no-deps --target venv/lib/python3.10/site-packages -r requirements.txt
    pip install --platform macosx_11_0_arm64 --no-deps --target venv/lib/python3.10/site-packages -r requirements-stage2.txt
fi
