from shared.browser_utils.input_helpers import InputHelper


def test_input_helper_instance():
    helper = InputHelper()
    assert helper is not None

def test_react_fill_js():
    js = InputHelper.react_fill_js("hello")
    assert "hello" in js
    assert "dispatchEvent" in js
