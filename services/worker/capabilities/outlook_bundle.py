"""default_outlook_bundle：组装 Outlook 注册用的 ServiceBundle。

M2a 阶段只含零根改动的适配器（browser/tokens）；captcha(PerimeterXHoldSolver)、proxy 等
依赖根抽取，留待 M2b（gated 待干净 IP 实跑验证）。
"""

from worker.capabilities.bundle import ServiceBundle
from worker.capabilities.browser import IxBrowserService
from worker.capabilities.token import GraphTokenExtractor


def default_outlook_bundle() -> ServiceBundle:
    """生产用默认 bundle。惰性 import 的适配器在调用其方法时才接触根脚本。"""
    return ServiceBundle(
        browser=IxBrowserService(),
        tokens=GraphTokenExtractor(),
        # captcha / proxy / sms / emails / accounts：M2b 或后续里程碑注入
    )
