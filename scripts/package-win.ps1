$ErrorActionPreference = 'Stop'
# TODO: parametrize the version
ISCC .\setup.iss
signtool sign -v -n "Stefan Matting SPC" -s My -t http://timestamp.digicert.com  Output/pointer-cc-1.0-install.exe