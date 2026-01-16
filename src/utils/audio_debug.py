# utils/audio_debug.py
import numpy as np
import soundfile as sf
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


def save_audio_for_debugging(
    audio_bytes: bytes,
    sample_rate: int = 48000,
    channels: int = 2,
    output_path: str = "debug_audio.wav",
):
    """
    Save Discord audio to WAV file for debugging.

    Args:
        audio_bytes: Raw PCM bytes from Discord
        sample_rate: Sample rate (48000 for Discord)
        channels: Number of channels (2 for stereo)
        output_path: Where to save the file
    """
    try:
        # Convert bytes to int16 array
        audio = np.frombuffer(audio_bytes, dtype=np.int16)

        # Reshape for stereo
        if channels == 2:
            audio = audio.reshape(-1, 2)

        # Normalize to float32
        audio_float = audio.astype(np.float32) / 32768.0

        # Save as WAV
        sf.write(output_path, audio_float, sample_rate)

        logger.info(f"Saved audio to {output_path}")
        logger.info(f"Duration: {len(audio) / (sample_rate * channels):.2f}s")
        logger.info(f"Shape: {audio_float.shape}")

    except Exception as e:
        logger.error(f"Failed to save audio: {e}", exc_info=True)


def play_audio(audio_path: str):
    """
    Play audio file (requires sounddevice).

    Install: uv add sounddevice
    """
    try:
        import sounddevice as sd

        audio, sample_rate = sf.read(audio_path)
        sd.play(audio, sample_rate)
        sd.wait()

    except ImportError:
        logger.error("sounddevice not installed. Install with: uv add sounddevice")
    except Exception as e:
        logger.error(f"Failed to play audio: {e}", exc_info=True)
