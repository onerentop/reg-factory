"""代理文本解析纯函数测试。无 DB、无网络。"""
from gateway.proxy_import import ProxyDraft, parse_proxy_lines


def test_webshare_four_field_format_uses_default_type():
    drafts, invalid = parse_proxy_lines("45.61.125.104:6115:proxyuser:proxypass", "http")
    assert invalid == []
    assert drafts == [ProxyDraft(type="http", host="45.61.125.104", port=6115,
                                 username="proxyuser", password="proxypass")]


def test_userpass_at_host_format():
    drafts, _ = parse_proxy_lines("u:p@1.2.3.4:8080", "http")
    assert drafts[0].username == "u" and drafts[0].password == "p"
    assert drafts[0].host == "1.2.3.4" and drafts[0].port == 8080


def test_host_port_only_has_no_credentials():
    drafts, _ = parse_proxy_lines("1.2.3.4:8080", "http")
    assert drafts[0].username is None and drafts[0].password is None


def test_scheme_prefix_overrides_default_type():
    drafts, _ = parse_proxy_lines("socks5://u:p@1.2.3.4:1080", "http")
    assert drafts[0].type == "socks5" and drafts[0].port == 1080


def test_blank_lines_and_comments_are_skipped():
    drafts, invalid = parse_proxy_lines("\n# comment\n\n1.2.3.4:8080\n", "http")
    assert len(drafts) == 1 and invalid == []


def test_garbage_line_is_reported_with_line_number():
    drafts, invalid = parse_proxy_lines("1.2.3.4:8080\ngarbage", "http")
    assert len(drafts) == 1
    assert invalid[0].line_no == 2 and invalid[0].raw == "garbage"


def test_non_numeric_port_is_invalid():
    _, invalid = parse_proxy_lines("1.2.3.4:notaport", "http")
    assert len(invalid) == 1


def test_out_of_range_port_is_invalid():
    _, invalid = parse_proxy_lines("1.2.3.4:70000", "http")
    assert len(invalid) == 1
