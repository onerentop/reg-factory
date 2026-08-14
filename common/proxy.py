"""Outlook 与 Google 共享的代理连接工具。"""

import random
import re
import string


def rotate_proxy_sid(proxy_str: str) -> str:
    """为 1024proxy 的 sid 创建新会话；其它代理保持原样。"""
    if not proxy_str or "-sid-" not in proxy_str:
        return proxy_str
    new_sid = "".join(random.choices(string.ascii_letters + string.digits, k=8))
    return re.sub(r"(-sid-)[A-Za-z0-9]+", r"\g<1>" + new_sid, proxy_str, count=1)
