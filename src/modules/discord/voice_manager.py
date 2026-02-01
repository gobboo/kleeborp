# modules/integrations/discord/voice_manager.py
import logging
from core.event_bus import EventBus
import discord
from discord import VoiceClient
from typing import Optional, Dict, Any
import asyncio
import random
from modules.discord.audio.audio_input import UserAudioInput
from modules.discord.bot import KleeborgBot
from events import Event, EventType
from discord.ext import voice_recv

from utils.pcm_audio import StreamingPCMSource

logger = logging.getLogger(__name__)


class VoiceManager:
    """
    Manages all voice channel operations and behaviors.
    Contains the personality/logic for voice interactions.
    """

    def __init__(self, bot: KleeborgBot, event_bus: EventBus):
        self.bot = bot
        self.event_bus = event_bus

        # State
        self.voice_client: Optional[VoiceClient] = None
        self.current_channel_id: Optional[int] = None
        self.is_in_tantrum = False

        # each users audio input
        self.audio_inputs: Dict[int, UserAudioInput] = {}

        self.voice_source = None
        self.current_tts_generation: int | None = None

        self.event_bus.subscribe(EventType.TTS_STARTED, self._on_tts_started)
        self.event_bus.subscribe(EventType.TTS_AUDIO_CHUNK, self._on_tts_chunk)
        self.event_bus.subscribe(EventType.TTS_EXHAUSTED, self._on_tts_exhausted)
        self.event_bus.subscribe(EventType.TTS_CANCELLED, self._on_tts_cancelled)

    def _setup_voice_receiver(self):
        """Setup voice receiver to capture audio from users"""

        def audio_callback(user, data: voice_recv.VoiceData):
            """Called when Discord receives audio"""
            if not user:
                 return

            if user.id in self.audio_inputs:
                # Queue audio to the user's input handler
                self.audio_inputs[user.id].queue_audio(data.pcm)

        if self.voice_client:
            self.voice_client.listen(voice_recv.BasicSink(audio_callback))
            logger.info("Voice receiver started")

    async def _add_user_audio_input(self, user_id: int, user_name: str):
        """Create and start audio input handler for a user"""
        if user_id in self.audio_inputs:
            logger.warning(f"Audio input already exists for {user_name}")
            return

        input_handler = UserAudioInput(
            user_id=user_id, user_name=user_name, event_bus=self.event_bus
        )

        await input_handler.start()
        self.audio_inputs[user_id] = input_handler

        logger.info(f"Started audio input for {user_name}")

    async def _remove_user_audio_input(self, user_id: int):
        """Stop and remove audio input handler for a user"""
        if user_id not in self.audio_inputs:
            return

        input_handler = self.audio_inputs.pop(user_id)
        await input_handler.stop()

        logger.info(f"Stopped audio input for user {user_id}")

    async def _create_all_audio_inputs(self, channel = None):
        channel = channel or self.get_current_channel()
        
        if channel is None:
            return

        for member in channel.members:
            if not member.bot:  # Don't track bots
                await self._add_user_audio_input(member.id, member.name)

    async def _cleanup_all_audio_inputs(self):
        """Stop all audio input handlers"""
        logger.info("Cleaning up all audio inputs")

        tasks = [handler.stop() for handler in self.audio_inputs.values()]
        await asyncio.gather(*tasks, return_exceptions=True)

        self.audio_inputs.clear()

    async def on_voice_state_update(self, member, before, after):
        """
        Handle voice state changes.
        Called by discord_module when Discord.py fires the event.
        """
        # If we moved channel, remove all our previous audio inputs and create new ones
        if self.get_current_channel() == after.channel and member.bot:
            logger.info('kleeb moved channels, updating all user inputs')
            await self._cleanup_all_audio_inputs()

            await self._create_all_audio_inputs(channel=after.channel)

            self._setup_voice_receiver()

        # User joined our channel
        if after.channel == self.get_current_channel() and not member.bot:
            if before.channel != after.channel:
                # User entered the channel
                await self._add_user_audio_input(member.id, member.name)

        # User left our channel
        if before.channel == self.get_current_channel() and not member.bot:
            if after.channel != before.channel:
                # User left the channel
                await self._remove_user_audio_input(member.id)

    async def join_channel(self, channel_id: int) -> bool:
        """
        Join a voice channel.

        Args:
            channel_id: Discord voice channel ID

        Returns:
            True if successful
        """
        try:
            channel = self.bot.get_channel(channel_id)

            if not channel or not isinstance(channel, discord.VoiceChannel):
                logger.error(f"Voice channel {channel_id} not found")
                return False

            # Leave current channel if connected
            if self.is_connected():
                await self.leave_channel()

            # Join new channel
            self.voice_client = await channel.connect(cls=voice_recv.VoiceRecvClient)
            self.current_channel_id = channel_id

            logger.info(f"Joined voice channel: {channel.name}")

            if self.is_connected():  # success
                self._setup_voice_receiver()

                # Create audio inputs for existing users in channel
                channel = self.get_current_channel()
                
                await self._create_all_audio_inputs()

                # Emit event
                await self.event_bus.emit(
                    Event(
                        type=EventType.DISCORD_VOICE_JOINED,
                        data={
                            "channel_id": channel_id,
                            "channel_name": channel.name,
                            "users": [m.name for m in channel.members],
                        },
                        source="voice_manager",
                    )
                )

            return True

        except Exception as e:
            logger.error(f"Failed to join voice channel: {e}", exc_info=True)
            return False

    async def leave_channel(self) -> bool:
        """
        Leave current voice channel.

        Returns:
            True if successfully left
        """
        if not self.is_connected():
            logger.warning("Not in a voice channel")
            return False

        channel_name = self.voice_client.channel.name
        channel_id = self.current_channel_id

        await self.voice_client.disconnect()
        self.voice_client = None
        self.current_channel_id = None

        await self._cleanup_all_audio_inputs()

        logger.info(f"Left voice channel: {channel_name}")

        # Emit event
        await self.event_bus.emit(
            Event(
                type=EventType.DISCORD_VOICE_LEFT,
                data={"channel_id": channel_id, "channel_name": channel_name},
                source="voice_manager",
            )
        )

        return True

    async def move_to_channel(self, channel_id: int) -> bool:
        """
        Move to a different voice channel.

        Args:
            channel_id: Target voice channel ID

        Returns:
            True if successful
        """
        return await self.join_channel(channel_id)

    # async def tantrum(self, reason: str = "I'm upset!"):
    #     """
    #     Kleeborp has a tantrum - leave, complain, maybe rejoin elsewhere.
    #     This is personality logic!

    #     Args:
    #         reason: Why Kleeborp is upset
    #     """
    #     if self.is_in_tantrum:
    #         logger.warning("Already in tantrum mode")
    #         return

    #     self.is_in_tantrum = True
    #     logger.info(f"Kleeborp tantrum triggered: {reason}")

    #     # Emit tantrum event
    #     await self.event_bus.emit(Event(
    #         type=EventType.KLEEBORP_TANTRUM,
    #         data={'reason': reason},
    #         source='voice_manager',
    #         priority=EventPriority.HIGH.value
    #     ))

    #     # Leave current channel dramatically
    #     if self.is_connected():
    #         await self.leave_channel()

    #     # Wait a bit (sulking time)
    #     await asyncio.sleep(random.uniform(3, 8))

    #     # Maybe join a different channel (or stay away)
    #     guild = self.bot.get_guild()
    #     if guild:
    #         voice_channels = [
    #             c for c in guild.channels
    #             if isinstance(c, discord.VoiceChannel)
    #         ]

    #         if voice_channels and random.random() > 0.3:  # 70% chance to rejoin
    #             # Pick a random channel (preferably empty or quiet)
    #             empty_channels = [c for c in voice_channels if len(c.members) == 0]
    #             target = random.choice(empty_channels if empty_channels else voice_channels)

    #             logger.info(f"Rejoining after tantrum: {target.name}")
    #             await self.join_channel(target.id)

    #     self.is_in_tantrum = False

    def is_connected(self) -> bool:
        """Check if currently in a voice channel"""
        return self.voice_client is not None and self.voice_client.is_connected()

    def get_current_channel(self) -> Optional[discord.VoiceChannel]:
        """Get current voice channel"""
        if self.is_connected():
            return self.voice_client.channel

        return None

    def get_users_in_channel(self) -> list[discord.Member]:
        """Get users in current voice channel"""
        channel = self.get_current_channel()

        if not channel:
            return []

        return channel.members

    def get_voice_client(self) -> Optional[VoiceClient]:
        """Get the Discord voice client (for audio handlers)"""
        return self.voice_client

    def get_state(self) -> Dict[str, Any]:
        """Get current voice state"""
        if not self.is_connected():
            return {"connected": False, "channel": None}

        channel = self.get_current_channel()
        users = self.get_users_in_channel()

        return {
            "connected": True,
            "in_tantrum": self.is_in_tantrum,
            "channel": {
                "id": channel.id,
                "name": channel.name,
                "users": [{"id": u.id, "name": u.name, "bot": u.bot} for u in users],
            },
        }
    

    async def _start_playback_if_needed(self):
        if self.voice_source is None:
            self.voice_source = StreamingPCMSource()

        loop = asyncio.get_event_loop()
        def after_playback(_):
          loop.call_soon_threadsafe(
              asyncio.create_task,
              self._on_playback_finished()
          )

        if not self.voice_client.is_playing():
            self.voice_client.play(self.voice_source, after=after_playback)

    

    async def _on_tts_cancelled(self, event):
        logger.info("TTS cancelled (gen=%d)", event.data["generation_id"])
        self.voice_source.reset()


    async def _on_tts_started(self, event):
        gen = event.data["generation_id"]
        logger.info("TTS started (gen=%d)", gen)

        self.current_tts_generation = gen

        await self._start_playback_if_needed()
        self.voice_source.reset()


    async def _on_tts_chunk(self, event: Event):
        gen = event.data["generation_id"]

        if gen != self.current_tts_generation:
            logger.debug(
                "Dropping stale TTS chunk (gen=%d, current=%s)",
                gen,
                self.current_tts_generation,
            )
            return

        if not self.voice_source:
            return

        audio = event.data["audio"]
        self.voice_source.write(audio)

    async def _on_tts_exhausted(self, event):
        logger.info("TTS exhausted (gen=%d)", event.data["generation_id"])
        # DO NOT close here
        self.voice_source.mark_eof()

    async def _on_playback_finished(self):
        logger.info("Playback fully completed")

        self.voice_source.close()
        self.voice_source = None
        self.current_tts_generation = None

        await self.event_bus.emit(Event(EventType.TTS_PLAYER_COMPLETE))
