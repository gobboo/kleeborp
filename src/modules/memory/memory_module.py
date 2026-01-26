import asyncio
import copy
import json
from events import EventType, event_handler, Event
from modules.base import BaseModule
from modules.memory.rag_database import RAGDatabase
from prompts.prompts import load_prompt
from services.llm_client import LLMClient


class MemoryModule(BaseModule):
    def __init__(self, event_bus, module_manager, config=None):
        super().__init__("memory", event_bus, module_manager, config)

        self.rag = RAGDatabase(config["modules"]["memory"])
        self.llm_client = LLMClient(config["modules"]["memory"], config["modules"]["memory"]["model"])

        self.previous_conversations = []
        self.current_processed_memories = 0
        
        self.to_commit_messages = []

        # required as we will be passing "raw" config to this module so we can create the llmclient above
        self.config = config["modules"]["memory"]

        self.current_relevant_memories = []

    # TODO: Maybe listen on USER_INPUT as we may move the transcription_complete to some other place
    @event_handler(EventType.USER_INPUT)
    async def on_transcription_complete(self, event: Event):
        # dont commit to the messages this turn as brain module does that
        self.to_commit_messages.append(f'{event.data["message"]["content"]}')

        raw_transcript = event.data["message"]["content"].split(":")[1].strip()

        self.current_relevant_memories = await self.rag.query_relevant_entries(
            raw_transcript
        )

    @event_handler(EventType.LLM_GENERATION_COMPLETE)
    async def on_llm_generation_complete(self, event: Event):
        # commit the previous conversation for the next iteration to use
        for message in self.to_commit_messages:
            self.previous_conversations.append(message)

        self.to_commit_messages.clear()

        self.previous_conversations.append(f'Kleeborp: {event.data['message']}')

    async def get_prompt_fragment(self):
        prompt = "Previous conversation history DO NOT OUTPUT THIS:\n"

        conversation = '\n'.join(self.previous_conversations[-50:])

        memories = "\n".join(self.current_relevant_memories)

        return f"{prompt}{conversation}\n\nRelevant Memories:\n{memories}"

    async def _run(self):
        try:
            while self._running:
                if self.current_processed_memories > len(self.previous_conversations):
                    self.current_processed_memories = 0
                
                # here we're just checking we have 20 messages in our convo to parse into memories
                if len(self.previous_conversations) - self.current_processed_memories >= 40:
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
        messages = copy.deepcopy(self.previous_conversations[-20:])

        if not messages:
            return
        
        self.logger.info('creating memories from previous 20 messages')

        system_prompt = await asyncio.to_thread(load_prompt, "memory")

        output_message = ""
        
        stream = self.llm_client.stream_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                *(
                    {"role": "user", "content": content}
                    for content in self.previous_conversations[-20:]
                ),
            ],
        tools = [{
          "type": "function",
          "function": {
            "name": "create_memories",
            "description": "Store extracted memories into the RAG memory store",
            "parameters": {
              "type": "object",
              "properties": {
                "memories": {
                  "type": "array",
                  "items": {
                    "type": "object",
                    "properties": {
                      "question": { "type": "string" },
                      "answer": { "type": "string" },
                      "type": { "type": "string" },
                      "entities": {
                        "type": "array",
                        "items": { "type": "string" }
                      },
                      "confidence": {
                        "type": "number",
                        "minimum": 0,
                        "maximum": 1
                      }
                    },
                    "required": [
                      "question",
                      "answer",
                      "type",
                      "entities",
                      "confidence"
                    ]
                  }
                }
              },
              "required": ["memories"]
            }
          }
        }]
        )

        async for chunk in stream:
            if chunk.get("type") != "tool_call":
                continue

            tool_call = chunk.get("tool_call", {})

            if tool_call.get("name") != "create_memories":
                self.logger.warning(f"Unknown tool call: {tool_call.get('name')}")
                continue

            arguments = tool_call.get("arguments", {})
            memories = arguments.get("memories")

            if not isinstance(memories, list):
                self.logger.error("Tool call 'memories' is not a list")
                continue

            for mem in memories:
                if not isinstance(mem, dict):
                    continue

                question = mem.get("question")
                answer = mem.get("answer")
                mem_type = mem.get("type")

                if not all([question, answer, mem_type]):
                    self.logger.warning(f"Skipping malformed memory: {mem}")
                    continue

                await self.rag.upsert(
                    document=answer,
                    metadata={
                        "question": question,
                        "type": mem_type,
                        "entities": ', '.join(mem.get("entities", [])),
                    },
                )
                
        self.current_processed_memories = len(self.previous_conversations)

