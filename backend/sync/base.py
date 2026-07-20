from abc import ABC, abstractmethod
from typing import List, Dict, Any

class BaseSyncAdapter(ABC):
    @property
    @abstractmethod
    def platform_name(self) -> str:
        """Name of the platform this adapter handles (e.g. 'leetcode', 'github')."""
        pass

    @abstractmethod
    async def sync(self, credential: str) -> List[Dict[str, Any]]:
        """
        Pulls recent events from the platform.
        
        Args:
            credential: The auth token, handle, or session details needed for sync.
            
        Returns:
            A list of dictionary objects representing sync events. Each event should have:
                - event_id: A unique ID for the event.
                - timestamp: ISO 8601 string.
                - mapped_topic: The name of the RecallAI topic, or None.
                - raw_payload: The complete dict containing original metadata.
        """
        pass

class SyncRegistry:
    _registry: Dict[str, type] = {}

    @classmethod
    def register(cls, adapter_cls: type):
        """Decorator to register a sync adapter class."""
        # Instantiate or check attribute to confirm platform name
        instance = adapter_cls()
        platform = instance.platform_name
        cls._registry[platform] = adapter_cls
        return adapter_cls

    @classmethod
    def get_adapter(cls, platform: str) -> BaseSyncAdapter:
        """Retrieves an instance of the adapter registered for the platform."""
        adapter_cls = cls._registry.get(platform)
        if not adapter_cls:
            raise ValueError(f"No adapter registered for platform: '{platform}'")
        return adapter_cls()

    @classmethod
    def list_platforms(cls) -> List[str]:
        """Lists all registered platform names."""
        return list(cls._registry.keys())
