import abc

from subscriptions import Subscriptions

try:
    from typing import Any, Awaitable, Callable, List, Optional, Tuple
except ImportError:
    pass


class Config:
    name: str
    id: str
    location: str
    device: str
    type: str
    action: str
    params: dict[str, Any]

    def __init__(
            self, name: str, id: str, location: str, device: str, type: str, action: str, params: dict[str, Any]
            ) -> None:
        self.name = name
        self.id = id
        self.location = location
        self.device = device
        self.type = type
        self.action = action
        self.params = params


Callback = Callable[[Config, list[str], str, Any], Awaitable[None]]


class Command():
    location: str
    device: str
    message: dict[str, Any]


class Button():
    config: Config

    @abc.abstractmethod
    def __init__(self, config: Config) -> None:
        raise NotImplementedError()

    @abc.abstractmethod
    def get_topics(self) -> List[Tuple[List[str], str, str]]:
        raise NotImplementedError()

    @abc.abstractmethod
    def process_nessage(self, label: str, data: Any) -> None:
        raise NotImplementedError()

    @abc.abstractmethod
    def get_display_state(self) -> str:
        raise NotImplementedError()

    @abc.abstractmethod
    def get_press_commands(self) -> List[Command]:
        raise NotImplementedError()


def _has_scene(scenes: Optional[List[str]], scene: str) -> Optional[bool]:
    if scenes is None:
        return None
    else:
        return scene in scenes


def _has_priority(priorities: Optional[List[int]], priority: int) -> Optional[bool]:
    if priorities is None:
        return None
    else:
        return priority in priorities


class LightButton(Button):
    power: Optional[str]
    scenes: Optional[List[str]]
    priorities: Optional[List[int]]

    def __init__(self, config: Config) -> None:
        self.power = None
        self.scenes = None
        self.priorities = None
        self.config = config

    def get_topics(self) -> List[Tuple[List[str], str, str]]:
        config = self.config

        return [
            (
                ["state", config.location, config.device, "power"],
                "raw", "power"
            ),
            (
                ["state", config.location, config.device, "scenes"],
                "json", "scenes"
            ),
            (
                ["state", config.location, config.device, "priorities"],
                "json", "priorities"
            )
        ]

    def process_nessage(self, label: str, data: Any) -> None:
        if label == "power":
            self.power = data
        elif label == "scenes":
            self.scenes = data
        elif label == "priorities":
            self.priorities = data
        else:
            raise RuntimeError("Unknown label {}".format(label))

    def get_display_state(self) -> str:
        config = self.config
        correct_scene = _has_scene(self.scenes, config.params["scene"])
        correct_priority = _has_priority(self.priorities, config.params["priority"])

        if self.power == "HARD_OFF":
            return "state_hard_off"
        elif config.action == "turn_on":
            if self.power == "ON" and self.scenes == []:
                return "state_on"
            elif self.power == "OFF" and self.scenes == []:
                return "state_off"
            elif correct_scene is None:
                return "state_unknown"
            elif correct_scene is True:
                return "state_on"
            elif correct_scene is False:
                return "state_off"
            else:
                raise RuntimeError()
        elif config.action == "turn_off":
            if self.power == "ON" and self.scenes == []:
                return "state_off"
            elif self.power == "OFF" and self.scenes == []:
                return "state_on"
            elif correct_priority is None:
                return "state_unknown"
            elif correct_priority is True:
                return "state_off"
            elif correct_priority is False:
                return "state_on"
            else:
                raise RuntimeError()
        elif config.action == "toggle":
            if self.power == "ON" and self.scenes == []:
                return "state_on"
            elif self.power == "OFF" and self.scenes == []:
                return "state_off"
            elif correct_scene is None:
                return "state_unknown"
            elif correct_scene is True:
                return "state_on"
            elif correct_scene is False:
                return "state_off"
            else:
                raise RuntimeError()
        else:
            raise RuntimeError()

    def get_press_commands(self) -> List[Command]:
        config = self.config
        message = {
            "scene": config.params["scene"],
            "priority": config.params["priority"]
        }

        if config.action == "turn_on":
            pass
        elif config.action == "turn_off":
            message["action"] = "turn_off"
        elif config.action == "toggle":
            display_state = self.get_display_state()
            if display_state == "state_on":
                message["action"] = "turn_off"
        else:
            raise RuntimeError()

        command = Command()
        command.location = config.location
        command.device = config.device
        command.message = message
        return [command]


class SwitchButton(Button):
    power: Optional[str]

    def __init__(self, config: Config) -> None:
        self.power = None
        self.config = config

    def get_topics(self) -> List[Tuple[List[str], str, str]]:
        config = self.config

        return [
            (
                ["state", config.location, config.device, "power"],
                "raw", "power"
            ),
        ]

    def process_nessage(self, label: str, data: Any) -> None:
        if label == "power":
            self.power = data or None
        else:
            raise RuntimeError("Unknown label {}".format(label))

    def get_display_state(self) -> str:
        config = self.config

        if self.power == "HARD_OFF":
            return "state_hard_off"
        elif self.power == "HARD_OFF":
            return "state_error"
        elif self.power is None:
            return "state_unknown"
        elif config.action == "turn_on":
            if self.power == "ON":
                return "state_on"
            elif self.power == "OFF":
                return "state_off"
            else:
                raise RuntimeError()
        elif config.action == "turn_off":
            if self.power == "ON":
                return "state_off"
            elif self.power == "OFF":
                return "state_on"
            else:
                raise RuntimeError()
        elif config.action == "toggle":
            if self.power == "ON":
                return "state_on"
            elif self.power == "OFF":
                return "state_off"
            else:
                raise RuntimeError()
        else:
            raise RuntimeError()

    def get_press_commands(self) -> List[Command]:
        config = self.config
        message = {}

        if config.action == "turn_on":
            message["action"] = "turn_on"
        elif config.action == "turn_off":
            message["action"] = "turn_off"
        elif config.action == "toggle":
            display_state = self.get_display_state()
            if display_state == "state_on":
                message["action"] = "turn_off"
            else:
                message["action"] = "turn_on"
        else:
            raise RuntimeError()

        command = Command()
        command.location = config.location
        command.device = config.device
        command.message = message
        return [command]


def get_button_controller(config: Config) -> Button:
    if config.type == "light":
        return LightButton(config)
    elif config.type == "switch":
        return SwitchButton(config)

    raise RuntimeError("Uknown button type {}".format(config.type))


async def subscribe_topics(button: Button, subscriptions: Subscriptions, callback: Callback) -> None:
    topics = button.get_topics()

    async def internal_callback(topic: list[str], label: str, data: Any) -> None:
        await callback(button.config, topic, label, data)

    for topic, format, label in topics:
        await subscriptions.subscribe(topic, label, internal_callback, format)
