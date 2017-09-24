import json
import math

import uasyncio as asyncio
import utime as time
import asyn
import aswitch
import machine
import neopixel

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


class LightsState:
    def __init__(
            self, pin: machine.Pin, num_lights: int,
            write_ok_func: Callable[['LightsState'], bool]) -> None:
        self._np = neopixel.NeoPixel(pin, NUM_LIGHTS, timing=True)
        self._n = num_lights
        self._write_ok_func = write_ok_func

    def fill(self, color: Color) -> None:
        for i in range(self._n):
            self[i] = color

    def clear(self) -> None:
        self.fill((0, 0, 0))

    @property
    def n(self) -> int:
        return self._n

    def __getitem__(self, index: int) -> Color:
        color = self._np[index]  # type: Color
        return color

    def __setitem__(self, index: int, value: Color) -> None:
        self._np[index] = value

    def write(self) -> None:
        if self._write_ok_func(self):
            self._np.write()

    def _set_timer(self, minutes: int) -> None:
        colors = [(1, 0, 0), (0, 1, 0), (0, 0, 1)]  # type: List[Color]
        num_lights = (minutes % self._n)
        num_cycles = (minutes // self._n)

        if num_cycles > len(colors)-1:
            fg = (1, 1, 1)
        else:
            fg = colors[num_cycles]

        if num_cycles == 0:
            bg = (0, 0, 0)
        else:
            prev_cycles = num_cycles - 1
            if prev_cycles > len(colors)-1:
                bg = (1, 1, 0)
            else:
                bg = colors[prev_cycles]

        self.fill(bg)
        for i in range(num_lights):
            self[i] = fg
        self.write()

    async def set_timer(self, minutes: int) -> None:
        self._set_timer(minutes)
        await asyncio.sleep(0.5)
        self._set_timer(minutes + 1)
        await asyncio.sleep(0.5)
        self._set_timer(minutes)
        await asyncio.sleep(0.5)
        self._set_timer(minutes + 1)
        await asyncio.sleep(0.5)
        self._set_timer(minutes)


class Lights:
    def __init__(self, pin: machine.Pin) -> None:
        self._pin = pin  # Initialise for input
        self._task_id = 0
        self._task_name = None  # type: Optional[str]
        self._task_running = False
        self._task_state = LightsState(pin, NUM_LIGHTS, self._write_task_ok)
        self._state = LightsState(pin, NUM_LIGHTS, self._write_ok)

    @property
    def state(self) -> LightsState:
        return self._state

    def _write_ok(self, state: LightsState) -> bool:
        return not self._task_running

    def _write_task_ok(self, state: LightsState) -> bool:
        return self._task_running

    def set_ok(self) -> None:
        loop = asyncio.get_event_loop()
        color = (0, 31, 0)
        self._task_id = self._task_id + 1
        self._task_name = "ok"
        loop.create_task(self.flash(self._task_id, color, 0.2))

    def set_danger(self) -> None:
        loop = asyncio.get_event_loop()
        color = (31, 0, 0)
        self._task_id = self._task_id + 1
        self._task_name = "danger"
        loop.create_task(self.flash(self._task_id, color, 0.2))

    def set_boot(self) -> None:
        loop = asyncio.get_event_loop()
        color = (1, 0, 0)
        self._task_id = self._task_id + 1
        self._task_name = "boot"
        loop.create_task(self.rotate(self._task_id, color, 0.2))

    def stop_boot(self) -> None:
        if self._task_name == "boot":
            self._task_id = self._task_id + 1
            self._task_running = False
            self._state.write()

    async def rotate(self, task_id: int, color: Color, delay: float) -> None:
        i = 0
        n = 1
        self._task_running = True
        state = self._task_state

        try:
            for repeat in range(int(10 / delay)):
                state.fill((0, 0, 0))
                state[(i + 0) % state.n] = color
                state[(i + 1) % state.n] = color
                state[(i + 2) % state.n] = color
                state[(i + 3) % state.n] = color
                state.write()

                await asyncio.sleep(delay)
                if self._task_id != task_id:
                    # another task running, just exit
                    return

                i = (i + 1*n) % state.n
        finally:
            if self._task_id == task_id:
                self._task_running = False
                self._task_name = None
                self._state.write()

    async def flash(self, task_id: int, color: Color, delay: float) -> None:
        self._task_running = True
        state = self._task_state

        try:
            for repeat in range(4):
                state.fill(color)
                state.write()

                await asyncio.sleep(delay)
                if self._task_id != task_id:
                    # another task running, just exit
                    return

                state.clear()
                state.write()

                await asyncio.sleep(delay)
                if self._task_id != task_id:
                    # another task running, just exit
                    return
        finally:
            if self._task_id == task_id:
                self._task_running = False
                self._task_name = None
                self._state.write()


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
        self._lights.stop_boot()

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

    async def sound(self, locations: List[str], sound: str):
        action = {
            "sound": {"name": sound},
        }
        data = {
            "locations": locations,
            "actions": [action],
        }
        await self._publish("/execute/", data)

    async def music(self, locations: List[str], play_list: Optional[str]):
        action = {}  # type: Dict[str, Any]
        if play_list is not None:
            action["music"] = {"play_list": play_list}
        else:
            action["music"] = None
        data = {
            "locations": locations,
            "actions": [action],
        }
        await self._publish("/execute/", data)

    async def music_lights(
            self, locations: List[str],
            play_list: Optional[str], color: Dict[str, int]):
        action = {
            "lights": {"action": "turn_on", "color": color},
            }  # type: Dict[str, Any]
        if play_list is not None:
            action["music"] = {"play_list": play_list}
        else:
            action["music"] = None
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
        loop = asyncio.get_event_loop()
        state = self._lights.state

        if self._timer_running:
            await self._mqtt.say(locations, "Timer is already set.")
            print("Timer is already set.")
            return

        self._timer_running = True
        last_flash_time = 2000
        one_minute = 60000
        timer_stop = time.ticks_add(
            loop.time(), minutes*one_minute - last_flash_time)
        try:
            print("Timer started at %d minutes." % minutes)
            await self._mqtt.say(
                locations, "Timer started at %d minutes." % minutes)

            last_minute = minutes
            twait = time.ticks_diff(timer_stop, loop.time())
            while twait > 0:
                minute = math.ceil(twait / one_minute)
                print("Timer left %d minutes of %d." % (minute, minutes))
                await state.set_timer(minute)
                if minute != last_minute:
                    await self._mqtt.sound(locations, "beep")
                    last_minute = minute

                twait = time.ticks_diff(timer_stop, loop.time())
                sleep = twait % one_minute
                if sleep == 0:
                    sleep = one_minute
                await asyncio.sleep_ms(sleep)
                twait = time.ticks_diff(timer_stop, loop.time())

            print("Timer stopped %d minutes." % minutes)
            await state.set_timer(0)
            await self._mqtt.say(
                locations, "Beep. Beep. Beep. The time is up!")
        except Exception as e:
            print("Timer encountered as error: %s" % e)
            state.clear()
            state.write()
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

    loc1 = ['Brian']
    current_play_list = None  # type: Optional[str]
    current_color = None  # type: Optional[Dict[str, int]]

    async def button_press(play_list: str) -> None:
        nonlocal current_play_list
        if current_play_list != play_list:
            await mqtt.music(loc1, play_list)
            current_play_list = play_list
        else:
            await mqtt.music(loc1, None)
            current_play_list = None

    async def button_long(color: Dict[str, int]) -> None:
        nonlocal current_color
        if current_color != color:
            await mqtt.lights(loc1, 'turn_on', color)
            current_color = color
        else:
            await mqtt.lights(loc1, 'turn_off', color)
            current_color = None

    button_UL.press_func(lambda: button_press('red'))
    button_LL.press_func(lambda: button_press('green'))
    button_UR.press_func(lambda: button_press('blue'))
    button_LR.press_func(lambda: button_press('white'))

    button_UL.long_func(lambda: button_long(RED))
    button_LL.long_func(lambda: button_long(GREEN))
    button_UR.long_func(lambda: button_long(BLUE))
    button_LR.long_func(lambda: button_long(WHITE))

    loc2 = ['Brian']
    button_UL.double_func(lambda: timer.execute(loc2, 5))
    button_LL.double_func(lambda: timer.execute(loc2, 10))
    button_UR.double_func(lambda: timer.execute(loc2, 15))
    button_LR.double_func(lambda: timer.execute(loc2, 20))

    lights.set_boot()

    loop = asyncio.get_event_loop()
    loop.create_task(mqtt.connect())

    try:
        loop.run_forever()
    finally:
        mqtt.close()  # Prevent LmacRxBlk:1 errors
        loop.close()