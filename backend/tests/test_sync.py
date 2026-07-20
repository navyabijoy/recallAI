"""
Tests for the sync adapter registry pattern and mock adapters.
"""
import pytest
import asyncio
from backend.sync.base import SyncRegistry, BaseSyncAdapter
import backend.sync  # noqa: F401 — registers all adapters


@pytest.mark.asyncio
async def test_registry_has_leetcode():
    assert "leetcode" in SyncRegistry.list_platforms()

@pytest.mark.asyncio
async def test_registry_has_github():
    assert "github" in SyncRegistry.list_platforms()

@pytest.mark.asyncio
async def test_registry_has_codeforces():
    assert "codeforces" in SyncRegistry.list_platforms()

@pytest.mark.asyncio
async def test_leetcode_mock_returns_events():
    adapter = SyncRegistry.get_adapter("leetcode")
    events = await adapter.sync("mock")
    assert isinstance(events, list)
    assert len(events) > 0
    for e in events:
        assert "event_id" in e
        assert "timestamp" in e
        assert "raw_payload" in e

@pytest.mark.asyncio
async def test_github_mock_returns_events():
    adapter = SyncRegistry.get_adapter("github")
    events = await adapter.sync("mock")
    assert isinstance(events, list)
    assert len(events) > 0
    for e in events:
        assert "event_id" in e
        assert "mapped_topic" in e

@pytest.mark.asyncio
async def test_codeforces_mock_returns_events():
    adapter = SyncRegistry.get_adapter("codeforces")
    events = await adapter.sync("mock")
    assert isinstance(events, list)
    assert len(events) > 0
    for e in events:
        assert "event_id" in e
        assert "verdict" in e["raw_payload"]

@pytest.mark.asyncio
async def test_unknown_platform_raises():
    with pytest.raises(ValueError, match="No adapter registered"):
        SyncRegistry.get_adapter("hackerrank")

@pytest.mark.asyncio
async def test_custom_adapter_registration():
    """Tests that a new custom adapter can be registered without modifying existing code."""
    @SyncRegistry.register
    class HackerRankAdapter(BaseSyncAdapter):
        @property
        def platform_name(self):
            return "hackerrank"
        async def sync(self, credential: str):
            return [{"event_id": "hr_mock_1", "timestamp": "2026-07-09T00:00:00Z", "mapped_topic": "Arrays", "raw_payload": {}}]
    
    assert "hackerrank" in SyncRegistry.list_platforms()
    adapter = SyncRegistry.get_adapter("hackerrank")
    events = await adapter.sync("mock")
    assert len(events) == 1
    assert events[0]["event_id"] == "hr_mock_1"
    
    # Clean up
    SyncRegistry._registry.pop("hackerrank", None)
