# modules/tools/mcp_module.py
from typing import Any, Dict
from modules.base import BaseModule
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from .tool_registry import ToolRegistry
import asyncio


class MCPModule(BaseModule):
    """
    MCP Client - connects to external MCP servers.
    Registers their tools in the ToolRegistry.
    """

    def __init__(self, event_bus, module_manager, config, tool_registry: ToolRegistry):
        super().__init__("mcp", event_bus, module_manager, config)
        self.tool_registry = tool_registry
        self.sessions: Dict[str, ClientSession] = {}
        self._server_tasks = []

    async def _setup(self):
        """Connect to configured MCP servers"""
        servers = self.config.get("servers", {})

        for server_name, server_config in servers.items():
            task = asyncio.create_task(self._connect_server(server_name, server_config))
            self._server_tasks.append(task)

    async def _connect_server(self, server_name: str, config: dict):
        """Connect to an MCP server and register its tools"""
        try:
            server_params = StdioServerParameters(
                command=config["command"],
                args=config.get("args", []),
                env=config.get("env"),
            )

            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()

                    # Store session
                    self.sessions[server_name] = session

                    # List and register tools
                    tools_response = await session.list_tools()

                    for tool in tools_response.tools:
                        self.tool_registry.register_mcp_tool(
                            name=tool.name,
                            description=tool.description,
                            parameters=tool.inputSchema,
                            mcp_server=server_name,
                        )

                    self.logger.info(
                        f"Connected to MCP server '{server_name}' "
                        f"with {len(tools_response.tools)} tools"
                    )

                    # Keep connection alive
                    while self._running:
                        await asyncio.sleep(1)

        except Exception as e:
            self.logger.error(
                f"Error connecting to MCP server '{server_name}': {e}", exc_info=True
            )

    async def call_tool(self, server_name: str, tool_name: str, arguments: dict) -> Any:
        """
        Call a tool on an MCP server.

        Args:
            server_name: Which MCP server to call
            tool_name: Tool name
            arguments: Tool arguments

        Returns:
            Tool result
        """
        if server_name not in self.sessions:
            raise ValueError(f"MCP server '{server_name}' not connected")

        session = self.sessions[server_name]
        result = await session.call_tool(tool_name, arguments)

        return result.content

    async def _run(self):
        """Keep server connections alive"""
        try:
            # Wait for all server tasks
            await asyncio.gather(*self._server_tasks)
        except asyncio.CancelledError:
            self.logger.info("MCP module cancelled")
            raise

    async def _cleanup(self):
        """Disconnect from MCP servers"""
        self.logger.info("Disconnecting from MCP servers")
        # Sessions auto-close via context managers
