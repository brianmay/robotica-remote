#!/bin/sh
set -ex
#flake8 src
rm -rf build
mkdir build
cp -a src/*.py \
    build
mypy --strict --ignore-missing-imports build
cp -a \
    ./micropython-async/asyn.py \
    ./micropython-async/aswitch.py \
    ./micropython-mqtt/mqtt_as/mqtt_as.py \
    build
mkdir build/uasyncio
cp -a \
    micropython-lib/uasyncio/uasyncio/__init__.py \
    micropython-lib/uasyncio.core/uasyncio/core.py \
    build/uasyncio
cp -a \
    ./micropython-lib/typing/typing.py \
    ./micropython-lib/abc/abc.py \
    build
