import asyncio
from typing import Any

import azure.cognitiveservices.speech as speechsdk
from pydantic import BaseModel, ConfigDict, Field


class MessageBase(BaseModel):
    version: str
    id: str
    type: str
    seq: int
    parameters: dict[str, Any]


class ClientMessageBase(MessageBase):
    serverseq: int
    position: str


class ServerMessageBase(MessageBase):
    clientseq: int
    position: str


class Conversation(BaseModel):
    """Pydantic model to store conversation details"""

    model_config = ConfigDict(extra="ignore")

    id: str
    session_id: str
    active: bool = True
    ani: str
    ani_name: str
    dnis: str
    media: dict[str, Any]
    position: str
    rtt: list[str] = Field(default_factory=list)
    transcript: list[dict[str, Any]] = Field(default_factory=list)


class WebSocketSessionStorage(BaseModel):
    """Temporary in-memory storage for WebSocket session state"""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    conversation_id: str | None = None
    raw_audio_buffer: bytes | None = None
    audio_buffer: speechsdk.audio.PushAudioInputStream | None = None
    recognize_task: asyncio.Task | None = None
    client_seq: int = 0
    server_seq: int = 0


class HealthCheckResponse(BaseModel):
    """Pydantic model to model Health Check response"""

    status: str


class ConversationsResponse(BaseModel):
    """Pydantic model to model Conversations response"""

    count: int
    conversations: list[Conversation] = Field(default_factory=list)
