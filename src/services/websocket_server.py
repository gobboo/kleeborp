# services/websocket_server.py
import asyncio
import json
import logging
from typing import Set
from core.event_bus import Event, EventBus
from core.module_manager import ModuleManager
import websockets

from modules.games.game_module import GameModule

logger = logging.getLogger(__name__)

class WebSocketServer:
    def __init__(
        self,
        module_manager: ModuleManager,
        event_bus: EventBus,
        host: str = "0.0.0.0",
        port: int = 8765,
    ):
        self.module_manager = module_manager
        self.event_bus = event_bus
        self.host = host
        self.port = port
        self._clients: Set[websockets.WebSocketServerProtocol] = set()
        
        self.game_module: GameModule | None = None

    async def start(self):
        """Start WebSocket server"""
        logger.info(f"Starting WebSocket server on {self.host}:{self.port}")
        self.game_module = self.module_manager.get_module('game')
        stop = asyncio.get_running_loop().create_future()

        async with websockets.serve(self._handle_client, self.host, self.port):
            await stop  # Run forever

    async def _handle_client(self, websocket):
        """Handle individual client connection"""
        logger.info(f"Client connected: {websocket.remote_address}")
        self._clients.add(websocket)


        try:
            async for message in websocket:
                await self._process_message(websocket, message)
        except websockets.exceptions.ConnectionClosed:
            logger.info(f"Client disconnected: {websocket.remote_address}")
        finally:
            self._clients.remove(websocket)

    async def _process_message(self, websocket, message: str):
        """Process incoming WebSocket message"""
        try:
            data = json.loads(message)
            command = data.get("command")
            
            # specific commands for the game module
            game_commands = ["startup", "context", "actions/force", "actions/register", "actions/unregister", "action/result"]

            if command == "get_state":
                state = self.module_manager.get_all_state()
                await websocket.send(json.dumps({"type": "state", "data": state}))

            elif command == "emit_event":
                event = Event(
                    type=data["event_type"],
                    data=data.get("event_data"),
                    source="websocket",
                )

                await self.event_bus.emit(event)

                await websocket.send(json.dumps({"type": "ack", "success": True}))

            elif command in game_commands:
                # Handle memory management
                self.game_module.handle_incoming_command(command, data)

        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
            await websocket.send(json.dumps({"type": "error", "message": str(e)}))

    async def broadcast(self, message: dict):
        """Broadcast message to all connected clients"""
        if self._clients:
            await asyncio.gather(
                *[client.send(json.dumps(message)) for client in self._clients],
                return_exceptions=True,
            )
