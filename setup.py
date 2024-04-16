from setuptools import setup, find_packages
from setuptools.command.install import install
import os

class PutVersion(install):
    description = "Custom command example"

    def run(self):
        version = os.environ['POINTER_CC_VERSION']
        with open('./pointercc/version.py', 'w') as f:
            f.write(f'version = "{version}"\n')

setup(
    name='pointer-cc',
    version='0.0.0',
    description='Control your mouse via MIDI controler to control your software instruments',
    author='Stefan Matting',
    author_email='stefan.matting@gmail.com',
    packages=find_packages(),
    cmdclass={
        'put_version': PutVersion,
    },
)
