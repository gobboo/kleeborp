import asyncio
import logging
from queue import Empty, Queue
from events import event_handler, EventType, Event
from modules.base import BaseModule
from azure.cognitiveservices.speech import (
    SpeechSynthesizer,
    SpeechConfig,
    audio,
    ResultReason,
    CancellationReason,
    SpeechSynthesisOutputFormat,
)


class PushAudioOutputStreamSampleCallback(audio.PushAudioOutputStreamCallback):
    """
    Push audio callback that receives synthesized audio chunks.
    One instance == one TTS generation.
    """

    def __init__(self, generation_id: int) -> None:
        super().__init__()
        self.generation_id = generation_id

        self.logger = logging.getLogger(__name__)
        self._frame_buffer = bytes()
        self.audio_queue = Queue()
        self._closed = False

        self.logger.info(
            "Audio callback created for generation %d", generation_id
        )

    def write(self, audio_buffer: memoryview) -> int:
        if self._closed:
            return 0

        self._frame_buffer += audio_buffer

        while len(self._frame_buffer) >= 1920:
            mono = self._frame_buffer[:1920]
            self._frame_buffer = self._frame_buffer[1920:]

            stereo = self._convert_to_stereo(mono)
            self.audio_queue.put((self.generation_id, stereo))

        return audio_buffer.nbytes

    def _convert_to_stereo(self, pcm: bytes) -> bytes:
        stereo = bytearray(len(pcm) * 2)
        j = 0
        for i in range(0, len(pcm), 2):
            sample = pcm[i:i + 2]
            stereo[j:j + 2] = sample
            stereo[j + 2:j + 4] = sample
            j += 4
        return bytes(stereo)

    def close(self) -> None:
        if self._closed:
            return

        self._closed = True
        self.audio_queue.put((self.generation_id, None))

        self.logger.info(
            "Audio callback closed for generation %d", self.generation_id
        )


class TTSModule(BaseModule):
    def __init__(self, event_bus, module_manager, config=None):
        super().__init__('tts', event_bus, module_manager, config)

        self.logger.info("Initializing TTS module")

        self._tts_generation = 0
        self.tts_task = None
        self.loop = None

        self.speech_config = SpeechConfig(
            subscription=self.config["speech_key"],
            endpoint=self.config["speech_endpoint"],
        )
        self.speech_config.speech_synthesis_voice_name = self.config["voice"]
        self.speech_config.set_speech_synthesis_output_format(
            SpeechSynthesisOutputFormat.Raw48Khz16BitMonoPcm
        )

        self.callback: PushAudioOutputStreamSampleCallback | None = None

        self.logger.info(
            "TTS module initialized with voice '%s'", self.config["voice"]
        )

    @event_handler(EventType.LLM_GENERATION_COMPLETE)
    async def on_llm_completion(self, event: Event):
        self._tts_generation += 1
        generation = self._tts_generation

        text = event.data["message"]

        # Cancel previous generation
        if self.tts_task and not self.tts_task.done():
            self.logger.info("Cancelling previous TTS generation")
            self.tts_task.cancel()
            await self.event_bus.emit(
                Event(
                    EventType.TTS_CANCELLED,
                    data={"generation_id": generation - 1},
                )
            )

        old_callback = self.callback
        self.callback = PushAudioOutputStreamSampleCallback(generation)

        if old_callback:
            old_callback.close()

        await self.event_bus.emit(
            Event(
                EventType.TTS_STARTED,
                data={"generation_id": generation},
            )
        )

        self.tts_task = self.loop.run_in_executor(
            None,
            self._create_tts_stream,
            generation,
            text,
        )


    def _create_tts_stream(self, generation: int, text: str):
        self.logger.info("Starting TTS synthesis (gen=%d)", generation)

        callback = self.callback
        synthesizer = None

        try:
            stream = audio.PushAudioOutputStream(callback)
            audio_config = audio.AudioOutputConfig(stream=stream)

            synthesizer = SpeechSynthesizer(
                speech_config=self.speech_config,
                audio_config=audio_config,
            )

            ssml = f"""
<speak version="1.0"
       xmlns="http://www.w3.org/2001/10/synthesis"
       xmlns:mstts="https://www.w3.org/2001/mstts"
       xml:lang="en-US">
    <voice name="{self.config["voice"]}">
        <prosody pitch="25%">
            {text}
        </prosody>
    </voice>
</speak>
"""

            result = synthesizer.speak_ssml_async(ssml).get()

            if result.reason == ResultReason.SynthesizingAudioCompleted:
                self.logger.info("TTS synthesis completed (gen=%d)", generation)
            elif result.reason == ResultReason.Canceled:
                details = result.cancellation_details
                self.logger.info(
                    "TTS synthesis cancelled (gen=%d, reason=%s)",
                    generation,
                    details.reason,
                )

        except asyncio.CancelledError:
            self.logger.info("TTS executor cancelled (gen=%d)", generation)

        except Exception:
            self.logger.exception("Unhandled TTS error (gen=%d)", generation)

        finally:
            # Stop Azure first to prevent late writes
            if synthesizer:
                try:
                    synthesizer.stop_speaking_async().get()
                except Exception:
                    pass

            # Only close if this is still the active generation
            if callback and callback is self.callback:
                callback.close()

            self.logger.info("TTS stream finalized (gen=%d)", generation)

    async def _run(self):
        self.logger.info("TTS run loop started")

        while self._running:
            callback = self.callback
            if not callback:
                await asyncio.sleep(0)
                continue

            try:
                generation_id, chunk = await asyncio.to_thread(
                    callback.audio_queue.get, False
                )

                # Drop stale audio
                if generation_id != self._tts_generation:
                    continue

                if chunk is None:
                    self.logger.info("TTS exhausted (gen=%d)", generation_id)
                    await self.event_bus.emit(
                        Event(
                            EventType.TTS_EXHAUSTED,
                            data={"generation_id": generation_id},
                        )
                    )

                    continue

                await self.event_bus.emit(
                    Event(
                        EventType.TTS_AUDIO_CHUNK,
                        data={
                            "generation_id": generation_id,
                            "audio": chunk,
                        },
                    )
                )

            except Empty:
                continue

    async def _cleanup(self):
        self.logger.info("Cleaning up TTS module")

        self._running = False

        if self.callback:
            self.callback.close()
            self.callback = None

    async def _setup(self):
        self.loop = asyncio.get_event_loop()
        self.logger.info("TTS module setup complete")
