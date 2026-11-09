import json
from unittest.mock import Mock

from tools.wave.network.api.api_handler import ApiHandler
from tools.wave.network.api.general_api_handler import GeneralApiHandler
from tools.wave.network.api.sessions_api_handler import SessionsApiHandler
from tools.wave.network.api.devices_api_handler import DevicesApiHandler
from tools.wave.data.exceptions.invalid_data_exception import InvalidDataException
from tools.wave.data.exceptions.not_found_exception import NotFoundException


def make_request(path="/_wave/api/sessions", query="", method="GET",
                 user_agent="Firefox/120.0"):
    request = Mock()
    request.method = method
    request.url_parts.path = path
    request.url_parts.query = query
    request.headers = {b"user-agent": user_agent.encode("utf-8")}
    return request


def make_response():
    response = Mock()
    response.headers = []
    response.content = None
    response.status = None
    return response


def make_web_root():
    return "/_wave"


def make_general_handler():
    return GeneralApiHandler(
        web_root=make_web_root(),
        read_sessions_enabled=True,
        import_results_enabled=False,
        reports_enabled=False,
        version_string="v3.0.2",
        dpctf_version_string="v0.4.3",
        test_type_selection_enabled=False,
    )


def make_sessions_handler(sessions_manager, read_sessions_enabled=True):
    return SessionsApiHandler(
        sessions_manager=sessions_manager,
        results_manager=Mock(),
        event_dispatcher=Mock(),
        web_root=make_web_root(),
        read_sessions_enabled=read_sessions_enabled,
    )


def test_api_handler_parse_uri_strips_web_root():
    handler = ApiHandler(make_web_root())

    uri_parts = handler.parse_uri(make_request("/_wave/api/sessions"))

    assert uri_parts == ["api", "sessions"]


def test_api_handler_parse_uri_without_web_root():
    handler = ApiHandler(None)

    uri_parts = handler.parse_uri(make_request("/api/sessions/token"))

    assert uri_parts == ["api", "sessions", "token"]


def test_api_handler_parse_query_parameters():
    handler = ApiHandler(None)

    params = handler.parse_query_parameters(
        make_request(query="index=10&count=5"))

    assert params == {"index": "10", "count": "5"}


def test_api_handler_send_json_sets_content_headers_status():
    handler = ApiHandler(None)
    response = make_response()

    handler.send_json({"token": "x"}, response)

    assert json.loads(response.content) == {"token": "x"}
    assert response.status == 200
    assert ("Content-Type", "application/json") in response.headers


def test_api_handler_send_json_with_status():
    handler = ApiHandler(None)
    response = make_response()

    handler.send_json({"error": "x"}, response, status=400)

    assert response.status == 400


def test_api_handler_send_file_and_zip():
    handler = ApiHandler(None)
    response = make_response()

    handler.send_file(b"blob", "results.zip", response)

    assert response.content == b"blob"
    assert ("Content-Disposition", "attachment;filename=results.zip") \
        in response.headers

    zip_response = make_response()
    handler.send_zip(b"data", "export.zip", zip_response)
    assert ("Content-Type", "application/x-compressed") in zip_response.headers


def test_api_handler_create_hal_list_pagination():
    handler = ApiHandler(None)

    hal = handler.create_hal_list(
        items=["a", "b"],
        uris={"self": "/api/sessions", "sessions": "/api/sessions/{token}"},
        index=0,
        count=2,
        total=6,
    )

    assert hal["items"] == ["a", "b"]
    links = hal["_links"]
    assert links["sessions"]["templated"] is True
    assert links["self"]["href"] == "/api/sessions?index=0&count=2"
    assert links["first"]["href"] == "/api/sessions?index=0&count=2"
    # last = total - (total % count) = 6 for total=6, count=2
    assert links["last"]["href"] == "/api/sessions?index=6&count=2"
    assert links["next"]["href"] == "/api/sessions?index=2&count=2"
    assert "previous" not in links


def test_api_handler_create_hal_list_previous_link():
    handler = ApiHandler(None)

    hal = handler.create_hal_list(
        items=["a"], uris={"self": "/api/sessions"}, index=2, count=2, total=6)

    assert hal["_links"]["previous"]["href"] == "/api/sessions?index=0&count=2"
    assert hal["_links"]["next"]["href"] == "/api/sessions?index=4&count=2"


def test_general_handler_read_status():
    handler = make_general_handler()

    result = handler.read_status()

    assert result["format"] == "application/json"
    assert result["data"]["version_string"] == "v3.0.2"
    assert result["data"]["dpctf_version_string"] == "v0.4.3"
    assert result["data"]["read_sessions_enabled"] is True
    assert result["data"]["import_results_enabled"] is False


def test_general_handler_serves_status_over_get():
    handler = make_general_handler()
    response = make_response()

    handler.handle_request(make_request("/_wave/api/status"), response)

    assert response.status == 200
    assert json.loads(response.content)["version_string"] == "v3.0.2"


def test_general_handler_unknown_request_is_404():
    handler = make_general_handler()
    response = make_response()

    handler.handle_request(make_request("/_wave/api/unknown"), response)

    assert response.status == 404


def test_sessions_handler_create_session_returns_token():
    sessions_manager = Mock()
    session = Mock()
    session.token = "new-token"
    sessions_manager.create_session.return_value = session
    handler = make_sessions_handler(sessions_manager)

    result = handler.create_session(
        json.dumps({"tests": {"include": ["/group"]}}).encode("utf-8"),
        make_request().headers)

    assert result["data"]["token"] == "new-token"
    sessions_manager.create_session.assert_called_once()


def test_sessions_handler_create_session_empty_body():
    sessions_manager = Mock()
    handler = make_sessions_handler(sessions_manager)

    result = handler.create_session(b"", make_request().headers)

    assert result["data"]["token"]
    sessions_manager.create_session.assert_called_once()


def test_sessions_handler_create_session_invalid_data_is_400():
    sessions_manager = Mock()
    sessions_manager.create_session.side_effect = InvalidDataException("bad")
    handler = make_sessions_handler(sessions_manager)

    result = handler.create_session(b"{}", make_request().headers)

    assert result["status"] == 400
    assert result["data"]["error"] == "Invalid input data!"


def test_sessions_handler_create_session_unexpected_error_is_500():
    sessions_manager = Mock()
    sessions_manager.create_session.side_effect = RuntimeError("boom")
    handler = make_sessions_handler(sessions_manager)

    result = handler.create_session(b"{}", make_request().headers)

    assert result == {"status": 500}


def test_sessions_handler_read_session_serializes_public_fields():
    sessions_manager = Mock()
    from tools.wave.data.session import Session
    session = Session()
    session.token = "token"
    sessions_manager.read_session.return_value = session
    handler = make_sessions_handler(sessions_manager)

    result = handler.read_session("token")

    for key in ("token", "tests", "types", "timeouts", "reference_tokens",
                "user_agent", "browser", "is_public", "date_created", "labels"):
        assert key in result["data"]


def test_sessions_handler_read_session_unknown_is_404():
    sessions_manager = Mock()
    sessions_manager.read_session.return_value = None
    handler = make_sessions_handler(sessions_manager)

    result = handler.read_session("missing-token")

    assert result == {"status": 404}


def test_sessions_handler_read_sessions_paginates_with_hal():
    sessions_manager = Mock()
    sessions_manager.read_sessions.return_value = ["token-0", "token-1"]
    sessions_manager.get_total_sessions.return_value = 4
    handler = make_sessions_handler(sessions_manager)

    result = handler.read_sessions(
        {"index": "0", "count": "2"}, "/api/sessions")

    assert result["format"] == "application/json"
    data = result["data"]
    assert data["items"] == ["token-0", "token-1"]
    links = data["_links"]
    assert "next" in links
    assert "previous" not in links
    # _embedded only appears when the expand query parameter is used
    assert "_embedded" not in data


def test_sessions_handler_read_sessions_disabled():
    # read_sessions itself does not consult the flag; the handler stores it
    sessions_manager = Mock()
    handler = make_sessions_handler(sessions_manager, read_sessions_enabled=False)

    assert handler._read_sessions_enabled is False


def test_devices_handler_read_devices():
    devices_manager = Mock()
    from tools.wave.data.device import Device
    devices_manager.read_devices.return_value = [
        Device("t1", "Firefox/120.0", "Firefox 120.0", 1690000000000),
    ]
    handler = DevicesApiHandler(devices_manager, Mock(), make_web_root())
    response = make_response()

    handler.read_devices(make_request("/_wave/api/devices"), response)

    assert response.status == 200
    devices = json.loads(response.content)
    assert len(devices) == 1
    assert devices[0]["token"] == "t1"


def test_devices_handler_read_device_unknown_is_404():
    devices_manager = Mock()
    devices_manager.read_device.side_effect = NotFoundException("nope")
    handler = DevicesApiHandler(devices_manager, Mock(), make_web_root())
    response = make_response()

    handler.read_device(make_request("/_wave/api/devices/missing"), response)

    assert response.status == 404


def test_devices_handler_read_device():
    devices_manager = Mock()
    from tools.wave.data.device import Device
    devices_manager.read_device.return_value = Device(
        "found", "Firefox/120.0", "Firefox 120.0", 1690000000000)
    handler = DevicesApiHandler(devices_manager, Mock(), make_web_root())
    response = make_response()

    handler.read_device(make_request("/_wave/api/devices/found"), response)

    assert response.status == 200
    assert json.loads(response.content)["token"] == "found"


def test_devices_handler_create_device():
    devices_manager = Mock()
    device = Mock()
    device.token = "created-token"
    devices_manager.create_device.return_value = device
    handler = DevicesApiHandler(devices_manager, Mock(), make_web_root())
    response = make_response()

    handler.create_device(make_request("/_wave/api/devices"), response)

    assert response.status == 200
    assert json.loads(response.content)["token"] == "created-token"
    devices_manager.create_device.assert_called_once_with("Firefox/120.0")
