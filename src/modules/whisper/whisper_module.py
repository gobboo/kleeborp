import asyncio
from concurrent.futures import ThreadPoolExecutor
import logging
import time

from faster_whisper import WhisperModel
import numpy as np
import torch
import torchaudio
from events import EventType, Event, event_handler
from modules.base import BaseModule
from utils.audio_debug import save_audio_for_debugging

logger = logging.getLogger(__name__)

RESAMPLER = torchaudio.transforms.Resample(orig_freq=48_000, new_freq=16_000)


class WhisperModule(BaseModule):
    def __init__(self, event_bus, module_manager, config=None):
        super().__init__("whisper", event_bus, module_manager, config)

        self._stt_queue = asyncio.Queue()

        self._model = WhisperModel(
            model_size_or_path=config.get("model", "distil-large-v3.5"),
            device="cuda",
            compute_type="float16",
            num_workers=config.get("num_workers", 5),
        )

        self._executor = ThreadPoolExecutor(max_workers=config.get("num_workers", 5))

    @event_handler(EventType.TRANSCRIPTION_REQUEST)
    async def on_transcription_request(self, event: Event):
        await self._stt_queue.put(event.data)

    async def _run(self):
        tasks = []
        try:
            while self._running:
                job = await self._stt_queue.get()
                task = asyncio.create_task(self._transcribe_job(job))
                tasks.append(task)

                # Clean up completed tasks
                tasks = [t for t in tasks if not t.done()]
        except asyncio.CancelledError:
            # Wait for pending transcriptions
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            raise

    async def _transcribe_job(self, job):
        try:
            logger.debug("got transcription job, transcribing...")
            audio_data = job.get("audio_data")

            if not audio_data:
                logger.warning("got transcribe job with no audio data")
                return

            user_name = job.get("user_name", "unknown")
            # debug_path = f"debug_audio_{user_name}_{int(time.time())}.wav"
            # save_audio_for_debugging(
            #     audio_data,
            #     sample_rate=48000,
            #     channels=2,
            #     output_path=debug_path
            # )

            loop = asyncio.get_running_loop()
            segments = await loop.run_in_executor(
                self._executor, self._blocking_transcribe, audio_data
            )
            
            self.logger.info(segments)
            
            text = " ".join(
                segment.text
                for segment in segments
                if segment.no_speech_prob < 0.1  # More lenient threshold
            ).strip()

            if not text:
                logger.debug(f"No speech detected for {user_name}")
                return

            logger.info(f"Transcribed ({user_name}): {text}")

            await self.event_bus.emit(
                Event(
                    type=EventType.TRANSCRIPTION_COMPLETE,
                    data={
                        "user_name": user_name,
                        "user_id": job.get("user_id"),
                        "transcription": text,
                    },
                    source="whisper",
                )
            )

        except Exception as e:
            logger.error(f"Transcription job failed: {e}", exc_info=True)

    def _pcm48k_to_whisper(self, audio_bytes: bytes) -> np.ndarray:
        # Discord sends stereo interleaved: LRLRLRLR...
        audio = np.frombuffer(audio_bytes, dtype=np.int16)

        # Reshape to (frames, 2) for stereo
        audio = audio.reshape(-1, 2)

        # Convert to mono by averaging channels
        audio = audio.mean(axis=1)

        # Normalize to float32 [-1, 1]
        audio = audio.astype(np.float32) / 32768.0

        # Resample 48kHz → 16kHz
        audio_tensor = torch.from_numpy(audio)
        audio_resampled = RESAMPLER(audio_tensor)

        return audio_resampled.numpy()

    def _blocking_transcribe(self, audio_data: bytes):
        if len(audio_data) < 3200:  # Less than ~0.1s of audio
            logger.warning("Audio too short, skipping")
            return []

        audio = self._pcm48k_to_whisper(audio_data)

        logger.debug("attempting to transcribe audio data")

        segments, _ = self._model.transcribe(
            audio,
            language="en",
            vad_filter=True,  # you already did VAD
            beam_size=5,
            condition_on_previous_text=False,
            initial_prompt=(
                "The following conversation mentions a character named Kleeborp. "
                "Kleeborp is spelled K-L-E-E-B-O-R-P."
            ),
        )

        logger.debug("audio transcribed")

        return list(segments)

    async def _setup(self):
        return await super()._setup()

    async def _cleanup(self):
        self._running = False

        # Shutdown executor
        self._executor.shutdown(wait=True)
        logger.info("Whisper executor shut down")
