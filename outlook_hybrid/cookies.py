"""Playwright cookie → requests CookieJar 转植。"""


def playwright_cookies_to_requests(jar, cookies):
    """把 Playwright context.cookies() 结果装进 requests 的 CookieJar。

    - 去掉域名前导点（.live.com → live.com），requests 用裸域名匹配
    - 缺 path 默认 '/'
    - 缺 name 或 value 的条目跳过
    """
    for c in cookies or []:
        name = c.get("name")
        value = c.get("value")
        if not name or value is None:
            continue
        domain = (c.get("domain") or "").lstrip(".")
        path = c.get("path") or "/"
        jar.set(name, value, domain=domain, path=path)
    return jar
