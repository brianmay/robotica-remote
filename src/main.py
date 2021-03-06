import json

import buttons
import uasyncio as asyncio
import asyn
import aswitch
import machine
import neopixel

from mqtt_as import MQTTClient
from config import config
import subscriptions

try:
    from typing import Any, Dict, List, Callable, Optional, Tuple
    from typing import Type, TypeVar
    Color = Tuple[int, int, int]
    Callback = Callable[[], Any]
except ImportError:
    def TypeVar(*args: None, **kwargs: None) -> None:  # type: ignore
        pass

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


def _handle_exception(loop: asyncio.AbstractEventLoop, context: Dict[str, Any]) -> None:
    print('Global handler')
    print(context)
    print(context["exception"])


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

    async def set_timer(self, minutes: int, no_flash: bool = False) -> None:
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


class LightsTaskColor(LightsTask):
    async def _set_color(self, color: Color) -> None:
        try:
            while not self._cancel:
                self.fill(color)
                self.write()

                await asyncio.sleep(1000)
        finally:
            # self.clear()
            # self.write()
            self.stop()

    def set_color(self, color: Color) -> None:
        loop = asyncio.get_event_loop()
        loop.create_task(self._set_color(color))


class LightsTaskButtonColor(LightsTask):

    def set_button_colors(self, number: int, colors: List[Color]) -> None:
        number = number*4 + 2
        self[(number+0) % 16] = colors[0]
        self[(number+1) % 16] = colors[1]
        self[(number+2) % 16] = colors[2]
        self[(number+3) % 16] = colors[3]
        self.write()


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

    def create_task(self, task_type: Type[T]) -> 'T':
        task = task_type(
            self._pin, NUM_LIGHTS, self._write_task_ok, self._stop_task)
        self._tasks.append(task)
        return task

    def create_bg_task(self, task_type: Type[T]) -> 'T':
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
    def __init__(self) -> None:
        config['subs_cb'] = self._callback
        config['connect_coro'] = self._conn_han
        MQTTClient.DEBUG = True  # Optional: print diagnostic messages
        self._client = MQTTClient(config)
        self.subscriptions = subscriptions.Subscriptions(self._client)

    def _callback(self, topic: bytes, message: bytes, retained: bool) -> None:
        print("MQTT._callback()")
        print("--->", topic, message, retained)
        try:
            coro = self.subscriptions.message(topic, message, retained)
            loop = asyncio.get_event_loop()
            loop.create_task(coro)
        except ValueError as e:
            print("JSON Error %s" % e)

        print("MQTT._callback() done")

    async def _conn_han(self, client: MQTTClient) -> None:
        print("MQTT._conn_han()")
        await self.subscriptions.connected()
        print("MQTT._conn_han() done")

    async def connect(self) -> None:
        print("MQTT.connect()")
        await self._client.connect()
        print("MQTT._conn_han() done")

    def close(self) -> None:
        print("MQTT.close()")
        self._client.close()
        print("MQTT.close() done")

    async def _publish(self, topic: str, data: Any) -> None:
        topic_raw = topic.encode('UTF8')
        msg_raw = json.dumps(data).encode('UTF8')
        print("<---", topic, data)
        await self._client.publish(topic_raw, msg_raw, qos=0)

    async def lights(
            self, location: str, device: str, light_action: str,
            color: Optional[Dict[str, int]] = None) -> None:
        command = {
            "action": light_action,
            "scene": "default",
        }  # type: Dict[str, Any]
        if color is not None:
            command["color"] = color
        await self._publish("command/{}/{}".format(location, device), command)

    async def command(
            self, location: str, device: str, message: Dict[str, Any]) -> None:
        await self._publish("command/{}/{}".format(location, device), message)


button_configs: List[buttons.Config] = [
    buttons.Config(
        name="Brian",
        id="0",
        location="Brian",
        device="Light",
        type="light",
        action="toggle",
        params={
            "scene": "default",
            "priority": 100
        }
    ),
    buttons.Config(
        name="Passage",
        id="1",
        location="Passage",
        device="Light",
        type="light",
        action="toggle",
        params={
            "scene": "default",
            "priority": 100
        }
    ),
    buttons.Config(
        name="Twins",
        id="2",
        location="Twins",
        device="Light",
        type="light",
        action="toggle",
        params={
            "scene": "default",
            "priority": 100
        }
    ),
    buttons.Config(
        name="Fan",
        id="3",
        location="Brian",
        device="Fan",
        type="switch",
        action="toggle",
        params={}
    ),
    buttons.Config(
        name="Night",
        id="night",
        location="Brian",
        device="Night",
        type="switch",
        action="toggle",
        params={}
    )
]


def main() -> None:
    lights = Lights(machine.Pin(13))
    dict_buttons: Dict[str, buttons.Button] = {}

    for button_config in button_configs:
        dict_buttons[button_config.id] = buttons.get_button_controller(button_config)

    button_lights = lights.create_task(LightsTaskButtonColor)

    boot_lights = lights.create_task(LightsTaskBoot)
    boot_lights.set_boot()

    black_task: Optional[LightsTaskColor] = None

    mqtt = MQTT()

    pin_UL = machine.Pin(33, machine.Pin.IN, machine.Pin.PULL_UP)
    pin_LL = machine.Pin(27, machine.Pin.IN, machine.Pin.PULL_UP)
    pin_UR = machine.Pin(15, machine.Pin.IN, machine.Pin.PULL_UP)
    pin_LR = machine.Pin(12, machine.Pin.IN, machine.Pin.PULL_UP)

    button_UL = Button(pin_UL)
    button_LL = Button(pin_LL)
    button_UR = Button(pin_UR)
    button_LR = Button(pin_LR)

    async def button_press(number: int) -> None:
        print("button_press", number)
        button = dict_buttons[str(number)]
        for command in button.get_press_commands():
            print(command.message)
            await mqtt.command(command.location, command.device, command.message)

    async def button_long(number: int) -> None:
        print("button_long", number)
        button = dict_buttons[str(number)]
        for command in button.get_long_commands():
            print(command.message)
            await mqtt.command(command.location, command.device, command.message)

    async def button_double(number: int) -> None:
        print("button_double", number)
        button = dict_buttons[str(number)]
        for command in button.get_double_commands():
            print(command.message)
            await mqtt.command(command.location, command.device, command.message)

    button_UL.press_func(lambda: button_press(0))
    button_LL.press_func(lambda: button_press(1))
    button_LR.press_func(lambda: button_press(2))
    button_UR.press_func(lambda: button_press(3))

    button_UL.long_func(lambda: button_long(0))
    button_LL.long_func(lambda: button_long(1))
    button_LR.long_func(lambda: button_long(2))
    button_UR.long_func(lambda: button_long(3))

    button_UL.double_func(lambda: button_double(0))
    button_LL.double_func(lambda: button_double(1))
    button_LR.double_func(lambda: button_double(2))
    button_UR.double_func(lambda: button_double(3))

    async def callback(config: buttons.Config, topic: List[str], label: str, data: Any) -> None:
        button = dict_buttons[config.id]
        button.process_nessage(label, data)
        state = button.get_display_state()

        if config.id == "night":
            nonlocal black_task
            if state == "state_on" and black_task is None:
                black_task = lights.create_task(LightsTaskColor)
                black_task.set_color((0, 0, 0))
            if state != "state_on" and black_task is not None:
                black_task.stop()
                black_task = None
        else:
            number = int(config.id)

            colors = [(0, 0, 0)]*4
            if state == "state_on":
                colors = [(0, 1, 0)]*4
            elif state == "state_dim":
                colors = [(1, 1, 0)]*4
            elif state == "state_rainbow":
                colors = [(1, 0, 0), (0, 1, 0), (0, 0, 1), (1, 0, 1)]
            elif state == "state_off":
                colors = [(0, 0, 1)]*4
            elif state == "state_error":
                colors = [(1, 0, 0)]*4
            elif state == "state_hard_off":
                colors = [(0, 0, 0)]*4
            elif state == "state_unknown":
                colors = [(0, 0, 0)]*4

            print("{}=={}=={}".format(number, state, colors))
            button_lights.set_button_colors(number, colors)

    async def subscribe() -> None:
        await mqtt.connect()
        for button in dict_buttons.values():
            await buttons.subscribe_topics(button, mqtt.subscriptions, callback)
        boot_lights.cancel()

    async def battery() -> None:
        adc = machine.ADC(machine.Pin(35))
        adc.atten(machine.ADC.ATTN_11DB)
        while True:
            await asyncio.sleep(60)
            await mqtt._publish("battery/brian", adc.read())

    loop = asyncio.get_event_loop()
    loop.set_exception_handler(_handle_exception)
    loop.create_task(subscribe())
    loop.create_task(battery())

    try:
        loop.run_forever()
    finally:
        mqtt.close()  # Prevent LmacRxBlk:1 errors
        loop.close()


main()
