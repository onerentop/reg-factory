import inspect
import register_outlook_standalone as ros


def test_helper_exists_and_is_async_context_manager():
    assert hasattr(ros, "_open_ixbrowser_page")
    # 应为 async generator 函数（@asynccontextmanager 装饰）
    fn = ros._open_ixbrowser_page
    assert hasattr(fn, "__wrapped__") or inspect.isasyncgenfunction(getattr(fn, "__wrapped__", fn))


def test_register_one_browser_still_present():
    # 重构后入口仍在，签名不变
    sig = inspect.signature(ros._register_one_browser)
    assert list(sig.parameters) == ["bb", "idx", "proxy_str"]
