from modules.base import BaseModule
from prompts.prompts import load_prompt


class PersonaModule(BaseModule):
    def __init__(self, event_bus, module_manager, config=None):
        super().__init__("persona", event_bus, module_manager, config)

    # TODO techincally all these defs are blocking, as we do IO bound shti in the event loop, so fix it later
    def _get_identity_prompt(self):
        return load_prompt("identity")

    def _get_style_prompt(self):
        return load_prompt("style")

    def _get_constaints_prompt(self):
        return load_prompt("constraints")

    def _get_response_prompt(self):
        return load_prompt("response")

    async def get_prompt_fragment(self):
        return f"""
{self._get_identity_prompt()}
{self._get_style_prompt()}
{self._get_constaints_prompt()}
{self._get_response_prompt()}
"""

    async def _cleanup(self):
        pass

    async def _run(self):
        pass

    async def _setup(self):
        pass
