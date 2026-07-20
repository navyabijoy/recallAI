import httpx
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any
from .base import BaseSyncAdapter, SyncRegistry

logger = logging.getLogger(__name__)

# Map Codeforces tags to our recallAI graph topics
TAG_MAPPING = {
    "graphs": "Graphs",
    "dfs and similar": "Graphs",
    "dp": "Dynamic Programming",
    "binary search": "Binary Search",
    "two pointers": "Arrays",
    "divide and conquer": "Binary Search",
    "recursion": "Recursion"
}

async def sync_codeforces(handle: str) -> List[Dict[str, Any]]:
    """
    Pulls recent submissions for a Codeforces user handle.
    If handle is 'mock', returns simulated submissions.
    """
    if handle == "mock" or not handle:
        now = datetime.now(timezone.utc)
        return [
            {
                "submission_id": "cf_mock_1",
                "problem_name": "Maximum Flow",
                "problem_rating": 1700,
                "timestamp": now.isoformat(),
                "verdict": "OK",
                "time_to_solve_sec": 1200,
                "tags": ["graphs"],
                "mapped_topic": "Graphs"
            },
            {
                "submission_id": "cf_mock_2",
                "problem_name": "Knapsack Revision",
                "problem_rating": 1400,
                "timestamp": now.isoformat(),
                "verdict": "WRONG_ANSWER",
                "time_to_solve_sec": None,
                "tags": ["dp"],
                "mapped_topic": "Dynamic Programming"
            }
        ]

    url = f"https://codeforces.com/api/user.status?handle={handle}&from=1&count=10"
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=10.0)
            if response.status_code != 200:
                logger.error(f"Codeforces API returned status {response.status_code} for handle {handle}")
                return []
                
            res_json = response.json()
            if res_json.get("status") != "OK":
                logger.error(f"Codeforces API response status is not OK: {res_json.get('comment')}")
                return []
                
            submissions = res_json.get("result", [])
            processed = []
            
            for sub in submissions:
                sub_id = sub.get("id")
                problem = sub.get("problem", {})
                problem_name = problem.get("name", "")
                rating = problem.get("rating")
                verdict = sub.get("verdict", "")
                creation_time = sub.get("creationTimeSeconds", 0)
                relative_time = sub.get("relativeTimeSeconds")  # Time-to-solve if contest submission
                
                # Check for tag mapping
                cf_tags = problem.get("tags", [])
                mapped_topic = None
                for tag in cf_tags:
                    if tag in TAG_MAPPING:
                        mapped_topic = TAG_MAPPING[tag]
                        break
                        
                ts = datetime.fromtimestamp(creation_time, timezone.utc)
                
                processed.append({
                    "submission_id": f"cf_{sub_id}",
                    "problem_name": problem_name,
                    "problem_rating": rating,
                    "timestamp": ts.isoformat(),
                    "verdict": verdict,
                    "time_to_solve_sec": relative_time if relative_time != 2147483647 else None,
                    "tags": cf_tags,
                    "mapped_topic": mapped_topic
                })
                
            return processed
    except Exception as e:
        logger.error(f"Error syncing Codeforces for handle {handle}: {e}")
        return []

@SyncRegistry.register
class CodeforcesAdapter(BaseSyncAdapter):
    @property
    def platform_name(self) -> str:
        return "codeforces"

    async def sync(self, credential: str) -> List[Dict[str, Any]]:
        events = await sync_codeforces(credential)
        formatted = []
        for e in events:
            formatted.append({
                "event_id": e["submission_id"],
                "timestamp": e["timestamp"],
                "mapped_topic": e["mapped_topic"],
                "raw_payload": e
            })
        return formatted
