import pytest
from unittest.mock import Mock

from tools.wave.testing.tests_manager import TestsManager
from tools.wave.testing.results_manager import ResultsManager
from tools.wave.data.session import Session


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
    tests_manager._timeouts.append({
        "test": "group/test1.html",
        "timeout": Mock(),
    })

    tests_manager._on_test_timeout("token", "group/test1.html")

    cached = results_manager._read_from_cache("token")
    result = cached["group"][0]
    assert result["test"] == "group/test1.html"
    assert result["status"] == "TIMEOUT"
    assert result["logs"] == ["timeout log line"]


def test_on_test_timeout_does_not_leak_sibling_logs():
    tests_manager, results_manager = make_tests_and_results_manager()

    tests_manager.add_logs("token", "group/test2.html", ["sibling log"])
    tests_manager._timeouts.append({
        "test": "group/test1.html",
        "timeout": Mock(),
    })

    tests_manager._on_test_timeout("token", "group/test1.html")

    cached = results_manager._read_from_cache("token")
    result = cached["group"][0]
    assert result["test"] == "group/test1.html"
    assert result["logs"] == []
