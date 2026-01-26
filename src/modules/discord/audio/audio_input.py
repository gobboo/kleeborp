# modules/discord/audio/input_handler.py
import asyncio
import logging
import torch
import numpy as np
import time
import wave
import os

from datetime import datetime
from typing import Optional

import torchaudio
from core.event_bus import EventBus
from modules.discord.audio.vad import SharedVAD
from events import Event, EventType, EventPriority

logger = logging.getLogger(__name__)

RESAMPLER = torchaudio.transforms.Resample(orig_freq=48_000, new_freq=16_000)

# ==========================
# Debug audio dumping config
# ==========================
DEBUG_AUDIO_DUMP = True
DEBUG_AUDIO_DIR = "debug_audio"


class UserAudioInput:
    """
    Handles audio input for a single Discord user.
    Uses Silero VAD directly without wrapper.
    """

    def __init__(
        self,
        user_id: int,
        user_name: str,
        event_bus: EventBus,
        vad_threshold: float = 0.25,
        silence_duration: float = 1,
    ):
        self.user_id = user_id
        self.user_name = user_name
        self.event_bus = event_bus
        self.silence_duration = silence_duration
        self.vad_threshold = vad_threshold

        # Audio queue
        self.audio_queue = asyncio.Queue()

        # Load Silero VAD model
        logger.debug(f"Loading VAD model for {user_name}")
        self.vad_model = SharedVAD.get_model()
        self.vad_buffer = torch.zeros(0)

        self.resampler = RESAMPLER

        # State
        self.is_speaking = False
        self.speech_buffer = []
        self.last_speech_time = 0
        self.silence_start_time = None

        # Debug
        self._debug_dumped_vad = False

        # Control
        self._running = False
        self._task: Optional[asyncio.Task] = None

        logger.info(f"Created audio input handler for {user_name}")

    # ==========================
    # Debug helpers
    # ==========================
    def _ensure_debug_dir(self):
        if not os.path.exists(DEBUG_AUDIO_DIR):
            os.makedirs(DEBUG_AUDIO_DIR, exist_ok=True)

    def _write_wav(
        self,
        filename: str,
        pcm_bytes: bytes,
        sample_rate: int,
        channels: int,
        sample_width: int,
    ):
        self._ensure_debug_dir()
        path = os.path.join(DEBUG_AUDIO_DIR, filename)

        with wave.open(path, "wb") as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(sample_width)
            wf.setframerate(sample_rate)
            wf.writeframes(pcm_bytes)

        logger.info(f"[AUDIO DEBUG] Wrote {path}")

    # ==========================
    # VAD logic
    # ==========================
    def _is_speech(self, audio_chunk: bytes, dump_debug: bool = False) -> bool:
        # int16 PCM
        audio = np.frombuffer(audio_chunk, dtype=np.int16)

        # Discord sends INTERLEAVED stereo
        if audio.size % 2 != 0:
            return False  # corrupt frame, extremely rare

        audio = audio.reshape(-1, 2)  # (samples, channels)

        # Stereo → mono
        audio = audio.mean(axis=1)

        # Normalize to float32 [-1, 1]
        audio = audio.astype(np.float32) / 32768.0

        # Torch tensor (shape: [samples])
        audio = torch.from_numpy(audio)

        audio = audio.contiguous()

        audio = self.resampler(audio)

        # Dump post-resample VAD input ONCE per utterance
        if (
            dump_debug
            and DEBUG_AUDIO_DUMP
            and not self._debug_dumped_vad
            and audio.numel() >= 16000 // 4  # ~250ms of audio
            ):
            vad_view = torch.cat([self.vad_buffer, audio])

            pcm16 = (vad_view.clamp(-1, 1) * 32767).short().cpu().numpy().tobytes()

            ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")

            self._write_wav(
                filename=f"{self.user_name}_{ts}_vad_input.wav",
                pcm_bytes=pcm16,
                sample_rate=16000,
                channels=1,
                sample_width=2,
            )

            self._debug_dumped_vad = True

        # Append to VAD buffer
        self.vad_buffer = torch.cat([self.vad_buffer, audio])

        speech_detected = False

        # Process EXACT 512-sample frames
        while self.vad_buffer.numel() >= 512:
            frame = self.vad_buffer[:512]
            self.vad_buffer = self.vad_buffer[512:]

            with torch.no_grad():
                prob = self.vad_model(frame, 16000).item()

            if prob >= self.vad_threshold:
                speech_detected = True

        return speech_detected

    # ==========================
    # Lifecycle
    # ==========================
    async def start(self):
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._process_audio())
        logger.info(f"Started audio processing for {self.user_name}")

    async def stop(self):
        if not self._running:
            return

        logger.info(f"Stopping audio processing for {self.user_name}")
        self._running = False

        if self.is_speaking and self.speech_buffer:
            await self._emit_transcription_request()

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        logger.info(f"Stopped audio processing for {self.user_name}")

    def queue_audio(self, audio_data: bytes):
        try:
            self.audio_queue.put_nowait(audio_data)
        except asyncio.QueueFull:
            logger.warning(f"Audio queue full for {self.user_name}, dropping packet")

    # ==========================
    # Main loop
    # ==========================
    async def _process_audio(self):
        speaking_emit_interval = 0.1
        last_speaking_emit = 0

        try:
            while self._running:
                try:
                    audio_chunk = await asyncio.wait_for(
                        self.audio_queue.get(), timeout=0.1
                    )

                    is_speech = self._is_speech(
                        audio_chunk,
                        dump_debug=not self.is_speaking,
                    )

                    current_time = time.time()

                    if is_speech:
                        if not self.is_speaking:
                            logger.debug(f"{self.user_name} started speaking")
                            self.is_speaking = True
                            self.speech_buffer = []
                            self.silence_start_time = None
                            self._debug_dumped_vad = False

                            await self.event_bus.emit(
                                Event(
                                    type=EventType.USER_SPEAKING_STARTED,
                                    data={
                                        "user_id": self.user_id,
                                        "user_name": self.user_name,
                                    },
                                    source="audio_input",
                                    priority=EventPriority.HIGH.value,
                                )
                            )

                        self.speech_buffer.append(audio_chunk)
                        self.last_speech_time = current_time
                        self.silence_start_time = None

                        if current_time - last_speaking_emit >= speaking_emit_interval:
                            await self.event_bus.emit(
                                Event(
                                    type=EventType.USER_SPEAKING,
                                    data={
                                        "user_id": self.user_id,
                                        "user_name": self.user_name,
                                        "duration": len(self.speech_buffer) * 0.02,
                                    },
                                    source="audio_input",
                                    priority=EventPriority.HIGH.value,
                                )
                            )
                            last_speaking_emit = current_time

                    else:
                        if self.is_speaking:
                            self.speech_buffer.append(audio_chunk)

                            if self.silence_start_time is None:
                                self.silence_start_time = current_time

                            if (
                                current_time - self.silence_start_time
                                >= self.silence_duration
                            ):
                                logger.debug(f"{self.user_name} stopped speaking")
                                await self._emit_transcription_request()
                                self.is_speaking = False
                                self.speech_buffer = []
                                self.silence_start_time = None

                except asyncio.TimeoutError:
                    if self.is_speaking:
                        current_time = time.time()
                        if self.silence_start_time is None:
                            self.silence_start_time = current_time

                        if (
                            current_time - self.silence_start_time
                            >= self.silence_duration
                        ):
                            logger.debug(f"{self.user_name} stopped (timeout)")
                            await self._emit_transcription_request()
                            self.is_speaking = False
                            self.speech_buffer = []
                            self.silence_start_time = None

        except asyncio.CancelledError:
            logger.info(f"Audio processing cancelled for {self.user_name}")
            raise
        except Exception as e:
            logger.error(f"Error processing audio: {e}", exc_info=True)

    # ==========================
    # Transcription emit
    # ==========================
    async def _emit_transcription_request(self):
        if not self.speech_buffer:
            return

        combined_audio = b"".join(self.speech_buffer)

        # Dump RAW Discord audio
        if DEBUG_AUDIO_DUMP:
            ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
            self._write_wav(
                filename=f"{self.user_name}_{ts}_raw.wav",
                pcm_bytes=combined_audio,
                sample_rate=48000,
                channels=2,
                sample_width=2,
            )

        logger.info(
            f"Transcription request for {self.user_name} ({len(combined_audio)} bytes)"
        )

        await self.event_bus.emit(
            Event(
                type=EventType.TRANSCRIPTION_REQUEST,
                data={
                    "user_id": self.user_id,
                    "user_name": self.user_name,
                    "audio_data": combined_audio,
                    "sample_rate": 48000,
                    "channels": 2,
                    "sample_width": 2,
                },
                source="audio_input",
            )
        )

        await self.event_bus.emit(
            Event(
                type=EventType.USER_SPEAKING_STOPPED,
                data={
                    "user_id": self.user_id,
                    "user_name": self.user_name,
                },
                source="audio_input",
            )
        )
