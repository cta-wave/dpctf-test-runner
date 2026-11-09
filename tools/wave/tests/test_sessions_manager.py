import pytest
from unittest.mock import Mock

from tools.wave.testing.sessions_manager import SessionsManager
from tools.wave.data.session import Session, PENDING, RUNNING, PAUSED, ABORTED, COMPLETED
from tools.wave.data.exceptions.invalid_data_exception import InvalidDataException
from tools.wave.data.exceptions.not_found_exception import NotFoundException


CONFIGURATION = {
    "timeouts": {
        "automatic": 60000,
        "manual": 300000,
    },
}


def make_test_loader(tests=None):
    test_loader = Mock()
    test_loader.get_tests.return_value = tests if tests is not None else {}
    return test_loader


def make_tests_manager(test_files_count=None):
    tests_manager = Mock()
    tests_manager.calculate_test_files_count.return_value = (
        test_files_count if test_files_count is not None else {})
    return tests_manager


def make_results_manager():
    return Mock()


def make_sessions_manager(tests=None, test_files_count=None):
    sessions_manager = SessionsManager()
    sessions_manager.initialize(
        make_test_loader(tests),
        Mock(),
        make_tests_manager(test_files_count),
        "",
        make_results_manager(),
        CONFIGURATION,
    )
    return sessions_manager


def make_session(token="token", status=PENDING, is_public=False):
    session = Session()
    session.token = token
    session.status = status
    session.is_public = is_public
    session.pending_tests = {"group": ["group/test1.html"]}
    session.running_tests = {}
    session.test_state = {
        "group": {
            "pass": 0,
            "fail": 0,
            "timeout": 0,
            "not_run": 0,
            "total": 1,
            "complete": 0,
        }
    }
    return session


def test_create_session_applies_defaults():
    sessions_manager = make_sessions_manager()

    session = sessions_manager.create_session()

    assert session.token
    assert session.status == PENDING
    assert session.tests["include"] == ["/"]
    assert session.tests["exclude"] == []
    assert session.timeouts["automatic"] == 60000
    assert session.timeouts["manual"] == 300000
    assert session.test_types == ["automatic", "manual"]


def test_create_session_initializes_test_state_per_api():
    sessions_manager = make_sessions_manager(
        tests={"group": ["/group/test1.html"]},
        test_files_count={"group": 1},
    )

    session = sessions_manager.create_session()

    assert session.test_state["group"] == {
        "pass": 0,
        "fail": 0,
        "timeout": 0,
        "not_run": 0,
        "total": 1,
        "complete": 0,
    }


def test_create_session_rejects_unknown_test_type():
    sessions_manager = make_sessions_manager()

    with pytest.raises(InvalidDataException):
        sessions_manager.create_session(test_types=["selenium"])


def test_create_session_uses_given_tests_and_tokens():
    test_loader = make_test_loader({"group": ["/group/test1.html"]})
    sessions_manager = SessionsManager()
    sessions_manager.initialize(
        test_loader,
        Mock(),
        make_tests_manager({"group": 1}),
        "",
        make_results_manager(),
        CONFIGURATION,
    )
    sessions_manager._results_directory_path = ""

    session = sessions_manager.create_session(
        tests={"include": ["/group"], "exclude": ["/group/skip"]},
        reference_tokens=["ref-token"],
    )

    test_loader.get_tests.assert_called_once_with(
        ["automatic", "manual"],
        include_list=["/group"],
        exclude_list=["/group/skip"],
        reference_tokens=["ref-token"],
    )
    assert session.reference_tokens == ["ref-token"]


def test_start_session_moves_pending_to_running_and_dispatches():
    sessions_manager = make_sessions_manager()
    session = make_session()
    sessions_manager.add_session(session)
    event_dispatcher = sessions_manager._event_dispatcher

    sessions_manager.start_session(session.token)

    assert session.status == RUNNING
    assert session.date_started is not None
    event_dispatcher.dispatch_event.assert_called_once_with(
        session.token,
        event_type="status",
        data=RUNNING,
    )


def test_start_session_is_noop_when_running():
    sessions_manager = make_sessions_manager()
    session = make_session(status=RUNNING)
    sessions_manager.add_session(session)
    event_dispatcher = sessions_manager._event_dispatcher

    sessions_manager.start_session(session.token)

    assert session.status == RUNNING
    event_dispatcher.dispatch_event.assert_not_called()


def test_start_session_resumes_paused_session():
    sessions_manager = make_sessions_manager()
    session = make_session(status=PAUSED)
    sessions_manager.add_session(session)

    sessions_manager.start_session(session.token)

    assert session.status == RUNNING


def test_pause_session_persists_and_dispatches():
    sessions_manager = make_sessions_manager()
    session = make_session(status=RUNNING)
    sessions_manager.add_session(session)
    results_manager = sessions_manager._results_manager

    sessions_manager.pause_session(session.token)

    assert session.status == PAUSED
    results_manager.persist_session.assert_called_once_with(session)


def test_pause_session_is_noop_when_not_running():
    sessions_manager = make_sessions_manager()
    session = make_session(status=PENDING)
    sessions_manager.add_session(session)

    sessions_manager.pause_session(session.token)

    assert session.status == PENDING


def test_stop_session_sets_aborted_and_is_idempotent():
    sessions_manager = make_sessions_manager()
    session = make_session(status=RUNNING)
    sessions_manager.add_session(session)

    sessions_manager.stop_session(session.token)
    assert session.status == ABORTED
    date_finished = session.date_finished
    assert date_finished is not None

    sessions_manager.stop_session(session.token)
    assert session.date_finished == date_finished


def test_complete_session_is_idempotent():
    sessions_manager = make_sessions_manager()
    session = make_session(status=RUNNING)
    sessions_manager.add_session(session)

    sessions_manager.complete_session(session.token)
    assert session.status == COMPLETED
    date_finished = session.date_finished

    sessions_manager.complete_session(session.token)
    assert session.date_finished == date_finished


def test_delete_session_removes_private_session_only():
    sessions_manager = make_sessions_manager()
    private = make_session(token="private-token")
    public = make_session(token="public-token", is_public=True)
    sessions_manager.add_session(private)
    sessions_manager.add_session(public)

    sessions_manager.delete_session(public.token)
    assert sessions_manager.read_session("public-token") is not None

    sessions_manager.delete_session("private-token")
    assert sessions_manager.read_session("private-token") is None


def test_delete_session_is_noop_for_unknown_token():
    sessions_manager = make_sessions_manager()
    sessions_manager.delete_session("unknown-token")


def test_update_labels_ignores_public_sessions():
    sessions_manager = make_sessions_manager()
    public = make_session(token="public-token", is_public=True)
    sessions_manager.add_session(public)

    sessions_manager.update_labels("public-token", ["qa"])

    assert public.labels == []
    sessions_manager._results_manager.create_info_file.assert_not_called()


def test_update_labels_updates_private_session():
    sessions_manager = make_sessions_manager()
    session = make_session()
    sessions_manager.add_session(session)

    sessions_manager.update_labels(session.token, ["qa"])

    assert session.labels == ["qa"]
    sessions_manager._results_manager.create_info_file.assert_called_once_with(session)


def test_find_token_requires_eight_characters():
    sessions_manager = make_sessions_manager()
    sessions_manager.add_session(make_session(token="12345678-aaaa"))

    assert sessions_manager.find_token("1234") is None


def test_find_token_resolves_unique_fragment():
    sessions_manager = make_sessions_manager()
    sessions_manager.add_session(make_session(token="12345678-aaaa"))
    sessions_manager.add_session(make_session(token="87654321-bbbb"))

    assert sessions_manager.find_token("12345678") == "12345678-aaaa"


def test_find_token_returns_none_for_ambiguous_fragment():
    sessions_manager = make_sessions_manager()
    sessions_manager.add_session(make_session(token="12345678-aaaa"))
    sessions_manager.add_session(make_session(token="12345678-bbbb"))

    assert sessions_manager.find_token("12345678") is None


def test_read_session_returns_none_without_token():
    sessions_manager = make_sessions_manager()

    assert sessions_manager.read_session(None) is None


def test_load_session_info_reads_persisted_session(tmp_path):
    sessions_manager = make_sessions_manager()
    results_manager = sessions_manager._results_manager
    session = make_session(token="persisted-token")
    results_manager.load_results.return_value = {}
    results_manager.parse_test_state.return_value = session.test_state
    import json
    from tools.wave.utils.serializer import serialize_session

    session_directory = tmp_path / "persisted-token"
    session_directory.mkdir()
    info = serialize_session(session)
    del info["running_tests"]
    del info["pending_tests"]
    (session_directory / "info.json").write_text(json.dumps(info))

    sessions_manager._results_directory = str(tmp_path)

    loaded = sessions_manager.load_session("persisted-token")

    assert loaded is not None
    assert loaded.token == "persisted-token"
    assert loaded.test_state == session.test_state


def test_load_session_info_returns_none_without_directory(tmp_path):
    sessions_manager = make_sessions_manager()
    sessions_manager._results_directory = str(tmp_path)

    assert sessions_manager.load_session_info("missing-token") is None


def test_update_session_configuration_recalculates_test_state():
    test_loader = make_test_loader({"group": ["/group/test1.html"],
                                    "other": ["/other/test2.html"]})
    sessions_manager = SessionsManager()
    sessions_manager.initialize(
        test_loader,
        Mock(),
        make_tests_manager({"group": 1, "other": 1}),
        "",
        make_results_manager(),
        CONFIGURATION,
    )
    sessions_manager._results_directory_path = ""
    session = make_session()
    sessions_manager.add_session(session)

    updated = sessions_manager.update_session_configuration(
        session.token,
        tests={"include": ["/group", "/other"], "exclude": []},
        test_types=None,
        timeouts=None,
        reference_tokens=None,
        type=None,
    )

    assert updated is not None
    assert "other" in session.test_state
    assert session.test_state["other"]["total"] == 1


def test_update_session_configuration_skips_started_sessions():
    sessions_manager = make_sessions_manager()
    session = make_session(status=RUNNING)
    session.tests = {"include": ["/group"], "exclude": []}
    sessions_manager.add_session(session)

    result = sessions_manager.update_session_configuration(
        session.token,
        tests={"include": ["/other"], "exclude": []},
        test_types=None,
        timeouts=None,
        reference_tokens=None,
        type=None,
    )

    assert result is None
    # pending tests are left untouched once the session started
    assert session.tests["include"] == ["/group"]
    test_loader = sessions_manager._test_loader
    test_loader.get_tests.assert_not_called()


def test_get_test_path_with_query_appends_include_queries():
    sessions_manager = make_sessions_manager()
    session = make_session()
    session.tests = {
        "include": ["/group/test1.html?timeout=short", "/group"],
        "exclude": [],
    }

    path = sessions_manager.get_test_path_with_query(
        "/group/test1.html", session)

    assert path.startswith("/group/test1.html?")
    assert "timeout=short" in path


def test_test_in_session_and_completeness():
    sessions_manager = make_sessions_manager()
    session = make_session()
    session.pending_tests = {"group": ["group/test1.html"]}
    session.running_tests = {"group": ["group/test2.html"]}

    assert sessions_manager.test_in_session("group/test1.html", session)
    assert sessions_manager.is_test_running("group/test2.html", session)
    assert not sessions_manager.is_test_running("group/test1.html", session)
    assert not sessions_manager.is_test_complete("group/test1.html", session)
    assert sessions_manager.is_test_complete("group/test3.html", session)


def test_read_sessions_paginates():
    sessions_manager = make_sessions_manager()
    for i in range(15):
        sessions_manager.add_session(make_session(token="token-{:02d}".format(i)))

    first_page = sessions_manager.read_sessions(index=0, count=10)
    second_page = sessions_manager.read_sessions(index=10, count=10)

    assert len(first_page) == 10
    assert len(second_page) == 5


def test_read_public_sessions_filters_by_visibility():
    sessions_manager = make_sessions_manager()
    sessions_manager.add_session(make_session(token="private"))
    sessions_manager.add_session(make_session(token="public", is_public=True))

    assert sessions_manager.read_public_sessions() == ["public"]


def test_update_session_configuration_unknown_token_raises():
    sessions_manager = make_sessions_manager()

    with pytest.raises(NotFoundException):
        sessions_manager.update_session_configuration(
            "unknown-token", None, None, None, None, None)
