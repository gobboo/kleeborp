# main.py
import asyncio
from core.application import Application
from core.config import Config
from utils.logger import setup_logging


async def main():
    setup_logging(level="INFO")

    config = Config("config.toml")
    app = Application(config)

    try:
        await app.start()
    finally:
        # 🔥 This ALWAYS runs, even on Ctrl+C
        await app.shutdown()

if __name__ == "__main__":
    asyncio.run(main())