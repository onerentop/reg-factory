# perimeterx_solver/recon/cookie_snapshotter.py
from ..models import CookieSnapshot

PX_COOKIE_NAMES = ("_px3", "_pxhd", "_pxvid", "pxcts")
_PX_COOKIE_PREFIXES = ("_pxff_", "_px")


def is_px_cookie(name: str) -> bool:
    return name in PX_COOKIE_NAMES or any(name.startswith(p) for p in _PX_COOKIE_PREFIXES)


class PxCookieSnapshotter:
    """各生命周期节点快照 PX cookie（Memento）。"""

    def snapshot(self, label: str, ts: float, cookies) -> CookieSnapshot:
        flat = {c["name"]: c["value"] for c in cookies if is_px_cookie(c.get("name", ""))}
        return CookieSnapshot(label=label, ts=ts, cookies=flat)

    @staticmethod
    def diff(a: CookieSnapshot, b: CookieSnapshot) -> dict:
        """返回 {name: (old, new)}，仅含变化项（含新增/删除）。"""
        out = {}
        keys = set(a.cookies) | set(b.cookies)
        for k in keys:
            old = a.cookies.get(k)
            new = b.cookies.get(k)
            if old != new:
                out[k] = (old, new)
        return out
