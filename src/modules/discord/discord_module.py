# modules/integrations/discord/discord_module.py
import asyncio
import logging
from typing import Dict

from discord import datetime
from modules.base import BaseModule
from events import Event, EventType, event_handler
from modules.discord.audio.audio_input import UserAudioInput
from utils.user_name_to_name import user_name_to_name
from .bot import KleeborgBot
from .voice_manager import VoiceManager

logger = logging.getLogger(__name__)


class DiscordModule(BaseModule):
    def __init__(self, event_bus, module_manager, config):
        super().__init__("discord", event_bus, module_manager, config)

        # Create components
        self.bot = KleeborgBot(token=config["token"])
        self.voice_manager = VoiceManager(self.bot, event_bus)

        # Set bot callbacks
        self.bot.on_ready_callback = self._on_bot_ready
        self.bot.on_voice_state_update_callback = self._on_voice_state_update
        self.bot.on_member_join_callback

    async def _on_bot_ready(self, _):
        voice_channel_id = self.config.get("default_voice_channel")
        auto_join_enabled = self.config.get("auto_join")

        if not auto_join_enabled:
            return

        if not voice_channel_id:
            logger.warning("could not join an initial channel on bot startup.")
            return

        await self.event_bus.emit(
            Event(
                type=EventType.DISCORD_VOICE_JOIN, data={"channel_id": voice_channel_id}
            )
        )

    async def get_prompt_fragment(self):
        # return the current discord state
        prompt = f'This is ambient context. Not everything here requires a response.\nCurrent date time: {datetime.now()}\nCURRENT VOICE CHANNEL STATE: \nUsers Present:\n'
        
        users = self.voice_manager.get_users_in_channel()

        for member in users:
            name = user_name_to_name(member.name)

            if name:
                prompt += f'{name} - is_streaming: {member.voice.self_stream} - has_camera_on: {member.voice.self_video} - is_muted: {member.voice.self_mute or member.voice.mute} - is_defeaned: {member.voice.deaf or member.voice.self_deaf}\n'
    
        return prompt

    @event_handler(EventType.DISCORD_VOICE_JOIN)
    async def handle_join_request(self, event: Event):
        """External request to join voice"""
        channel_id = event.data["channel_id"]

        await self.voice_manager.join_channel(channel_id)

    @event_handler(EventType.DISCORD_VOICE_LEAVE)
    async def handle_leave_request(self, event: Event):
        """External request to leave voice"""
        await self.voice_manager.leave_channel()

    @event_handler(EventType.TOOL_CALL_REQUEST)
    async def handle_tool_call(self, event: Event):
        """Handle tool calls from brain (like AI saying 'join voice')"""
        tool_name = event.data["name"]
        args = event.data["arguments"]

        if tool_name == "discord_join_voice":
            await self.voice_manager.join_channel(args["channel_id"])
        elif tool_name == "discord_leave_voice":
            await self.voice_manager.leave_channel()
        elif tool_name == "discord_tantrum":
            await self.voice_manager.tantrum(args.get("reason", "Unknown"))

    async def _on_voice_state_update(self, member, before, after):
        """Discord.py callback - someone's voice state changed"""
        await self.voice_manager.on_voice_state_update(member, before, after)

    async def _setup(self):
        return await super()._setup()

    async def _run(self):
        try:
            await self.bot.connect()
        except asyncio.CancelledError:
            logger.info("Discord module cancelled")
            raise  # Must re-raise to stop properly
        except Exception as e:
            logger.error(f"Error in Discord connection: {e}")
            raise
    
    
    async def _cleanup(self):
        return await super()._cleanup()
