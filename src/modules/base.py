# modules/base.py
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
import asyncio
import logging
from core.event_bus import EventBus
from events import Event, EventType

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.module_manager import ModuleManager


class BaseModule(ABC):
    def __init__(
        self,
        name: str,
        event_bus: EventBus,
        module_manager: "ModuleManager",
        config: Dict[str, Any] = None,
    ):
        self.name = name
        self.event_bus = event_bus
        self.config = config or {}
        self.module_manager = module_manager
        self.logger = logging.getLogger(f"module.{name}")
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def initialize(self):
        """Initialize module (setup, connections, etc)"""
        self.logger.info(f"Initializing {self.name}")
        await self._setup()

        self._auto_register_handlers()

    def _auto_register_handlers(self):
        """Automatically register methods decorated with @event_handler"""
        for attr_name in dir(self):
            attr = getattr(self, attr_name)

            # Check if method is decorated as event handler
            if hasattr(attr, "_is_event_handler"):
                event_types = attr._event_types
                priority = attr._event_priority

                for event_type in event_types:
                    self.event_bus.subscribe(event_type, attr, priority)
                    self.logger.debug(
                        f"Auto-registered handler {attr_name} for {event_type}"
                    )

    async def start(self):
        """Start the module"""
        if self._running:
            return

        self._running = True
        self.logger.info(f"Starting {self.name}")

        # Emit module started event
        await self.event_bus.emit(
            Event(
                type=EventType.MODULE_STARTED,
                data={"module": self.name},
                source=self.name,
            )
        )

        self._task = asyncio.create_task(self._run())

    async def stop(self):
        """Stop the module gracefully"""
        if not self._running:
            return

        self.logger.info(f"Stopping {self.name}")
        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        await self._cleanup()

        # Emit module stopped event
        await self.event_bus.emit(
            Event(
                type=EventType.MODULE_STOPPED,
                data={"module": self.name},
                source=self.name,
            )
        )

    @abstractmethod
    async def _setup(self):
        """Module-specific setup"""
        pass

    @abstractmethod
    async def _run(self):
        """Main module loop"""
        pass

    @abstractmethod
    async def _cleanup(self):
        """Module-specific cleanup"""
        pass

    async def get_prompt_fragment(self) -> Optional[str]:
        """Return prompt fragment if module contributes to system prompt"""
        return None

    def get_state(self) -> Dict[str, Any]:
        """Return current module state for external inspection"""
        return {"name": self.name, "running": self._running}
