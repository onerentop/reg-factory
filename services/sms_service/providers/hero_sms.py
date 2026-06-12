from sms_service.providers.base import ProviderRegistry
from sms_service.providers.sms_activate_base import SmsActivateProvider


@ProviderRegistry.register("hero_sms")
class HeroSmsProvider(SmsActivateProvider):
    display_name = "HeroSMS"
    _default_base_url = "https://hero-sms.com/stubs/handler_api.php"
    config_schema = {
        "api_key": {"type": "string", "label": "API Key", "required": True},
        "base_url": {
            "type": "string",
            "label": "API Base URL",
            "default": "https://hero-sms.com/stubs/handler_api.php",
        },
    }
