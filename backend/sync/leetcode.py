import httpx
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any
from .base import BaseSyncAdapter, SyncRegistry

logger = logging.getLogger(__name__)

LEETCODE_GRAPHQL_URL = "https://leetcode.com/graphql"

# Maps LeetCode difficulty to FSRS difficulties
DIFFICULTY_MAP = {
    "Easy": "GOOD",
    "Medium": "HARD",
    "Hard": "AGAIN"
}

# Mapping of LeetCode topic tags to our recallAI graph topics
TAG_MAPPING = {
    "array": "Arrays",
    "two-pointers": "Arrays",
    "matrix": "Arrays",
    "prefix-sum": "Arrays",
    "simulation": "Arrays",
    "sliding-window": "Sliding Window",
    "binary-search": "Binary Search",
    "divide-and-conquer": "Binary Search",
    "graph": "Graphs",
    "depth-first-search": "Graphs",
    "breadth-first-search": "Graphs",
    "topological-sort": "Graphs",
    "shortest-path": "Graphs",
    "union-find": "Union Find",
    "dynamic-programming": "Dynamic Programming",
    "memoization": "Dynamic Programming",
    "trie": "Trie",
    "recursion": "Recursion",
    # Newly covered topics
    "linked-list": "Linked List",
    "math": "Math",
    "number-theory": "Math",
    "combinatorics": "Math",
    "string": "Strings",
    "string-matching": "Strings",
    "greedy": "Greedy",
    "stack": "Stack",
    "monotonic-stack": "Stack",
    "hash-table": "Hash Table",
    "counting": "Hash Table",
    "backtracking": "Backtracking",
    "sorting": "Sorting",
    "bit-manipulation": "Bit Manipulation",
    "bitmask": "Bit Manipulation",
    "tree": "Trees",
    "binary-tree": "Trees",
    "binary-search-tree": "Trees",
    "heap-priority-queue": "Heap",
}

async def fetch_question_details(title_slug: str) -> Dict[str, Any]:
    """Fetches difficulty and tags for a specific LeetCode question."""
    query = """
    query questionData($titleSlug: String!) {
      question(titleSlug: $titleSlug) {
        difficulty
        topicTags {
          name
          slug
        }
      }
    }
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                LEETCODE_GRAPHQL_URL,
                json={"query": query, "variables": {"titleSlug": title_slug}},
                timeout=10.0
            )
            if response.status_code == 200:
                data = response.json().get("data", {}).get("question")
                if data:
                    return {
                        "difficulty": data.get("difficulty", "Medium"),
                        "tags": [tag.get("slug") for tag in data.get("topicTags", [])]
                    }
    except Exception as e:
        logger.error(f"Error fetching LeetCode question details for {title_slug}: {e}")
    return {"difficulty": "Medium", "tags": []}

async def sync_leetcode(username: str) -> List[Dict[str, Any]]:
    """
    Pulls recent submissions for a LeetCode user.
    If username is 'mock', returns simulated submissions.
    """
    if username == "mock" or not username:
        # Return mock events for local demonstration/testing
        now = datetime.now(timezone.utc)
        return [
            {
                "submission_id": "mock_lc_1",
                "problem_slug": "two-sum",
                "problem_title": "Two Sum",
                "difficulty": "Easy",
                "language": "python3",
                "timestamp": now.isoformat(),
                "status": "Accepted",
                "runtime": "32ms",
                "memory": "16.4MB",
                "tags": ["array", "hash-table"],
                "mapped_topic": "Arrays"
            },
            {
                "submission_id": "mock_lc_2",
                "problem_slug": "longest-substring-without-repeating-characters",
                "problem_title": "Longest Substring Without Repeating Characters",
                "difficulty": "Medium",
                "language": "python3",
                "timestamp": now.isoformat(),
                "status": "Accepted",
                "runtime": "56ms",
                "memory": "16.2MB",
                "tags": ["hash-table", "string", "sliding-window"],
                "mapped_topic": "Sliding Window"
            },
            {
                "submission_id": "mock_lc_3",
                "problem_slug": "longest-palindromic-substring",
                "problem_title": "Longest Palindromic Substring",
                "difficulty": "Medium",
                "language": "python3",
                "timestamp": now.isoformat(),
                "status": "Time Limit Exceeded",
                "runtime": "N/A",
                "memory": "N/A",
                "tags": ["string", "dynamic-programming"],
                "mapped_topic": "Dynamic Programming"
            }
        ]

    # Real GraphQL request to fetch recent submissions
    query = """
    query userProfileUserSubmissions($username: String!, $limit: Int!) {
      recentSubmissionList(username: $username, limit: $limit) {
        titleSlug
        title
        timestamp
        statusDisplay
        lang
      }
    }
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                LEETCODE_GRAPHQL_URL,
                json={"query": query, "variables": {"username": username, "limit": 10}},
                headers={"Referer": "https://leetcode.com"},
                timeout=10.0
            )
            
            if response.status_code != 200:
                logger.error(f"LeetCode GraphQL returned status {response.status_code}")
                return []
                
            submissions = response.json().get("data", {}).get("recentSubmissionList", [])
            if not submissions:
                return []
                
            processed_events = []
            for sub in submissions:
                slug = sub.get("titleSlug")
                # Fetch detailed question info (tags/difficulty)
                q_details = await fetch_question_details(slug)
                
                # Map to our topics
                mapped_topic = None
                for t in q_details.get("tags", []):
                    if t in TAG_MAPPING:
                        mapped_topic = TAG_MAPPING[t]
                        break
                        
                ts_int = int(sub.get("timestamp", 0))
                ts = datetime.fromtimestamp(ts_int, timezone.utc)
                
                processed_events.append({
                    "submission_id": f"lc_{slug}_{sub.get('timestamp')}",
                    "problem_slug": slug,
                    "problem_title": sub.get("title"),
                    "difficulty": q_details.get("difficulty"),
                    "language": sub.get("lang"),
                    "timestamp": ts.isoformat(),
                    "status": sub.get("statusDisplay"),
                    "runtime": "N/A",  # Not exposed on public recentSubmissionList API
                    "memory": "N/A",   # Not exposed on public recentSubmissionList API
                    "tags": q_details.get("tags", []),
                    "mapped_topic": mapped_topic
                })
            return processed_events
    except Exception as e:
        logger.error(f"Error syncing LeetCode for {username}: {e}")
        return []

@SyncRegistry.register
class LeetCodeAdapter(BaseSyncAdapter):
    @property
    def platform_name(self) -> str:
        return "leetcode"

    async def sync(self, credential: str) -> List[Dict[str, Any]]:
        events = await sync_leetcode(credential)
        formatted = []
        for e in events:
            formatted.append({
                "event_id": e["submission_id"],
                "timestamp": e["timestamp"],
                "mapped_topic": e["mapped_topic"],
                "raw_payload": e
            })
        return formatted
