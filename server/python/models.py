from typing import Any
from dataclasses import dataclass, field


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


@dataclass(kw_only=True)
class HealthCheckResponse:
    """Dataclass to model Health Check response"""

    status: str
    connected_clients: int
    sessions: dict[str, ClientSession]
