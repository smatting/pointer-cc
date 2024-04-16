$ErrorActionPreference = 'Stop'
ISCC .\setup.iss
$items = Get-ChildItem .\Output\
$firstItem = $items[0]
signtool sign -v -n "Stefan Matting SPC" -s My -t http://timestamp.digicert.com  Output\$firstItem
