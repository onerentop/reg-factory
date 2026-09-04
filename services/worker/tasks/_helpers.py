from worker.legacy_bridge import LegacyBridge

LegacyBridge().ensure_importable()
from common.proxy import rotate_proxy_sid


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
