# perimeterx_solver/classify.py
import json
from dataclasses import dataclass, field
from enum import Enum
from urllib.parse import urlparse, parse_qs

_PX_HOST_SUFFIXES = (".px-cdn.net", ".px-cloud.net", ".hsprotect.net", ".pxchk.net")
_PX_HOST_CONTAINS = ("px-cloud.net", "px-cdn.net")


class PxKind(str, Enum):
    COLLECTOR = "collector"
    SCRIPT = "script"
    CHALLENGE_IFRAME = "challenge_iframe"
    OTHER = "other"


def is_px_url(url: str) -> bool:
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return False
    if not host:
        return False
    return host.endswith(_PX_HOST_SUFFIXES) or any(s in host for s in _PX_HOST_CONTAINS)


def classify_px_url(url: str, method: str) -> PxKind:
    if not is_px_url(url):
        return PxKind.OTHER
    path = (urlparse(url).path or "").lower()
    host = (urlparse(url).hostname or "").lower()
    if "/collector" in path and method.upper() == "POST":
        return PxKind.COLLECTOR
    if path.endswith(".js"):
        return PxKind.SCRIPT
    if "hsprotect.net" in host:
        return PxKind.CHALLENGE_IFRAME
    return PxKind.OTHER


@dataclass
class CollectorPayload:
    encrypted_blob: str = ""
    plaintext_fields: dict = field(default_factory=dict)
    raw: str = ""


def parse_collector_body(body: str) -> CollectorPayload:
    raw = body or ""
    # 先试 JSON
    stripped = raw.strip()
    if stripped.startswith("{"):
        try:
            d = json.loads(stripped)
            blob = str(d.pop("payload", "")) if "payload" in d else ""
            return CollectorPayload(encrypted_blob=blob, plaintext_fields={k: v for k, v in d.items()}, raw=raw)
        except Exception:
            pass
    # 再试 form 编码
    qs = parse_qs(raw, keep_blank_values=True)
    flat = {k: v[0] if v else "" for k, v in qs.items()}
    blob = flat.pop("payload", "")
    return CollectorPayload(encrypted_blob=blob, plaintext_fields=flat, raw=raw)
