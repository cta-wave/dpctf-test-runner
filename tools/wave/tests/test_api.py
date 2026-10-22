import pytest
import requests
import json
import copy
import os
import subprocess
import tempfile
import time
import shutil

def test_import_results():
    # Arrange
    token = create_session()
    print(token)
    tests = read_available_tests()
    apis = list(tests.keys())
    api = apis[0]
    test = tests[api][0]
    set_session_tests(token, [test])
    print(api)
    print(test)
    start_session(token)
    next_test = read_next_test(token)
    create_positive_result(token, test)
    next_test = read_next_test(token)
    
    # Act
    url = "/".join([get_url(), "api/results", token, api, "json"])
    r = requests.get(url)
    old_results = copy.deepcopy(r.json())

    new_results = copy.deepcopy(old_results)
    new_results["results"][0]["subtests"].append({"name": "Subtest ab", "status": "FAIL", "message": None})
    url = "/".join([get_url(), "api/results", token, api, "json"])
    r = requests.post(url, data=json.dumps(new_results))
    status_code = r.status_code
    
    url = "/".join([get_url(), "api/results", token, api, "json"])
    r = requests.get(url)
    updated_results = r.json()
    
    # Assert
    assert status_code == 200
    assert updated_results == new_results
    assert updated_results != old_results
    
    # CleanUp
    delete_session(token)
    
def test_last_completed_tests():
    # Arrange
    token = create_session()
    print(token)
    tests = read_available_tests()
    apis = list(tests.keys())
    api = apis[0]
    test = tests[api][0]
    set_session_tests(token, [test])
    print(api)
    print(test)
    start_session(token)
    next_test = read_next_test(token)
    create_timed_out_result(token, test)
    next_test = read_next_test(token)
    
    # Act
    url = "/".join([get_url(), "api/tests/", token, "/last_completed"])
    r = requests.get(url)
    status_code = r.status_code
    
    url = "/".join([get_url(), "api/results", token, api, "json"])
    r = requests.get(url)
    updated_results = r.json()
    
    # Assert
    assert status_code == 200
    
    # CleanUp
    delete_session(token)
    
def test_normal_result_contains_tests_logs():
    # Arrange
    token = create_session()
    tests = read_available_tests()
    apis = list(tests.keys())
    api = apis[0]
    test = tests[api][0]
    set_session_tests(token, [test])
    start_session(token)
    next_test = read_next_test(token)
    create_logs(token, test, ["log line 1", "log line 2"])
    
    # Act
    create_positive_result(token, test)
    
    # Assert
    updated_results = read_results(token, api)
    result = next(r for r in updated_results["results"] if r["test"] == test)
    assert result["logs"] == ["log line 1", "log line 2"]
    
    # CleanUp
    delete_session(token)
    
def test_logs_are_isolated_between_tests():
    # Arrange
    token = create_session()
    tests = read_available_tests()
    apis = list(tests.keys())
    api = apis[0]
    tests_in_api = tests[api]
    test1 = tests_in_api[0]
    test2 = tests_in_api[1]
    set_session_tests(token, [test1, test2])
    start_session(token)
    
    # Act
    next_test = read_next_test(token)
    create_logs(token, test1, ["test1 log"])
    create_positive_result(token, test1)
    
    next_test = read_next_test(token)
    create_logs(token, test2, ["test2 log"])
    create_positive_result(token, test2)
    
    # Assert
    updated_results = read_results(token, api)
    result1 = next(r for r in updated_results["results"] if r["test"] == test1)
    result2 = next(r for r in updated_results["results"] if r["test"] == test2)
    assert result1["logs"] == ["test1 log"]
    assert result2["logs"] == ["test2 log"]
    
    # CleanUp
    delete_session(token)
    
def test_timeout_result_contains_tests_logs():
    # Arrange
    token = create_session()
    tests = read_available_tests()
    apis = list(tests.keys())
    api = apis[0]
    test = tests[api][0]
    set_session_tests(token, [test])
    start_session(token)
    next_test = read_next_test(token)
    create_logs(token, test, ["timeout log line"])
    
    # Act
    create_timed_out_result(token, test)
    
    # Assert
    updated_results = read_results(token, api)
    result = next(r for r in updated_results["results"] if r["test"] == test)
    assert result["logs"] == ["timeout log line"]
    
    # CleanUp
    delete_session(token)
    
def create_session():
    url = "/".join([get_url(), "api/sessions"])
    r = requests.post(url)
    response_payload = r.json()
    token = response_payload["token"]
    return token

def read_session(token):
    url = "/".join([get_url(), "api/sessions", token])
    r = requests.get(url)
    session = r.json()
    return session

def read_session_status(token):
    url = "/".join([get_url(), "api/sessions", token, "status"])
    r = requests.get(url)
    status = r.json()
    return status
    
def read_available_tests():
    url = "/".join([get_url(), "api/tests"])
    r = requests.get(url)
    tests = r.json()
    return tests

def set_session_tests(token, tests):
    url = "/".join([get_url(), "api/sessions", token])
    config = {
        "tests": {
            "include": tests
        }
    }
    
    r = requests.put(url, data=json.dumps(config))
    
def read_next_test(token):
    url = "/".join([get_url(), "api/tests", token, "next"])
    r = requests.get(url)
    next_test = r.json()["next_test"]
    return next_test
    

def start_session(token):
    url = "/".join([get_url(), "api/sessions", token, "start"])
    r = requests.post(url)
    
def create_result(token, test, result):
    url = "/".join([get_url(), "api/results", token])
    r = requests.post(url, data=json.dumps(result))
    print(r.status_code)
    print(result)
    
def create_positive_result(token, test):
    result = {
        "test": test,
        "status": "OK",
        "message": None,
        "subtests": [
            {"name": "Subtest xy", "status": "PASS", "message": None}
        ]
    }
    
    create_result(token, test, result)

def create_timed_out_result(token, test):
    result = {
        "test": test,
        "status": "TIMEOUT",
        "message": None,
        "subtests": []
    }
    
    create_result(token, test, result)
    
def create_logs(token, test, logs):
    url = "/".join([get_url(), "api/tests", token, "logs"])
    data = {
        "test": test,
        "logs": logs
    }
    r = requests.post(url, data=json.dumps(data))
    print(r.status_code)
    
def read_results(token, api):
    url = "/".join([get_url(), "api/results", token, api, "json"])
    r = requests.get(url)
    return r.json()
def read_session_tests(token):
    url = "/".join([get_url(), "api/tests", token])
    r = requests.get(url)
    tests = r.json()
    return tests

def delete_session(token):
    url = "/".join([get_url(), "api/sessions", token])
    r = requests.delete(url)
    

def get_url():
    host = "127.0.0.1:8000"
    base_url = "_wave"
    return "/".join(["http:/", host, base_url])


def start_wave_server(config_path):
    repo_root = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    return subprocess.Popen(
        [os.path.join(repo_root, "wpt"), "serve-wave", "--config", config_path],
        preexec_fn=os.setsid)

def stop_wave_server(process, url=None):
    os.killpg(os.getpgid(process.pid), 15)
    process.wait()
    if url is not None:
        deadline = time.time() + 30
        while time.time() < deadline:
            try:
                requests.get(url, timeout=2)
                time.sleep(1)
            except requests.exceptions.ConnectionError:
                return
        assert False, "WAVE Test Runner failed: Server did not stop within 30s."

def wait_for_server(url, process, timeout=120):
    start = time.time()
    while True:
        if process.poll() is not None:
            assert False, "WAVE Test Runner failed: Server not running."
        if time.time() - start > timeout:
            assert False, "WAVE Test Runner failed: Server did not start responding within {}s.".format(timeout)
        try:
            r = requests.get(url)
        except requests.exceptions.ConnectionError:
            time.sleep(1)
            continue
        if r.status_code == 200:
            return
        time.sleep(1)

def summarize_results(results):
    # Mirrors the server-side counter rules for a list of result dicts.
    summary = {"pass": 0, "fail": 0, "timeout": 0, "not_run": 0, "complete": 0}
    for result in results:
        if "subtests" not in result:
            if result["status"] == "OK":
                summary["pass"] += 1
            elif result["status"] == "ERROR":
                summary["fail"] += 1
            elif result["status"] == "TIMEOUT":
                summary["timeout"] += 1
            elif result["status"] in ("NOTRUN", "NOT_RUN"):
                summary["not_run"] += 1
        else:
            for subtest in result["subtests"]:
                if subtest["status"] == "PASS":
                    summary["pass"] += 1
                elif subtest["status"] == "FAIL":
                    summary["fail"] += 1
                elif subtest["status"] == "TIMEOUT":
                    summary["timeout"] += 1
                elif subtest["status"] in ("NOTRUN", "NOT_RUN"):
                    summary["not_run"] += 1
        summary["complete"] += 1
    return summary

def start_wave_server(config_path):
    repo_root = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    return subprocess.Popen(
        [os.path.join(repo_root, "wpt"), "serve-wave", "--config", config_path],
        preexec_fn=os.setsid)

def stop_wave_server(process, url=None):
    os.killpg(os.getpgid(process.pid), 15)
    process.wait()
    if url is not None:
        deadline = time.time() + 30
        while time.time() < deadline:
            try:
                requests.get(url, timeout=2)
                time.sleep(1)
            except requests.exceptions.ConnectionError:
                return
        assert False, "WAVE Test Runner failed: Server did not stop within 30s."

def wait_for_server(url, process, timeout=120):
    start = time.time()
    while True:
        if process.poll() is not None:
            assert False, "WAVE Test Runner failed: Server not running."
        if time.time() - start > timeout:
            assert False, "WAVE Test Runner failed: Server did not start responding within {}s.".format(timeout)
        try:
            r = requests.get(url)
        except requests.exceptions.ConnectionError:
            time.sleep(1)
            continue
        if r.status_code == 200:
            return
        time.sleep(1)

def summarize_results(results):
    # Mirrors the server-side counter rules for a list of result dicts.
    summary = {"pass": 0, "fail": 0, "timeout": 0, "not_run": 0, "complete": 0}
    for result in results:
        if "subtests" not in result:
            if result["status"] == "OK":
                summary["pass"] += 1
            elif result["status"] == "ERROR":
                summary["fail"] += 1
            elif result["status"] == "TIMEOUT":
                summary["timeout"] += 1
            elif result["status"] in ("NOTRUN", "NOT_RUN"):
                summary["not_run"] += 1
        else:
            for subtest in result["subtests"]:
                if subtest["status"] == "PASS":
                    summary["pass"] += 1
                elif subtest["status"] == "FAIL":
                    summary["fail"] += 1
                elif subtest["status"] == "TIMEOUT":
                    summary["timeout"] += 1
                elif subtest["status"] in ("NOTRUN", "NOT_RUN"):
                    summary["not_run"] += 1
        summary["complete"] += 1
    return summary

def test_overview_in_sync_with_report_after_restart():
    # Arrange: an isolated setup (own results dir, import enabled).
    # The WaveServer always reads ./config.json from the repo root (see
    # tools/serve/wave.py), so the test temporarily writes that file and
    # restores it afterwards.
    repo_root = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    config_path = os.path.join(repo_root, "config.json")
    with open(config_path, "r") as config_file:
        original_config = config_file.read()

    tmp_dir = tempfile.mkdtemp()
    config = json.loads(original_config)
    wave_config = config.get("wave", {})
    wave_config["results"] = os.path.join(tmp_dir, "results")
    wave_config["enable_import_results"] = True
    config["wave"] = wave_config
    with open(config_path, "w") as config_file:
        json.dump(config, config_file)

    # The wptserve ports come from the --config file (8080, free here; the
    # deployment server runs on 8000).
    wpt_config_path = os.path.join(tmp_dir, "wpt.json")
    with open(wpt_config_path, "w") as config_file:
        json.dump({"ports": {"http": [8080, "auto"], "https": [8483]}},
                  config_file)

    base_url = "http://127.0.0.1:8080/_wave"
    processes = []
    token = None
    try:
        processes.append(start_wave_server(wpt_config_path))
        wait_for_server(base_url + "/api/sessions/public", processes[-1])

        url = "/".join([base_url, "api/sessions"])
        r = requests.post(url)
        token = r.json()["token"]

        url = "/".join([base_url, "api/tests"])
        tests = requests.get(url).json()
        apis = list(tests.keys())
        assert len(apis) > 0, "No APIs available"
        api = apis[0]
        test = tests[api][0]

        config = {"tests": {"include": [test]}}
        url = "/".join([base_url, "api/sessions", token])
        requests.put(url, data=json.dumps(config))
        url = "/".join([base_url, "api/sessions", token, "start"])
        requests.post(url)
        url = "/".join([base_url, "api/tests", token, "next"])
        requests.get(url)

        result = {
            "test": test,
            "status": "OK",
            "message": None,
            "subtests": [{"name": "Subtest xy", "status": "PASS", "message": None}]
        }
        url = "/".join([base_url, "api/results", token])
        requests.post(url, data=json.dumps(result))

        # Enrichment (observation framework): overwrite the api results
        url = "/".join([base_url, "api/results", token, api, "json"])
        r = requests.get(url)
        assert r.status_code == 200
        enriched = copy.deepcopy(r.json())
        enriched["results"][0]["subtests"].append(
            {"name": "Subtest ab", "status": "FAIL", "message": None})
        r = requests.post(url, data=json.dumps(enriched))
        assert r.status_code == 200

        # Act: restart the server (session reloaded from disk, cold cache)
        stop_wave_server(processes[-1], base_url + "/api/sessions/public")
        processes.append(start_wave_server(wpt_config_path))
        wait_for_server(base_url + "/api/sessions/public", processes[-1])

        # Assert: overview counters match the full results
        url = "/".join([base_url, "api/results", token, "compact"])
        r = requests.get(url)
        assert r.status_code == 200
        compact = r.json()

        url = "/".join([base_url, "api/results", token])
        r = requests.get(url)
        assert r.status_code == 200
        full_results = r.json()

        assert api in compact, "Overview is missing the api after restart"
        assert enriched["results"][0] in full_results[api], \
            "Enriched results are missing after restart"
        expected = summarize_results(full_results[api])
        expected["total"] = len(full_results[api])
        for key in ("pass", "fail", "timeout", "not_run", "complete", "total"):
            assert compact[api][key] == expected[key], \
                "Overview '{}' is {} but full results have {}".format(
                    key, compact[api][key], expected[key])
    finally:
        if token is not None:
            url = "/".join([base_url, "api/sessions", token])
            try:
                requests.delete(url)
            except requests.exceptions.ConnectionError:
                pass
        for process in processes:
            if process.poll() is None:
                stop_wave_server(process)
        with open(config_path, "w") as config_file:
            config_file.write(original_config)
        shutil.rmtree(tmp_dir, ignore_errors=True)