"""rotate_proxy_sid 单元测试：1024proxy username 的 sid 段轮换。
让并发注册的每个窗口/每次注册拿不同 sid → 不同出口 IP(避免 PerimeterX 同 IP 关联)。"""
import re

from worker.tasks._helpers import rotate_proxy_sid

PROXY = "socks5://sb7f3017-region-Rand-sid-jY63iQZE-t-5:f3vxcmih@us.1024proxy.io:3000"


def test_rotate_changes_sid():
    out = rotate_proxy_sid(PROXY)
    assert "sid-jY63iQZE" not in out
    assert re.search(r"-sid-[A-Za-z0-9]+-t-", out)


def test_rotate_preserves_rest():
    out = rotate_proxy_sid(PROXY)
    assert out.startswith("socks5://sb7f3017-region-Rand-sid-")
    assert out.endswith("-t-5:f3vxcmih@us.1024proxy.io:3000")


def test_rotate_non_sid_proxy_unchanged():
    p = "socks5://user:pass@1.2.3.4:1080"
    assert rotate_proxy_sid(p) == p


def test_rotate_empty_unchanged():
    assert rotate_proxy_sid("") == ""


def test_rotate_two_calls_differ():
    a = rotate_proxy_sid(PROXY)
    b = rotate_proxy_sid(PROXY)
    assert a != b
