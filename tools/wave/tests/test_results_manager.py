import json
import zipfile

import pytest
from unittest.mock import Mock

from tools.wave.testing.results_manager import ResultsManager
from tools.wave.data.exceptions.duplicate_exception import DuplicateException
from tools.wave.data.exceptions.invalid_data_exception import InvalidDataException
from tools.wave.data.exceptions.permission_denied_exception import PermissionDeniedException


def make_results_manager(tmp_path, import_results_enabled=False):
    results_manager = ResultsManager()
    sessions_manager = Mock()
    tests_manager = Mock()
    tests_manager.get_logs.return_value = []
    results_manager.initialize(
        results_directory_path=str(tmp_path),
        sessions_manager=sessions_manager,
        tests_manager=tests_manager,
        import_results_enabled=import_results_enabled,
        reports_enabled=False,
        tests_base_url="",
        persisting_interval=20,
    )
    return results_manager, sessions_manager


def make_subtest(status):
    return {"name": "sub", "status": status, "message": None}


def make_result(test="group/test1.html", status="OK", subtests=None):
    result = {
        "test": test,
        "status": status,
        "message": None,
    }
    if subtests is not None:
        result["subtests"] = subtests
    return result


def make_test_state():
    return {
        "group": {
            "pass": 0,
            "fail": 0,
            "timeout": 0,
            "not_run": 0,
            "total": 1,
            "complete": 0,
        }
    }


def test_prepare_result_maps_numeric_harness_status():
    results_manager, _ = make_results_manager("/tmp")

    assert results_manager.prepare_result(make_result(status=0))["status"] == "OK"
    assert results_manager.prepare_result(make_result(status=1))["status"] == "ERROR"
    assert results_manager.prepare_result(make_result(status=2))["status"] == "TIMEOUT"
    assert results_manager.prepare_result(make_result(status=3))["status"] == "NOTRUN"


def test_prepare_result_renames_tests_to_subtests_and_drops_stacks():
    results_manager, _ = make_results_manager("/tmp")

    result = results_manager.prepare_result({
        "test": "group/test1.html",
        "status": 0,
        "stack": "trace",
        "tests": [
            {"name": "s", "status": 1, "stack": "sub trace"},
        ],
    })

    assert result["status"] == "OK"
    assert "stack" not in result
    assert "tests" not in result
    assert result["subtests"][0]["status"] == "FAIL"
    assert "stack" not in result["subtests"][0]


def test_update_test_state_counts_subtests_by_status():
    results_manager, sessions_manager = make_results_manager("/tmp")
    session = Mock()
    session.test_state = make_test_state()

    results_manager._update_test_state(make_result(
        status="OK",
        subtests=[make_subtest("PASS"), make_subtest("FAIL"),
                  make_subtest("TIMEOUT"), make_subtest("NOTRUN")],
    ), session)

    state = session.test_state["group"]
    assert state["pass"] == 1
    assert state["fail"] == 1
    assert state["timeout"] == 1
    assert state["not_run"] == 1
    assert state["complete"] == 1
    sessions_manager.update_session.assert_called_once_with(session)


def test_update_test_state_counts_harness_status_without_subtests():
    results_manager, _ = make_results_manager("/tmp")
    session = Mock()
    session.test_state = make_test_state()

    results_manager._update_test_state(make_result(status="ERROR"), session)
    assert session.test_state["group"]["fail"] == 1
    results_manager._update_test_state(make_result(status="TIMEOUT"), session)
    assert session.test_state["group"]["timeout"] == 1
    results_manager._update_test_state(make_result(status="NOT_RUN"), session)
    assert session.test_state["group"]["not_run"] == 1
    results_manager._update_test_state(make_result(status="OK"), session)
    assert session.test_state["group"]["pass"] == 1


def test_parse_test_state_sums_results_per_api():
    results_manager, _ = make_results_manager("/tmp")

    state = results_manager.parse_test_state({
        "group": [
            make_result(status="OK", subtests=[make_subtest("PASS")]),
            make_result(status="TIMEOUT"),
        ],
        "other": [
            make_result(status="ERROR"),
        ],
    })

    assert state["group"]["pass"] == 1
    assert state["group"]["timeout"] == 1
    assert state["group"]["total"] == 2
    assert state["group"]["complete"] == 2
    assert state["other"]["fail"] == 1


def test_cache_push_read_and_clear():
    results_manager, _ = make_results_manager("/tmp")

    results_manager._push_to_cache("token", make_result())
    results_manager._push_to_cache("token", make_result(test="other/test2.html"))

    cached = results_manager._read_from_cache("token")
    assert sorted(cached.keys()) == ["group", "other"]
    assert cached["group"][0]["test"] == "group/test1.html"

    results_manager._clear_cache_api("token", "group")
    assert sorted(results_manager._read_from_cache("token").keys()) == ["other"]

    results_manager._push_to_cache(None, make_result())
    assert results_manager._read_from_cache("missing") == []


def test_combine_results_by_api():
    results_manager, _ = make_results_manager("/tmp")

    combined = results_manager._combine_results_by_api(
        {"group": ["a"], "shared": ["b"]},
        {"shared": ["c"], "other": ["d"]},
    )

    assert combined["group"] == ["a"]
    assert sorted(combined["shared"]) == ["b", "c"]
    assert combined["other"] == ["d"]


def test_read_results_combines_cache_and_disk(tmp_path):
    results_manager, _ = make_results_manager(tmp_path)

    # persisted results: <token>/<api>/<file>.json
    api_dir = tmp_path / "token" / "group"
    api_dir.mkdir(parents=True)
    (api_dir / "aa001.json").write_text(json.dumps({
        "results": [make_result(test="group/persisted.html", subtests=[])]
    }))

    results_manager._push_to_cache("token", make_result(
        test="group/cached.html", subtests=[]))

    results = results_manager.read_results("token")

    tests = sorted(r["test"] for r in results["group"])
    assert tests == ["group/cached.html", "group/persisted.html"]


def test_read_results_filters_by_path(tmp_path):
    results_manager, _ = make_results_manager(tmp_path)

    results_manager._push_to_cache("token", make_result(
        test="/group/test1.html", subtests=[]))
    results_manager._push_to_cache("token", make_result(
        test="/group/sub/test2.html", subtests=[]))
    results_manager._push_to_cache("token", make_result(
        test="/other/test3.html", subtests=[]))

    results = results_manager.read_results("token", filter_path="/group")

    assert sorted(results.keys()) == ["group"]
    tests = sorted(r["test"] for r in results["group"])
    assert tests == ["/group/sub/test2.html", "/group/test1.html"]


def test_create_info_file_persists_serialized_session(tmp_path):
    results_manager, _ = make_results_manager(tmp_path)
    from tools.wave.data.session import Session, COMPLETED

    session = Session()
    session.token = "info-token"
    session.status = COMPLETED
    session.pending_tests = {"group": ["x"]}
    session.running_tests = {"group": ["y"]}

    results_manager.create_info_file(session)

    info_file = tmp_path / "info-token" / "info.json"
    assert info_file.is_file()
    info = json.loads(info_file.read_text())
    assert info["token"] == "info-token"
    assert "pending_tests" not in info
    assert "running_tests" not in info


def test_import_results_requires_enabled_flag(tmp_path):
    results_manager, _ = make_results_manager(tmp_path, import_results_enabled=False)

    with pytest.raises(PermissionDeniedException):
        results_manager.import_results(b"blob")


def test_import_results_rejects_zip_without_info(tmp_path):
    results_manager, _ = make_results_manager(tmp_path, import_results_enabled=True)

    buffer = io_bytes_zip(["results.json"])

    with pytest.raises(InvalidDataException):
        results_manager.import_results(buffer)


def test_import_results_rejects_duplicate_session(tmp_path):
    results_manager, sessions_manager = make_results_manager(
        tmp_path, import_results_enabled=True)
    sessions_manager.read_session.return_value = Mock()

    with pytest.raises(DuplicateException):
        results_manager.import_results(io_bytes_zip(["info.json"]))


def test_import_results_extracts_session(tmp_path):
    results_manager, sessions_manager = make_results_manager(
        tmp_path, import_results_enabled=True)
    sessions_manager.read_session.return_value = None

    info = json.dumps({"token": "imported-token"})
    blob = io_bytes_zip(["info.json"], {b"info.json": info})

    token = results_manager.import_results(blob)

    assert token == "imported-token"
    assert (tmp_path / "imported-token" / "info.json").is_file()


def io_bytes_zip(names, contents=None):
    import io
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zip_file:
        for name in names:
            if contents and name.encode() in contents:
                zip_file.writestr(name, contents[name.encode()])
            else:
                zip_file.writestr(name, "{}")
    return buffer.getvalue()


def test_get_comparison_identifier_sorts_tokens_and_appends_hash():
    results_manager, _ = make_results_manager("/tmp")

    identifier = results_manager.get_comparison_identifier(
        ["0a1b2c3d-b", "9f8e7d6c-a"], ref_tokens=["ref-1"])

    # tokens are sorted, short UUID fragments are used and a hash suffix
    # is appended; deterministic for the same inputs
    assert identifier.startswith("comparison-9f8e7d6c-0a1b2c3d-")
    again = results_manager.get_comparison_identifier(
        ["0a1b2c3d-b", "9f8e7d6c-a"], ref_tokens=["ref-1"])
    assert identifier == again


def test_read_common_passed_tests_returns_none_without_tokens(tmp_path):
    results_manager, _ = make_results_manager(tmp_path)

    assert results_manager.read_common_passed_tests(None) is None
    assert results_manager.read_common_passed_tests([]) is None


def test_read_common_passed_tests_keeps_only_common_passes(tmp_path):
    results_manager, _ = make_results_manager(tmp_path)

    results_manager._push_to_cache("token-1", make_result(
        test="/group/common.html", subtests=[make_subtest("PASS")]))
    results_manager._push_to_cache("token-2", make_result(
        test="/group/common.html", subtests=[make_subtest("PASS")]))
    results_manager._push_to_cache("token-1", make_result(
        test="/group/only1.html", subtests=[make_subtest("PASS")]))
    results_manager._push_to_cache("token-1", make_result(
        test="/group/failed.html", subtests=[make_subtest("FAIL")]))

    passed = results_manager.read_common_passed_tests(["token-1", "token-2"])

    assert "/group/common.html" in passed["group"]
    assert "/group/only1.html" not in passed["group"]
    assert "/group/failed.html" not in passed["group"]


def test_get_json_path_abbreviates_browser(tmp_path):
    results_manager, sessions_manager = make_results_manager(tmp_path)
    from tools.wave.data.session import Session

    session = Session()
    session.token = "browser-token"
    session.user_agent = (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36")
    sessions_manager.read_session.return_value = session

    path = results_manager.get_json_path("browser-token", "group")

    assert path.endswith("Ch121.json")


def test_get_json_path_abbreviates_unknown_browser(tmp_path):
    results_manager, sessions_manager = make_results_manager(tmp_path)
    from tools.wave.data.session import Session

    session = Session()
    session.token = "browser-token"
    session.user_agent = "SomeUnknownBrowser/1.0"
    sessions_manager.read_session.return_value = session

    path = results_manager.get_json_path("browser-token", "group")

    assert path.endswith("Xx00.json")


def test_delete_results_removes_session_directory(tmp_path):
    results_manager, _ = make_results_manager(tmp_path)

    session_dir = tmp_path / "doomed-token"
    session_dir.mkdir()
    (session_dir / "info.json").write_text("{}")

    results_manager.delete_results("doomed-token")
    assert not session_dir.exists()

    # deleting a missing session is a no-op
    results_manager.delete_results("doomed-token")


def test_export_results_api_json(tmp_path):
    results_manager, _ = make_results_manager(tmp_path)

    results_manager._push_to_cache("token", make_result(subtests=[]))

    blob = results_manager.export_results_api_json("token", "group")

    assert blob is not None
    assert "results" in json.loads(blob)


def test_read_results_wpt_report_uri_requires_api_directory(tmp_path):
    results_manager, _ = make_results_manager(tmp_path)

    assert results_manager.read_results_wpt_report_uri("token", "group") is None

    (tmp_path / "token" / "group").mkdir(parents=True)
    uri = results_manager.read_results_wpt_report_uri("token", "group")
    assert uri == "/results/token/group/all.html"


def test_load_session_from_info_file(tmp_path):
    results_manager, _ = make_results_manager(tmp_path)
    from tools.wave.data.session import Session
    from tools.wave.utils.serializer import serialize_session

    session = Session()
    session.token = "disk-token"
    info = serialize_session(session)
    info_file = tmp_path / "info.json"
    info_file.write_text(json.dumps(info))

    loaded = results_manager.load_session_from_info_file(str(info_file))
    assert loaded.token == "disk-token"

    assert results_manager.load_session_from_info_file(
        str(tmp_path / "missing.json")) is None


def test_save_api_results_writes_meta_and_results(tmp_path):
    results_manager, sessions_manager = make_results_manager(tmp_path)
    from tools.wave.data.session import Session

    session = Session()
    session.token = "save-token"
    session.date_started = 1000000
    session.date_finished = 2000000
    sessions_manager.read_session.return_value = session

    results_manager._push_to_cache("save-token", make_result(
        test="group/test1.html", subtests=[make_subtest("PASS")]))

    results_manager.save_api_results("save-token", "group")

    data_file = tmp_path / "save-token" / "group" / "Xx00.json"
    assert data_file.is_file()
    saved = json.loads(data_file.read_text())
    assert len(saved["results"]) == 1
    assert "meta" in saved
