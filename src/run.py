# main.py
import asyncio
from core.application import Application
from core.config import Config
from utils.logger import setup_logging


async def main():
    setup_logging(level="DEBUG")

    config = Config("config.toml")
    app = Application(config)

    await app.start()


if __name__ == "__main__":
    asyncio.run(main())
