from perimeterx_solver.analysis.hook_injector import HookInjector, HookFamily


def test_each_family_targets_its_anchor():
    inj = HookInjector()
    assert "XMLHttpRequest.prototype.send" in inj.snippet(HookFamily.NETWORK_EGRESS)
    assert "btoa" in inj.snippet(HookFamily.ENCODING)
    assert "requestAnimationFrame" in inj.snippet(HookFamily.BEHAVIORAL)
    assert "navigator" in inj.snippet(HookFamily.FINGERPRINT)


def test_all_use_binding_and_native_tostring_guard():
    inj = HookInjector()
    js = inj.build([HookFamily.NETWORK_EGRESS, HookFamily.ENCODING])
    assert "__pxhook" in js
    assert "native code" in js  # toString 伪装存在
    # 组合应包含两族锚点
    assert "XMLHttpRequest.prototype.send" in js and "btoa" in js
