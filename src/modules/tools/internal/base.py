# modules/tools/internal/base.py
import logging
from typing import Dict, Any, List
from dataclasses import dataclass


@dataclass
class ToolDefinition:
    """Tool definition for registration"""

    name: str
    description: str
    parameters: dict
    handler: callable


class BaseTool:
    """
    Base class for tool groups.
    Subclasses define tools and auto-register them.
    """

    def __init__(self, config: dict, **dependencies):
        """
        Args:
            **dependencies: Module references (discord_module, memory_module, etc.)
        """
        self.dependencies = dependencies
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__)

    def get_tools(self) -> List[ToolDefinition]:
        """
        Get all tool definitions from this tool group.
        Override in subclasses or use the decorator pattern.
        """
        tools = []

        # Auto-discover methods decorated with @tool
        for attr_name in dir(self):
            attr = getattr(self, attr_name)

            if hasattr(attr, "_is_tool"):
                tools.append(
                    ToolDefinition(
                        name=attr._tool_name,
                        description=attr._tool_description,
                        parameters=attr._tool_parameters,
                        handler=attr,
                    )
                )

        return tools


def tool(name: str, description: str, parameters: dict):
    """
    Decorator to mark a method as a tool.

    Usage:
        @tool(
            name="send_message",
            description="Send a Discord message",
            parameters={...}
        )
        async def send_message(self, channel_id: int, message: str):
            pass
    """

    def decorator(func):
        func._is_tool = True
        func._tool_name = name
        func._tool_description = description
        func._tool_parameters = parameters
        return func

    return decorator
