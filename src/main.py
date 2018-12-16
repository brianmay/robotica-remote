import json

import uasyncio as asyncio
import asyn
import aswitch
import machine
import neopixel

from mqtt_as import MQTTClient
from config import config

try:
    from typing import Any, Dict, List, Callable, Optional, Tuple
    from typing import Type, TypeVar
    Color = Tuple[int, int, int]
    Callback = Callable[[], Any]
except ImportError:
    def TypeVar(*args: None, **kwargs: None) -> None:
        pass

MQTT_SERVER = '192.168.3.6'  # Change to suit e.g. 'iot.eclipse.org'
NUM_LIGHTS = 16

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
YELLOW = {
    'hue': 55,
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
    debounce_ms = 20
    double_click_ms = 500

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
                print("got short click %s" % self.pin)
                launch(self._press_func)
            elif num_ups == 1 and num_downs == 0:
                print("got long press %s" % self.pin)
                launch(self._long_func)
            elif num_ups == 2:
                print("got double click %s" % self.pin)
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


class LightsTask:
    def __init__(
            self, pin: machine.Pin, num_lights: int,
            write_ok_func: Callable[['LightsTask'], bool],
            stop_func: Callable[['LightsTask'], None]) -> None:
        self._np = neopixel.NeoPixel(pin, NUM_LIGHTS, timing=True)
        self._n = num_lights
        self._write_ok_func = write_ok_func
        self._stop_func = stop_func
        self._stop = False
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def stop(self) -> None:
        self._stopped = True
        self._stop_func(self)

    @property
    def is_stopped(self) -> bool:
        return self._stopped

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

    def __str__(self) -> str:
        return ",".join(str(self._np[index]) for index in range(self._n))

    def write(self) -> None:
        if self._write_ok_func(self):
            self._np.write()

    async def rotate(self, color: Color, delay: float) -> None:
        i = 0
        n = 1

        try:
            for repeat in range(int(10 / delay)):
                self.fill((0, 0, 0))
                self[(i + 0) % self.n] = color
                self[(i + 1) % self.n] = color
                self[(i + 2) % self.n] = color
                self[(i + 3) % self.n] = color
                self.write()

                await asyncio.sleep(delay)
                if self._cancel:
                    break

                i = (i + 1*n) % self.n
        finally:
            # self.clear()
            # self.write()
            self.stop()

    async def flash(self, color: Color, repeats: int, delay: float) -> None:
        try:
            for repeat in range(repeats):
                self.fill(color)
                self.write()

                await asyncio.sleep(delay)
                if self._cancel:
                    break

                self.clear()
                self.write()

                await asyncio.sleep(delay)
                if self._cancel:
                    break
        finally:
            # self.clear()
            # self.write()
            self.stop()


class LightsTaskTimer(LightsTask):

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

    async def set_timer(self, minutes: int, no_flash: bool=False) -> None:
        if not no_flash:
            self._set_timer(minutes)
            await asyncio.sleep(0.5)
            self._set_timer(minutes + 1)
            await asyncio.sleep(0.5)
            self._set_timer(minutes)
            await asyncio.sleep(0.5)
            self._set_timer(minutes + 1)
            await asyncio.sleep(0.5)
        self._set_timer(minutes)
        # we don't call stop here as display expected to continue


class LightsTaskStatus(LightsTask):

    def set_warn(self) -> None:
        loop = asyncio.get_event_loop()
        color = (0, 0, 31)
        loop.create_task(self.flash(color, 4, 0.2))

    def set_ok(self) -> None:
        loop = asyncio.get_event_loop()
        color = (0, 31, 0)
        loop.create_task(self.flash(color, 1, 0.2))

    def set_danger(self) -> None:
        loop = asyncio.get_event_loop()
        color = (31, 0, 0)
        loop.create_task(self.flash(color, 4, 0.2))


class LightsTaskBoot(LightsTask):

    def set_boot(self) -> None:
        loop = asyncio.get_event_loop()
        color = (1, 0, 0)
        loop.create_task(self.rotate(color, 0.2))


class Lights:
    def __init__(self, pin: machine.Pin) -> None:
        self._pin = pin  # Initialise for input
        self._tasks = []  # type: List[LightsTask]

    T = TypeVar('T', bound=LightsTask)

    def create_task(self, task_type: Type[T]) -> T:
        task = task_type(
            self._pin, NUM_LIGHTS, self._write_task_ok, self._stop_task)
        self._tasks.append(task)
        return task

    def create_bg_task(self, task_type: Type[T]) -> T:
        task = task_type(
            self._pin, NUM_LIGHTS, self._write_task_ok, self._stop_task)
        self._tasks.insert(0, task)
        return task

    def _write_task_ok(self, task: LightsTask) -> bool:
        if len(self._tasks) <= 0:
            return False
        return task is self._tasks[-1]

    def _stop_task(self, task: LightsTask) -> None:
        if len(self._tasks) <= 0:
            return
        self._tasks.remove(task)
        if len(self._tasks) > 0:
            self._tasks[-1].write()
        else:
            np = neopixel.NeoPixel(self._pin, NUM_LIGHTS, timing=True)
            np.fill((0, 0, 0))
            np.write()


class MQTT:
    def __init__(
            self, server: str,
            lights: Lights, boot_lights: LightsTaskBoot) -> None:
        self._lights = lights
        self._boot_lights = boot_lights  # type: Optional[LightsTaskBoot]
        self._timer_task = None  # type: Optional[LightsTaskTimer]
        config['subs_cb'] = self._callback
        config['connect_coro'] = self._conn_han
        config['server'] = server
        MQTTClient.DEBUG = True  # Optional: print diagnostic messages
        self._client = MQTTClient(config)

    def _get_timer_task(self) -> LightsTaskTimer:
        if self._timer_task is None:
            self._timer_task = self._lights.create_bg_task(LightsTaskTimer)
        return self._timer_task

    async def _process(self, topic: str, data: Any) -> None:
        if topic.startswith('/action/Brian/'):
            print("--->", topic, data)
            if data.get('timer_warn') is not None:
                timer = data['timer_warn']
                if timer['name'] == 'default':
                    task = self._get_timer_task()
                    await task.set_timer(
                        minutes=timer['time_left'],
                        no_flash=False,
                    )
            if data.get('timer_status') is not None:
                timer = data['timer_status']
                if timer['name'] == 'default':
                    task = self._get_timer_task()
                    if timer['time_left'] == 0:
                        task.stop()
                        self._timer_task = None
                    else:
                        await task.set_timer(
                            minutes=timer['time_left'],
                            no_flash=True,
                        )
            if data.get('message') is not None:
                status_task = self._lights.create_task(LightsTaskStatus)
                status_task.set_warn()

    def _callback(self, topic: bytes, msg: bytes) -> None:
        topic_str = topic.decode('UTF8')
        msg_str = msg.decode('UTF8')

        try:
            data = json.loads(msg_str)
            coro = self._process(topic_str, data)
            loop = asyncio.get_event_loop()
            loop.create_task(coro)
        except ValueError as e:
            print("JSON Error %s" % e)

    async def _conn_han(self, client: MQTTClient) -> None:
        await client.subscribe('/action/Brian/', 0)

    async def connect(self) -> None:
        await self._client.connect()
        if self._boot_lights is not None:
            self._boot_lights.cancel()
            self._boot_lights = None

    def close(self) -> None:
        self._client.close()

    async def _publish(self, topic: str, data: Any) -> None:
        topic_raw = topic.encode('UTF8')
        msg_raw = json.dumps(data).encode('UTF8')
        print("<---", topic, data)
        await self._client.publish(topic_raw, msg_raw, qos=0)

    async def say(self, locations: List[str], text: str, flash: bool=False) -> None:
        action = {
            "message": {"text": text}
        }
        if flash:
            action['lights'] = {"action": "flash"}
        data = {
            "locations": locations,
            "action": action,
        }
        await self._publish("execute", data)

    async def lights(
            self, locations: List[str], light_action: str,
            color: Optional[Dict[str, int]]=None) -> None:
        action = {
            "lights": {"action": light_action},
        }  # type: Dict[str, Any]
        if color is not None:
            action["lights"]["color"] = color
        data = {
            "locations": locations,
            "action": action,
        }
        await self._publish("execute", data)

    async def sound(self, locations: List[str], sound: str) -> None:
        action = {
            "sound": {"name": sound},
        }
        data = {
            "locations": locations,
            "action": action,
        }
        await self._publish("execute", data)

    async def music(self, locations: List[str], play_list: Optional[str]) -> None:
        action = {}  # type: Dict[str, Any]
        if play_list is not None:
            action["music"] = {"play_list": play_list}
        else:
            action["music"] = {"stop": True}
        data = {
            "locations": locations,
            "action": action,
        }
        await self._publish("execute", data)

    async def music_lights(
            self, locations: List[str],
            play_list: Optional[str], color: Dict[str, int]) -> None:
        action = {
            "lights": {"action": "turn_on", "color": color},
            }  # type: Dict[str, Any]
        if play_list is not None:
            action["music"] = {"play_list": play_list}
        else:
            action["music"] = {"stop": True}
        data = {
            "locations": locations,
            "action": action,
        }
        await self._publish("execute", data)

    async def timer(self, locations: List[str], minutes: int) -> None:
        # FIXME
        actions = [
            {
                "timer": {
                    "name": "default",
                    "minutes": minutes,
                },
                "message": {
                    "text": "The timer is starting at %d minutes." % minutes,
                },
            },
            {
                "message": {
                    "text": "Beep beep beep. The time is up.",
                },
            }
        ]
        data = {
            "locations": locations,
            "actions": actions,
        }
        await self._publish("timer", data)


def main() -> None:
    lights = Lights(machine.Pin(13))

    boot_lights = lights.create_task(LightsTaskBoot)
    boot_lights.set_boot()

    mqtt = MQTT(MQTT_SERVER, lights, boot_lights)

    pin_UL = machine.Pin(33, machine.Pin.IN, machine.Pin.PULL_UP)
    pin_LL = machine.Pin(27, machine.Pin.IN, machine.Pin.PULL_UP)
    pin_UR = machine.Pin(15, machine.Pin.IN, machine.Pin.PULL_UP)
    pin_LR = machine.Pin(12, machine.Pin.IN, machine.Pin.PULL_UP)

    button_UL = Button(pin_UL)
    button_LL = Button(pin_LL)
    button_UR = Button(pin_UR)
    button_LR = Button(pin_LR)

    loc1 = ['Brian']
    loc2 = ['Brian']

    current_play_list = None  # type: Optional[str]
    current_color = None  # type: Optional[Dict[str, int]]

    async def button_press(play_list: str) -> None:
        print("button_press", play_list)
        nonlocal current_play_list
        if current_play_list != play_list:
            await mqtt.music(loc1, play_list)
            current_play_list = play_list
        else:
            await mqtt.music(loc1, None)
            current_play_list = None
        task = lights.create_task(LightsTaskStatus)
        task.set_ok()

    async def button_long(color: Dict[str, int]) -> None:
        print("button_long", color)
        nonlocal current_color
        if current_color != color:
            await mqtt.lights(loc1, 'turn_on', color)
            current_color = color
        else:
            await mqtt.lights(loc1, 'turn_off', color)
            current_color = None
        task = lights.create_task(LightsTaskStatus)
        task.set_ok()

    async def button_double(minutes: int) -> None:
        print("button_double", minutes)
        await mqtt.timer(loc2, minutes)

    button_UL.press_func(lambda: button_press('red'))
    button_LL.press_func(lambda: button_press('yellow'))
    button_UR.press_func(lambda: button_press('blue'))
    button_LR.press_func(lambda: button_press('white'))

    button_UL.long_func(lambda: button_long(RED))
    button_LL.long_func(lambda: button_long(YELLOW))
    button_UR.long_func(lambda: button_long(BLUE))
    button_LR.long_func(lambda: button_long(WHITE))

    button_UL.double_func(lambda: button_double(5))
    button_LL.double_func(lambda: button_double(10))
    button_UR.double_func(lambda: button_double(15))
    button_LR.double_func(lambda: button_double(30))

    async def battery() -> None:
        adc = machine.ADC(machine.Pin(35))
        adc.atten(machine.ADC.ATTN_11DB)
        while True:
            await asyncio.sleep(60)
            await mqtt._publish("battery/brian", adc.read())

    loop = asyncio.get_event_loop()
    loop.create_task(mqtt.connect())
    loop.create_task(battery())

    try:
        loop.run_forever()
    finally:
        mqtt.close()  # Prevent LmacRxBlk:1 errors
        loop.close()


main()
