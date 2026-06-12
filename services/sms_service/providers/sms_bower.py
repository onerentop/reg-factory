from sms_service.providers.base import ProviderRegistry
from sms_service.providers.sms_activate_base import SmsActivateProvider


@ProviderRegistry.register("sms_bower")
class SmsBowerProvider(SmsActivateProvider):
    display_name = "SmsBower"
    _default_base_url = "https://smsbower.com/stubs/handler_api.php"
    config_schema = {
        "api_key": {"type": "string", "label": "API Key", "required": True},
        "base_url": {
            "type": "string",
            "label": "API Base URL",
            "default": "https://smsbower.com/stubs/handler_api.php",
        },
    }
