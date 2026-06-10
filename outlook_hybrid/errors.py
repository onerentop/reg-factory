"""混合注册的领域异常。"""


class MintFailed(Exception):
    """浏览器侧铸凭证失败（过不了 PerimeterX / 验证码 / 未截获 CreateAccount）。"""


class SubmitRejected(Exception):
    """协议侧 replay 被 MS 拒绝（HSol 失效 / canary 失效 / 其他 error）。"""
