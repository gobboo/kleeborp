# modules/brain/brain_module.py
import json
import logging
import random
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
        self.tool_results = []

        self.last_tools_used = [] # used to try and prevent loops, if a new tool was requested whilst we're giving back previous tool data, and its in here, we discard the new tool request
        self.pending_tool_calls = []
        self.pending_conversation_buffer = [] # this gets cleared at LLM_COMPLETION
        self.queued_conversation_buffer = [] # when speaking or generation is happening we store this to appl to the above later
        
        self.is_forced_generating = False
        self.is_generating = False
        
        self.generation_task = None

        self.last_generation_started_at = time.monotonic() # used
        self.last_generation_finished_at = time.monotonic()

        self.patience = random.randint(30, 60)

        self._is_speaking = False

        self.time_since_last_spoke = time.monotonic()

    @event_handler(EventType.USER_SPEAKING)
    async def on_user_speaking(self, _):
        self.time_since_last_spoke = time.monotonic()

        if self.generation_task != None:
            self._cancel_task_safe()

    @event_handler(EventType.TRANSCRIPTION_COMPLETE)
    async def on_user_input(self, event: Event):
        """Handle user input and generate response"""
        user_message = event.data["transcription"]

        # Lookup "name" from "user_name"
        name = user_name_to_name(event.data["user_name"])
        message = {
            "role": "user",
            "content": f"{name}: {user_message}",
        }

        if self.is_generating or self._is_speaking:
            # self.queued_conversation_buffer.append(message)
            self.logger.warning("Already generating / speaking, queueing input") # TODO Maybe actually queue transcriptions?
            return

        self.pending_conversation_buffer.append(message)

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

    @event_handler(EventType.TTS_STARTED)
    async def on_tts_started(self, _):
        self._is_speaking = True
        self.logger.info('tts is currently active')

    @event_handler(EventType.TTS_PLAYER_COMPLETE)
    async def on_tts_complete(self, _):
        self._is_speaking = False
        self.time_since_last_spoke = time.monotonic()
        self.logger.info('tts is no longer active')

    @event_handler(EventType.INTERRUPT)
    async def on_interruption(self, _):
        self._is_speaking = False
        self.time_since_last_spoke = time.monotonic()
    
    async def force_generate_response(self, cancel = False):
        self.logger.info('forcing generation as we havent been able to speak for a while.')

        self.is_forced_generating = True

        # cancel existing task if there is one
        if cancel:
            self._cancel_task_force()
        
        await self._generate_response()

    async def _generate_response(self):
        """Generate streaming response"""
        self.is_generating = True
        self.last_generation_started_at = time.monotonic()

        # Get tools from MCP module or tool registry
        tools = []
        if len(self.last_tools_used) <= 0: # helps prevent looping, we dont allow another tool call if we have pending tool results
          tools = await self._get_available_tools() 
          self.logger.info(tools)

        # Build messages with system prompt
        messages = await self._build_messages()

        self.logger.info(messages)

        # self.logger.info(messages)

        try:
            assistant_message = {"role": "assistant", "content": ""}

            # self.logger.info(self.tool_results)

            async for chunk in self.llm_client.stream_completion(
                messages=messages,
                tools=tools
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
                        
                    # here we do a check to see if the last tool used is the same tool now, to prevent looping
                    # tool calls are cleared after a successful llm generation so you can still use it
                    # back to back basically but this prevents loops
                    # COMMENTED OUT IN FAVOUR OF REMOVING THE TOOL TEMPROARILY FROM TOOLS LIST WHEN IT WAS JUST USED

                    # if len(self.last_tools_used) > 0 and raw['name'] in self.last_tools_used:
                    #     continue

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
                    # self.conversation_buffer.append(assistant_message)

                    # If there were tool calls, wait for results
                    if (
                        "tool_calls" in assistant_message
                        and assistant_message["tool_calls"]
                    ):
                        self.pending_tool_calls = assistant_message["tool_calls"]
                        # Will continue when all tool results arrive
                    else:
                        # Done generating
                        self.logger.info(assistant_message)

                        self.patience = random.randint(40, 60)
                        self.last_generation_finished_at = time.monotonic()

                        self.pending_conversation_buffer.clear()

                        # add what was said when generating or speaking to the current conversational buffer
                        self.pending_conversation_buffer.extend(self.queued_conversation_buffer)
                        self.queued_conversation_buffer.clear()
                        
                        # clear the last tools used so they can be potentially used in the enxt prompt (that isnt a response to a tool used)
                        self.last_tools_used.clear()
                        

                        await self.event_bus.emit(
                            Event(
                                type=EventType.LLM_GENERATION_COMPLETE,
                                data={"message": assistant_message["content"]},
                                source="brain",
                            )
                        )
                        
                        self.tool_results.clear()

        except asyncio.CancelledError:
            self.logger.info("Generation interrupted")
        except Exception as e:
            self.logger.error(f"Error generating response: {e}", exc_info=True)
        finally:
            self.logger.info('finished prompt generation')
            self.is_generating = False
            self.is_forced_generating = False

    @event_handler(EventType.TOOL_RESULT)
    async def on_tool_result(self, event: Event):
        """Handle tool execution result"""
        tool_result = event.data
        
        self.logger.info(tool_result)

        # Add tool result to conversation
        self.tool_results.append(
            {
                "role": "tool",
                "tool_call_id": tool_result["id"],
                "content": json.dumps(tool_result["result"]),
            }
        )

        self.last_tools_used.append(tool_result["name"])

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

          # games prompts if we're playing a game
          # games_module = self.module_manager.get_module("game")

          # game_pending_llm_messages = []
          # if games_module and games_module.game != None:
          #     game_pending_llm_messages = games_module.pending_llm_messages
          #     game_pending_llm_messages.pending_llm_messages.clear()

          memory_module = self.module_manager.get_module('memory')

          previous_messages = []
          if memory_module and len(memory_module.previous_conversations) > 0:   
            # jumpscare ah code
            previous_messages =  map(lambda x: {"role": "assistant" if "assistant" in x else "user", "content": x.replace('assistant:', '')}, memory_module.previous_conversations[-40:])
          
          messages = map(lambda x: {"role": "user", "content": x["content"]}, self.pending_conversation_buffer)

          return [{"role": "system", "content": system_prompt}, *previous_messages, *self.tool_results, *messages]
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
        # Check if theres a game currently in progress
        # if there is we want to send the games registered
        # tools
        tool_definitions = []

        games_module = self.module_manager.get_module("game")

        if games_module and games_module.game != None:
          games_registered_actions = games_module.registered_actions

          tool_definitions.extend(games_registered_actions)

        # Query MCP module or tool registry
        tools_module = self.module_manager.get_module("tools")

        if tools_module:
            tools = tools_module.get_tool_definitions_for_llm()

            tool_definitions.extend(tools)

        return tool_definitions
    
    def _cancel_task_force(self):
        if self.generation_task and not self.generation_task.done():
          self.generation_task.cancel() # TODO Maybe call interruption?

        self.generation_task = None

        self.logger.info('generation task forced cancel.')
        
    def _cancel_task_safe(self):
        now = time.monotonic()

        if self.is_generating and self.is_forced_generating:
            self.logger.info('cannot cancel generation task, we are being forced to think')
            return
        
        grace_period_elapsed = now - self.last_generation_started_at

        if self.is_generating and grace_period_elapsed >= self.config.get('cancel_grace_period', 1):
            self.logger.info('cannot cancel generation task, grace period over.')
            return

        # if theres an existing task and its not done, then we're allowed to cancel it
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

            now = time.monotonic()

            # cooldown basically, checks to make sure 2 seconds have passed since last generation
            if now - self.last_generation_finished_at <= 2:
                continue

            if self.is_generating or self._is_speaking or len(self.pending_tool_calls) > 0:
                continue
            
            self.logger.debug(f'silence: {now - self.time_since_last_spoke}')

            if now - self.time_since_last_spoke <= 2:
                # check to see if our patience has ran out
                if now - self.last_generation_finished_at >= self.patience:
                    self.generation_task = asyncio.create_task(
                        self.force_generate_response()
                    )

                continue

            if len(self.pending_conversation_buffer) <= 0:
                continue

            self.logger.info("we'd send our generation now")


            self.generation_task = asyncio.create_task(
                self._generate_response()
            )

    async def _cleanup(self):
        pass
