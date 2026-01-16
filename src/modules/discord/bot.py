# modules/integrations/discord/bot.py
import logging
import discord
from typing import Optional, Callable

logger = logging.getLogger(__name__)


class KleeborgBot:
    """
    Minimal wrapper around discord.py client.
    ONLY handles connection, authentication, and event callbacks.
    Does NOT contain any business logic.
    """

    def __init__(self, token: str, intents: Optional[discord.Intents] = None):
        self.token = token

        if intents is None:
            intents = discord.Intents.default()
            # intents.message_content = True
            intents.voice_states = True
            intents.guilds = True
            intents.members = True

        self.client = discord.Client(intents=intents)
        self.is_connected = False

        # Callbacks - parent module sets these
        self.on_ready_callback: Optional[Callable] = None
        self.on_message_callback: Optional[Callable] = None
        self.on_voice_state_update_callback: Optional[Callable] = None
        self.on_member_join_callback: Optional[Callable] = None
        self.on_member_remove_callback: Optional[Callable] = None

        self._setup_events()

    def _setup_events(self):
        """Setup Discord.py event handlers - just call callbacks"""

        @self.client.event
        async def on_ready():
            self.is_connected = True
            logger.info(f"Discord bot connected as {self.client.user}")

            if self.on_ready_callback:
                await self.on_ready_callback(self.client.user)

        @self.client.event
        async def on_disconnect():
            self.is_connected = False
            logger.warning("Discord bot disconnected")

        @self.client.event
        async def on_message(message: discord.Message):
            if message.author == self.client.user:
                return

            if self.on_message_callback:
                await self.on_message_callback(message)

        @self.client.event
        async def on_voice_state_update(
            member: discord.Member,
            before: discord.VoiceState,
            after: discord.VoiceState,
        ):
            if self.on_voice_state_update_callback:
                await self.on_voice_state_update_callback(member, before, after)

        @self.client.event
        async def on_member_join(member: discord.Member):
            if self.on_member_join_callback:
                await self.on_member_join_callback(member)

        @self.client.event
        async def on_member_remove(member: discord.Member):
            if self.on_member_remove_callback:
                await self.on_member_remove_callback(member)

    async def connect(self):
        """Connect to Discord"""
        logger.info("Connecting to Discord...")

        await self.client.start(self.token)

    async def disconnect(self):
        """Disconnect from Discord"""
        logger.info("Disconnecting from Discord...")
        await self.client.close()

        self.is_connected = False

    async def send_message(
        self, channel_id: int, content: str
    ) -> Optional[discord.Message]:
        """Send a text message"""
        try:
            channel = self.client.get_channel(channel_id)

            if not channel:
                logger.error(f"Channel {channel_id} not found")
                return None

            return await channel.send(content)
        except Exception as e:
            logger.error(f"Failed to send message: {e}", exc_info=True)
            return None

    # Simple getters - NO logic
    def get_guild(self, guild_id: Optional[int] = None) -> Optional[discord.Guild]:
        """Get guild by ID or first guild"""
        if guild_id:
            return self.client.get_guild(guild_id)

        guilds = self.client.guilds

        return guilds[0] if guilds else None

    def get_channel(self, channel_id: int):
        """Get channel by ID"""
        return self.client.get_channel(channel_id)

    def get_member(self, guild_id: int, user_id: int) -> Optional[discord.Member]:
        """Get member from guild"""
        guild = self.get_guild(guild_id)

        if not guild:
            return None

        return guild.get_member(user_id)
