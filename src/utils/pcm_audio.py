import discord
import queue
import numpy as np

FRAME_SIZE = 3840  # 20ms of 48kHz stereo s16le

class StreamingPCMSource(discord.AudioSource):
    def __init__(self):
        self.queue = queue.Queue()
        self.eof = False
        self.closed = False

    def write(self, pcm: bytes):
        if not self.closed:
            self.queue.put(pcm)

    def mark_eof(self):
        self.eof = True

    def close(self):
        self.closed = True

    def reset(self):
        while not self.queue.empty():
            self.queue.get_nowait()

        self.eof = False
        self.closed = False

    def read(self) -> bytes:
        if self.closed:
            return b""

        try:
            return self.queue.get_nowait()
        except queue.Empty:
            print("queue is empty: eof: ", self.eof)
            if self.eof:
                return b""  # triggers discord after-callback

            return b"\x00" * 3840  # silence while waiting



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
