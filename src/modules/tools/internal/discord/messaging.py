# modules/tools/internal/discord/messaging.py
from ..base import BaseTool, tool


class DiscordMessagingTools(BaseTool):
    """Tools for Discord messaging"""

    @tool(
        name="send_discord_message",
        description="Send a text message to the primary Discord channel.",
        parameters={
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Message content"}
            },
            "required": ["message"],
        },
    )
    async def send_message(self, message: str):
        """Send a message to Discord channel"""
        discord = self.dependencies["discord_module"]

        try:
            sent = await discord.bot.send_message(932334357832663080, message)
            return {"success": True, "message_id": sent.id if sent else None}
        except Exception as e:
            self.logger.error(f"Failed to send message: {e}")
            return {"success": False, "error": str(e)}
