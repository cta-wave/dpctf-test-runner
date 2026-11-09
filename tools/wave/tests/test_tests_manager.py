import os
import pytest
import time
from unittest.mock import Mock

from tools.wave.testing.tests_manager import TestsManager
from tools.wave.testing.results_manager import ResultsManager
from tools.wave.data.session import Session
from tools.wave.data.exceptions.duplicate_exception import DuplicateException
from tools.wave.data.exceptions.invalid_data_exception import InvalidDataException
from tools.wave.data.exceptions.not_found_exception import NotFoundException
from tools.wave.data.exceptions.permission_denied_exception import PermissionDeniedException


def make_tests_manager():
    tests_manager = TestsManager()
    tests_manager.initialize(None, None, None, None)
    return tests_manager


def make_session():
    session = Session()
    session.token = "token"
    session.running_tests = {
        "group": ["group/test1.html"],
    }
    session.test_state = {
        "group": {
            "pass": 0,
            "fail": 0,
            "timeout": 0,
            "not_run": 0,
            "complete": 0,
        }
    }
    session.last_completed_test = None
    session.recent_completed_count = 0
    return session


def make_sessions_manager():
    sessions_manager = Mock()
    session = make_session()
    sessions_manager.read_session.return_value = session
    sessions_manager.test_in_session.return_value = True
    sessions_manager.is_test_running.return_value = True
    sessions_manager.is_api_complete.return_value = False
    return sessions_manager


def make_tests_and_results_manager():
    tests_manager = TestsManager()
    results_manager = ResultsManager()
    sessions_manager = make_sessions_manager()
    results_manager.initialize(
        results_directory_path="",
        sessions_manager=sessions_manager,
        tests_manager=tests_manager,
        import_results_enabled=False,
        reports_enabled=False,
        tests_base_url="",
        persisting_interval=100,
    )
    tests_manager.initialize(
        test_loader=None,
        sessions_manager=sessions_manager,
        results_manager=results_manager,
        event_dispatcher=Mock(),
    )
    return tests_manager, results_manager


def test_add_logs_keys_by_token_and_test():
    tests_manager = make_tests_manager()

    tests_manager.add_logs("token", "group/test1.html", ["a", "b"])
    tests_manager.add_logs("token", "group/test2.html", ["c"])
    tests_manager.add_logs("token", "group/test1.html", ["d"])

    assert tests_manager.get_logs("token", "group/test1.html") == ["a", "b", "d"]
    assert tests_manager.get_logs("token", "group/test2.html") == ["c"]
    assert tests_manager.get_logs("token", "group/test3.html") == []
    assert tests_manager.get_logs("other", "group/test1.html") == []


def test_create_result_merges_tests_logs():
    results_manager = ResultsManager()
    tests_manager = Mock()
    sessions_manager = Mock()

    results_manager.initialize(
        results_directory_path="",
        sessions_manager=sessions_manager,
        tests_manager=tests_manager,
        import_results_enabled=False,
        reports_enabled=False,
        tests_base_url="",
        persisting_interval=100,
    )

    session = Mock()
    session.test_state = {
        "group": {
            "pass": 0,
            "fail": 0,
            "timeout": 0,
            "not_run": 0,
            "complete": 0,
        }
    }
    session.last_completed_test = None
    session.recent_completed_count = 0
    sessions_manager.read_session.return_value = session
    sessions_manager.test_in_session.return_value = True
    sessions_manager.is_test_running.return_value = True
    sessions_manager.is_api_complete.return_value = False
    tests_manager.get_logs.return_value = ["line1", "line2"]

    results_manager.create_result("token", {
        "test": "group/test1.html",
        "status": "OK",
        "message": None,
        "subtests": [{"name": "s", "status": "PASS", "message": None}],
    })

    tests_manager.get_logs.assert_called_once_with("token", "group/test1.html")
    cached = results_manager._read_from_cache("token")
    result = cached["group"][0]
    assert result["logs"] == ["line1", "line2"]


def test_on_test_timeout_result_contains_tests_logs():
    tests_manager, results_manager = make_tests_and_results_manager()

    tests_manager.add_logs("token", "group/test1.html", ["timeout log line"])

    tests_manager._on_test_timeout("token", "group/test1.html")

    cached = results_manager._read_from_cache("token")
    result = cached["group"][0]
    assert result["test"] == "group/test1.html"
    assert result["status"] == "TIMEOUT"
    assert result["logs"] == ["timeout log line"]


def test_on_test_timeout_does_not_leak_sibling_logs():
    tests_manager, results_manager = make_tests_and_results_manager()

    tests_manager.add_logs("token", "group/test2.html", ["sibling log"])

    tests_manager._on_test_timeout("token", "group/test1.html")

    cached = results_manager._read_from_cache("token")
    result = cached["group"][0]
    assert result["test"] == "group/test1.html"
    assert result["logs"] == []


def test_clear_logs_discards_buffered_logs_at_persist():
    tests_manager = make_tests_manager()

    tests_manager.add_logs("token", "group/test1.html", ["a"])
    tests_manager.add_logs("token", "group/test2.html", ["b"])
    tests_manager.add_logs("other", "group/test1.html", ["c"])

    tests_manager.clear_logs("token")

    assert tests_manager.get_logs("token", "group/test1.html") == []
    assert tests_manager.get_logs("token", "group/test2.html") == []
    assert tests_manager.get_logs("other", "group/test1.html") == ["c"]


def make_deadline_sessions_manager():
    sessions_manager = Mock()
    session = make_session()
    sessions_manager.read_session.return_value = session
    sessions_manager.is_test_running.return_value = True
    return sessions_manager


def test_next_test_sets_deadline_in_millis(monkeypatch):
    tests_manager = TestsManager()
    sessions_manager = make_deadline_sessions_manager()
    tests_manager.initialize(
        test_loader=None,
        sessions_manager=sessions_manager,
        results_manager=Mock(),
        event_dispatcher=Mock(),
        timeout_check_interval=1000,
    )

    session = make_session()
    session.timeouts = {"automatic": 1000, "manual": 1000}
    session.pending_tests = {"group": ["group/test1.html"]}

    import tools.wave.testing.tests_manager as tm
    # freeze time so we can assert the exact deadline value
    monkeypatch.setattr(tm.time, "time", lambda: 0)

    tests_manager.next_test(session)

    assert "group/test1.html" in tests_manager._deadlines["token"]
    assert tests_manager._deadlines["token"]["group/test1.html"] == 1000
    # the test moved out of pending into running
    assert session.pending_tests == {}
    assert session.running_tests == {"group": ["group/test1.html"]}


def make_enrichment_results_manager(tmp_path, import_results_enabled=False):
    results_manager = ResultsManager()
    sessions_manager = Mock()
    sessions_manager.read_session.return_value = make_session()
    results_manager.initialize(
        results_directory_path=str(tmp_path),
        sessions_manager=sessions_manager,
        tests_manager=Mock(),
        import_results_enabled=import_results_enabled,
        reports_enabled=False,
        tests_base_url="",
        persisting_interval=100,
    )
    return results_manager, sessions_manager


def test_import_results_api_json_enriches_without_import_flag(tmp_path, monkeypatch):
    results_manager, sessions_manager = make_enrichment_results_manager(
        tmp_path, import_results_enabled=False)
    monkeypatch.setattr(results_manager, "generate_report",
                        lambda token, api: None)
    monkeypatch.setattr(results_manager, "create_info_file",
                        lambda session: None)

    api_dir = tmp_path / "token" / "group"
    api_dir.mkdir(parents=True)
    (api_dir / "aa001.json").write_text('{"results": []}')

    results_manager.import_results_api_json(
        "token", "group", b'{"results": [{"status": "OK"}]}')

    assert (api_dir / "aa001.json").read_bytes() == b'{"results": [{"status": "OK"}]}'
    sessions_manager.update_session.assert_called_once()


def test_import_results_api_json_unknown_session_raises_not_found(tmp_path):
    results_manager, sessions_manager = make_enrichment_results_manager(tmp_path)
    sessions_manager.read_session.return_value = None

    with pytest.raises(NotFoundException):
        results_manager.import_results_api_json("token", "group", b'{"results": []}')


def test_import_results_api_json_rejects_path_traversal(tmp_path):
    results_manager, _ = make_enrichment_results_manager(tmp_path)

    with pytest.raises(InvalidDataException):
        results_manager.import_results_api_json("..", "group", b'{"results": []}')
    with pytest.raises(InvalidDataException):
        results_manager.import_results_api_json("token", "..", b'{"results": []}')


def test_import_results_api_json_without_result_file_raises_invalid_data(tmp_path):
    results_manager, _ = make_enrichment_results_manager(tmp_path)

    # no token/group directory at all
    with pytest.raises(InvalidDataException):
        results_manager.import_results_api_json("token", "group", b'{"results": []}')

    # directory exists but holds no result file to patch
    (tmp_path / "token" / "group").mkdir(parents=True)
    with pytest.raises(InvalidDataException):
        results_manager.import_results_api_json("token", "group", b'{"results": []}')


def test_import_results_api_json_permission_error_is_actionable(tmp_path):
    if os.getuid() == 0:
        pytest.skip("root bypasses file-mode write restrictions")

    results_manager, _ = make_enrichment_results_manager(tmp_path)

    api_dir = tmp_path / "token" / "group"
    api_dir.mkdir(parents=True)
    result_file = api_dir / "aa001.json"
    result_file.write_text('{"results": []}')
    result_file.chmod(0o444)

    with pytest.raises(PermissionError, match="owned by uid"):
        results_manager.import_results_api_json("token", "group", b'{"results": [1]}')


def test_import_results_zip_still_requires_import_flag(tmp_path):
    results_manager, _ = make_enrichment_results_manager(
        tmp_path, import_results_enabled=False)

    with pytest.raises(PermissionDeniedException):
        results_manager.import_results(b"not a zip")


def test_check_timeouts_resolves_expired_deadline_to_timeout():
    tests_manager, results_manager = make_tests_and_results_manager()

    tests_manager._deadlines["token"] = {
        "group/test1.html": 1,  # already past
    }
    sessions_manager = tests_manager._sessions_manager
    sessions_manager.is_test_running.return_value = True

    tests_manager.check_timeouts()

    cached = results_manager._read_from_cache("token")
    result = cached["group"][0]
    assert result["status"] == "TIMEOUT"
    # deadline removed after resolution
    assert tests_manager._deadlines == {}


def test_check_timeouts_leaves_future_deadline_alone():
    tests_manager, results_manager = make_tests_and_results_manager()

    # deadline far in the future
    tests_manager._deadlines["token"] = {
        "group/test1.html": int(time.time() * 1000) + 100000,
    }
    sessions_manager = tests_manager._sessions_manager
    sessions_manager.is_test_running.return_value = True

    tests_manager.check_timeouts()

    assert results_manager._read_from_cache("token") == []
    assert "group/test1.html" in tests_manager._deadlines["token"]


def test_check_timeouts_drops_deadline_for_no_longer_running_test():
    tests_manager, results_manager = make_tests_and_results_manager()

    tests_manager._deadlines["token"] = {
        "group/test1.html": 1,
    }
    sessions_manager = tests_manager._sessions_manager
    # test already resolved elsewhere -> not running any more
    sessions_manager.is_test_running.return_value = False

    tests_manager.check_timeouts()

    assert results_manager._read_from_cache("token") == []
    assert tests_manager._deadlines == {}


def test_complete_result_removes_deadline():
    tests_manager, results_manager = make_tests_and_results_manager()

    tests_manager._deadlines["token"] = {
        "group/test1.html": 9999999999999,
    }

    results_manager.create_result("token", {
        "test": "group/test1.html",
        "status": "OK",
        "message": None,
        "subtests": [{"name": "s", "status": "PASS", "message": None}],
    })

    assert tests_manager._deadlines == {}
