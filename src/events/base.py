# events/base.py
from dataclasses import dataclass, field
from typing import Any, Optional
from datetime import datetime
from .types import EventType, EventPriority


@dataclass(order=True)
class Event:
    """
    Base event class for the Kleeborp event system.
    """

    type: EventType
    data: Any = None
    source: Optional[str] = None
    priority: int = EventPriority.NORMAL.value
    timestamp: datetime = field(default_factory=datetime.now)
    id: Optional[str] = field(default=None)

    def __post_init__(self):
        # Auto-generate ID if not provided
        if self.id is None:
            self.id = f"{self.type.value}_{self.timestamp.timestamp()}"

        # Convert EventType to its value if needed
        if isinstance(self.type, EventType):
            self.type = self.type
        elif isinstance(self.type, str):
            # Allow string fallback for dynamic events
            self.type = self.type

    def to_dict(self) -> dict:
        """Convert event to dictionary for serialization"""
        return {
            "id": self.id,
            "type": str(self.type),
            "data": self.data,
            "source": self.source,
            "priority": self.priority,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Event":
        """Create event from dictionary"""
        return cls(
            type=EventType(data["type"]),
            data=data.get("data"),
            source=data.get("source"),
            priority=data.get("priority", EventPriority.NORMAL.value),
            id=data.get("id"),
        )

    def __str__(self):
        return f"Event({self.type}, source={self.source}, priority={self.priority})"
