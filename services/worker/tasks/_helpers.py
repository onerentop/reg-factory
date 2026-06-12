import random
import re
import string


def rotate_proxy_sid(proxy_str: str) -> str:
    """把 1024proxy username 里的 sid-XXXX 替换为新随机 8 位 sid。
    非该格式(无 -sid-)的 proxy 原样返回。让并发注册的每个窗口/每次注册拿
    不同 sid → 不同出口 IP(避免 PerimeterX 因同 IP 关联多个账号)。"""
    if not proxy_str or "-sid-" not in proxy_str:
        return proxy_str
    new_sid = "".join(random.choices(string.ascii_letters + string.digits, k=8))
    return re.sub(r"(-sid-)[A-Za-z0-9]+", r"\g<1>" + new_sid, proxy_str, count=1)


def _fetch_proxy_from_manager() -> str:
    """从 Gateway 代理管理获取一个激活的代理，格式化为 URL。"""
    import requests as _req
    try:
        # proxies 显式禁用：取内部 /proxy 不受 os.environ 代理污染(否则失败→无代理注册)
        resp = _req.get("http://localhost:8000/proxy", timeout=5, proxies={"http": None, "https": None})
        proxy_list = resp.json().get("data", [])
        available = [p for p in proxy_list if p.get("status") in ("active", "available")]
        if available:
            selected = random.choice(available)
            ptype = selected.get("type", "socks5")
            host = selected.get("host", "")
            port = selected.get("port", "")
            user = selected.get("username", "")
            pwd = selected.get("password", "")
            if user and pwd:
                return f"{ptype}://{user}:{pwd}@{host}:{port}"
            return f"{ptype}://{host}:{port}"
    except Exception:
        pass
    return ""
