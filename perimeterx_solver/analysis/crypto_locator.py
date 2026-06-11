from ..models import CryptoFinding

_MAP = {"btoa": "base64", "subtle_encrypt": "aes", "xor": "xor"}


class CryptoLocator:
    """从 hook 事件启发式定位「最终加密串」的生成原语。"""

    def locate(self, events) -> CryptoFinding:
        kinds, ev = [], []
        for e in sorted(events, key=lambda x: x.get("t", 0)):
            k = _MAP.get(e["kind"])
            if k and k not in kinds:
                kinds.append(k)
                ev.append({"kind": e["kind"], "t": e.get("t"), "data": e.get("data")})
        return CryptoFinding(kinds=kinds, evidence=ev)
