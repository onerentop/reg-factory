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


def test_unicode_digit_crash_regression():
    """Unicode 数字（如 ⁵）通过 isdigit() 但在 int() 时失败。不应该崩溃，应该报错。"""
    drafts, invalid = parse_proxy_lines("1.2.3.4:⁵⁵⁵⁵", "http")
    assert len(drafts) == 0
    assert len(invalid) == 1
    assert invalid[0].reason == "端口必须是 1-65535 之间的数字"


def test_port_range_error_reason():
    """验证端口范围错误的具体错误消息。"""
    _, invalid = parse_proxy_lines("1.2.3.4:70000", "http")
    assert invalid[0].reason == "端口必须是 1-65535 之间的数字"


def test_non_numeric_port_error_reason():
    """验证非数字端口的具体错误消息。"""
    _, invalid = parse_proxy_lines("1.2.3.4:notaport", "http")
    assert invalid[0].reason == "端口必须是 1-65535 之间的数字"


def test_case_insensitive_scheme():
    """Scheme 大小写不敏感。"""
    drafts, _ = parse_proxy_lines("SOCKS5://1.2.3.4:1080", "http")
    assert drafts[0].type == "socks5"

    drafts, _ = parse_proxy_lines("HTTPS://1.2.3.4:443", "http")
    assert drafts[0].type == "https"

    drafts, _ = parse_proxy_lines("HTTP://1.2.3.4:80", "http")
    assert drafts[0].type == "http"


def test_empty_host_is_invalid():
    """空主机地址应该被拒绝。"""
    _, invalid = parse_proxy_lines(":8080", "http")
    assert len(invalid) == 1
    assert "主机" in invalid[0].reason or "空" in invalid[0].reason


def test_malformed_at_form_without_port():
    """@形式缺少端口的情况。"""
    drafts, invalid = parse_proxy_lines("u:p@1.2.3.4", "http")
    assert len(drafts) == 0
    assert len(invalid) == 1


def test_scheme_with_four_field_format():
    """Scheme 前缀加四段式。"""
    drafts, _ = parse_proxy_lines("socks5://1.2.3.4:1080:user:pass", "http")
    assert drafts[0].type == "socks5"
    assert drafts[0].host == "1.2.3.4"
    assert drafts[0].port == 1080
    assert drafts[0].username == "user"
    assert drafts[0].password == "pass"


def test_https_prefix_type():
    """https:// 前缀应该设置 type='https'。"""
    drafts, _ = parse_proxy_lines("https://1.2.3.4:8080", "http")
    assert drafts[0].type == "https"


def test_http_prefix_type():
    """http:// 前缀应该设置 type='http'。"""
    drafts, _ = parse_proxy_lines("http://1.2.3.4:8080", "socks5")
    assert drafts[0].type == "http"


def test_three_part_colon_line():
    """三个冒号的行应该被拒绝。"""
    _, invalid = parse_proxy_lines("1.2.3.4:8080:user", "http")
    assert len(invalid) == 1


def test_five_part_colon_line():
    """五个冒号的行应该被拒绝。"""
    _, invalid = parse_proxy_lines("a:1:b:c:d", "http")
    assert len(invalid) == 1


def test_password_with_colon():
    """@形式的密码可以包含冒号。"""
    drafts, _ = parse_proxy_lines("user:pass:word@1.2.3.4:8080", "http")
    assert drafts[0].username == "user"
    assert drafts[0].password == "pass:word"
    assert drafts[0].host == "1.2.3.4"
    assert drafts[0].port == 8080
