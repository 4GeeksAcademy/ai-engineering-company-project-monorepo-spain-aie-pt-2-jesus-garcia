import time

import pytest

from app.core.cache import TTLCache, cached


def test_miss_then_hit():
    c = TTLCache()
    assert c.get("k") is None
    c.set("k", {"data": 123}, ttl=60)
    assert c.get("k") == {"data": 123}
    assert c.get("k") == {"data": 123}


def test_expiry():
    c = TTLCache()
    c.set("k", "value", ttl=0.05)
    assert c.get("k") == "value"
    time.sleep(0.06)
    assert c.get("k") is None


def test_delete_and_delete_prefix():
    c = TTLCache()
    c.set("inventory:products", [1], ttl=60)
    c.set("inventory:orders", [2], ttl=60)
    c.set("suppliers", [3], ttl=60)
    assert c.delete_prefix("inventory:") == 2
    assert c.get("inventory:products") is None
    assert c.get("suppliers") == [3]
    c.delete("suppliers")
    assert c.get("suppliers") is None


def test_no_expiry_when_ttl_none():
    c = TTLCache()
    c.set("k", "v")
    assert c.get("k") == "v"


def test_default_ttl():
    c = TTLCache(default_ttl=0.05)
    c.set("k", "v")
    time.sleep(0.06)
    assert c.get("k") is None


def test_stats():
    c = TTLCache()
    c.set("a", 1, ttl=60)
    c.get("a")
    c.get("a")
    c.get("b")
    stats = c.stats()
    assert stats["hits"] == 2
    assert stats["misses"] == 1
    assert stats["size"] == 1
    assert stats["hit_rate"] == pytest.approx(2 / 3)


def test_clear_resets_stats():
    c = TTLCache()
    c.set("a", 1, ttl=60)
    c.get("a")
    c.clear()
    assert c.stats()["hits"] == 0
    assert c.stats()["misses"] == 0
    assert c.stats()["size"] == 0


def test_cached_helper_computes_once():
    c = TTLCache()
    calls = []

    def compute():
        calls.append(1)
        return "heavy"

    assert cached(c, "key", ttl=60, compute=compute) == "heavy"
    assert cached(c, "key", ttl=60, compute=compute) == "heavy"
    assert len(calls) == 1


def test_cached_helper_falsy_values_are_cached():
    c = TTLCache()
    calls = []

    def compute():
        calls.append(1)
        return []

    assert cached(c, "key", ttl=60, compute=compute) == []
    assert cached(c, "key", ttl=60, compute=compute) == []
    assert len(calls) == 1