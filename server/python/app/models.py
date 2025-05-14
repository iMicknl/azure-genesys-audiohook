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


class TranscriptItem(BaseModel):
    channel: int | None = None
    text: str
    start: str | None = None  # ISO 8601 duration string, e.g., "PT1.23S"
    end: str | None = None  # ISO 8601 duration string, e.g., "PT1.23S"


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
    transcript: list[TranscriptItem] = Field(default_factory=list)


class WebSocketSessionStorage(BaseModel):
    """Temporary in-memory storage for WebSocket session state"""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    client_seq: int = 0
    server_seq: int = 0
    conversation_id: str | None = None
    # Provider-specific speech session storage
    speech_session: Any | None = None


class Error(BaseModel):
    """Pydantic model to model Error response"""

    code: str
    message: str


class HealthCheckResponse(BaseModel):
    """Pydantic model to model Health Check response"""

    status: str
    error: Error | None = None


class ConversationsResponse(BaseModel):
    """Pydantic model to model Conversations response"""

    count: int
    conversations: list[Conversation] = Field(default_factory=list)


class AzureAISpeechSession(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    audio_buffer: speechsdk.audio.PushAudioInputStream
    raw_audio: bytearray
    media: dict[str, Any]
    recognize_task: asyncio.Task
