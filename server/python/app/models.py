import asyncio
from dataclasses import dataclass, field
from typing import Any

import azure.cognitiveservices.speech as speechsdk


@dataclass
class MessageBase:
    version: str
    id: str
    type: str
    seq: int
    parameters: dict[str, Any]


@dataclass
class ClientMessageBase(MessageBase):
    serverseq: int
    position: str


@dataclass
class ServerMessageBase(MessageBase):
    clientseq: int
    position: str


@dataclass(kw_only=True)
class Conversation:
    """Dataclass to store conversation details"""

    session_id: str
    conversation_id: str
    active: bool = True
    ani: str
    ani_name: str
    dnis: str
    media: dict  # todo type
    rtt: list[int] = field(default_factory=list)
    last_rtt: int | None = None
    transcript: list[dict] = field(default_factory=list)


@dataclass(kw_only=True)
class WebSocketSessionStorage:
    """Temporary in-memory storage for WebSocket session state"""

    conversation_id: str | None = None
    raw_audio_buffer: bytes | None = None
    audio_buffer: speechsdk.audio.PushAudioInputStream | None = None
    recognize_task: asyncio.Task | None = None
    client_seq: int = 0
    server_seq: int = 0


@dataclass(kw_only=True)
class HealthCheckResponse:
    """Dataclass to model Health Check response"""

    status: str


@dataclass(kw_only=True)
class ConversationsResponse:
    """Dataclass to model Conversations response"""

    count: int
    conversations: list[Conversation] = field(default_factory=list)
