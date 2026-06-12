"""hero_sms / sms_bower 子类配置测：注册名、默认 base_url、display_name。
直接实例化子类(register 装饰器在 import 时已注入 name)，不需要 mock HTTP。"""
from sms_service.providers.hero_sms import HeroSmsProvider


def test_hero_config():
    p = HeroSmsProvider({"api_key": "k"})
    assert p.name == "hero_sms"
    assert p.display_name == "HeroSMS"
    assert p._base_url == "https://hero-sms.com/stubs/handler_api.php"


def test_hero_config_base_url_override():
    p = HeroSmsProvider({"api_key": "k", "base_url": "https://custom/handler_api.php"})
    assert p._base_url == "https://custom/handler_api.php"
