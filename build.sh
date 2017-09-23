#!/bin/sh
set -ex
rm -rf build
mkdir build
cp -a src/arequests.py src/main.py src/boot.py src/config.py \
    ./micropython-async/asyn.py \
    ./micropython-async/aswitch.py \
    ./micropython-mqtt/mqtt_as/mqtt_as.py \
    ./micropython-lib/typing/typing.py \
    build
mkdir build/uasyncio
cp -a \
    micropython-lib/uasyncio/uasyncio/__init__.py \
    micropython-lib/uasyncio.core/uasyncio/core.py \
    build/uasyncio
