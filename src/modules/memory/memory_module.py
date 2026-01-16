import asyncio
import copy
from events import EventType, event_handler, Event
from modules.base import BaseModule
from modules.memory.rag_database import RAGDatabase
from prompts.prompts import load_prompt
from services.llm_client import LLMClient


class MemoryModule(BaseModule):
    def __init__(self, event_bus, module_manager, config=None):
        super().__init__("memory", event_bus, module_manager, config)

        self.rag = RAGDatabase(config["modules"]["memory"])
        self.llm_client = LLMClient(config["llm"])

        self.previous_conversations = []

        # required as we will be passing "raw" config to this module so we can create the llmclient above
        self.config = config["modules"]["memory"]

        self.current_relevant_memories = []

    # TODO: Maybe listen on USER_INPUT as we may move the transcription_complete to some other place
    @event_handler(EventType.USER_INPUT)
    async def on_transcription_complete(self, event: Event):
        self.previous_conversations.append(f'[{event.data["name"]}]: {event.data["message"]}')

        raw_transcript = event.data["message"]["content"].split(":")[1].strip()

        self.current_relevant_memories = await self.rag.query_relevant_entries(
            raw_transcript
        )

    async def get_prompt_fragment(self):
        prompt = "Previous conversation snippets:\n"

        conversation = '\n'.join(self.previous_conversations[-20:])

        memories = "\n".join(self.current_relevant_memories)

        return f"{prompt}{conversation}\nRelevant Memories:\n{memories}"

    async def _run(self):
        try:
            while self._running:
                # here we're just checking we have 20 messages in our convo to parse into memories
                if len(self.previous_conversations) >= 20:
                    await self._create_memories_from_conversation()

                await asyncio.sleep(5)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            self.logger.error(f"memory module ran into an error: {e}", exc_info=True)
            raise

    async def _setup(self):
        self.logger.info("warming up chromadb")
        await self.rag.initialize()

    async def _cleanup(self):
        pass

    # TODO Make it so it uses the MCP server to insert memories
    async def _create_memories_from_conversation(self):
        messages = copy.deepcopy(self.current_relevant_memories[-20:])

        if not messages:
            return

        system_prompt = await asyncio.to_thread(load_prompt, "memory")

        output_message = ""

        stream = self.llm_client.stream_completion(
            messages=[
                {"type": "system", "content": system_prompt},
                *self.previous_conversations[-20:],
            ]
        )

        for chunk in stream:
            if chunk["type"] == "tool_call":
                tool_call = chunk["tool_call"]

                if tool_call["name"] != "create_memories":
                    self.logger.warning(
                        f"memory attempt to call unknown tool {tool_call}"
                    )
                    continue

                memories = tool_call["arguments"]["memories"]

                for mem in memories:
                    await self.rag.upsert(
                        document=mem["answer"],
                        metadata={
                            "question": mem["question"],
                            "type": mem["type"],
                            "entities": mem.get("entities", []),
                        },
                    )
