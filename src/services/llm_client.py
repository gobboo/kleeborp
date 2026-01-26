# services/llm_client.py
import logging
from openai import AsyncOpenAI
from typing import AsyncIterator, Dict, Any, Optional
import json

logger = logging.getLogger(__name__)


class LLMClient:
    def __init__(self, config: Dict[str, Any], model_override: str = None):
        self.config = config

        # Works for both OpenAI and OpenRouter
        self.client = AsyncOpenAI(
            api_key=config["api_key"],
            base_url=config.get("base_url"),  # None for OpenAI, set for OpenRouter
        )

        self.model = model_override or config.get("model", "gpt-4-turbo-preview")
        print(self.model)

    async def stream_completion(
        self, messages: list, tools: Optional[list] = None, tool_choice: str = "auto"
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Stream completion and yield structured chunks.

        Yields:
            {
                'type': 'text' | 'tool_call' | 'done',
                'content': str (for text),
                'tool_call': {...} (for tool_call),
                'finish_reason': str (for done)
					}
        """
        try:
            stream = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tools,
                tool_choice=tool_choice if tools else "none",
                stream=True,
                stream_options={"include_usage": True},
                top_p=self.config.get('top_p', 0.8),
                temperature=self.config.get('tempurate', 0.75),
                max_tokens=self.config.get('max_tokens', 300),
                frequency_penalty=self.config.get('frequency_penalty', 0.8),
                presence_penalty=self.config.get('presence_penalty', 0.3)
            )

            # Track tool calls being built
            tool_calls_buffer = {}

            async for chunk in stream:
                if not chunk.choices:
                    # Usage info or other metadata
                    continue

                delta = chunk.choices[0].delta
                finish_reason = chunk.choices[0].finish_reason

                # Handle text content
                if delta.content:
                    yield {"type": "text", "content": delta.content}

                # Handle tool calls
                if delta.tool_calls:
                    for tool_call in delta.tool_calls:
                        idx = tool_call.index

                        # Initialize buffer for this tool call
                        if idx not in tool_calls_buffer:
                            tool_calls_buffer[idx] = {
                                "id": tool_call.id,
                                "name": "",
                                "arguments": "",
                            }

                        # Accumulate tool call data
                        if tool_call.function.name:
                            tool_calls_buffer[idx]["name"] = tool_call.function.name

                        if tool_call.function.arguments:
                            tool_calls_buffer[idx]["arguments"] += (
                                tool_call.function.arguments
                            )

                # When stream finishes, yield complete tool calls
                if finish_reason:
                    if tool_calls_buffer:
                        for tool_call in tool_calls_buffer.values():
                            # Parse arguments JSON
                            try:
                                arguments = json.loads(tool_call["arguments"])
                            except json.JSONDecodeError:
                                logger.error(
                                    f"Failed to parse tool arguments: {tool_call['arguments']}"
                                )
                                arguments = {}

                            yield {
                                "type": "tool_call",
                                "tool_call": {
                                    "id": tool_call["id"],
                                    "name": tool_call["name"],
                                    "arguments": arguments,
                                },
                            }

                    yield {"type": "done", "finish_reason": finish_reason}

        except Exception as e:
            logger.error(f"Error in LLM stream: {e}", exc_info=True)
            raise
