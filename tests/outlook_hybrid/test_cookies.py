import requests
from outlook_hybrid.cookies import playwright_cookies_to_requests


def test_strips_leading_dot_from_domain():
    jar = requests.Session().cookies
    playwright_cookies_to_requests(jar, [
        {"name": "_px3", "value": "v1", "domain": ".live.com", "path": "/"},
    ])
    assert jar.get("_px3", domain="live.com") == "v1"


def test_keeps_plain_domain():
    jar = requests.Session().cookies
    playwright_cookies_to_requests(jar, [
        {"name": "a", "value": "v2", "domain": "signup.live.com", "path": "/"},
    ])
    assert jar.get("a", domain="signup.live.com") == "v2"


def test_defaults_missing_path_to_root():
    jar = requests.Session().cookies
    playwright_cookies_to_requests(jar, [
        {"name": "b", "value": "v3", "domain": "live.com"},
    ])
    assert jar.get("b", domain="live.com") == "v3"


def test_skips_entries_without_name_or_value():
    jar = requests.Session().cookies
    playwright_cookies_to_requests(jar, [
        {"value": "noname", "domain": "live.com"},
        {"name": "noval", "domain": "live.com"},
    ])
    assert len(jar) == 0
