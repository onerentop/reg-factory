"""代理列表文本解析。纯函数，无 DB / 网络依赖，便于隔离测试。

支持格式（每行一条）：
    host:port:user:pass          Webshare 导出格式
    user:pass@host:port
    host:port
    以上均可带 socks5:// / http:// / https:// 前缀，前缀优先于 default_type
空行与 # 开头的注释行被跳过。
"""
from dataclasses import dataclass

_SCHEMES = ("socks5://", "https://", "http://")


@dataclass(frozen=True)
class ProxyDraft:
    type: str
    host: str
    port: int
    username: str | None
    password: str | None


@dataclass(frozen=True)
class InvalidLine:
    line_no: int
    raw: str
    reason: str


def _build(ptype: str, host: str, port: str, user: str | None, pwd: str | None) -> ProxyDraft | None:
    if not host or not port.isdigit():
        return None
    port_num = int(port)
    if not 1 <= port_num <= 65535:
        return None
    return ProxyDraft(type=ptype, host=host, port=port_num, username=user or None, password=pwd or None)


def _parse_one(line: str, ptype: str) -> ProxyDraft | None:
    if "@" in line:                       # user:pass@host:port
        cred, _, addr = line.rpartition("@")
        user, _, pwd = cred.partition(":")
        host, _, port = addr.rpartition(":")
        return _build(ptype, host, port, user, pwd)
    parts = line.split(":")
    if len(parts) == 4:                   # host:port:user:pass
        return _build(ptype, parts[0], parts[1], parts[2], parts[3])
    if len(parts) == 2:                   # host:port
        return _build(ptype, parts[0], parts[1], None, None)
    return None


def parse_proxy_lines(text: str, default_type: str = "http") -> tuple[list[ProxyDraft], list[InvalidLine]]:
    drafts: list[ProxyDraft] = []
    invalid: list[InvalidLine] = []
    for line_no, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        ptype = default_type
        for scheme in _SCHEMES:
            if line.lower().startswith(scheme):
                ptype = scheme[:-3]
                line = line[len(scheme):]
                break
        draft = _parse_one(line, ptype)
        if draft is None:
            invalid.append(InvalidLine(line_no=line_no, raw=raw, reason="无法识别的代理格式"))
        else:
            drafts.append(draft)
    return drafts, invalid
