import asyncio


class DynamicSemaphore:
    """可运行时调整大小的异步信号量。

    扩容：立即释放差额槽位。
    缩容：不中断运行中任务，自然过渡。
    """

    def __init__(self, max_size: int):
        self._max_size = max_size
        self._semaphore = asyncio.Semaphore(max_size)
        self._active = 0
        self._waiting = 0

    @property
    def max_size(self) -> int:
        return self._max_size

    @property
    def active(self) -> int:
        return self._active

    @property
    def waiting(self) -> int:
        return self._waiting

    def resize(self, new_max: int) -> None:
        if new_max < 1:
            new_max = 1
        diff = new_max - self._max_size
        self._max_size = new_max
        if diff > 0:
            for _ in range(diff):
                self._semaphore.release()
        elif diff < 0:
            for _ in range(-diff):
                self._semaphore._value = max(0, self._semaphore._value - 1)

    def status(self) -> dict:
        return {
            "max": self._max_size,
            "active": self._active,
            "waiting": self._waiting,
        }

    async def __aenter__(self) -> "DynamicSemaphore":
        self._waiting += 1
        await self._semaphore.acquire()
        self._waiting -= 1
        self._active += 1
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        self._active -= 1
        self._semaphore.release()
