




from enum import Enum
from modules.base import BaseModule
import jsonschema

class State(Enum):
    NO_GAME = 0
    IDLE = 1,
    PENDING_ACTION = 2,
    PENDING_ACTION_FORCED = 3

class GameModule(BaseModule):
    def __init__(self, event_bus, module_manager, config = None):
        super().__init__("game", event_bus, module_manager, config)

        self.state = State.NO_GAME
        self.game = None

        self.pending_action_id = None
        self.pending_llm_messages = []
        
        self.registered_actions = []

    def on_startup(self, game: str):
        self.logger.info(f'we got startup for game: {game}')

        self.state = State.IDLE
        self.game = game

        # reset state
        self.registered_actions = []

        self.pending_llm_messages.append({
            "role": "user",
            "content": f"You have just started playing a game called: {game}"
        })

        # TODO prompt the brain telling it its now playing x game
        # prompt brain

    def on_context(self, message: str, silent: bool):
        if self.pending_action_id:
            self.logger.warning("got a context message while waiting for an action result")
            return
        
        context = {
            "role": "user",
            "content": message
        }

        self.pending_llm_messages.append(context)

        if not silent:
            pass # TODO Brain call


        self.logger.info(f'we got context "{message}" - silent: {silent}')
        pass

    def on_action_register(self, actions):
        self.logger.info(f'we got register actions "{actions}"')

        for action in actions:
            # check for duplicates
            if "schema" not in action:
                self.logger.warning(f'no schemas sent for action {action["name"]}')
                return
            
            try:
                jsonschema.validate(action["schema"])

                self.registered_actions.append(action)
            except jsonschema.ValidationError as e:
                self.logger.warning(f'schema validation failed for actio {action["name"]}')
                return
        pass

    def on_action_unregister(self, action_ids):
        self.registered_actions = filter(lambda x: x["name"] not in action_ids)
        self.logger.info(f'unregister actions: "{action_ids}"')

    def on_action_force(self, data):
        self.logger.info(f'we got force action "{data}"')
        pass

    def on_action_result(self, data):
        if self.state == State.PENDING_ACTION or self.state == State.PENDING_ACTION_FORCED:
            self.logger.warning(f'got a result to handle but in bad state {self.state.name}')
            return
        
        # TODO implement result
        # pending_action = 

        self.logger.info(f'we got force action "{data}"')
        pass

    def handle_incoming_command(self, command: str, data):
        self.logger.info(f'incoming command {command} with {data}')

        if self.state == State.NO_GAME and command != 'startup':
            self.logger.warning(f'got command {command} before startup was called, ignoring')
            return

        match command:
            case 'startup':
                self.on_startup(data["game"])
        
            case 'context':
                self.on_context(data["data"]["message"], data["data"]["silent"])

            case 'actions/register':
                self.on_action_register(data["data"]["actions"])

            case 'actions/unregister':
                self.on_action_unregister(data["data"]["action_names"])

            case 'actions/force':
                self.on_action_force(data["data"])

            case 'action/result':
                self.on_action_result(data["data"])

            case _:
                self.logger.warning(f'got unknown game command: {command}')

    async def get_prompt_fragment(self):
        pass

    def _run(self):
        return super()._run()
    
    def _cleanup(self):
        return super()._cleanup()
    
    def _setup(self):
        return super()._setup()