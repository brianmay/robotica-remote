#!/bin/sh
set -ex
rm -rf build
mkdir build
cp -a arequests.py main.py boot.py config.py micropython-async/asyn.py micropython-mqtt/mqtt_as/mqtt_as.py build
mkdir build/uasyncio
cp -a micropython-lib/uasyncio/uasyncio/__init__.py micropython-lib/uasyncio.core/uasyncio/core.py build/uasyncio
