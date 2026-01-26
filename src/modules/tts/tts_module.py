import asyncio
import logging
from queue import Empty, Queue
from events import event_handler, EventType, Event
from modules.base import BaseModule
from azure.cognitiveservices.speech import SpeechSynthesizer, SpeechConfig, audio, ResultReason, CancellationReason, SpeechSynthesisRequestInputType, SpeechSynthesisOutputFormat, SpeechSynthesisRequest

class PushAudioOutputStreamSampleCallback(audio.PushAudioOutputStreamCallback):
    """
    Example class that implements the PushAudioOutputStreamCallback, which is used to show
    how to push output audio to a stream
    """
    def __init__(self) -> None:
        super().__init__()
        
        self.logger = logging.getLogger(__name__)
        self._audio_data = bytes(0)
        self._frame_buffer = bytes(0)
        self.audio_queue = Queue()
        self._closed = False

    def write(self, audio_buffer: memoryview) -> int:
        """
        The callback function which is invoked when the synthesizer has an output audio chunk
        to write out
        """
        self._audio_data += audio_buffer
        self._frame_buffer += audio_buffer
        
        while len(self._frame_buffer) >= 1920:
            # take the first 1920 bytes
            mono_bytes = self._frame_buffer[0:1920]

            stereo_bytes = self._convert_to_stereo(mono_bytes)
            self.audio_queue.put(stereo_bytes)

            self._frame_buffer = self._frame_buffer[1920:]
        
        return audio_buffer.nbytes
    
    def _convert_to_stereo(self, pcm: bytes):
        stereo = bytearray(len(pcm) * 2)

        j = 0
        for i in range(0, len(pcm), 2):
            sample = pcm[i:i+2]
            stereo[j:j+2] = sample      # Left
            stereo[j+2:j+4] = sample    # Right
            j += 4

        return bytes(stereo)

    def close(self) -> None:
        """
        The callback function which is invoked when the synthesizer is about to close the
        stream.
        """
        self.audio_queue.put(None)
        self._closed = True

    def get_audio_data(self) -> bytes:
        return self._audio_data

    def get_audio_size(self) -> int:
        return len(self._audio_data)

class TTSModule(BaseModule):
    def __init__(self, event_bus, module_manager, config = None):
        super().__init__('tts', event_bus, module_manager, config)

        self.speech_config = SpeechConfig(
            subscription=self.config["speech_key"],
            endpoint=self.config["speech_endpoint"],
        )

        self.speech_config.speech_synthesis_voice_name=self.config["voice"]
        self.speech_config.set_speech_synthesis_output_format(SpeechSynthesisOutputFormat.Raw48Khz16BitMonoPcm)

        self.callback = PushAudioOutputStreamSampleCallback()

        self._is_speaking = False
        self.loop = None
    
    @event_handler(EventType.LLM_GENERATION_COMPLETE)
    async def on_llm_completion(self, event: Event):
        # we now have text "Hey hows it going blah blah blah"
        # So lets send a request to TTS and stream the output
        content = event.data["message"]

        await self.event_bus.emit(
            Event(EventType.TTS_STARTED)
        )
        
        self.loop.run_in_executor(None,
            self._create_tts_stream,
            content,
        )

    def _create_tts_stream(self, text: str):
        try:
            # here is where we create the AsyncIterator
            # we loop over the chunks and as we do we emit the audio chunks for
            # other modules to listen to
            if not self.callback:
              self.callback = PushAudioOutputStreamSampleCallback()

            stream = audio.PushAudioOutputStream(self.callback)
            audio_config = audio.AudioOutputConfig(stream=stream)

            synthesizer = SpeechSynthesizer(
                speech_config=self.speech_config,
                audio_config=audio_config
            )

            ssml_string = f"""
<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xmlns:mstts="https://www.w3.org/2001/mstts" xml:lang="en-US">
    <voice name="{self.config["voice"]}">
        <prosody pitch="25%">
            {text}
        </prosody>
    </voice>
</speak>
"""

            result = synthesizer.speak_ssml_async(ssml_string).get()

            if result.reason == ResultReason.SynthesizingAudioCompleted:
                self.logger.info("Speech synthesized for text [{}], and the audio was written to output stream.".format(text))
            elif result.reason == ResultReason.Canceled:
                cancellation_details = result.cancellation_details
                self.logger.info("Speech synthesis canceled: {}".format(cancellation_details.reason))
                if cancellation_details.reason == CancellationReason.Error:
                    self.logger.info("Error details: {}".format(cancellation_details.error_details))
            
            del result
            del synthesizer

            self.logger.info("successfully deleted result and synthesiser")
        except Exception as e:
            self.logger.error(e, exc_info=True)
            raise
        finally:
            self.logger.info("cleaning up tts")
            synthesizer.stop_speaking_async().get()

            self.callback.close()
            self.callback = None
            self.logger.info("cleaned up tts")
            

    async def _run(self):
        while self._running:
            try:
              chunk = await asyncio.to_thread(self.callback.audio_queue.get, False)

              if chunk is None:
                  await self.event_bus.emit(Event(
                      type=EventType.TTS_EXHAUSTED
                  ))

                  continue

              await self.event_bus.emit(
                  Event(EventType.TTS_AUDIO_CHUNK, data={"audio": chunk})
              )
            except Empty as e:
                continue
              
    
    async def _cleanup(self):
        self.logger.info("cleaning up tts")
        self._running = False
        self.callback.close()

    async def _setup(self):
        self.loop = asyncio.get_event_loop()