# events/types.py
from enum import Enum, auto


class EventType(str, Enum):
    """
    All event types in the Kleeborp system.

    Using str, Enum makes them JSON-serializable and comparable to strings.
    """

    # === Core System Events ===
    SYSTEM_STARTUP = "system.startup"
    SYSTEM_SHUTDOWN = "system.shutdown"
    MODULE_INITIALIZED = "module.initialized"
    MODULE_STARTED = "module.started"
    MODULE_STOPPED = "module.stopped"
    MODULE_ERROR = "module.error"

    # === User Input Events ===
    USER_INPUT = "user.input"
    USER_SPEAKING_STARTED = "user.speaking.started"
    USER_SPEAKING = "user.speaking"
    USER_SPEAKING_STOPPED = "user.speaking.stopped"
    USER_JOINED = "user.joined"
    USER_LEFT = "user.left"
    USER_MUTED = "user.muted"
    USER_UNMUTED = "user.unmuted"

    # === Brain/LLM Events ===
    LLM_GENERATION_STARTED = "llm.generation.started"
    LLM_TEXT_CHUNK = "llm.text.chunk"
    LLM_GENERATION_COMPLETE = "llm.generation.complete"
    LLM_GENERATION_INTERRUPTED = "llm.generation.interrupted"
    LLM_ERROR = "llm.error"

    # === Tool Events ===
    TOOL_CALL_REQUEST = "tool.call.request"
    TOOL_CALL_STARTED = "tool.call.started"
    TOOL_CALL_COMPLETE = "tool.call.complete"
    TOOL_CALL_ERROR = "tool.call.error"
    TOOL_RESULT = "tool.result"

    # === Memory Events ===
    MEMORY_CREATED = "memory.created"
    MEMORY_RETRIEVED = "memory.retrieved"
    MEMORY_SEARCH = "memory.search"
    CONVERSATION_COMMITTED = "conversation.committed"

    # === Speech Events ===
    TRANSCRIPTION_REQUEST = "speech.transcription.request"
    TRANSCRIPTION_COMPLETE = "speech.transcription.complete"
    TTS_REQUEST = "tts.request"
    TTS_CANCELLED = "tts.cancelled"
    TTS_AUDIO_CHUNK = "tts.audio.chunk"
    TTS_PLAYER_COMPLETE = "tts.player.complete"
    TTS_EXHAUSTED = "tts.exhausted"
    TTS_STARTED = "tts.started"

    # === Audio Playback Events ===
    AUDIO_PLAY = "audio.play"
    AUDIO_PLAYING = "audio.playing"
    AUDIO_PAUSED = "audio.paused"
    AUDIO_STOPPED = "audio.stopped"
    AUDIO_COMPLETE = "audio.complete"

    # === Discord Events ===
    DISCORD_CONNECTED = "discord.connected"
    DISCORD_DISCONNECTED = "discord.disconnected"
    DISCORD_VOICE_JOIN = "discord.voice.join"
    DISCORD_VOICE_LEAVE = "discord.voice.leave"
    DISCORD_VOICE_JOINED = "discord.voice.joined"
    DISCORD_VOICE_LEFT = "discord.voice.left"
    DISCORD_MESSAGE = "discord.message"

    # === Game Integration Events ===
    GAME_CONNECTED = "game.connected"
    GAME_DISCONNECTED = "game.disconnected"
    GAME_STATE_CHANGED = "game.state.changed"
    GAME_ACTION_REQUEST = "game.action.request"
    GAME_ACTION_COMPLETE = "game.action.complete"

    # === WebSocket Events ===
    WS_CLIENT_CONNECTED = "ws.client.connected"
    WS_CLIENT_DISCONNECTED = "ws.client.disconnected"
    WS_MESSAGE_RECEIVED = "ws.message.received"
    WS_STATE_REQUEST = "ws.state.request"

    # === Interrupt Events ===
    INTERRUPT = "interrupt"
    FORCE_RESPONSE = "force.response"

    def __str__(self):
        return self.value


class EventPriority(Enum):
    """Event priority levels"""

    CRITICAL = 100  # System-critical events
    HIGH = 75  # Interrupts, user input
    NORMAL = 50  # Regular events
    LOW = 25  # Background tasks
    IDLE = 0  # Lowest priority
