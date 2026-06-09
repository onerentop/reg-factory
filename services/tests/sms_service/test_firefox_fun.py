from sms_service.providers.base import ProviderRegistry

def test_firefox_fun_registered():
    import sms_service.providers.firefox_fun
    assert ProviderRegistry.is_registered("firefox_fun")

def test_firefox_fun_config_schema():
    import sms_service.providers.firefox_fun
    providers = ProviderRegistry.list_providers()
    ff = next(p for p in providers if p["name"] == "firefox_fun")
    assert "token" in ff["config_schema"]
    assert "project_id" in ff["config_schema"]
