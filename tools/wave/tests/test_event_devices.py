import time
import pytest
from unittest.mock import Mock

from tools.wave.testing.event_dispatcher import (
    EventDispatcher,
    STATUS_EVENT,
    RESUME_EVENT,
)
from tools.wave.testing.devices_manager import DevicesManager
from tools.wave.data.exceptions.not_found_exception import NotFoundException


def make_listener():
    listener = Mock()
    listener.dispatcher_token = "dispatcher-token"
    listener.token = None
    return listener


def make_dispatcher(cache_duration=60000):
    return EventDispatcher(cache_duration)


def test_add_event_listener_registers_and_returns_token():
    dispatcher = make_dispatcher()
    listener = make_listener()

    token = dispatcher.add_event_listener(listener)

    assert token
    assert listener.token == token
    assert dispatcher._listeners["dispatcher-token"] == [listener]


def test_remove_event_listener():
    dispatcher = make_dispatcher()
    listener = make_listener()
    token = dispatcher.add_event_listener(listener)

    dispatcher.remove_event_listener(token)

    assert "dispatcher-token" not in dispatcher._listeners
    # removing an unknown or already-removed token is a no-op
    dispatcher.remove_event_listener(token)
    dispatcher.remove_event_listener(None)


def test_dispatch_event_sends_to_registered_listeners():
    dispatcher = make_dispatcher()
    listener = make_listener()
    dispatcher.add_event_listener(listener)

    dispatcher.dispatch_event("dispatcher-token", STATUS_EVENT, data="running")

    listener.send_message.assert_called_once()
    event = listener.send_message.call_args[0][0][0]
    assert event["type"] == STATUS_EVENT
    assert event["data"] == "running"
    assert event["number"] == 0


def test_dispatch_event_without_listener_caches():
    dispatcher = make_dispatcher()

    dispatcher.dispatch_event("unknown-token", RESUME_EVENT, data="x")

    assert dispatcher._events["unknown-token"][0]["type"] == RESUME_EVENT


def test_dispatch_event_increments_event_numbers():
    dispatcher = make_dispatcher()

    dispatcher.dispatch_event("token", STATUS_EVENT, data="a")
    dispatcher.dispatch_event("token", STATUS_EVENT, data="b")

    numbers = [e["number"] for e in dispatcher._events["token"]]
    assert numbers == [0, 1]


def test_add_event_listener_replays_missed_events():
    dispatcher = make_dispatcher()

    dispatcher.dispatch_event("dispatcher-token", STATUS_EVENT, data="a")
    dispatcher.dispatch_event("dispatcher-token", STATUS_EVENT, data="b")

    late_listener = make_listener()

    def send_message_with_capture(events):
        send_message_with_capture.received = events
    late_listener.send_message.side_effect = send_message_with_capture

    dispatcher.add_event_listener(late_listener, last_event_number=0)

    received = send_message_with_capture.received
    assert [e["data"] for e in received] == ["b"]


def test_delete_expired_events():
    dispatcher = make_dispatcher(cache_duration=0)

    dispatcher.dispatch_event("token", STATUS_EVENT, data="a")
    assert len(dispatcher._events["token"]) == 1

    # the event's expiration_date is now + 0; wait past that millisecond
    time.sleep(0.002)
    dispatcher._delete_expired_events()
    assert "token" not in dispatcher._events


def test_devices_manager_create_device_dispatches_add_event():
    event_dispatcher = Mock()
    manager = DevicesManager()
    manager.initialize(event_dispatcher)

    device = manager.create_device(
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36")

    assert device.token in manager.devices
    assert device.name == "Chrome 121.0.0"
    event_dispatcher.dispatch_event.assert_called_once()
    args = event_dispatcher.dispatch_event.call_args
    assert args[0][0] == "devices"
    assert args[0][1] == "device_added"


def test_devices_manager_read_device_unknown_raises():
    manager = DevicesManager()
    manager.initialize(Mock())

    with pytest.raises(NotFoundException):
        manager.read_device("missing-token")


def test_devices_manager_update_delete_refresh():
    event_dispatcher = Mock()
    manager = DevicesManager()
    manager.initialize(event_dispatcher)
    device = manager.create_device("Firefox/120.0")

    # updating an unknown device is a no-op
    stranger = Mock()
    stranger.token = "stranger"
    manager.update_device(stranger)
    assert "stranger" not in manager.devices

    # refresh updates last_active
    old_last_active = device.last_active
    manager.refresh_device(device.token)
    assert manager.devices[device.token].last_active >= old_last_active

    # delete dispatches removal
    manager.delete_device(device.token)
    assert device.token not in manager.devices
    assert event_dispatcher.dispatch_event.call_count == 2
    args = event_dispatcher.dispatch_event.call_args
    assert args[0][1] == "device_removed"

    # deleting again is a no-op
    manager.delete_device(device.token)


def test_devices_manager_read_devices():
    manager = DevicesManager()
    manager.initialize(Mock())
    manager.create_device("Firefox/120.0")
    manager.create_device("Chrome/121.0")

    devices = manager.read_devices()

    assert len(devices) == 2


def test_devices_manager_post_events():
    event_dispatcher = Mock()
    manager = DevicesManager()
    manager.initialize(event_dispatcher)

    manager.post_event("handle", "custom_event", {"x": 1})
    manager.post_global_event("global_event", {"y": 2})
    manager.post_event("handle", None, {"skipped": True})

    assert event_dispatcher.dispatch_event.call_count == 2
