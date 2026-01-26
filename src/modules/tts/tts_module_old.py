# modules/speech/tts_module.py
import asyncio
import re
import io
import numpy as np
import soundfile as sf

from RealtimeTTS import TextToAudioStream, AzureEngine
from events import EventType, event_handler, Event, EventPriority
from modules.base import BaseModule
from utils.pcm_audio import DiscordAudioProcessor

DISCORD_FRAME_BYTES = 3840  # 20ms @ 48kHz stereo s16le


class TTSModule(BaseModule):
    def __init__(self, event_bus, module_manager, config):
        super().__init__("tts", event_bus, module_manager, config)

        self.text_buffer = ""
        self.sentence_pattern = re.compile(r"[.!?]+\s+")

        self.engine = None
        self.stream = None

        self._synthesis_queue = asyncio.Queue()
        self._synthesis_worker_task = None
        self._is_synthesizing = False
        self._is_speaking = False

        self._event_loop = None
        self._audio_processor = DiscordAudioProcessor()

    # ---------------- SETUP ---------------- #

    async def _setup(self):
        self._event_loop = asyncio.get_event_loop()

        speech_key = self.config.get("azure_speech_key")
        speech_region = self.config.get("azure_speech_region")

        if not speech_key or "your-azure" in speech_key.lower():
            raise ValueError("Azure Speech Key not configured")

        self.engine = AzureEngine(
            speech_key=speech_key,
            service_region=speech_region,
            voice=self.config.get("voice", "en-US-AriaNeural"),
            pitch=25,
            audio_format="riff-48khz-16bit-mono-pcm",
        )

        self.stream = TextToAudioStream(self.engine, muted=True)

        self.logger.info("✓ Azure TTS ready")

    # ---------------- TEXT INGEST ---------------- #

    @event_handler(EventType.LLM_TEXT_CHUNK)
    async def on_text_chunk(self, event: Event):
        self.text_buffer += event.data.get("text", "")

        sentences = self.sentence_pattern.split(self.text_buffer)
        if len(sentences) > 1:
            for sentence in sentences[:-1]:
                sentence = sentence.strip()
                if sentence:
                    await self._queue_sentence(sentence)

            self.text_buffer = sentences[-1]

    @event_handler(EventType.LLM_GENERATION_COMPLETE)
    async def on_generation_complete(self, event: Event):
        if self.text_buffer.strip():
            await self._queue_sentence(self.text_buffer.strip())
            self.text_buffer = ""

    async def _queue_sentence(self, text: str):
        was_empty = self._synthesis_queue.empty() and not self._is_synthesizing
        await self._synthesis_queue.put(text)

        if was_empty and not self._is_speaking:
            self._is_speaking = True
            await self.event_bus.emit(Event(
                type=EventType.TTS_STARTED,
                source="tts"
            ))

    # ---------------- INTERRUPT ---------------- #

    @event_handler(EventType.INTERRUPT, priority=EventPriority.HIGH.value)
    async def on_interrupt(self, event: Event):
        self.logger.info("🛑 TTS interrupted")

        self.text_buffer = ""
        self._audio_processor.reset()

        while not self._synthesis_queue.empty():
            try:
                self._synthesis_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

        if self.stream:
            self.stream.stop()

        self._is_synthesizing = False

        if self._is_speaking:
            self._is_speaking = False
            await self.event_bus.emit(Event(
                type=EventType.TTS_COMPLETE,
                source="tts"
            ))

    # ---------------- WORKER ---------------- #

    async def _run(self):
        self._synthesis_worker_task = asyncio.create_task(self._synthesis_worker())
        await self._synthesis_worker_task

    async def _synthesis_worker(self):
        while self._running:
            try:
                text = await asyncio.wait_for(self._synthesis_queue.get(), timeout=0.1)
                await self._synthesize_text(text)

                if self._synthesis_queue.empty() and self._is_speaking:
                    self._is_speaking = False
                    await self.event_bus.emit(Event(
                        type=EventType.TTS_COMPLETE,
                        source="tts"
                    ))

            except asyncio.TimeoutError:
                continue

    async def _synthesize_text(self, text: str):
        if self._is_synthesizing:
            return

        self._is_synthesizing = True
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._blocking_synthesis, text)
        finally:
            self._is_synthesizing = False

    def _blocking_synthesis(self, text: str):
        self.stream.feed(text)
        self.stream.play(
            on_audio_chunk=self._on_audio_chunk,
            muted=False,
            log_synthesized_text=False,
        )

    # ---------------- AUDIO CALLBACK ---------------- #

    def _on_audio_chunk(self, chunk: bytes):
        if not self._event_loop or self._event_loop.is_closed():
            return

        asyncio.run_coroutine_threadsafe(
            self._emit_audio_chunk(chunk),
            self._event_loop,
        )

    async def _emit_audio_chunk(self, chunk: bytes):
        try:
            frames = self._audio_processor.process(chunk)
            for frame in frames:
                await self.event_bus.emit(Event(
                    type=EventType.TTS_AUDIO_CHUNK,
                    data={"audio": frame},
                    source="tts"
                ))
        except Exception as e:
            self.logger.error(f"Audio processing error: {e}", exc_info=True)

    # ---------------- CLEANUP ---------------- #

    async def _cleanup(self):
        self._running = False
        self._audio_processor.reset()

        if self._synthesis_worker_task:
            self._synthesis_worker_task.cancel()
            try:
                await self._synthesis_worker_task
            except asyncio.CancelledError:
                pass

        if self.stream:
            self.stream.stop()

        if self.engine:
            self.engine.shutdown()

        self.logger.info("TTS cleanup complete")
