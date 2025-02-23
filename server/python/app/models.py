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
class ClientSession:
    """Dataclass to store client session details"""

    ani_name: str | None = None
    dnis: str | None = None
    conversation_id: str | None = None
    client_seq: int = 0
    server_seq: int = 0
    rtt: list[int] = field(default_factory=list)
    last_rtt: int | None = None
    media: dict | None = None
    raw_audio_buffer: bytes | None = None
    audio_buffer: speechsdk.audio.PushAudioInputStream | None = None
    recognize_task: Any | None = None
    transcript: str = ""


@dataclass(kw_only=True)
class HealthCheckResponse:
    """Dataclass to model Health Check response"""

    status: str
    connected_clients: int
    client_sessions: list[ClientSession]
