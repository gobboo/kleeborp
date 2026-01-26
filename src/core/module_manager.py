# core/module_manager.py
from typing import Any, Dict, List, Optional
import asyncio
import logging

from modules.base import BaseModule

logger = logging.getLogger(__name__)


class ModuleManager:
    def __init__(self):
        self._modules: Dict[str, BaseModule] = {}

    def register(self, module: BaseModule):
        """Register a module"""
        self._modules[module.name] = module

        logger.info(f"Registered Module: {module.name}")

    async def initialize_all(self):
        """Initialize all modules"""
        logger.info("Initializing all modules")
        tasks = [module.initialize() for module in self._modules.values()]

        await asyncio.gather(*tasks)

    async def start_all(self):
        """Start all modules"""
        logger.info("Starting all modules")
        tasks = [module.start() for module in self._modules.values()]

        await asyncio.gather(*tasks)

    async def stop_all(self):
        """Stop all modules gracefully"""
        logger.info("Stopping all modules")
        tasks = [module.stop() for module in self._modules.values()]

        await asyncio.gather(*tasks, return_exceptions=True)

    async def get_prompt_fragments(self) -> str:
        """Collect prompt fragments from all modules"""
        fragments = []

        for module in self._modules.values():
            logger.info(f'fetching prompt from module {module.name}')
            fragment = await module.get_prompt_fragment()

            if fragment:
                fragments.append(f"# {module.name}\n{fragment}")

        return "\n\n".join(fragments)

    def get_module(self, name: str) -> Optional[BaseModule]:
        """Get module by name"""
        return self._modules.get(name)

    def get_all_state(self) -> Dict[str, Any]:
        """Get state of all modules"""
        return {name: module.get_state() for name, module in self._modules.items()}
