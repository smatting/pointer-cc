from setuptools import setup, find_packages

setup(
    name='pointer-cc',
    version='0.0.1',
    app=[
        {"script": "main.py"}
    ],
    description='Control your mouse via MIDI cc to control software instruments - oh my',
    author='Stefan Matting',
    author_email='stefan.matting@gmail.com',
    packages=find_packages(),
    options = {
        "py2app": {
        }
    }
)
