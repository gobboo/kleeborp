import discord
import queue
import numpy as np

FRAME_SIZE = 3840  # 20ms of 48kHz stereo s16le

class StreamingPCMSource(discord.AudioSource):
    def __init__(self):
        self.buffer = queue.Queue()
        self.closed = False

    def write(self, data: bytes):
        if not self.closed:
          self.buffer.put(data)

    def close(self):
        self.closed = True

    def read(self) -> bytes:
        # END CONDITION: no more data will ever arrive
        if self.closed and self.buffer.empty():
            return b""  # <-- THIS is what Discord waits for

        try:
            return self.buffer.get(timeout=0.02)
        except queue.Empty:
            # Stream still open but no data yet → return silence
            return b"\x00" * FRAME_SIZE

    def is_opus(self):
        return False



DISCORD_FRAME_BYTES = 3840  # 20ms @ 48kHz stereo s16le

class DiscordAudioProcessor:
    def __init__(self):
        self._buffer = bytearray()
        self._header_parsed = False
        self._pcm_offset = 0

    def reset(self):
        self._buffer.clear()
        self._header_parsed = False
        self._pcm_offset = 0

    def _strip_wav_header(self, data: bytes) -> bytes:
        """
        Strips RIFF/WAV header ONCE.
        Assumes PCM16 mono 48kHz afterwards.
        """
        if data[:4] != b"RIFF":
            return data  # already raw PCM

        # Find "data" chunk
        idx = data.find(b"data")
        if idx == -1:
            return b""  # incomplete header, drop

        data_start = idx + 8  # skip 'data' + size
        return data[data_start:]

    def process(self, chunk: bytes) -> list[bytes]:
        frames = []

        # ---- First chunk may contain WAV header ----
        if not self._header_parsed:
            chunk = self._strip_wav_header(chunk)
            if not chunk:
                return []
            self._header_parsed = True

        # ---- Mono → Stereo ----
        pcm = np.frombuffer(chunk, dtype=np.int16)
        stereo = np.repeat(pcm, 2)

        self._buffer.extend(stereo.tobytes())

        # ---- Emit exact Discord frames ----
        while len(self._buffer) >= DISCORD_FRAME_BYTES:
            frames.append(bytes(self._buffer[:DISCORD_FRAME_BYTES]))
            del self._buffer[:DISCORD_FRAME_BYTES]

        return frames
