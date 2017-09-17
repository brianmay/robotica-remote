import uasyncio as asyncio
import asyn
import aswitch
import machine
import neopixel
import arequests

from mqtt_as import MQTTClient
from config import config


class Button:
    debounce_ms = 50
    long_press_ms = 1000
    double_click_ms = 400

    def __init__(self, pin):
        self.pin = pin  # Initialise for input
        self._press_func = None
        self._release_func = None
        self._double_func = None
        self._long_func = None
        self._event = asyn.Event()
        self.sense = pin.value()  # Convert from electrical to logical value
        self.buttonstate = self.rawstate()  # Initial state

        # pin.irq(
        #    trigger=machine.Pin.IRQ_RISING | machine.Pin.IRQ_FALLING,
        #    handler=lambda param: print("IRQ", param))
        pin.irq(
           trigger=machine.Pin.IRQ_RISING | machine.Pin.IRQ_FALLING,
           handler=self.irq)
        loop = asyncio.get_event_loop()
        loop.create_task(self.buttoncheck())  # Thread runs forever

    def press_func(self, func, args=[]):
        self._press_func = func
        self._press_args = args

    def release_func(self, func, args=[]):
        self._release_func = func
        self._release_args = args

    def double_func(self, func, args=[]):
        self._double_func = func
        self._double_args = args

    def long_func(self, func, args=[]):
        self._long_func = func
        self._long_args = args

    # Current non-debounced logical button state: True == pressed
    def rawstate(self):
        return bool(self.pin.value() ^ self.sense)

    # Current debounced state of button (True == pressed)
    def __call__(self):
        return self.buttonstate

    def irq(self, pin):
        # print("got irq", self._event.is_set())
        self._event.set()
        # print("got irq", self._event.is_set())

    async def buttoncheck(self):
        if self._long_func:
            longdelay = aswitch.Delay_ms(self._long_func, self._long_args)
        if self._double_func:
            doubledelay = aswitch.Delay_ms()

        while True:
            # print("waiting", self._event.is_set())
            await self._event
            # print("finished waiting", self._event.is_set())

            state = self.rawstate()
            if state != self.buttonstate:
                # Ignore state changes until switch has settled
                await asyncio.sleep_ms(self.debounce_ms)
                state = self.rawstate()

            # State has changed: act on it now.
            if state != self.buttonstate:
                self.buttonstate = state
                if state:
                    # Button is pressed
                    if self._long_func and not longdelay.running():
                        # Start long press delay
                        longdelay.trigger(self.long_press_ms)
                    if self._double_func:
                        if doubledelay.running():
                            asyn.launch(self._double_func, self._double_args)
                        else:
                            # First click: start doubleclick timer
                            doubledelay.trigger(self.double_click_ms)
                    if self._press_func:
                        asyn.launch(self._press_func, self._press_args)
                else:
                    # Button release
                    if self._long_func and longdelay.running():
                        # Avoid interpreting a second click as a long push
                        longdelay.stop()
                    if self._release_func:
                        asyn.launch(self._release_func, self._release_args)

            self._event.clear()


class Lights:
    def __init__(self, pin):
        self._pin = pin  # Initialise for input
        self._np = neopixel.NeoPixel(pin, 12, timing=True)

        self.brightness = 32
        self.delay = 0.1

        loop = asyncio.get_event_loop()
        loop.create_task(self.rotate())  # Thread runs forever

    def adj_brightness(self, value):
        self.brightness = (self.brightness + value) % 256

    def adj_delay(self, value):
        self.delay = self.delay * value

    async def rotate(self):
        i = 0
        n = 1
        while True:
            np = self._np

            np.fill([0] * 12)

            brightness = self.brightness
            np[(i + 0) % 12] = (0, brightness, 0)
            np[(i + 1) % 12] = (int(brightness*0.1), int(brightness*0.1), 0)
            np[(i + 2) % 12] = (int(brightness*0.1), int(brightness*0.1), 0)
            np[(i + 3) % 12] = (brightness, 0, 0)

            np.write()

            await asyncio.sleep(self.delay)

            i = (i + 1*n) % 12
            if i == 0:
                n = n * -1


def main():
    lights = Lights(machine.Pin(13))

    pin_UL = machine.Pin(25, machine.Pin.IN, machine.Pin.PULL_UP)
    pin_LL = machine.Pin(26, machine.Pin.IN, machine.Pin.PULL_UP)
    pin_UR = machine.Pin(23, machine.Pin.IN, machine.Pin.PULL_UP)
    pin_LR = machine.Pin(22, machine.Pin.IN, machine.Pin.PULL_UP)

    button_UL = Button(pin_UL)
    button_LL = Button(pin_LL)
    button_UR = Button(pin_UR)
    button_LR = Button(pin_LR)

    button_UL.press_func(lambda: lights.adj_delay(2))
    button_LL.press_func(lambda: lights.adj_delay(0.5))

    button_UR.press_func(lambda: lights.adj_brightness(16))
    button_LR.press_func(lambda: lights.adj_brightness(-16))

    button_UL.long_func(lambda: do_http())

    loop = asyncio.get_event_loop()
    loop.run_forever()
    loop.close()


async def do_http():
    url = "http://dining.pri:8080/execute/"
    json = {
        "locations": ["Brian", "Dining", "Twins", "Akira"],
        "actions": [
            {
                "message": {"text": "It is time to watch Fergus."}
            },
            # {
            #     "message": {"text": "It is time to watch the lights flash"}
            # },
            # {
            #     "lights": {"action": "flash"}
            # }
        ]
    }
    headers = {
        'ACCEPT': 'application/json',
        'Content-Type': 'application/json',
        'Authorization': 'Basic YWRtaW46cTF3MmUzcjQ=',
    }
    response = await arequests.request("POST", url, json=json, headers=headers)
    print(response)
    print(await response.content())
    if response.status_code == 200:
        print(await response.json())


SERVER = '192.168.3.6'  # Change to suit e.g. 'iot.eclipse.org'


def callback(topic, msg):
    print((topic, msg))


async def conn_han(client):
    await client.subscribe('/action/Brian/', 0)


async def main2(client):
    await client.connect()
    n = 0
    while True:
        await asyncio.sleep(5)
        print('publish', n)
        # If WiFi is down the following will pause for the duration.
        await client.publish('test', '{}'.format(n), qos=0)
        n += 1


def main3():
    config['subs_cb'] = callback
    config['connect_coro'] = conn_han
    config['server'] = SERVER

    MQTTClient.DEBUG = True  # Optional: print diagnostic messages
    client = MQTTClient(config)
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main2(client))
    finally:
        client.close()  # Prevent LmacRxBlk:1 errors
