# -*- coding: utf-8 -*-
"""Outlook / Google 本机注册链的根配置。"""

import os
from pathlib import Path


def _load_env_file() -> None:
    env_path = Path(__file__).with_name(".env")
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env_file()


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


# 浏览器 provider：默认 Donut，ixBrowser 保留为本机兼容回退。
BROWSER_PROVIDER = _env("BROWSER_PROVIDER", "donut")
DONUT_API_BASE = _env("DONUT_API_BASE", "http://127.0.0.1:10108")
DONUT_API_TOKEN = _env("DONUT_API_TOKEN", "")
DONUT_PROFILE_REUSE = _env("DONUT_PROFILE_REUSE", "true").lower() == "true"
IXBROWSER_TARGET = _env("IXBROWSER_TARGET", "127.0.0.1")
IXBROWSER_PORT = int(_env("IXBROWSER_PORT", "53200"))
IXBROWSER_KERNEL_VERSION = _env("IXBROWSER_KERNEL_VERSION", "")

# Outlook 的可选代理/验证码支持。
OUTLOOK_PROXIES = _env("OUTLOOK_PROXIES", "")
OUTLOOK_API_BASE = _env("OUTLOOK_API_BASE", "http://api.shankeyun.com")
OUTLOOK_CARD = _env("OUTLOOK_CARD", "")
OUTLOOK_TYPE = _env("OUTLOOK_TYPE", "outlook")
CAPSOLVER_API_KEY = _env("CAPSOLVER_API_KEY", "")
EZCAPTCHA_API_KEY = _env("EZCAPTCHA_API_KEY", "")
EZCAPTCHA_API_BASE = _env("EZCAPTCHA_API_BASE", "https://api.ez-captcha.com")
CLASH_API = _env("CLASH_API", "http://127.0.0.1:9097")
CLASH_SECRET = _env("CLASH_SECRET", "")
CLASH_PROXY = _env("CLASH_PROXY", "http://127.0.0.1:7897")
CLASH_GROUP = _env("CLASH_GROUP", "GLOBAL")

# Google 网页/Donut hybrid 与 protocol fallback 的接码配置。
SMS_API_BASE = _env("SMS_API_BASE", "http://www.firefox.fun/yhapi.ashx")
SMS_TOKEN = _env("SMS_TOKEN", "")
HERO_SMS_API_BASE = _env("HERO_SMS_API_BASE", "https://hero-sms.com/stubs/handler_api.php")
HERO_SMS_API_KEY = _env("HERO_SMS_API_KEY", "")
SMS_PROJECT_ID_GMAIL = _env("SMS_PROJECT_ID_GMAIL", "")
HERO_SMS_SERVICE_GMAIL = _env("HERO_SMS_SERVICE_GMAIL", "go")
SMS_MAXPRICE_GMAIL = _env("SMS_MAXPRICE_GMAIL", "0")
SMS_COUNTRY_BLACKLIST_GMAIL = [
    item.strip() for item in _env("SMS_COUNTRY_BLACKLIST_GMAIL", "").split(",") if item.strip()
]
SMS_HERO_COUNTRIES = [
    item.strip() for item in _env("SMS_HERO_COUNTRIES", "52,6,4,10,73,22,54,19,60,7").split(",") if item.strip()
]
SMS_HERO_OPERATOR = _env("SMS_HERO_OPERATOR", "")
SMS_HERO_FIXED_PRICE = _env("SMS_HERO_FIXED_PRICE", "true").lower() in {"1", "true", "yes"}
SMS_MAX_TRIES = int(_env("SMS_MAX_TRIES", "10"))
SMS_CODE_WAIT = int(_env("SMS_CODE_WAIT", "90"))
SMS_SERVICE_URL = _env("SMS_SERVICE_URL", "http://127.0.0.1:8000")
