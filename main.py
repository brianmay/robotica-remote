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
    from typing import Any, Dict, List, Callable, Optional, Tuple
    Color = Tuple[int, int, int]
    Callback = Callable[[], Any]
except ImportError:
    pass

MQTT_SERVER = '192.168.3.6'  # Change to suit e.g. 'iot.eclipse.org'
NUM_LIGHTS = 12

WHITE = {
    'hue': 0,
    'saturation': 0,
    'brightness': 100,
    'kelvin': 5500,
}
RED = {
    'hue': 0,
    'saturation': 100,
    'brightness': 100,
    'kelvin': 5500,
}
GREEN = {
    'hue': 120,
    'saturation': 100,
    'brightness': 100,
    'kelvin': 5500,
}
BLUE = {
    'hue': 240,
    'saturation': 100,
    'brightness': 100,
    'kelvin': 5500,
}


# If a callback is passed, run it and return.
# If a coro is passed initiate it and return.
# coros are passed by name i.e. not using function call syntax.
def launch(func: Optional[Callback]) -> None:
    if func is not None:
        res = func()
        if isinstance(res, asyn.type_coro):
            loop = asyncio.get_event_loop()
            loop.create_task(res)


class Button:
    debounce_ms = 50
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
        num_downs = 0
        num_ups = 0

        def _timer() -> None:
            if num_ups == 1 and num_downs == 1:
                print("got short click")
                launch(self._press_func)
            elif num_ups == 1 and num_downs == 0:
                print("got long press")
                launch(self._long_func)
            elif num_ups == 2:
                print("got double click")
                launch(self._double_func)

        doubledelay = aswitch.Delay_ms(_timer)

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
                    if not doubledelay.running():
                        doubledelay.trigger(self.double_click_ms)
                        num_ups = 0
                        num_downs = 0
                    num_ups += 1
                else:
                    num_downs += 1

            self._event.clear()


class Lights:
    def __init__(self, pin: machine.Pin) -> None:
        self._pin = pin  # Initialise for input
        self._np = neopixel.NeoPixel(pin, NUM_LIGHTS, timing=True)
        self._taskid = 0
        self._task_initial = None  # type: Optional[List[Color]]

    def get_state(self) -> List[Color]:
        return [
            self._np[i]
            for i in range(self._np.n)
            ]

    def set_state(self, colors: List[Color]) -> None:
        for i, color in enumerate(colors):
            self._np[i] = color
        self._np.write()

    def clear(self) -> None:
        self._np.fill((0, 0, 0))
        self._np.write()

    def set_ok(self) -> None:
        loop = asyncio.get_event_loop()
        color = (0, 31, 0)
        self._taskid = self._taskid + 1
        loop.create_task(self.flash(self._taskid, color, 0.2))

    def set_danger(self) -> None:
        loop = asyncio.get_event_loop()
        color = (31, 0, 0)
        self._taskid = self._taskid + 1
        loop.create_task(self.flash(self._taskid, color, 0.2))

    def set_timer(self, minutes: int) -> None:
        self._np.fill((0, 0, 0))
        colors = [ (7,0,0), (0,7,0), (0,0,7) ]  # type: List[Color]
        num_lights = ((minutes - 1) % self._np.n) + 1
        num_cycles = ((minutes - 1) // self._np.n)
        if num_cycles > len(colors)-1:
            num_cycles = len(colors)-1
        for i in range(num_lights):
            self._np[i] = colors[num_cycles]
        self._np.write()

    async def rotate(self, taskid: int, color: Color, delay: float) -> None:
        i = 0
        n = 1
        if self._task_initial is None:
            self._task_initial = self.get_state()

        try:
            for repeat in range(int(10 / delay)):
                np = self._np

                np.fill((0, 0, 0))
                np[(i + 0) % np.n] = color
                np[(i + 1) % np.n] = color
                np[(i + 2) % np.n] = color
                np[(i + 3) % np.n] = color

                np.write()

                await asyncio.sleep(delay)
                if self._taskid != taskid:
                    # another task running, just exit
                    return

                i = (i + 1*n) % np.n
        finally:
            if self._taskid == taskid:
                self.set_state(self._task_initial)
                self._task_initial = None

    async def flash(self, taskid: int, color: Color, delay: float) -> None:
        if self._task_initial is None:
            self._task_initial = self.get_state()
        try:
            for repeat in range(4):
                np = self._np

                np.fill(color)
                np.write()

                await asyncio.sleep(delay)
                if self._taskid != taskid:
                    # another task running, just exit
                    return

                self.clear()

                await asyncio.sleep(delay)
                if self._taskid != taskid:
                    # another task running, just exit
                    return
        finally:
            if self._taskid == taskid:
                self.set_state(self._task_initial)
                self._task_initial = None


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
            if 'message' in data:
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

    async def lights(
            self, locations: List[str], light_action: str,
            color: Optional[Dict[str, int]]=None):
        action = {
            "lights": {"action": light_action},
        }  # type: Dict[str, Any]
        if color is not None:
            action["lights"]["color"] = color
        data = {
            "locations": locations,
            "actions": [action],
        }
        await self._publish("/execute/", data)

    async def music(self, locations: List[str], play_list: str):
        action = {
            "music": {"play_list": play_list},
        }
        data = {
            "locations": locations,
            "actions": [action],
        }
        await self._publish("/execute/", data)

    async def music_lights(
            self, locations: List[str], play_list: str,
            color: Dict[str, int]):
        action = {
            "music": {"play_list": play_list},
            "lights": {"action": "turn_on", "color": color},
        }
        data = {
            "locations": locations,
            "actions": [action],
        }
        await self._publish("/execute/", data)


class Timer:

    def __init__(self, lights: Lights, mqtt: MQTT) -> None:
        self._lights = lights
        self._mqtt = mqtt
        self._timer_running = False

    async def execute(self, locations: List[str], minutes: int):
        if self._timer_running:
            await self._mqtt.say(locations, "Timer is already set.")
            print("Timer is already set.")
            return

        self._timer_running = True
        try:
            print("Timer started at %d minutes." % minutes)
            await self._mqtt.say(locations, "Timer started at %d minutes." % minutes)
            for minute in range(minutes):
                print("Timer elapsed %d minutes of %d." % (minute, minutes))
                self._lights.set_timer(minutes - minute)
                await asyncio.sleep(60)
            print("Timer stopped %d minutes." % minutes)
            self._lights.clear()
            await self._mqtt.say(locations, "The time is up!")
        except Exception as e:
            print("Timer encountered as error: %s" % e)
            self._lights.clear()
            await self._mqtt.say(locations, "The timer crashed!")
        finally:
            self._timer_running = False


def main() -> None:
    lights = Lights(machine.Pin(13))
    mqtt = MQTT(MQTT_SERVER, lights)
    timer = Timer(lights, mqtt)

    pin_UL = machine.Pin(25, machine.Pin.IN, machine.Pin.PULL_UP)
    pin_LL = machine.Pin(26, machine.Pin.IN, machine.Pin.PULL_UP)
    pin_UR = machine.Pin(23, machine.Pin.IN, machine.Pin.PULL_UP)
    pin_LR = machine.Pin(22, machine.Pin.IN, machine.Pin.PULL_UP)

    button_UL = Button(pin_UL)
    button_LL = Button(pin_LL)
    button_UR = Button(pin_UR)
    button_LR = Button(pin_LR)

    loc = ['Brian']
    button_UL.press_func(lambda: mqtt.music_lights(loc, 'red', RED))
    button_LL.press_func(lambda: mqtt.music_lights(loc, 'green', GREEN))
    button_UR.press_func(lambda: mqtt.music_lights(loc, 'blue', BLUE))
    button_LR.press_func(lambda: mqtt.music_lights(loc, 'white', WHITE))

    button_UL.long_func(lambda: mqtt.lights(loc, 'turn_off'))
    button_LL.long_func(lambda: mqtt.lights(loc, 'turn_on', WHITE))
    button_UR.long_func(lambda: timer.execute(loc, 10))
    button_LR.long_func(lambda: timer.execute(loc, 15))

    lights.clear()
    loop = asyncio.get_event_loop()
    loop.create_task(mqtt.connect())

    try:
        loop.run_forever()
    finally:
        mqtt.close()  # Prevent LmacRxBlk:1 errors
        loop.close()
