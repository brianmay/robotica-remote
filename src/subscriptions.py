import json
from mqtt_as import MQTTClient

try:
    from typing import Callable, Any, Awaitable, List
except ImportError:
    pass


Callback = Callable[[List[str], str, Any], Awaitable[None]]
SubscriptionDetails = tuple[str, Callback, str]


def _get_message_format(message_str: str, format: str) -> Any:
    if format == "json":
        return json.loads(message_str)
    elif format == "raw":
        return message_str
    else:
        raise RuntimeError("Unknown message format %s" % format)


async def _send_to_client(topic: list[str], label: Any, callback: Callback, format: str, message_str: str) -> None:
    message = _get_message_format(message_str, format)
    await callback(topic, label, message)


class Subscriptions:
    _client: MQTTClient
    _subscriptions: dict[str, list[SubscriptionDetails]]
    _last_message: dict[str, str]

    def __init__(self, client: MQTTClient) -> None:
        print("Subscription.__init__()")
        self._client = client
        self._subscriptions = {}
        self._last_message = {}

    async def connected(self) -> None:
        print("Subscription.connect()")
        for topic_str in self._subscriptions.keys():
            print("Subscription.connect() subscribing to {}".format(topic_str))
            await self._client.subscribe(topic_str, 0)

    async def subscribe(self, topic: list[str], label: Any, callback: Callback, format: str) -> None:
        print("Subscription.subscribe()")
        topic_str = "/".join(topic)
        subscriptions: list[SubscriptionDetails] = []

        if topic_str in self._subscriptions:
            print("Subscription.subscribe(): Adding subscription to {}.".format(topic_str))
            subscriptions = self._subscriptions[topic_str]
        else:
            print("Subscription.subscribe(): Creating subscription to {}.".format(topic_str))
            await self._client.subscribe(topic_str, 0)
            print("Subscription.subscribe(): Done creating subscription to {}.".format(topic_str))

        subscriptions = subscriptions + [(label, callback, format)]
        self._subscriptions[topic_str] = subscriptions

        if topic_str in self._last_message:
            raw = self._last_message[topic_str]
            await _send_to_client(topic, label, callback, format, raw)

    async def message(self, topic_bytes: bytes, message_bytes: bytes, retained: bool) -> None:
        topic_str = topic_bytes.decode("UTF8")
        message_str = message_bytes.decode("UTF8")
        topic = topic_str.split("/")
        if retained:
            self._last_message[topic_str] = message_str
        for label, callback, format in self._subscriptions.get(topic_str, []):
            await _send_to_client(topic, label, callback, format, message_str)
