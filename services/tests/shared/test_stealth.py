from shared.browser_utils.stealth import STEALTH_JS, StealthInjector


def test_stealth_js_content():
    assert len(STEALTH_JS) > 500
    assert "webdriver" in STEALTH_JS
    assert "window.chrome" in STEALTH_JS
    assert "cdc_" in STEALTH_JS


def test_injector_instance():
    injector = StealthInjector()
    assert injector.script == STEALTH_JS

def test_custom_script():
    injector = StealthInjector(custom_script="custom()")
    assert injector.script == "custom()"
