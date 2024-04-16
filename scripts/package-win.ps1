$ErrorActionPreference = 'Stop'
ISCC .\setup.iss
$items = Get-ChildItem .\Output\
$firstItem = $items[0]
signtool sign /fd sha256  /v /n "Stefan Matting SPC" /s My /t http://timestamp.digicert.com  Output\$firstItem
