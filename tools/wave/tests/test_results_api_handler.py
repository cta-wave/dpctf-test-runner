import json
from unittest.mock import Mock

from tools.wave.network.api.results_api_handler import ResultsApiHandler
from tools.wave.data.exceptions.duplicate_exception import DuplicateException
from tools.wave.data.exceptions.invalid_data_exception import InvalidDataException
from tools.wave.data.exceptions.not_found_exception import NotFoundException
from tools.wave.data.exceptions.permission_denied_exception import PermissionDeniedException


def make_handler(manager):
    return ResultsApiHandler(manager, Mock(), None)


def make_upload_request():
    request = Mock()
    request.url_parts.path = "/api/results/token/group/json"
    request.body = b'{"results": []}'
    return request


def make_import_request():
    request = Mock()
    request.url_parts.path = "/api/results/import"
    request.body = b"zip blob"
    return request


def make_response():
    response = Mock()
    response.headers = []
    return response


def test_upload_api_json_maps_unknown_session_to_404():
    manager = Mock()
    manager.import_results_api_json.side_effect = NotFoundException()
    handler = make_handler(manager)
    response = make_response()

    handler.import_results_api_json(make_upload_request(), response)

    assert response.status == 404
    body = json.loads(response.content)
    assert body == {"error": "Could not find session!"}
    assert ("Content-Type", "application/json") in response.headers


def test_upload_api_json_maps_invalid_data_to_400():
    manager = Mock()
    manager.import_results_api_json.side_effect = InvalidDataException()
    handler = make_handler(manager)
    response = make_response()

    handler.import_results_api_json(make_upload_request(), response)

    assert response.status == 400
    body = json.loads(response.content)
    assert body == {"error": "Invalid input data!"}
    assert ("Content-Type", "application/json") in response.headers


def test_upload_api_json_maps_permission_error_to_500():
    manager = Mock()
    manager.import_results_api_json.side_effect = PermissionError(13)
    handler = make_handler(manager)
    response = make_response()

    handler.import_results_api_json(make_upload_request(), response)

    assert response.status == 500


def test_import_results_maps_permission_denied_to_403():
    manager = Mock()
    manager.import_results.side_effect = PermissionDeniedException()
    handler = make_handler(manager)
    response = make_response()

    handler.import_results(make_import_request(), response)

    assert response.status == 403


def test_import_results_maps_duplicate_to_400():
    manager = Mock()
    manager.import_results.side_effect = DuplicateException()
    handler = make_handler(manager)
    response = make_response()

    handler.import_results(make_import_request(), response)

    assert response.status == 400
