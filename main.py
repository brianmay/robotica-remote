import json

import uasyncio as asyncio
import asyn
import aswitch
import machine
import neopixel
import arequests

from mqtt_as import MQTTClient
from config import config

try:
    from typing import Any, List, Callable, Optional, Tuple
    Color = Tuple[int, int, int]
    Callback = Callable[[], Any]
except ImportError:
    pass

MQTT_SERVER = '192.168.3.6'  # Change to suit e.g. 'iot.eclipse.org'


# If a callback is passed, run it and return.
# If a coro is passed initiate it and return.
# coros are passed by name i.e. not using function call syntax.
def launch(func: Callback) -> None:
    res = func()
    if isinstance(res, asyn.type_coro):
        loop = asyncio.get_event_loop()
        loop.create_task(res)


class Button:
    debounce_ms = 50
    long_press_ms = 1000
    double_click_ms = 400

    def __init__(self, pin: machine.Pin) -> None:
        self.pin = pin  # Initialise for input
        self._press_func = None  # type: Optional[Callback]
        self._release_func = None  # type: Optional[Callback]
        self._double_func = None  # type: Optional[Callback]
        self._long_func = None  # type: Optional[Callback]
        self._event = asyn.Event()
        self.sense = pin.value()  # Convert from electrical to logical value
        self.buttonstate = self.rawstate()  # Initial state

        # pin.irq(
        #    trigger=machine.Pin.IRQ_RISING | machine.Pin.IRQ_FALLING,
        #    handler=lambda param: print("IRQ", param))
        pin.irq(
           trigger=machine.Pin.IRQ_RISING | machine.Pin.IRQ_FALLING,
           handler=self._irq)
        loop = asyncio.get_event_loop()
        loop.create_task(self._buttoncheck())  # Thread runs forever

    def press_func(self, func: Callback) -> None:
        self._press_func = func

    def release_func(self, func: Callback) -> None:
        self._release_func = func

    def double_func(self, func: Callback) -> None:
        self._double_func = func

    def long_func(self, func: Callback) -> None:
        self._long_func = func

    # Current non-debounced logical button state: True == pressed
    def rawstate(self) -> bool:
        return bool(self.pin.value() ^ self.sense)

    # Current debounced state of button (True == pressed)
    def __call__(self) -> bool:
        return self.buttonstate

    def _irq(self, pin: int) -> None:
        # print("got irq", self._event.is_set())
        self._event.set()
        # print("got irq", self._event.is_set())

    async def _buttoncheck(self) -> None:
        if self._long_func:
            longdelay = aswitch.Delay_ms(self._long_func)
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
                            launch(self._double_func)
                        else:
                            # First click: start doubleclick timer
                            doubledelay.trigger(self.double_click_ms)
                    if self._press_func:
                        launch(self._press_func)
                else:
                    # Button release
                    if self._long_func and longdelay.running():
                        # Avoid interpreting a second click as a long push
                        longdelay.stop()
                    if self._release_func:
                        launch(self._release_func)

            self._event.clear()


class Lights:
    def __init__(self, pin: machine.Pin) -> None:
        self._pin = pin  # Initialise for input
        self._np = neopixel.NeoPixel(pin, 12, timing=True)
        self._taskid = 0

    def clear(self) -> None:
        self._np.fill([0] * 12)
        self._np.write()

    def set_ok(self) -> None:
        loop = asyncio.get_event_loop()
        color = (0, 63, 0)
        self._taskid = self._taskid + 1
        loop.create_task(self.rotate(self._taskid, color, 0.1))

    def set_danger(self) -> None:
        loop = asyncio.get_event_loop()
        color = (63, 0, 0)
        self._taskid = self._taskid + 1
        loop.create_task(self.rotate(self._taskid, color, 0.1))

    async def rotate(self, taskid: int, color: Color, delay: float) -> None:
        i = 0
        n = 1
        for repeat in range(int(10 / delay)):
            np = self._np

            np.fill([0] * 12)
            np[(i + 0) % 12] = color
            np[(i + 1) % 12] = color
            np[(i + 2) % 12] = color
            np[(i + 3) % 12] = color

            np.write()

            await asyncio.sleep(delay)
            if self._taskid != taskid:
                # another task running, just exit
                return

            i = (i + 1*n) % 12

        self.clear()


async def do_http() -> None:
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


class MQTT:
    def __init__(self, server: str, lights: Lights) -> None:
        self._lights = lights
        config['subs_cb'] = self._callback
        config['connect_coro'] = self._conn_han
        config['server'] = server
        MQTTClient.DEBUG = True  # Optional: print diagnostic messages
        self._client = MQTTClient(config)

    def _process(self, topic: str, data: Any) -> None:
        if topic.startswith('/action/Brian/'):
            print((topic, data))
            if 'lights' in data:
                self._lights.set_danger()
            else:
                self._lights.set_ok()

    def _callback(self, topic: bytes, msg: bytes) -> None:
        topic_str = topic.decode('UTF8')
        msg_str = msg.decode('UTF8')

        try:
            data = json.loads(msg_str)
            self._process(topic_str, data)
        except json.JSONDecodeError as e:
            print("JSON Error %s" % e)

    async def _conn_han(self, client: MQTTClient) -> None:
        await client.subscribe('/action/Brian/', 0)

    async def connect(self) -> None:
        await self._client.connect()

    def close(self) -> None:
        self._client.close()

    async def _publish(self, topic: str, data: Any) -> None:
        topic_raw = topic.encode('UTF8')
        msg_raw = json.dumps(data).encode('UTF8')
        await self._client.publish(topic_raw, msg_raw, qos=0)

    async def say(self, locations: List[str], text: str, flash: bool=False):
        action = {
            "message": {"text": text}
        }
        if flash:
            action['lights'] = {"action": "flash"}
        data = {
            "locations": locations,
            "actions": [action],
        }
        await self._publish("/execute/", data)


def main() -> None:
    lights = Lights(machine.Pin(13))
    mqtt = MQTT(MQTT_SERVER, lights)

    pin_UL = machine.Pin(25, machine.Pin.IN, machine.Pin.PULL_UP)
    pin_LL = machine.Pin(26, machine.Pin.IN, machine.Pin.PULL_UP)
    pin_UR = machine.Pin(23, machine.Pin.IN, machine.Pin.PULL_UP)
    pin_LR = machine.Pin(22, machine.Pin.IN, machine.Pin.PULL_UP)

    button_UL = Button(pin_UL)
    button_LL = Button(pin_LL)
    button_UR = Button(pin_UR)
    button_LR = Button(pin_LR)

    button_UL.press_func(lambda: lights.set_ok())
    button_LL.press_func(lambda: lights.set_danger())

    button_UR.press_func(
        lambda: mqtt.say(['Brian'], "You pushed the wrong button."))
    button_LR.press_func(
        lambda: mqtt.say(['Brian'], "You pushed the dangerous button.",
        flash=True))

    loop = asyncio.get_event_loop()
    loop.create_task(mqtt.connect())

    try:
        loop.run_forever()
    finally:
        mqtt.close()  # Prevent LmacRxBlk:1 errors
        loop.close()
