# modules/tools/tools_module.py
import asyncio
from modules.base import BaseModule
from events import Event, EventType, event_handler
from .tool_registry import ToolRegistry
from .mcp_module import MCPModule
from .internal import TOOL_CLASSES


class ToolsModule(BaseModule):
    """Main tools orchestrator"""

    def __init__(self, event_bus, module_manager, config, **module_dependencies):
        """
        Args:
            event_bus: Event bus
            config: Config
            **module_dependencies: discord_module, memory_module, voice_manager, etc.
        """
        super().__init__("tools", event_bus, module_manager, config)

        self.tool_registry = ToolRegistry()
        self.module_dependencies = module_dependencies
        self.tool_instances = []

        # MCP module for external tools
        self.mcp_module = MCPModule(
            event_bus=event_bus,
            module_manager=self.module_manager,
            config=config.get("mcp", {}),
            tool_registry=self.tool_registry,
        )

    async def _setup(self):
        """Auto-register all internal tools"""
        # Instantiate all tool classes
        for ToolClass in TOOL_CLASSES:
            tool_instance = ToolClass(config=self.config, **self.module_dependencies)
            self.tool_instances.append(tool_instance)

            # Register all tools from this instance
            for tool_def in tool_instance.get_tools():
                self.tool_registry.register_internal_tool(
                    name=tool_def.name,
                    description=tool_def.description,
                    parameters=tool_def.parameters,
                    handler=tool_def.handler,
                )

                self.logger.debug(f"Registered tool: {tool_def.name}")

        # Initialize MCP module
        await self.mcp_module.initialize()
        await self.mcp_module.start()

        total_tools = len(self.tool_registry.get_all_tools())
        self.logger.info(f"Registered {total_tools} total tools")
        
    def normalize_mcp_content(self, content):
        """
        Converts MCP content blocks into JSON-serializable dicts
        """
        if isinstance(content, list):
            return [self.normalize_mcp_content(c) for c in content]

        # MCP TextContent
        if hasattr(content, "type"):
            data = {"type": content.type}

            # Pull common known fields safely
            if hasattr(content, "text"):
                data["text"] = content.text

            if hasattr(content, "annotations") and content.annotations is not None:
                data["annotations"] = content.annotations

            if hasattr(content, "meta") and content.meta is not None:
                data["meta"] = content.meta

            return data

        # Already JSON-safe
        return content


    @event_handler(EventType.TOOL_CALL_REQUEST)
    async def handle_tool_call(self, event: Event):
        """Handle tool calls"""
        tool_name = event.data["name"]
        tool_id = event.data["id"]
        arguments = event.data["arguments"]

        self.logger.info(f"Tool call: {tool_name}")

        try:
            if self.tool_registry.is_internal_tool(tool_name):
                # Internal tool
                tool_def = self.tool_registry.get_tool(tool_name)
                if arguments != None:
                    result = await tool_def.handler(**arguments)
                else:
                    result = await tool_def.handler()

            elif self.tool_registry.is_mcp_tool(tool_name):
                # MCP tool
                tool_def = self.tool_registry.get_tool(tool_name)
                result = await self.mcp_module.call_tool(
                    server_name=tool_def.mcp_server,
                    tool_name=tool_name,
                    arguments=arguments,
                )

                result = self.normalize_mcp_content(result)
            else:
                self.logger.warning(f"attempted to use unknown tool: {tool_name}")
                # raise ValueError(f"Unknown tool: {tool_name}")
                return
            
            # Transform the results


            # Emit result
            await self.event_bus.emit(
                Event(
                    type=EventType.TOOL_RESULT,
                    data={"id": tool_id, "name": tool_name, "result": result},
                    source="tools",
                )
            )

        except Exception as e:
            self.logger.error(f"Tool call failed: {e}", exc_info=True)
            await self.event_bus.emit(
                Event(
                    type=EventType.TOOL_CALL_ERROR,
                    data={"id": tool_id, "name": tool_name, "error": str(e)},
                    source="tools",
                )
            )

    def get_tool_definitions_for_llm(self) -> list:
        """Get all tool definitions for LLM"""
        return self.tool_registry.get_tool_definitions_for_llm()

    async def _run(self):
        while self._running:
            await asyncio.sleep(1)

    async def _cleanup(self):
        await self.mcp_module.stop()
