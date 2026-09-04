"""代理列表文本解析。纯函数，无 DB / 网络依赖，便于隔离测试。

支持格式（每行一条）：
    host:port:user:pass          Webshare 导出格式
    user:pass@host:port
    host:port
    以上均可带 socks5:// / http:// / https:// 前缀，前缀优先于 default_type
空行与 # 开头的注释行被跳过。
"""
from dataclasses import dataclass

# 前缀顺序很重要：https:// 必须在 http:// 之前，否则 "https://..." 会被 "http://" 匹配
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


def _build(proxy_type: str, host: str, port: str, user: str | None, pwd: str | None) -> tuple[ProxyDraft | None, str | None]:
    """验证并构建代理草稿。返回 (draft, reason)，成功时 reason=None，失败时 draft=None。"""
    if not host:
        return None, "主机地址不能为空"
    if not port:
        return None, "端口不能为空"
    # 用 isascii() 防止 Unicode 数字（如 ⁵）通过 isdigit() 但在 int() 时失败
    if not port.isascii() or not port.isdigit():
        return None, "端口必须是 1-65535 之间的数字"
    try:
        port_num = int(port)
    except ValueError:
        return None, "端口必须是 1-65535 之间的数字"
    if not 1 <= port_num <= 65535:
        return None, "端口必须是 1-65535 之间的数字"
    return ProxyDraft(type=proxy_type, host=host, port=port_num, username=user or None, password=pwd or None), None


def _parse_one(line: str, proxy_type: str) -> tuple[ProxyDraft | None, str | None]:
    """解析单行代理配置。返回 (draft, reason)，成功时 reason=None。"""
    if "@" in line:
        # user:pass@host:port 格式：用 partition 让密码可包含冒号 :
        cred, _, addr = line.rpartition("@")
        user, _, pwd = cred.partition(":")
        # 用 rpartition 让主机名理论上可包含冒号（虽然罕见）
        host, _, port = addr.rpartition(":")
        return _build(proxy_type, host, port, user, pwd)
    parts = line.split(":")
    if len(parts) == 4:                   # host:port:user:pass 格式
        return _build(proxy_type, parts[0], parts[1], parts[2], parts[3])
    if len(parts) == 2:                   # host:port 格式
        return _build(proxy_type, parts[0], parts[1], None, None)
    return None, "无法识别的代理格式"


def parse_proxy_lines(text: str, default_type: str = "http") -> tuple[list[ProxyDraft], list[InvalidLine]]:
    """解析多行代理配置文本。

    返回 (drafts, invalid_lines)。
    default_type: 没有前缀时的代理类型（默认 'http'）。
    """
    drafts: list[ProxyDraft] = []
    invalid: list[InvalidLine] = []
    for line_no, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        proxy_type = default_type
        for scheme in _SCHEMES:
            if line.lower().startswith(scheme):
                proxy_type = scheme[:-3]
                line = line[len(scheme):]
                break
        draft, reason = _parse_one(line, proxy_type)
        if draft is None:
            invalid.append(InvalidLine(line_no=line_no, raw=raw, reason=reason or "无法识别的代理格式"))
        else:
            drafts.append(draft)
    return drafts, invalid
