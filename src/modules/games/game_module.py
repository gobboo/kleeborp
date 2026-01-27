




from enum import Enum
import json
from events import EventType, Event, event_handler
from modules.base import BaseModule
from prompts.prompts import load_prompt

class State(Enum):
    NO_GAME = 0
    IDLE = 1,
    PENDING_ACTION = 2,
    PENDING_ACTION_FORCED = 3

class GameModule(BaseModule):
    def __init__(self, event_bus, module_manager, websocket_server, config = None):
        super().__init__("game", event_bus, module_manager, config)

        self.state = State.NO_GAME
        self.game = None

        self.pending_action_id = None
        self.pending_action = None
        
        self.registered_actions = []

        self.websocket_server = websocket_server
        
        self.brain_module = module_manager.get_module('brain')

        if not self.brain_module:
            raise Exception('GameModule depends on BrainModule')
        
        
    def _add_llm_message(self, message: str):
        self.brain_module.pending_conversation_buffer.append({
            "role": "user",
            "content": message
        })

    async def on_startup(self, game: str):
        self.logger.info(f'we got startup for game: {game}')

        self.state = State.IDLE
        self.game = game

        # reset state
        self.registered_actions = []

        self._add_llm_message(f"<game-context>You have just started playing a game called: {game}</game-context>")

        # TODO prompt the brain telling it its now playing x game
        # prompt brain
        await self.brain_module.force_generate_response(cancel=True)

    async def on_context(self, message: str, silent: bool):
        if self.pending_action_id:
            self.logger.warning("got a context message while waiting for an action result")
            return
        
        self._add_llm_message(f'<game-context>{message}</game-context>')

        if not silent:
            await self.brain_module.force_generate_response(cancel=True)


        self.logger.info(f'we got context "{message}" - silent: {silent}')

    def on_action_register(self, actions):
        self.logger.info(f'we got register actions "{actions}"')

        for action in actions:
            # check for duplicates
            if "schema" not in action:
                self.logger.warning(f'no schemas sent for action {action["name"]}')
                return
            
            # todo validate schema maybe idk

            self.logger.info(f'registered action {action["name"]}')

            tool = {
                "type": "function",
                "function": {
                    "name": action["name"],
                    "description": action["description"],
                    "parameters": action["schema"]
                }
            }

            self.registered_actions.append(tool)
        pass

    def on_action_unregister(self, action_ids):
        self.registered_actions = filter(lambda x: x["function"]["name"] not in action_ids)
        self.logger.info(f'unregister actions: "{action_ids}"')

    async def on_action_force(self, data):
        message = self._convert_forced_action_to_message(data)

        self._add_llm_message(message)

        await self.brain_module.force_generate_response(cancel=True)


    async def on_action_result(self, data):
        if self.state != State.PENDING_ACTION and self.state != State.PENDING_ACTION_FORCED:
            self.logger.warning(f'got a result to handle but in bad state {self.state.name}')
            return
        
        # TODO implement result
        if self.pending_action["data"]["id"] != data["id"]:
            self.logger.warning('received an action result with an id that doesn\'t match the pending id thats awaiting results')
            return
        
        content = {
            "success": data["success"]
        }

        if "message" in data and data["message"] != None:
            content["message"] = data["message"]

        # this will prompt brain module
        await self.event_bus.emit(
            Event(
                type=EventType.TOOL_RESULT,
                data={"id": data["id"], "name": self.pending_action["data"]["name"], "result": content},
                source="game",
            )
        )

        self.pending_action = None
        self.pending_action_id = None

        self.logger.info(f'we got force action "{data}"')


    def _convert_forced_action_to_message(self, message):
        content = ""

        # todo idk what state does tbf i just saw it got used in jibbity, ill do some more looking later
        if "ephemeral_context" in message:
            content += message["query"] + "\n\n"

            if "state" in message:
                content += f'<current-game-state>\n{message["state"]}\n</current-game-state>\n\n'

        content += f'<required-tools-to-use>\n{", ".join(message["action_names"])}\n</required-tools-to-use>'

        return content
    
    async def _send_action_to_game(self, action):
        self.logger.info(f'sending action to clients {action}')
        
        await self.websocket_server.broadcast(action)

    @event_handler(EventType.TOOL_CALL_REQUEST)
    async def on_tool_requested(self, event):
        """When we get a tool request we check if its for the game and if so we create an action, set state, and send it back to the game."""
        data = event.data

        self.logger.info(f"got game action request with data {data}")
        
        # check to see if the tool request is one of our actions, otherwise dismiss it
        registered_action = next((action for action in self.registered_actions if action['function']['name'] == data["name"]), None)

        if registered_action == None:
            self.logger.warning(f'got a game action requested but action isn\'t registered.')
            return

        action = {
            "command": "action",
            "data": {
                "id": data["id"],
                "name": data["name"],
                "data": json.dumps(data["arguments"])
            }
        }


        self.pending_action_id = data["id"]

        # todo: check for forced action and set our state accordingly
        self.pending_action = action
        self.state = State.PENDING_ACTION

        await self._send_action_to_game(action)

    async def handle_incoming_command(self, command: str, data):
        self.logger.info(f'incoming command {command} with {data}')

        if self.state == State.NO_GAME and command != 'startup':
            self.logger.warning(f'got command {command} before startup was called, ignoring')
            return

        match command:
            case 'startup':
                await self.on_startup(data["game"])
        
            case 'context':
                await self.on_context(data["data"]["message"], data["data"]["silent"])

            case 'actions/register':
                self.on_action_register(data["data"]["actions"])

            case 'actions/unregister':
                self.on_action_unregister(data["data"]["action_names"])

            case 'actions/force':
                await self.on_action_force(data["data"])

            case 'action/result':
                await self.on_action_result(data["data"])

            case _:
                self.logger.warning(f'got unknown game command: {command}')

    async def get_prompt_fragment(self):
        prompt = load_prompt("games")

        return prompt

    def _run(self):
        return super()._run()
    
    def _cleanup(self):
        return super()._cleanup()
    
    def _setup(self):
        return super()._setup()