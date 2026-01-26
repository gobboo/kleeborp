# core/application.py
import asyncio
import signal
import logging
import sys
from core.config import Config
from core.event_bus import EventBus
from core.module_manager import ModuleManager
from modules.brain.brain_module import BrainModule
from modules.discord.discord_module import DiscordModule
from modules.games.game_module import GameModule
from modules.memory.memory_module import MemoryModule
from modules.persona.persona_module import PersonaModule
from modules.tools.mcp_module import MCPModule
from modules.tools.tools_module import ToolsModule
from modules.tts.tts_module import TTSModule
from modules.whisper.whisper_module import WhisperModule
from services.websocket_server import WebSocketServer

logger = logging.getLogger(__name__)


class Application:
    def __init__(self, config: Config):
        self.config = config
        self.event_bus = EventBus()
        self.module_manager = ModuleManager()
        self.websocket_server = WebSocketServer(
            self.module_manager,
            self.event_bus,
            host=config.get("websocket.host", "localhost"),
            port=config.get("websocket.port", 8765),
        )
        self._shutdown_event = asyncio.Event()
        self._tasks = []  # keeps track of everything so we can use it to safely shutdown later

    def _setup_modules(self):
        """Instantiate and register all modules"""

        # register the rest as they dont depend on anything above
        modules = [
            PersonaModule(self.event_bus, self.module_manager),
            MemoryModule(self.event_bus, self.module_manager, self.config.raw),
            BrainModule(self.event_bus, self.module_manager, self.config.raw),
            WhisperModule(
                self.event_bus,
                self.module_manager,
                self.config.get("modules.whisper", {}),
            ),
            TTSModule(
                self.event_bus, self.module_manager, self.config.get("modules.tts", {})
            ),
            GameModule(self.event_bus, self.module_manager, self.config.get("modules.games"))
        ]
        
        for module in modules:
            self.module_manager.register(module)
        
        discord_module = DiscordModule(
            self.event_bus, self.module_manager, self.config.get("modules.discord", {})
        )

        self.module_manager.register(discord_module)

        tools_module = ToolsModule(
            event_bus=self.event_bus,
            module_manager=self.module_manager,
            config=self.config,
            discord_module=discord_module,
            voice_manager=discord_module.voice_manager,
        )

        self.module_manager.register(tools_module)



    def _setup_signal_handlers(self):
        """Setup signal handlers (cross-platform)"""

        def signal_handler(sig, frame):
            logger.info(f"Received signal {sig}")
            # Schedule shutdown in the event loop
            self._shutdown_event.set()

        # This works on both Windows and Unix
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        # On Windows, also handle CTRL_BREAK_EVENT
        if sys.platform == "win32":
            signal.signal(signal.SIGBREAK, signal_handler)

    async def start(self):
        """Start the application"""
        logger.info("Starting Kleeborp")

        # Setup signal handlers
        self._setup_signal_handlers()

        # Setup modules
        self._setup_modules()
        await self.module_manager.initialize_all()

        # Start everything
        self._tasks = [
            asyncio.create_task(self.event_bus.run(), name="event_bus"),
            asyncio.create_task(self.module_manager.start_all(), name="modules"),
            # Only start websocket if enabled
            asyncio.create_task(self.websocket_server.start(), name="websocket"),
        ]

        logger.info("Kleeborp started successfully")

        # Wait for shutdown
        await self._shutdown_event.wait()

    async def shutdown(self):
        """Graceful shutdown"""
        if self._shutdown_event.is_set():
            return  # Already shutting down

        logger.info("Shutting down Kleeborp")
        self._shutdown_event.set()

        await self.event_bus.stop()

        # Stop all modules
        await self.module_manager.stop_all()

        # Cancel all tasks
        for task in self._tasks:
            if not task.done():
                task.cancel()

        # Wait for tasks to complete
        try:
            await asyncio.wait_for(
                asyncio.gather(*self._tasks, return_exceptions=True), timeout=5.0
            )
        except asyncio.TimeoutError:
            logger.warning("Some tasks didn't stop in time, forcing shutdown")

        logger.info("Kleeborp shut down complete")
