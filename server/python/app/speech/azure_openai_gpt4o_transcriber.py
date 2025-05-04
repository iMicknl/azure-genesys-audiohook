import asyncio
import base64
import json
import logging
import os
from typing import Any, Awaitable, Callable

import websockets

from ..enums import AzureGenesysEvent
from ..models import WebSocketSessionStorage
from ..storage.base_conversation_store import ConversationStore
from ..utils.audio import split_stream
from .speech_provider import SpeechProvider

logger = logging.getLogger(__name__)


class AzureOpenAIGPT4oTranscriber(SpeechProvider):
    """Azure OpenAI GPT-4o streaming transcription provider."""

    supported_languages: list[str] = []

    def __init__(
        self,
        conversations_store: ConversationStore,
        send_event_callback: Callable[..., Awaitable[None]],
        logger_: logging.Logger = logger,
    ) -> None:
        self.conversations_store = conversations_store
        self.send_event = send_event_callback
        self.logger = logger_
        self.endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        self.api_key = os.getenv("AZURE_OPENAI_KEY")
        languages = os.getenv("AZURE_OPENAI_LANGUAGES", "en")
        self.supported_languages = [
            lang.strip() for lang in languages.split(",") if lang.strip()
        ]
        if not self.endpoint or not self.api_key:
            raise RuntimeError(
                "AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_KEY must be set in environment."
            )

    async def initialize_session(
        self,
        session_id: str,
        ws_session: WebSocketSessionStorage,
        media: dict[str, Any],
    ) -> None:
        """Create OpenAI transcription session and open websocket connection."""
        ws_url = (
            self.endpoint.replace("https://", "wss://")
            + "/openai/realtime?api-version=2024-10-01-preview&deployment=gpt-4o-transcribe&intent=transcription"
        )
        print(ws_url)
        headers = {
            "Authorization": f"Bearer {self.api_key}",
        }
        ws = await websockets.connect(ws_url, additional_headers=headers)
        # Send initial session config
        session_config = {
            "type": "transcription_session.update",
            "session": {
                "input_audio_format": "pcm16",
                "input_audio_transcription": {
                    "model": "gpt-4o-transcribe",
                    "language": self.supported_languages[0],
                    "prompt": "Transcribe the incoming audio in real time.",
                },
                "turn_detection": {"type": "server_vad", "silence_duration_ms": 800},
            },
        }
        await ws.send(json.dumps(session_config))
        ws_session.speech_session = {
            "ws": ws,
            "audio_buffer": bytearray(),
            "media": media,
            "send_task": asyncio.create_task(
                self._send_audio_loop(session_id, ws_session)
            ),
            "recv_task": asyncio.create_task(
                self._receive_events(session_id, ws_session)
            ),
            "shutdown_event": asyncio.Event(),
        }

    async def handle_audio_frame(
        self,
        session_id: str,
        ws_session: WebSocketSessionStorage,
        media: dict[str, Any],
        data: bytes,
    ) -> None:
        """Feed incoming PCM16 audio to the websocket stream."""
        speech_session = ws_session.speech_session
        if not speech_session:
            self.logger.error(
                "Speech session not initialized for session_id=%s", session_id
            )
            return
        # If stereo, split and use only customer channel (or both if needed)
        if media.get("channels", 1) > 1:
            customer, _ = split_stream(data)
            chunk = customer
        else:
            chunk = data
        speech_session["audio_buffer"] += chunk

    async def shutdown_session(
        self,
        session_id: str,
        ws_session: WebSocketSessionStorage,
    ) -> None:
        """Signal end of audio and close websocket."""
        speech_session = ws_session.speech_session
        if not speech_session:
            return
        # Signal send loop to finish
        speech_session["shutdown_event"].set()
        # Wait for send/recv tasks to finish
        await asyncio.gather(
            speech_session["send_task"],
            speech_session["recv_task"],
            return_exceptions=True,
        )
        # Close websocket
        ws = speech_session["ws"]
        await ws.close()
        ws_session.speech_session = None

    async def close(self) -> None:
        """No global cleanup needed."""
        return None

    async def _send_audio_loop(
        self, session_id: str, ws_session: WebSocketSessionStorage
    ) -> None:
        """Send audio chunks over websocket as they arrive."""
        speech_session = ws_session.speech_session
        ws = speech_session["ws"]
        audio_buffer = speech_session["audio_buffer"]
        shutdown_event = speech_session["shutdown_event"]
        chunk_size = 1024
        try:
            while not shutdown_event.is_set() or len(audio_buffer) > 0:
                if len(audio_buffer) == 0:
                    await asyncio.sleep(0.01)
                    continue
                chunk = audio_buffer[:chunk_size]
                del audio_buffer[:chunk_size]
                audio_b64 = base64.b64encode(chunk).decode("utf-8")
                await ws.send(
                    json.dumps(
                        {"type": "input_audio_buffer.append", "audio": audio_b64}
                    )
                )
                await asyncio.sleep(0.02)  # Simulate real-time
            # After shutdown, send commit
            await ws.send(json.dumps({"type": "input_audio_buffer.commit"}))
        except Exception as ex:
            self.logger.error("Error in send_audio_loop: %s", ex)

    async def _receive_events(
        self, session_id: str, ws_session: WebSocketSessionStorage
    ) -> None:
        """Receive events from OpenAI and emit to conversation store/callback."""
        speech_session = ws_session.speech_session
        ws = speech_session["ws"]
        try:
            async for message in ws:
                try:
                    event = json.loads(message)
                    event_type = event.get("type")
                    if event_type == "input_audio_buffer.speech_stopped":
                        # Could be used to trigger commit if needed
                        pass
                    elif (
                        event_type
                        == "conversation.item.input_audio_transcription.delta"
                    ):
                        delta = event.get("delta", "")
                        await self.send_event(
                            AzureGenesysEvent.PARTIAL_TRANSCRIPT,
                            session_id=session_id,
                            transcript=delta,
                        )
                    elif (
                        event_type
                        == "conversation.item.input_audio_transcription.completed"
                    ):
                        transcript = event.get("transcript", "")
                        self.logger.debug(
                            "Transcript completed for session_id=%s: %s",
                            session_id,
                            transcript,
                        )

                    elif event_type == "error":
                        self.logger.error("OpenAI error event: %s", event.get("error"))
                    else:
                        self.logger.debug("OpenAI event: %s", event_type)
                except Exception as ex:
                    self.logger.error("Error processing OpenAI event: %s", ex)
        except Exception as e:
            self.logger.error("Error receiving events: %s", e)
