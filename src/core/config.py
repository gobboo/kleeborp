# core/config.py
import tomllib  # Python 3.11+

# OR: import tomli as tomllib  # For Python 3.6-3.10
from pathlib import Path
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)


class Config:
    def __init__(self, config_path: str = "config.toml"):
        self.config_path = Path(config_path)
        self._config: Dict[str, Any] = {}

        self.load()

    def load(self):
        """Load configuration from TOML file"""
        if not self.config_path.exists():
            logger.warning(f"Config file not found: {self.config_path}")

            self._config = self._get_defaults()

            return

        with open(self.config_path, "rb") as f:
            self._config = tomllib.load(f)

        logger.info(f"Loaded config from {self.config_path}")

    def get(self, key: str, default=None):
        """Get config value with dot notation: config.get('llm.model')"""
        keys = key.split(".")
        value = self._config

        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)

                if value is None:
                    return default
            else:
                return default

        return value

    def get_section(self, section: str) -> Dict[str, Any]:
        """Get entire config section"""
        return self._config.get(section, {})

    def _get_defaults(self) -> Dict[str, Any]:
        """Default configuration"""
        return {
            "llm": {
                "model": "gpt-4-turbo-preview",
                "temperature": 0.7,
                "max_tokens": 4096,
            },
            "websocket": {"host": "localhost", "port": 8765},
            "logging": {"level": "INFO"},
        }

    @property
    def raw(self) -> Dict[str, Any]:
        """Get raw config dict"""
        return self._config
