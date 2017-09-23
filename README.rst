===============
Robotica-Remote
===============

.. image:: https://img.shields.io/travis/brianmay/robotica-remote.svg
        :target: https://travis-ci.org/brianmay/robotica-remote

.. image:: https://pyup.io/repos/github/brianmay/robotica-remote/shield.svg
     :target: https://pyup.io/repos/github/brianmay/robotica-remote/
     :alt: Updates


Robotic maid to scare innocent children. This is the ESP32 based remote
control.


* Free software: GNU General Public License v3
* Documentation: https://robotica.readthedocs.io.


Installation
------------

#. Create empty ``./boot.py`` file.
#. Create ``./config.py``::

    from mqtt_as import config
    from sys import platform

    if platform == 'esp32':
        config['ssid'] = 'XYZ'
        config['wifi_pw'] = 'XYZ'

#. Run ``./build.sh``.
#. Copy build directory to ESP32.


Features
--------

* TODO

License
-------
This software is GPLv3, with the exception of third party software, which
keep their original copyrights and licenses.

* ``arequests.py``: Derived from ``urequests.py`` in micropython-esp32 tree.
