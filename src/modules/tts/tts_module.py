# modules/speech/tts_module.py
import asyncio
import re
from RealtimeTTS import TextToAudioStream, AzureEngine, ElevenlabsEngine
from events import EventType, event_handler, Event, EventPriority
from modules.base import BaseModule

class TTSModule(BaseModule):
    def __init__(self, event_bus, module_manager, config):
        super().__init__("tts", event_bus, module_manager, config)
        
        self.text_buffer = ""
        self.sentence_pattern = re.compile(r'[.!?]+\s+')
        
        # Azure TTS engine
        self.engine = None
        self.stream = None
        
        # Queue for sequential playback
        self._synthesis_queue = asyncio.Queue()
        self._synthesis_worker_task = None
        self._is_synthesizing = False
        self._event_loop = None

        self._is_speaking = False
    
    async def _setup(self):
        """Initialize Azure TTS engine"""
        try:
            self._event_loop = asyncio.get_event_loop()

            # Validate config
            speech_key = self.config.get('azure_speech_key')
            speech_region = self.config.get('azure_speech_region')
            
            if not speech_key or 'your-azure' in speech_key.lower():
                raise ValueError(
                    "❌ Azure Speech Key not configured!\n"
                    "Get your key from: https://portal.azure.com\n"
                    "Create a Speech Service resource, then set:\n"
                    "  azure_speech_key = 'YOUR_KEY_HERE'\n"
                    "  azure_speech_region = 'YOUR_REGION' (e.g., 'eastus')"
                )
            
            self.logger.info(f"Initializing Azure TTS (region: {speech_region})")
            
            # Create Azure engine
            self.engine = AzureEngine(
                speech_key=speech_key,
                service_region=speech_region,
                voice=self.config.get('voice', 'en-US-AriaNeural'),
                pitch=25,
                audio_format='riff-48khz-16bit-mono-pcm'
            )
            
            # self.engine = ElevenlabsEngine(api_key="sk_735e71b569a3d3c5b934450216b892f436200bad98e628d7",
            #                                id="6nSuAMirWdAYpq0GlSTA", model="eleven_v3")
            
            # Create stream with muted=True (we handle playback via chunks)
            self.stream = TextToAudioStream(
                self.engine,
                muted=False,
            )
            
            self.logger.info(f"✓ Azure TTS ready (voice: {self.config.get('voice')})")
            
        except Exception as e:
            self.logger.error(f"❌ Failed to initialize Azure TTS: {e}", exc_info=True)
            raise
    
    @event_handler(EventType.LLM_TEXT_CHUNK)
    async def on_text_chunk(self, event: Event):
        """Buffer and process text chunks"""
        text = event.data.get("text", "")
        self.text_buffer += text
        
        # Check for complete sentences
        sentences = self.sentence_pattern.split(self.text_buffer)
        
        if len(sentences) > 1:
            # Queue all complete sentences
            for sentence in sentences[:-1]:
                cleaned = sentence.strip()
                if cleaned:
                    await self._queue_sentence(cleaned)
            
            # Keep incomplete sentence in buffer
            self.text_buffer = sentences[-1]
    
    @event_handler(EventType.LLM_GENERATION_COMPLETE)
    async def on_generation_complete(self, event: Event):
        """Process any remaining buffered text"""
        if self.text_buffer.strip():
            await self._synthesis_queue.put(self.text_buffer.strip())
            self.text_buffer = ""

    async def _queue_sentence(self, text: str):
        """
        Queue a sentence for synthesis.
        Emits TTS_STARTED on first sentence if not already speaking.
        """
        # If queue was empty and we're not speaking, we're about to start
        was_empty = self._synthesis_queue.empty() and not self._is_synthesizing
        
        # Add to queue
        await self._synthesis_queue.put(text)
        
        # Emit TTS_STARTED only when starting fresh
        if was_empty and not self._is_speaking:
            self._is_speaking = True
            self.logger.info("🎤 TTS Started (queue was empty)")
            await self.event_bus.emit(Event(
                type=EventType.TTS_STARTED,
                source="tts"
            ))
    
    @event_handler(EventType.INTERRUPT, priority=EventPriority.HIGH.value)
    async def on_interrupt(self, event: Event):
        """Stop current TTS playback immediately"""
        self.logger.info("🛑 TTS interrupted")
        
        # Clear buffer
        self.text_buffer = ""
        
        # Clear queue
        while not self._synthesis_queue.empty():
            try:
                self._synthesis_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        
        # Stop stream immediately
        if self.stream:
            self.stream.stop()
        
        self._is_synthesizing = False
        
        # Mark as no longer speaking
        if self._is_speaking:
            self._is_speaking = False
       
            await self.event_bus.emit(Event(
                type=EventType.TTS_COMPLETE,
                source="tts"
            ))
    
    async def _run(self):
        """Start synthesis worker"""
        self._synthesis_worker_task = asyncio.create_task(self._synthesis_worker())
        
        try:
            await self._synthesis_worker_task
        except asyncio.CancelledError:
            self.logger.info("TTS module cancelled")
            raise
    
    async def _synthesis_worker(self):
        """
        Worker that processes TTS queue sequentially.
        Emits TTS_COMPLETE when queue is empty.
        """
        self.logger.info("TTS synthesis worker started")
        
        try:
            while self._running:
                try:
                    # Get next text with timeout
                    text = await asyncio.wait_for(
                        self._synthesis_queue.get(),
                        timeout=0.1
                    )
                    
                    # Synthesize this text (blocks until complete)
                    await self._synthesize_text(text)
                    
                    # Check if queue is now empty
                    if self._synthesis_queue.empty():
                        # All done speaking!
                        if self._is_speaking:
                            self._is_speaking = False
                            self.logger.info("✅ TTS Complete (queue empty)")
                            await self.event_bus.emit(Event(
                                type=EventType.TTS_COMPLETE,
                                source="tts"
                            ))
                    
                except asyncio.TimeoutError:
                    continue
                    
        except asyncio.CancelledError:
            self.logger.info("TTS worker cancelled")
            raise
        except Exception as e:
            self.logger.error(f"Error in TTS worker: {e}", exc_info=True)
        finally:
            self.logger.info("TTS worker stopped")
    
    async def _synthesize_text(self, text: str):
        """Synthesize a single text segment (no events here)"""
        if self._is_synthesizing:
            self.logger.warning("Already synthesizing, skipping")
            return
        
        self._is_synthesizing = True
        
        try:
            self.logger.debug(f"🎤 Synthesizing: {text[:50]}...")
            
            # Run synthesis in executor
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                self._blocking_synthesis,
                text
            )
            
            self.logger.debug(f"✓ Synthesis complete")
            
        except Exception as e:
            self.logger.error(f"❌ Synthesis error: {e}", exc_info=True)
            
            await self.event_bus.emit(Event(
                type=EventType.TTS_ERROR,
                data={'text': text, 'error': str(e)},
                source="tts"
            ))
        finally:
            self._is_synthesizing = False
    
    def _blocking_synthesis(self, text: str):
        """Blocking synthesis (runs in executor)"""
        try:
            self.stream.feed(text)
            self.stream.play(
                on_audio_chunk=self._on_audio_chunk,
                muted=False,
                log_synthesized_text=False
            )
        except Exception as e:
            self.logger.error(f"Blocking synthesis error: {e}")
            raise
    
    def _on_audio_chunk(self, chunk: bytes):
        """Callback from RealtimeTTS (runs in RealtimeTTS thread)"""
        if not self._event_loop or self._event_loop.is_closed():
            self.logger.error("Event loop not available for audio callback")
            return
        
        try:
            asyncio.run_coroutine_threadsafe(
                self._emit_audio_chunk(chunk),
                self._event_loop
            )
        except Exception as e:
            self.logger.error(f"Error in audio chunk callback: {e}")
    
    async def _emit_audio_chunk(self, chunk: bytes):
        """Emit audio chunk event"""
        try:
            await self.event_bus.emit(Event(
                type=EventType.TTS_AUDIO_CHUNK,
                data={"audio": chunk},
                source="tts"
            ))
        except Exception as e:
            self.logger.error(f"Error emitting audio chunk: {e}")
    
    async def _cleanup(self):
        """Cleanup TTS resources"""
        self.logger.info("Cleaning up TTS module")
        
        self._running = False
        
        if self._synthesis_worker_task and not self._synthesis_worker_task.done():
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