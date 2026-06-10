"""限制同时占用的浏览器数（铸 token 阶段）。"""

import asyncio
from contextlib import asynccontextmanager


class BrowserPool:
    def __init__(self, max_concurrent: int = 3):
        self._sem = asyncio.Semaphore(max_concurrent)

    @asynccontextmanager
    async def slot(self):
        async with self._sem:
            yield
