# modules/tools/internal/discord/messaging.py
import base64
from io import BytesIO

from services.llm_client import LLMClient
from .base import BaseTool, tool
from PIL import ImageGrab

class VisionTools(BaseTool):
    """Tools for Seeinng"""
    def __init__(self, config, **dependencies):
        super().__init__(config, **dependencies)

        self.brain_module = self.dependencies["brain_module"]
        self.config = config

        if not self.brain_module:
            raise Exception('Vision tool requires brain_module dependency')
        
        self.llm_client = LLMClient(config["llm"], config["tools"]["vision"]["model"])

    @tool(
        name="screenshot_screen",
        description="Takes a screenshot of the screen for analysis, so that AI models can 'see' and 'look'.",
        parameters={}
    )
    async def analyse_screenshot(self):
        screenshot = ImageGrab.grab()
        screenshot.save('what_we_see.jpeg')

        buffered = BytesIO()

        # save the ss to the buffer
        screenshot.save(buffered, format="JPEG")
        base64_screenshot = base64.b64encode(buffered.getvalue()).decode("utf-8")

        try:
            assistant_message = ""

            messages = map(lambda x: {"role": "user", "content": x["content"]}, self.brain_module.pending_conversation_buffer)
            
            stream = self.llm_client.stream_completion(
              messages=[
                    {"role": "system", "content": "You are attempting to take the image recieved and describe it and answer the questions being asked about what you see and what you're currently looking at, the user messages are the previous conversation summary that led up to you being asked."},
                    *messages,
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": { "url": f"data:image/png;base64,{base64_screenshot}" }
                            }
                        ]
                    }
              ])
            
            async for chunk in stream:
                if chunk["type"] == "text":
                    assistant_message += chunk["content"]
                
                elif chunk["type"] == "done":
                    return {"success": True, "description": assistant_message}


        except Exception as e:
            self.logger.error(f"Failed to send message: {e}")
            return {"success": False, "error": str(e)}
