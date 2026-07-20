import httpx
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any
from .base import BaseSyncAdapter, SyncRegistry

logger = logging.getLogger(__name__)

# Keyword to topic mapping for weaker signal committing
KEYWORD_MAPPING = {
    "array": "Arrays",
    "search": "Binary Search",
    "sliding": "Sliding Window",
    "graph": "Graphs",
    "bfs": "Graphs",
    "dfs": "Graphs",
    "union": "Union Find",
    "dp": "Dynamic Programming",
    "dynamic": "Dynamic Programming",
    "trie": "Trie",
    "recur": "Recursion",
    "python": "Python Functions",
    "thread": "Python Concurrency",
    "async": "Python Concurrency",
    "cache": "Caching",
    "load": "Load Balancers",
    "shard": "Database Sharding"
}

async def sync_github(username: str) -> List[Dict[str, Any]]:
    """
    Pulls recent GitHub commits via the public user events API.
    If username is 'mock', returns simulated commit events.
    """
    if username == "mock" or not username:
        now = datetime.now(timezone.utc)
        return [
            {
                "event_id": "mock_gh_1",
                "repo": "my-algorithms-repo",
                "commit_message": "implement graph bfs search traversal",
                "timestamp": now.isoformat(),
                "languages": ["python"],
                "mapped_topic": "Graphs"
            },
            {
                "event_id": "mock_gh_2",
                "repo": "system-design-notes",
                "commit_message": "add load balancer notes and caching mechanism docs",
                "timestamp": now.isoformat(),
                "languages": ["markdown"],
                "mapped_topic": "Caching"
            }
        ]

    url = f"https://api.github.com/users/{username}/events/public"
    headers = {
        "User-Agent": "RecallAI-Agent-Client",
        "Accept": "application/vnd.github.v3+json"
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, timeout=10.0)
            if response.status_code != 200:
                logger.error(f"GitHub API returned status {response.status_code} for user {username}")
                return []
                
            events = response.json()
            processed_commits = []
            
            for event in events:
                if event.get("type") != "PushEvent":
                    continue
                    
                repo_name = event.get("repo", {}).get("name", "")
                payload = event.get("payload", {})
                commits = payload.get("commits", [])
                created_at = event.get("created_at")
                
                # Check each commit in the push
                for commit in commits:
                    message = commit.get("message", "").lower()
                    sha = commit.get("sha", "")
                    
                    # Map message keywords to topic
                    mapped_topic = None
                    for kw, topic in KEYWORD_MAPPING.items():
                        if kw in message:
                            mapped_topic = topic
                            break
                            
                    processed_commits.append({
                        "event_id": f"gh_{sha}",
                        "repo": repo_name,
                        "commit_message": commit.get("message"),
                        "timestamp": created_at,
                        "languages": [],  # High-level language mapping would require hitting the repo API, keep it simple for now
                        "mapped_topic": mapped_topic
                    })
                    
            return processed_commits
    except Exception as e:
        logger.error(f"Error syncing GitHub commits for {username}: {e}")
        return []

@SyncRegistry.register
class GitHubAdapter(BaseSyncAdapter):
    @property
    def platform_name(self) -> str:
        return "github"

    async def sync(self, credential: str) -> List[Dict[str, Any]]:
        events = await sync_github(credential)
        formatted = []
        for e in events:
            formatted.append({
                "event_id": e["event_id"],
                "timestamp": e["timestamp"],
                "mapped_topic": e["mapped_topic"],
                "raw_payload": e
            })
        return formatted
