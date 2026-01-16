# events/handlers.py
from functools import wraps
from typing import Callable
from .types import EventType, EventPriority


def event_handler(*event_types: EventType, priority: int = EventPriority.NORMAL.value):
    """
    Decorator to mark methods as event handlers.

    Usage:
        @event_handler(EventType.USER_INPUT, EventType.USER_SPEAKING_STOPPED)
        async def handle_user_interaction(self, event: Event):
            pass
    """

    def decorator(func: Callable):
        # Store metadata on the function
        func._event_types = event_types
        func._event_priority = priority
        func._is_event_handler = True

        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await func(*args, **kwargs)

        return wrapper

    return decorator


def priority(level: EventPriority):
    """
    Decorator to set handler priority.

    Usage:
        @event_handler(EventType.INTERRUPT)
        @priority(EventPriority.CRITICAL)
        async def handle_interrupt(self, event: Event):
            pass
    """

    def decorator(func: Callable):
        func._event_priority = level.value
        return func

    return decorator
