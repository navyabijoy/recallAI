"""
Tests for calendar agent tool integration.
Verifies calendar_api returns proper mock data and that tools are wired correctly.
"""
import pytest
import asyncio
from backend.sync.calendar_api import get_calendar_availability, get_upcoming_deadlines, _is_deadline_event, _extract_related_topics


@pytest.mark.asyncio
async def test_mock_calendar_availability_structure():
    """Mock mode returns expected free/busy block structure."""
    result = await get_calendar_availability("mock")
    assert "free_blocks" in result
    assert "busy_blocks" in result
    assert len(result["free_blocks"]) > 0
    for block in result["free_blocks"]:
        assert "date" in block
        assert "start" in block
        assert "end" in block

@pytest.mark.asyncio
async def test_mock_calendar_availability_7_days():
    """Mock mode returns 7 days of free blocks."""
    result = await get_calendar_availability("mock")
    dates = set(b["date"] for b in result["free_blocks"])
    assert len(dates) == 7, "Should return 7 different dates"

@pytest.mark.asyncio
async def test_mock_deadlines_returns_list():
    """Mock mode returns a list of deadline objects."""
    deadlines = await get_upcoming_deadlines("mock")
    assert isinstance(deadlines, list)
    assert len(deadlines) > 0
    for dl in deadlines:
        assert "event_title" in dl
        assert "date" in dl
        assert "related_topics" in dl
        assert isinstance(dl["related_topics"], list)

@pytest.mark.asyncio
async def test_mock_deadlines_contain_interview():
    """Mock deadlines should include an interview event."""
    deadlines = await get_upcoming_deadlines("mock")
    titles = [dl["event_title"].lower() for dl in deadlines]
    assert any("interview" in t for t in titles), "Mock should include at least one interview event"

@pytest.mark.asyncio
async def test_no_auth_token_uses_mock():
    """Calling with None or empty token should fall back to mock."""
    result1 = await get_calendar_availability(None)
    result2 = await get_calendar_availability("")
    assert len(result1["free_blocks"]) > 0
    assert len(result2["free_blocks"]) > 0

def test_is_deadline_event_interview():
    assert _is_deadline_event("Google SWE Interview - Round 2") is True

def test_is_deadline_event_exam():
    assert _is_deadline_event("CS101 Midterm Exam") is True

def test_is_deadline_event_irrelevant():
    assert _is_deadline_event("Team standup") is False

def test_extract_related_topics_graphs():
    topics = _extract_related_topics("Google interview - Graph traversal and DP")
    assert "Graphs" in topics
    assert "Dynamic Programming" in topics

def test_extract_related_topics_empty():
    topics = _extract_related_topics("Team lunch meeting")
    assert topics == []

@pytest.mark.asyncio
async def test_calendar_tool_in_agent_returns_data():
    """Tests that the calendar tool wrapper in agent works with mock DB."""
    from unittest.mock import MagicMock
    from backend.agent import tool_get_calendar_availability, tool_get_upcoming_deadlines
    from sqlmodel import Session
    
    mock_session = MagicMock(spec=Session)
    mock_session.exec.return_value.first.return_value = None  # No CalendarConnection, falls back to mock
    
    cal = await tool_get_calendar_availability(mock_session, "demo-user-id")
    assert "free_blocks" in cal
    assert len(cal["free_blocks"]) > 0
    
    deadlines = await tool_get_upcoming_deadlines(mock_session, "demo-user-id")
    assert isinstance(deadlines, list)
