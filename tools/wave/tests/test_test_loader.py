from unittest.mock import Mock

from tools.wave.testing.test_loader import TestLoader, AUTOMATIC, MANUAL


def make_test_loader(api_titles=None):
    loader = TestLoader()
    results_manager = Mock()
    # a real ResultsManager returns None for empty reference token lists
    results_manager.read_common_passed_tests.side_effect = (
        lambda tokens: None if not tokens else Mock())
    loader.initialize(
        exclude_list_file_path="",
        include_list_file_path="",
        results_manager=results_manager,
        api_titles=api_titles or [],
    )
    return loader


def make_manifest():
    # Mirrors the manifest shape produced by tools/serve/wave.py:
    # directories are dicts, test entries are [url, metadata] lists.
    return {
        "testharness": {
            "group": {
                "test1.html": ["/group/test1.html", {}],
                "test2.html": ["/group/test2.html", {"timeout": "long"}],
                "manual": {
                    "manual1.html": ["/group/manual/manual1.html", {}],
                },
            },
            "entry.js": [
                ["", {}],
                ["/other/JS/test1.html", {}],
            ],
        },
        "manual": {},
    }


def test_load_tests_splits_manual_from_testharness():
    loader = make_test_loader()
    loader.load_tests(make_manifest())

    automatic = loader._tests[AUTOMATIC]
    manual = loader._tests[MANUAL]

    assert automatic["group"] == ["/group/test1.html", "/group/test2.html"]
    assert "/group/manual/manual1.html" not in automatic["group"]
    assert "/group/manual/manual1.html" in manual["group"]


def test_load_tests_extracts_js_entry_paths():
    loader = make_test_loader()
    loader.load_tests(make_manifest())

    automatic = loader._tests[AUTOMATIC]

    assert "/other/JS/test1.html" in automatic["other"]


def test_is_valid_test_include_list():
    loader = make_test_loader()

    assert loader._is_valid_test("/group/test1.html", include_list=["/group"])
    assert not loader._is_valid_test("/other/test1.html", include_list=["/group"])
    # query parameters in the include list are ignored for matching
    assert loader._is_valid_test("/group/test1.html",
                                 include_list=["/group?timeout=short"])
    # an empty include list does not restrict
    assert loader._is_valid_test("/other/test1.html", include_list=[])


def test_is_valid_test_exclude_list():
    loader = make_test_loader()

    assert not loader._is_valid_test("/group/test1.html", exclude_list=["/group"])
    assert loader._is_valid_test("/other/test1.html", exclude_list=["/group"])
    assert loader._is_valid_test("/group/test1.html", exclude_list=[])


def test_is_valid_test_exclude_wins_over_include():
    loader = make_test_loader()

    assert not loader._is_valid_test(
        "/group/test1.html",
        include_list=["/group"],
        exclude_list=["/group/test1.html"])


def test_get_tests_applies_filters():
    loader = make_test_loader()
    loader.load_tests(make_manifest())

    tests = loader.get_tests(include_list=["/group"], exclude_list=[])

    assert sorted(tests.keys()) == ["group"]
    assert "/group/test1.html" in tests["group"]


def test_get_tests_filters_by_test_type():
    loader = make_test_loader()
    loader.load_tests(make_manifest())

    automatic_only = loader.get_tests(test_types=[AUTOMATIC])
    manual_only = loader.get_tests(test_types=[MANUAL])

    assert "/group/test1.html" in automatic_only["group"]
    assert "/group/manual/manual1.html" not in automatic_only["group"]
    assert "/group/manual/manual1.html" in manual_only["group"]
    assert "/group/test1.html" not in manual_only["group"]


def test_get_tests_skips_unknown_test_types():
    loader = make_test_loader()
    loader.load_tests(make_manifest())

    tests = loader.get_tests(test_types=["selenium"])

    assert tests == {}


def test_get_tests_uses_reference_results():
    results_manager = Mock()
    results_manager.read_common_passed_tests.return_value = {
        "group": ["/group/test1.html"],
        "other": [],
    }
    loader = TestLoader()
    loader.initialize(
        exclude_list_file_path="",
        include_list_file_path="",
        results_manager=results_manager,
        api_titles=[],
    )
    loader.load_tests(make_manifest())

    tests = loader.get_tests(reference_tokens=["ref-token"])

    results_manager.read_common_passed_tests.assert_called_once_with(["ref-token"])
    assert tests["group"] == ["/group/test1.html"]
    assert tests.get("other") is None or tests["other"] == []


def test_get_tests_without_reference_tokens_filters_nothing():
    results_manager = Mock()
    loader = TestLoader()
    loader.initialize(
        exclude_list_file_path="",
        include_list_file_path="",
        results_manager=results_manager,
        api_titles=[],
    )
    loader.load_tests(make_manifest())

    tests = loader.get_tests()

    # read_common_passed_tests is called with the empty token list and a
    # real manager answers None, so no reference filtering happens
    results_manager.read_common_passed_tests.assert_called_once_with([])
    assert "/group/test1.html" in tests["group"]
    assert "/other/JS/test1.html" in tests["other"]


def test_load_test_list_parses_lines_and_comments(tmp_path):
    # The product strips spaces and skips lines that are empty after
    # stripping (a bare "#" comment). Lines like "#comment" survive as
    # entries, matching the loader's actual parsing rules.
    list_file = tmp_path / "list.txt"
    list_file.write_text(
        "#\n"
        "\n"
        "/group/test1.html\n"
        "  /group/test2.html  \n"
    )
    loader = make_test_loader()

    tests = loader._load_test_list(str(list_file))

    assert tests == ["/group/test1.html", "/group/test2.html"]


def test_load_test_list_missing_file_returns_empty(tmp_path):
    loader = make_test_loader()

    assert loader._load_test_list(str(tmp_path / "missing.txt")) == []


def test_load_tests_reads_include_and_exclude_files(tmp_path):
    include_file = tmp_path / "include.txt"
    include_file.write_text("/group\n")
    exclude_file = tmp_path / "exclude.txt"
    exclude_file.write_text("/group/test2.html\n")

    loader = TestLoader()
    loader.initialize(
        exclude_list_file_path=str(exclude_file),
        include_list_file_path=str(include_file),
        results_manager=Mock(),
        api_titles=[],
    )
    loader.load_tests(make_manifest())

    tests = loader.get_tests()

    assert "/group/test1.html" in tests["group"]
    assert "/group/test2.html" not in tests["group"]


def test_get_apis_uses_titles():
    loader = make_test_loader(api_titles=[
        {"path": "/group", "title": "Group API"},
    ])
    loader.load_tests(make_manifest())

    apis = loader.get_apis()

    titles = {api["path"]: api["title"] for api in apis}
    assert titles["/group"] == "Group API"
    assert titles["/other"] == "other"


def test_parse_api_name_takes_first_path_segment():
    loader = make_test_loader()

    assert loader._parse_api_name("/group/sub/test1.html") == "group"
