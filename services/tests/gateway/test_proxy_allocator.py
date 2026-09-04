"""代理分配策略测试。纯逻辑，无 DB。"""
from gateway.proxy_manager import DailyUniqueAllocator, LeastUsedAllocator, RandomAllocator


def test_excludes_proxies_bound_today():
    proxies = [{"id": "a"}, {"id": "b"}]
    picked = DailyUniqueAllocator(RandomAllocator(), {"a"}).select(proxies)
    assert picked["id"] == "b"


def test_returns_none_when_all_bound_today():
    proxies = [{"id": "a"}, {"id": "b"}]
    assert DailyUniqueAllocator(RandomAllocator(), {"a", "b"}).select(proxies) is None


def test_returns_none_on_empty_pool():
    assert DailyUniqueAllocator(RandomAllocator(), set()).select([]) is None


def test_delegates_ordering_to_inner_allocator():
    """内层 LeastUsed 用外部计数种子，选累计最少的那个。"""
    proxies = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
    inner = LeastUsedAllocator({"a": 5, "b": 1, "c": 9})
    assert DailyUniqueAllocator(inner, set()).select(proxies)["id"] == "b"


def test_least_used_seed_is_optional():
    """不传种子时保持原有行为，全部计 0，返回第一个。"""
    assert LeastUsedAllocator().select([{"id": "a"}, {"id": "b"}])["id"] == "a"
