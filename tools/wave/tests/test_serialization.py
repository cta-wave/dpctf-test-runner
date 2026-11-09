from tools.wave.utils.serializer import (
    serialize_session,
    serialize_sessions,
    serialize_device,
    millis_to_iso,
)
from tools.wave.utils.deserializer import (
    deserialize_session,
    deserialize_sessions,
    iso_to_millis,
)
from tools.wave.data.session import Session, UNKNOWN, WMAS
from tools.wave.data.device import Device


def make_session():
    session = Session()
    session.token = "roundtrip-token"
    session.test_types = ["automatic"]
    session.user_agent = "Firefox/120.0"
    session.labels = ["qa"]
    session.tests = {"include": ["/group"], "exclude": []}
    session.timeouts = {"automatic": 60000}
    session.status = UNKNOWN
    session.test_state = {"group": {"pass": 1}}
    session.last_completed_test = None
    session.date_created = 1690000000000
    session.date_started = 1690000001000
    session.date_finished = None
    session.is_public = False
    session.reference_tokens = ["ref"]
    session.expiration_date = None
    session.type = WMAS
    session.malfunctioning_tests = []
    return session


def test_serialize_session_contains_expected_keys():
    session = make_session()
    serialized = serialize_session(session)

    for key in ("token", "types", "user_agent", "labels", "timeouts",
                "test_state", "tests", "status", "browser", "date_created",
                "date_started", "date_finished", "is_public",
                "reference_tokens", "expiration_date", "type",
                "malfunctioning_tests"):
        assert key in serialized

    assert serialized["token"] == "roundtrip-token"
    assert serialized["is_public"] is False


def test_serialize_sessions_maps_each_session():
    sessions = [make_session(), make_session()]
    serialized = serialize_sessions(sessions)

    assert len(serialized) == 2
    assert all(s["token"] == "roundtrip-token" for s in serialized)


def test_millis_to_iso():
    assert millis_to_iso(None) is None
    iso = millis_to_iso(0)
    assert iso == "1970-01-01T00:00:00+00:00"
    iso = millis_to_iso(1690000000000)
    assert iso.startswith("2023-07-22T")


def test_deserialize_session_applies_defaults():
    session = deserialize_session({})

    assert session.token == ""
    assert session.status == UNKNOWN
    assert session.is_public is False
    assert session.type == WMAS
    assert session.test_types == []
    assert session.labels == []
    assert session.reference_tokens == []
    assert session.malfunctioning_tests == []
    assert session.tests == {"include": [], "exclude": []}


def test_deserialize_session_reads_fields():
    serialized = {
        "token": "loaded-token",
        "status": "running",
        "tests": {"include": ["/group"], "exclude": []},
        "types": ["manual"],
        "timeouts": {"automatic": 1},
        "is_public": True,
        "labels": ["x"],
        "test_state": {"group": {}},
        "last_completed_test": "/group/test1.html",
        "malfunctioning_tests": ["/group/broken.html"],
    }
    session = deserialize_session(serialized)

    assert session.token == "loaded-token"
    assert session.status == "running"
    assert session.test_types == ["manual"]
    assert session.is_public is True
    assert session.last_completed_test == "/group/test1.html"
    assert session.malfunctioning_tests == ["/group/broken.html"]


def test_deserialize_session_converts_dates():
    serialized = {
        "token": "dates-token",
        "date_created": "1970-01-01T00:00:00+00:00",
        "date_started": "1970-01-01T00:01:00+00:00",
        "date_finished": "1970-01-01T00:02:00+00:00",
        "expiration_date": "1970-01-01T00:03:00+00:00",
    }
    session = deserialize_session(serialized)

    assert session.date_created == 0
    assert session.date_started == 60000
    assert session.date_finished == 120000
    assert session.expiration_date == 180000


def test_deserialize_sessions_maps_each():
    sessions = deserialize_sessions([{"token": "a"}, {"token": "b"}])

    assert [s.token for s in sessions] == ["a", "b"]


def test_deserialize_session_path_becomes_include():
    session = deserialize_session({"path": "/group, /other"})

    assert "/group" in session.tests["include"]
    assert "/other" in session.tests["include"]


def test_iso_to_millis_handles_none_and_invalid():
    assert iso_to_millis(None) is None
    # an unparseable string is passed through unchanged
    assert iso_to_millis("not-a-date") == "not-a-date"


def test_iso_to_millis_parses_utc():
    assert iso_to_millis("1970-01-01T00:01:00+00:00") == 60000


def test_serialize_serialize_roundtrip():
    session = make_session()
    restored = deserialize_session(serialize_session(session))

    assert restored.token == session.token
    assert restored.test_types == session.test_types
    assert restored.user_agent == session.user_agent
    assert restored.labels == session.labels
    assert restored.status == session.status
    assert restored.reference_tokens == session.reference_tokens
    assert restored.date_created == session.date_created


def test_serialize_device():
    device = Device("device-token", "Firefox/120.0", "Firefox 120.0", 1690000000000)

    serialized = serialize_device(device)

    assert serialized["token"] == "device-token"
    assert serialized["name"] == "Firefox 120.0"
    assert serialized["user_agent"] == "Firefox/120.0"
    assert serialized["last_active"].startswith("2023-07-22T")
