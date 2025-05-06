from abc import ABC, abstractmethod
from typing import Any


class SpeechProvider(ABC):
    """Interface for speech providers."""

    supported_languages: list[str] = []

    @abstractmethod
    async def initialize_session(
        self, session_id: str, ws_session: Any, media: dict[str, Any]
    ) -> None:
        """Initialize speech session resources for a new conversation."""
        raise NotImplementedError

    @abstractmethod
    async def handle_audio_frame(
        self, session_id: str, ws_session: Any, media: dict[str, Any], data: bytes
    ) -> None:
        """Handle incoming audio frames."""
        raise NotImplementedError

    @abstractmethod
    async def shutdown_session(self, session_id: str, ws_session: Any) -> None:
        """Shutdown and cleanup speech session after conversation end."""
        raise NotImplementedError

    @abstractmethod
    async def close(self) -> None:
        """Cleanup resources when server is shutting down."""
        raise NotImplementedError
