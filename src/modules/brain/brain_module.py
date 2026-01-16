# modules/brain/brain_module.py
import json
import logging
import time
from events.handlers import event_handler
from modules.base import BaseModule
from services.llm_client import LLMClient
from events import Event, EventType
import asyncio

from utils.user_name_to_name import user_name_to_name

logger = logging.getLogger(__name__)


class BrainModule(BaseModule):
    def __init__(self, event_bus, module_manager, config):
        super().__init__("brain", event_bus, config)

        self.module_manager = module_manager
        self.llm_client = LLMClient(config["llm"])
        self.conversation_buffer = []
        self.pending_tool_calls = []
        self.pending_conversation_buffer = []
        
        self.is_generating = False
        self.generation_task = None
        self.last_generation_started_at = time.monotonic() # used

        self._is_speaking = False

        self.time_since_last_spoke = time.monotonic()

    @event_handler(EventType.USER_SPEAKING)
    async def on_user_speaking(self, _):
        self.time_since_last_spoke = time.monotonic()

        if self.generation_task != None:
            self._cancel_task()

    @event_handler(EventType.TRANSCRIPTION_COMPLETE)
    async def on_user_input(self, event: Event):
        """Handle user input and generate response"""
        if self.is_generating or self._is_speaking:
            self.logger.warning("Already generating / speaking, queueing input") # TODO Maybe actually queue transcriptions?
            return

        user_message = event.data["transcription"]

        # Lookup "name" from "user_name"
        name = user_name_to_name(event.data["user_name"])
        message = {
            "role": "user",
            "content": f"[{name}]: {user_message}",
        }

        self.conversation_buffer.append(message)
        self.pending_conversation_buffer.append(message)

        self.logger.debug(self.conversation_buffer)

        await self.event_bus.emit(
            Event(
                type=EventType.USER_INPUT,
                data={
                    "user_name": event.data["user_name"],
                    "user_id": event.data["user_id"],
                    "name": name,
                    "message": message,
                },
            )
        )

        # TODO: Interruptions, and silence checking
        self.time_since_last_transcription = time.monotonic()

        if self.generation_task != None:
            self._cancel_task()


    @event_handler(EventType.TTS_STARTED)
    async def on_tts_started(self, _):
        self._is_speaking = True
        self.logger.info('tts is currently active')

    @event_handler(EventType.TTS_COMPLETE)
    async def on_tts_complete(self, _):
        self._is_speaking = False
        self.logger.info('tts is no longer active')

    @event_handler(EventType.INTERRUPT)
    async def on_interruption(self, _):
        self._is_speaking = False
        
    async def _generate_response(self):
        """Generate streaming response"""
        self.is_generating = True
        self.last_generation_started_at = time.monotonic()

        # Get tools from MCP module or tool registry
        tools = await self._get_available_tools()

        # self.logger.info(tools)

        # Build messages with system prompt
        messages = await self._build_messages()

        self.logger.info(messages)

        # self.logger.debug(messages)

        try:
            assistant_message = {"role": "assistant", "content": ""}

            self.logger.debug(self.conversation_buffer)

            async for chunk in self.llm_client.stream_completion(
                messages=messages, tools=tools
            ):
                if chunk["type"] == "text":
                    # Stream text to TTS
                    text = chunk["content"]
                    assistant_message["content"] += text

                    await self.event_bus.emit(
                        Event(
                            type=EventType.LLM_TEXT_CHUNK,
                            data={"text": text},
                            source="brain",
                        )
                    )

                elif chunk["type"] == "tool_call":
                    raw = chunk["tool_call"]

                    # Convert to OpenAI-compatible tool call
                    tool_call = {
                        "id": raw["id"],
                        "type": "function",
                        "function": {
                            "name": raw["name"],
                            "arguments": json.dumps(raw["arguments"]),
                        },
                    }

                    if not "tool_calls" in assistant_message:
                        assistant_message["tool_calls"] = []

                    assistant_message["tool_calls"].append(tool_call)

                    self.logger.info(f"Tool call: {raw['name']}")

                    # Execute tool
                    await self.event_bus.emit(
                        Event(
                            type=EventType.TOOL_CALL_REQUEST,
                            data={
                                "id": raw["id"],
                                "name": raw["name"],
                                "arguments": raw["arguments"],
                            },
                            source="brain",
                        )
                    )

                elif chunk["type"] == "done":
                    # Save assistant message
                    self.conversation_buffer.append(assistant_message)

                    # If there were tool calls, wait for results
                    if (
                        "tool_calls" in assistant_message
                        and assistant_message["tool_calls"]
                    ):
                        self.pending_tool_calls = assistant_message["tool_calls"]
                        # Will continue when all tool results arrive
                    else:
                        # Done generating
                        self.logger.debug(assistant_message)

                        await self.event_bus.emit(
                            Event(
                                type=EventType.LLM_GENERATION_COMPLETE,
                                data={"message": assistant_message["content"]},
                                source="brain",
                            )
                        )

        except asyncio.CancelledError:
            self.logger.info("Generation interrupted")
        except Exception as e:
            self.logger.error(f"Error generating response: {e}", exc_info=True)
        finally:
            self.logger.debug('finished prompt generation')
            self.pending_conversation_buffer.clear()
            self.is_generating = False

    @event_handler(EventType.TOOL_RESULT)
    async def on_tool_result(self, event: Event):
        """Handle tool execution result"""
        tool_result = event.data
        
        self.logger.info(tool_result)

        # Add tool result to conversation
        self.conversation_buffer.append(
            {
                "role": "tool",
                "tool_call_id": tool_result["id"],
                "content": json.dumps(tool_result["result"]),
            }
        )

        # Remove from pending
        self.pending_tool_calls = [
            tc for tc in self.pending_tool_calls if tc["id"] != tool_result["id"]
        ]

        # If all tools are done, continue generation
        if not self.pending_tool_calls:
            self.logger.info("All tool calls complete, continuing generation")
            await self._generate_response()

    @event_handler(EventType.INTERRUPT)
    async def on_interrupt(self, event: Event):
        """Handle interruption during generation"""
        if self.is_generating:
            self.logger.info("Interrupting generation")
            # Cancel current generation task
            # This is tricky - you might need to track the task
            self.is_generating = False

    async def _build_messages(self) -> list:
        """Build message list with system prompt"""
        try:
          system_prompt = await self._get_system_prompt()

          self.logger.info('got system prompt')

          content = '\n'.join(message["content"] for message in self.pending_conversation_buffer)

          return [{"role": "system", "content": system_prompt}, {"role": "user", "content": f'This is shared room speech. Most of it is not directed at you.\n{content}'}]
        except Exception as e:
            self.logger.error(e, exc_info=True)
            raise e
    async def _get_system_prompt(self) -> str:
        """Build system prompt from module fragments"""
        # Get from module manager
        fragments = await self.module_manager.get_prompt_fragments()

        return fragments

    async def _get_available_tools(self) -> list:
        """Get available tools from MCP or tool registry"""
        # Query MCP module or tool registry
        tools_module = self.module_manager.get_module("tools")

        if tools_module:
            return tools_module.get_tool_definitions_for_llm()

        return []
    
    def _cancel_task(self):
        now = time.monotonic()

        if self.is_generating and now - self.last_generation_started_at >= self.config.get('cancel_grace_period', 2):
            self.logger.debug('cannot cancel generation task, grace period over.')
            return

        if self.generation_task and not self.generation_task.done():
            self.generation_task.cancel() # TODO Maybe call interruption?

        self.is_generating = False
        self.generation_task = None

        self.logger.info('generation task cancelled.')

    async def _setup(self):
        pass

    async def _run(self):
        while self._running:
            await asyncio.sleep(0.1)

            if self.is_generating or self._is_speaking: # TODO Fix this
                continue

            now = time.monotonic()
            
            self.logger.debug(f'silence: {now - self.time_since_last_spoke}')

            if now - self.time_since_last_spoke <= 1.5:
                continue

            if len(self.pending_conversation_buffer) <= 0:
                continue

            self.logger.info("we'd send our generation now")


            self.generation_task = asyncio.create_task(
                self._generate_response()
            )

    async def _cleanup(self):
        pass
