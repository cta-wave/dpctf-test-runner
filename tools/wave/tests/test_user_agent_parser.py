from tools.wave.utils.user_agent_parser import parse_user_agent, abbreviate_browser_name


CHROME_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36")

FIREFOX_UA = (
    "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0")

SAFARI_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Safari/605.1.15")


def test_parse_chrome_user_agent():
    parsed = parse_user_agent(CHROME_UA)

    assert parsed["name"] == "Chrome"
    assert parsed["version"].startswith("121")


def test_parse_firefox_user_agent():
    parsed = parse_user_agent(FIREFOX_UA)

    assert parsed["name"] == "Firefox"
    assert parsed["version"].startswith("120")


def test_parse_safari_user_agent():
    parsed = parse_user_agent(SAFARI_UA)

    assert parsed["name"] == "Safari"


def test_parse_unknown_user_agent_defaults_version_to_zero():
    parsed = parse_user_agent("SomeUnknown/1.0")

    assert parsed["version"] == "0"


def test_parse_empty_user_agent():
    parsed = parse_user_agent("")

    assert parsed["name"] == "Other"
    assert parsed["version"] == "0"


def test_abbreviate_known_browsers():
    assert abbreviate_browser_name("Chrome") == "Ch"
    assert abbreviate_browser_name("Chrome Mobile WebView") == "Ch"
    assert abbreviate_browser_name("Chromium") == "Cm"
    assert abbreviate_browser_name("Firefox") == "FF"
    assert abbreviate_browser_name("Safari") == "Sf"
    assert abbreviate_browser_name("Edge") == "Ed"
    assert abbreviate_browser_name("Opera") == "Op"
    assert abbreviate_browser_name("IE") == "IE"
    assert abbreviate_browser_name("WebKit") == "Wk"


def test_abbreviate_unknown_browser():
    assert abbreviate_browser_name("Netscape") == "Xx"
