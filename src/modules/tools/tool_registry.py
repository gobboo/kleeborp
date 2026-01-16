# modules/tools/tool_registry.py
import logging
from typing import Dict, Callable, Any, Optional
from dataclasses import dataclass


@dataclass
class ToolDefinition:
    """Definition of a tool for LLM"""

    name: str
    description: str
    parameters: dict  # JSON schema
    handler: Optional[Callable] = None  # For internal tools
    mcp_server: Optional[str] = None  # For external MCP tools


class ToolRegistry:
    """
    Centralized registry for all tools (internal + external MCP).
    Provides unified interface for the brain module.
    """

    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}
        self.logger = logging.getLogger(__name__)

    def register_internal_tool(
        self, name: str, description: str, parameters: dict, handler: Callable
    ):
        """Register an internal tool with a handler function"""
        tool = ToolDefinition(
            name=name, description=description, parameters=parameters, handler=handler
        )
        self._tools[name] = tool
        self.logger.info(f"Registered internal tool: {name}")

    def register_mcp_tool(
        self, name: str, description: str, parameters: dict, mcp_server: str
    ):
        """Register an external MCP tool"""
        tool = ToolDefinition(
            name=name,
            description=description,
            parameters=parameters,
            mcp_server=mcp_server,
        )
        self._tools[name] = tool
        self.logger.info(f"Registered MCP tool: {name} (server: {mcp_server})")

    def get_tool(self, name: str) -> Optional[ToolDefinition]:
        """Get tool definition by name"""
        return self._tools.get(name)

    def get_all_tools(self) -> Dict[str, ToolDefinition]:
        """Get all registered tools"""
        return self._tools.copy()

    def get_tool_definitions_for_llm(self) -> list:
        """
        Get tool definitions in OpenAI format for LLM.

        Returns:
            List of tool definitions compatible with OpenAI API
        """
        definitions = []

        for tool in self._tools.values():
            definitions.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters,
                    },
                }
            )

        return definitions

    def is_internal_tool(self, name: str) -> bool:
        """Check if tool is internal (has handler)"""
        tool = self.get_tool(name)
        return tool is not None and tool.handler is not None

    def is_mcp_tool(self, name: str) -> bool:
        """Check if tool is external MCP tool"""
        tool = self.get_tool(name)
        return tool is not None and tool.mcp_server is not None
