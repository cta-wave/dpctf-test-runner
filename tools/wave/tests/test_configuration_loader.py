import json

from tools.wave import configuration_loader
from tools.wave.configuration_loader import load, load_configuration_file


def make_config(tmp_path, overrides=None):
    config = {}
    if overrides:
        config = overrides
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config))
    return str(path)


def test_load_with_no_file_uses_defaults():
    configuration = load(None)

    default = json.loads(
        open(configuration_loader.DEFAULT_CONFIGURATION_FILE_PATH).read())
    assert configuration["timeouts"]["automatic"] == default["wave"]["timeouts"]["automatic"]
    assert configuration["timeouts"]["manual"] == default["wave"]["timeouts"]["manual"]
    assert configuration["hostname"] == default["browser_host"]
    assert configuration["import_results_enabled"] == \
        default["wave"]["enable_import_results"]
    assert configuration["read_sessions_enabled"] == \
        default["wave"]["enable_read_sessions"]
    assert configuration["api_titles"] == default["wave"]["api_titles"]


def test_load_derives_wpt_ports():
    configuration = load(None)

    default = json.loads(
        open(configuration_loader.DEFAULT_CONFIGURATION_FILE_PATH).read())
    assert configuration["wpt_port"] == default["ports"]["http"][0]
    assert configuration["wpt_ssl_port"] == default["ports"]["https"][0]


def test_load_normalizes_web_root(tmp_path):
    configuration = load(make_config(tmp_path, {
        "wave": {"web_root": "_wave"},
    }))

    assert configuration["web_root"] == "/_wave/"

    configuration = load(make_config(tmp_path, {
        "wave": {"web_root": "/_wave/"},
    }))

    assert configuration["web_root"] == "/_wave/"


def test_load_reads_wave_overrides(tmp_path):
    overrides = {
        "browser_host": "other-host.test",
        "wave": {
            "results": "/tmp/results",
            "timeouts": {"automatic": 1234, "manual": 5678},
            "enable_import_results": True,
            "enable_read_sessions": True,
            "persisting_interval": 5,
            "event_cache_duration": 30,
            "api_titles": [{"path": "/group", "title": "Group"}],
            "pre_test_delay": 100,
            "enable_test_type_selection": True,
            "tests_base_url": "https://example.test",
        },
    }

    configuration = load(make_config(tmp_path, overrides))

    assert configuration["hostname"] == "other-host.test"
    assert configuration["results_directory_path"] == "/tmp/results"
    assert configuration["timeouts"]["automatic"] == 1234
    assert configuration["timeouts"]["manual"] == 5678
    assert configuration["import_results_enabled"] is True
    assert configuration["read_sessions_enabled"] is True
    assert configuration["persisting_interval"] == 5
    assert configuration["event_cache_duration"] == 30
    assert configuration["api_titles"] == [{"path": "/group", "title": "Group"}]
    assert configuration["pre_test_delay"] == 100
    assert configuration["enable_test_type_selection"] is True
    assert configuration["tests_base_url"] == "https://example.test"


def test_load_host_override_wins(tmp_path):
    overrides = {
        "browser_host": "browser-host.test",
        "wave": {"host_override": "override.test"},
    }

    configuration = load(make_config(tmp_path, overrides))

    assert configuration["hostname"] == "override.test"


def test_load_host_override_ignores_empty_string(tmp_path):
    overrides = {
        "browser_host": "browser-host.test",
        "wave": {"host_override": ""},
    }

    configuration = load(make_config(tmp_path, overrides))

    assert configuration["hostname"] == "browser-host.test"


def test_load_sets_manifest_and_tests_paths():
    configuration = load(None)

    assert configuration["manifest_file_path"].endswith("MANIFEST.json")
    assert configuration["tests_directory_path"]


def test_load_configuration_file_missing_returns_empty(tmp_path):
    assert load_configuration_file(str(tmp_path / "missing.json")) == {}


def test_load_configuration_file_parses_json(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"ports": {"http": [9000]}}))

    assert load_configuration_file(str(path)) == {"ports": {"http": [9000]}}
