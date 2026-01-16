# core/event_bus.py
import itertools
from typing import Callable, Dict, List, Any
import asyncio
from events import Event, EventType
import logging

logger = logging.getLogger(__name__)


class EventBus:
    def __init__(self):
        self._handlers: Dict[EventType, List[tuple[int, Callable]]] = {}
        self._queue = asyncio.PriorityQueue()
        self._running = False
        self._event_history: List[Event] = []  # For debugging
        self._max_history = 100

        self._counter = itertools.count()

    def subscribe(self, event_type: EventType, handler: Callable, priority: int = 50):
        """Subscribe to events with optional priority"""
        if event_type not in self._handlers:
            self._handlers[event_type] = []

        self._handlers[event_type].append((priority, handler))
        # Sort by priority (highest first)
        self._handlers[event_type].sort(key=lambda x: x[0], reverse=True)

        logger.debug(f"Handler subscribed to {event_type} with priority {priority}")

    def unsubscribe(self, event_type: EventType, handler: Callable):
        """Unsubscribe from events"""
        if event_type in self._handlers:
            self._handlers[event_type] = [
                (p, h) for p, h in self._handlers[event_type] if h != handler
            ]

    async def emit(self, event: Event):
        """Emit event to queue"""
        await self._queue.put((-event.priority, next(self._counter), event))
        logger.debug(
            f"Event emitted: {event.type} (priority={event.priority}, source={event.source})"
        )

    async def emit_and_wait(self, event: Event) -> List[Any]:
        """
        Emit event and wait for all handlers to complete.
        Returns list of handler results.
        """
        if event.type not in self._handlers:
            return []

        tasks = []
        for priority, handler in self._handlers[event.type]:
            tasks.append(handler(event))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        return results

    async def run(self):
        """Process events from queue"""
        self._running = True
        logger.info("Event bus started")

        while self._running:
            try:
                _, _, event = await asyncio.wait_for(self._queue.get(), timeout=0.1)

                # Store in history for debugging
                self._event_history.append(event)
                if len(self._event_history) > self._max_history:
                    self._event_history.pop(0)

                await self._dispatch(event)

            except asyncio.TimeoutError:
                # HANDLE TIMEOUT - just continue checking
                continue
            except asyncio.CancelledError:
                logger.info("Event bus cancelled")
                break
            except Exception as e:
                logger.error(f"Error processing event: {e}", exc_info=True)

    async def _dispatch(self, event: Event):
        """Dispatch event to handlers"""
        if event.type not in self._handlers:
            logger.debug(f"No handlers for event: {event.type}")
            return

        logger.debug(
            f"Dispatching {event.type} to {len(self._handlers[event.type])} handlers"
        )

        tasks = []
        for priority, handler in self._handlers[event.type]:
            tasks.append(self._handle_with_error_catching(handler, event))

        await asyncio.gather(*tasks, return_exceptions=True)

    async def _handle_with_error_catching(self, handler: Callable, event: Event):
        """Call handler with error catching"""
        try:
            await handler(event)
        except Exception as e:
            logger.error(
                f"Error in event handler for {event.type}: {e}",
                exc_info=True,
                extra={"event": event.to_dict()},
            )

    def get_history(self, event_type: EventType = None, limit: int = 10) -> List[Event]:
        """Get recent event history"""
        if event_type:
            events = [e for e in self._event_history if e.type == event_type]
        else:
            events = self._event_history

        return events[-limit:]

    async def stop(self):
        """Stop the event bus"""
        logger.info("Stopping event bus")
        self._running = False
