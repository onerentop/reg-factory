"""GraphTokenExtractor：包根 extract_graph_token，原生 token 抽取能力(Adapter)。
不改根脚本，方法内惰性 import 根函数(匹配项目模式)，BrowserContext 取自 page.context。"""

from worker.capabilities.interfaces import TokenExtractor, EmailAccount


class GraphTokenExtractor(TokenExtractor):
    async def extract(self, page, account: EmailAccount) -> dict:
        from register_outlook_standalone import extract_graph_token
        graph = await extract_graph_token(page, page.context, account.email, account.password)
        return graph or {}
