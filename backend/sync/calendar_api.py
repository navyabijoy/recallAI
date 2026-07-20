import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# Keywords used to detect deadline-like events in calendar
DEADLINE_KEYWORDS = [
    "interview", "exam", "test", "deadline", "assessment",
    "coding round", "oa", "online assessment", "contest", "midterm", "final"
]

# Topic keywords matched inside event titles for urgency detection
TOPIC_KEYWORDS = {
    "graph": "Graphs",
    "dp": "Dynamic Programming",
    "dynamic programming": "Dynamic Programming",
    "binary search": "Binary Search",
    "array": "Arrays",
    "trie": "Trie",
    "heap": "Heap",
    "union find": "Union Find",
    "system design": "Database Sharding",
    "caching": "Caching",
    "python": "Python Functions",
}


def _is_deadline_event(event_title: str) -> bool:
    lower = event_title.lower()
    return any(kw in lower for kw in DEADLINE_KEYWORDS)


def _extract_related_topics(event_title: str) -> List[str]:
    lower = event_title.lower()
    matched = []
    for kw, topic in TOPIC_KEYWORDS.items():
        if kw in lower:
            if topic not in matched:
                matched.append(topic)
    return matched


async def get_calendar_availability(auth_token: Optional[str] = None) -> Dict[str, Any]:
    """
    Fetches free/busy time blocks for the next 7 days.

    In Mock Mode (no auth_token or auth_token == 'mock'), returns deterministic sample data.
    In Real Mode, calls Google Calendar API using the provided OAuth refresh token.

    Returns:
        {
          "free_blocks": [{"date": "2026-07-09", "start": "09:00", "end": "12:00"}],
          "busy_blocks": [{"date": "2026-07-09", "start": "14:00", "end": "15:00"}]
        }
    """
    if not auth_token or auth_token == "mock":
        now = datetime.now(timezone.utc)
        free_blocks = []
        busy_blocks = []
        for i in range(7):
            day = (now + timedelta(days=i)).strftime("%Y-%m-%d")
            free_blocks.append({"date": day, "start": "09:00", "end": "12:00"})
            free_blocks.append({"date": day, "start": "14:00", "end": "17:00"})
            busy_blocks.append({"date": day, "start": "12:00", "end": "14:00"})
        return {"free_blocks": free_blocks, "busy_blocks": busy_blocks}

    # Real Google Calendar API call
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        import json

        creds_data = json.loads(auth_token)
        creds = Credentials(
            token=creds_data.get("token"),
            refresh_token=creds_data.get("refresh_token"),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=creds_data.get("client_id"),
            client_secret=creds_data.get("client_secret"),
        )
        service = build("calendar", "v3", credentials=creds)
        now = datetime.now(timezone.utc)
        time_min = now.isoformat()
        time_max = (now + timedelta(days=7)).isoformat()

        freebusy_result = service.freebusy().query(body={
            "timeMin": time_min,
            "timeMax": time_max,
            "items": [{"id": "primary"}]
        }).execute()

        busy_periods = freebusy_result.get("calendars", {}).get("primary", {}).get("busy", [])
        busy_blocks = []
        for period in busy_periods:
            start = datetime.fromisoformat(period["start"].replace("Z", "+00:00"))
            end = datetime.fromisoformat(period["end"].replace("Z", "+00:00"))
            busy_blocks.append({
                "date": start.strftime("%Y-%m-%d"),
                "start": start.strftime("%H:%M"),
                "end": end.strftime("%H:%M")
            })

        # Build free blocks as complement (simplified: 9am-5pm minus busy)
        free_blocks = []
        for i in range(7):
            day = (now + timedelta(days=i)).strftime("%Y-%m-%d")
            day_busy = [b for b in busy_blocks if b["date"] == day]
            if not day_busy:
                free_blocks.append({"date": day, "start": "09:00", "end": "17:00"})
            else:
                free_blocks.append({"date": day, "start": "09:00", "end": day_busy[0]["start"]})
                for j in range(len(day_busy) - 1):
                    free_blocks.append({"date": day, "start": day_busy[j]["end"], "end": day_busy[j + 1]["start"]})
                free_blocks.append({"date": day, "start": day_busy[-1]["end"], "end": "17:00"})

        return {"free_blocks": free_blocks, "busy_blocks": busy_blocks}
    except Exception as e:
        logger.error(f"Error fetching Google Calendar availability: {e}")
        return {"free_blocks": [], "busy_blocks": []}


async def get_upcoming_deadlines(auth_token: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Fetches upcoming calendar events that look like deadlines (interviews, exams, contests).

    In Mock Mode, returns deterministic sample deadline data.
    In Real Mode, fetches events from Google Calendar and filters by keywords.

    Returns:
        [{"event_title": "...", "date": "2026-07-11", "related_topics": ["Graphs", "DP"]}]
    """
    if not auth_token or auth_token == "mock":
        now = datetime.now(timezone.utc)
        return [
            {
                "event_title": "Google SWE Interview - Graphs & DP round",
                "date": (now + timedelta(days=3)).strftime("%Y-%m-%d"),
                "related_topics": ["Graphs", "Dynamic Programming"]
            },
            {
                "event_title": "Codeforces Round 950",
                "date": (now + timedelta(days=6)).strftime("%Y-%m-%d"),
                "related_topics": []
            }
        ]

    # Real Google Calendar Events fetch
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        import json

        creds_data = json.loads(auth_token)
        creds = Credentials(
            token=creds_data.get("token"),
            refresh_token=creds_data.get("refresh_token"),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=creds_data.get("client_id"),
            client_secret=creds_data.get("client_secret"),
        )
        service = build("calendar", "v3", credentials=creds)
        now = datetime.now(timezone.utc)

        events_result = service.events().list(
            calendarId="primary",
            timeMin=now.isoformat(),
            timeMax=(now + timedelta(days=14)).isoformat(),
            singleEvents=True,
            orderBy="startTime"
        ).execute()

        events = events_result.get("items", [])
        deadlines = []
        for event in events:
            title = event.get("summary", "")
            if _is_deadline_event(title):
                start = event.get("start", {})
                date_str = start.get("dateTime", start.get("date", ""))
                if date_str:
                    try:
                        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                        deadlines.append({
                            "event_title": title,
                            "date": dt.strftime("%Y-%m-%d"),
                            "related_topics": _extract_related_topics(title)
                        })
                    except Exception:
                        pass
        return deadlines
    except Exception as e:
        logger.error(f"Error fetching upcoming calendar deadlines: {e}")
        return []
