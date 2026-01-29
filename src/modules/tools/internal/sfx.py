# modules/tools/internal/discord/messaging.py
import asyncio
import base64
from io import BytesIO

from discord import FFmpegPCMAudio

from services.llm_client import LLMClient
from .base import BaseTool, tool
from PIL import ImageGrab
import pathlib

SCHEMA = {
    "type": "object",
    "properties": {
        "sound_name": {
            "type": "string",
            "description": "The name of the sound to play, must be one of these options.",
            "enum": []
        },

        "count": {
            "type": "number",
            "default": "1",
            "description": "How many times to play the same sound in a loop."
        }
    },
    "required": ["sound_name"],
}

class SFXTool(BaseTool):
    """Tools for playing sounds"""
    def __init__(self, config, **dependencies):
        super().__init__(config, **dependencies)

        self.voice_manager = self.dependencies["voice_manager"]

        if not self.voice_manager:
            raise Exception("SFXTool depends on voice_manager")

        self.config = config

        self.sounds_path = pathlib.Path('assets/sounds')
        
        self.registered_sounds = []

        self.is_playing = asyncio.Lock()

        self._register_sounds_from_repo()

    def _register_sounds_from_repo(self):
        files = self.sounds_path.glob('*.mp3')

        for file in list(files):
            self.register_sound(file.name)
        
    def register_sound(self, name: str):
        print(f'registered sound {name}')
        self.registered_sounds.append(name)
        SCHEMA["properties"]["sound_name"]["enum"] = self.registered_sounds
        

    def unregister_sound(self, name: str):
        self.registered_sounds.remove(name)
        SCHEMA["properties"]["sound_name"]["enum"] = self.registered_sounds

    def _on_finish(self, _):
        self.is_playing.release()
        pass
    
    @tool(
        name="play_sound_effect",
        description="Play a specific sound effect by name when asked, pranking or when its funny to do so, not to be spammed.",
        parameters=SCHEMA,
    )
    async def play_sfx(self, sound_name: str, count: int = 1):

        source = FFmpegPCMAudio(source=f'assets/sounds/{sound_name}')
        
        for _ in range(count):
            await self.is_playing.acquire() # lock the continuation
            if self.voice_manager.voice_client.is_playing():
              self.voice_manager.voice_client.stop()

            self.voice_manager.voice_client.play(source, after=self._on_finish)
            
            await self.is_playing.acquire() # unlock when done, but blocks until its unlocked
            
            self.is_playing.release()

            

        return {"success": True, "result": f"successfully played sound effect {sound_name}, we will not play again."}