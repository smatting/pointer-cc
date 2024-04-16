#!/usr/bin/env bash

set -euo pipefail

cert_name="Developer ID Application: Stefan Matting (FPDFQ974RQ)" 

destination_dmg="dist/pointer-cc-$POINTER_CC_VERSION-$(arch).dmg"
rm -rf "$destination_dmg"

codesign --deep --force --verify --verbose --sign "$cert_name" ./dist/pointer-cc.app

temp_dir=$(mktemp -d)

cp -R "./dist/pointer-cc.app" "$temp_dir/pointer-cc.app/"

ln -s "/Applications" "$temp_dir/Applications"

tmp_dmg="./tmp.dmg"

hdiutil create -srcfolder "$temp_dir" -volname "pointer-cc $POINTER_CC_VERSION" \
    -format UDRW -ov -fs HFS+ "$tmp_dmg"

hdiutil convert "$tmp_dmg" -format UDZO -o "$destination_dmg"

# Cleanup: Remove the temporary directory
rm -rf "$temp_dir"

set +e
xattr -d com.apple.FinderInfo "$destination_dmg"
set -e

codesign --force --verify --verbose --sign "$cert_name" "$destination_dmg"

echo "DMG created successfully at: $destination_dmg"
