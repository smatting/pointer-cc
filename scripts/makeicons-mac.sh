#!/usr/bin/env bash
#
export ICONDIR="tmp.iconset"
export ORIGICON=resources/logo-big.png

mkdir -p $ICONDIR

# Normal screen icons
for SIZE in 16 32 64 128 256 512; do
sips -z $SIZE $SIZE $ORIGICON --out $ICONDIR/icon_${SIZE}x${SIZE}.png ;
done

# Retina display icons
for SIZE in 32 64 256 512; do
sips -z $SIZE $SIZE $ORIGICON --out $ICONDIR/icon_$(expr $SIZE / 2)x$(expr $SIZE / 2)x2.png ;
done

iconutil -c icns -o resources/icon.icns $ICONDIR
rm -rf $ICONDIR


