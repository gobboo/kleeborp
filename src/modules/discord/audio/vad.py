# modules/discord/audio/shared_vad.py
import torch


class SharedVAD:
    """Singleton VAD model shared across all user inputs"""

    _instance = None
    _model = None

    @classmethod
    def get_model(cls):
        if cls._model is None:
            cls._model, _ = torch.hub.load(
                repo_or_dir="snakers4/silero-vad",
                model="silero_vad",
                force_reload=False,
            )

        return cls._model
