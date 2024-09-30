from enum import StrEnum, unique


@unique
class ServerMessageType(StrEnum):
    CLOSED = "closed"
    DISCONNECT = "disconnect"
    EVENT = "event"
    OPENED = "opened"
    PAUSE = "pause"
    PONG = "pong"
    RECONNECT = "reconnect"
    RESUME = "resume"
    UPDATED = "updated"


@unique
class ClientMessageType(StrEnum):
    CLOSE = "close"
    CLOSED = "closed"
    DISCARDED = "discarded"
    DTMF = "dtmf"
    ERROR = "error"
    OPEN = "open"
    PAUSED = "paused"
    PING = "ping"
    PLAYBACK_COMPLETED = "playback_completed"
    PLAYBACK_STARTED = "playback_started"
    RESUMED = "resumed"
    UPDATE = "update"


@unique
class CloseReason(StrEnum):
    DISCONNECT = "disconnect"
    END = "end"
    ERROR = "error"
    RECONNECT = "reconnect"


@unique
class DisconnectReason(StrEnum):
    COMPLETED = "completed"
    ERROR = "error"
    UNAUTHORIZED = "unauthorized"
