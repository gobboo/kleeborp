# modules/tools/internal_tools.py
from typing import Dict, Any


class InternalTools:
    """
    Internal tools that need access to Kleeborp's modules.
    These are NOT separate MCP servers - they run in-process.
    """

    def __init__(self, discord_module, memory_module, voice_manager):
        """
        Args:
            discord_module: Reference to Discord module
            memory_module: Reference to Memory module
            voice_manager: Reference to Voice manager
        """
        self.discord = discord_module
        self.memory = memory_module
        self.voice = voice_manager

    # === Discord Tools ===

    async def send_discord_message(
        self, channel_id: int, message: str
    ) -> Dict[str, Any]:
        """
        Send a message to a Discord channel.

        Args:
            channel_id: Discord channel ID
            message: Message content

        Returns:
            Success status and message info
        """
        try:
            sent_message = await self.discord.bot.send_message(channel_id, message)

            if sent_message:
                return {
                    "success": True,
                    "message_id": sent_message.id,
                    "content": message,
                }
            else:
                return {"success": False, "error": "Failed to send message"}

        except Exception as e:
            self.logger.error(f"Error sending Discord message: {e}")
            return {"success": False, "error": str(e)}

    async def join_voice_channel(self, channel_id: int) -> Dict[str, Any]:
        """
        Join a Discord voice channel.

        Args:
            channel_id: Voice channel ID

        Returns:
            Success status
        """
        try:
            success = await self.voice.join_channel(channel_id)

            if success:
                channel = self.voice.get_current_channel()
                return {
                    "success": True,
                    "channel_name": channel.name if channel else "unknown",
                    "users": [m.name for m in self.voice.get_users_in_channel()],
                }
            else:
                return {"success": False, "error": "Failed to join channel"}

        except Exception as e:
            self.logger.error(f"Error joining voice: {e}")
            return {"success": False, "error": str(e)}

    async def leave_voice_channel(self) -> Dict[str, Any]:
        """Leave current voice channel"""
        try:
            await self.voice.leave_channel()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def kleeborp_tantrum(self, reason: str = "I'm upset!") -> Dict[str, Any]:
        """
        Make Kleeborp have a tantrum (leave voice dramatically).

        Args:
            reason: Why Kleeborp is upset
        """
        try:
            await self.voice.tantrum(reason)
            return {"success": True, "message": f"Kleeborp had a tantrum: {reason}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # === Memory Tools ===

    async def create_memory(self, content: str, importance: int = 5) -> Dict[str, Any]:
        """
        Create a new memory.

        Args:
            content: Memory content
            importance: Importance score (1-10)
        """
        try:
            memory_id = await self.memory.create_memory(content, importance)
            return {"success": True, "memory_id": memory_id, "content": content}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def search_memories(self, query: str, limit: int = 5) -> Dict[str, Any]:
        """
        Search memories by query.

        Args:
            query: Search query
            limit: Max results
        """
        try:
            results = await self.memory.search(query, limit)
            return {"success": True, "memories": results}
        except Exception as e:
            return {"success": False, "error": str(e)}
