import asyncio
import base64
import json
import logging
import os
from typing import Any, Awaitable, Callable

import websockets

from ..enums import AzureGenesysEvent
from ..models import TranscriptItem, WebSocketSessionStorage
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
        """Create two OpenAI transcription websocket connections: one for customer, one for agent."""
        ws_url = (
            self.endpoint.replace("https://", "wss://")
            + "/openai/realtime?api-version=2025-04-01-preview&intent=transcription"
        )
        headers = {
            "api-key": self.api_key,
        }

        async def create_ws_and_task(channel: int):
            ws = await websockets.connect(ws_url, additional_headers=headers)
            session_config = {
                "type": "transcription_session.update",
                "session": {
                    "input_audio_format": "g711_ulaw",
                    "input_audio_transcription": {
                        "model": "gpt-4o-transcribe",
                        "prompt": "Transcribe the incoming audio in real time.",
                        # "language": "",  # ISO-639-1 format
                    },
                    "input_audio_noise_reduction": {"type": "near_field"},
                    "turn_detection": {"type": "server_vad"},
                },
            }
            await ws.send(json.dumps(session_config))
            recv_task = asyncio.create_task(
                self._receive_events(session_id, ws_session, ws, channel)
            )
            return ws, recv_task

        # Create two websocket connections: channel 0 (customer), channel 1 (agent)
        ws_customer, recv_task_customer = await create_ws_and_task(0)
        ws_agent, recv_task_agent = await create_ws_and_task(1)

        ws_session.speech_session = {
            "ws_customer": ws_customer,
            "ws_agent": ws_agent,
            "media": media,
            "recv_task_customer": recv_task_customer,
            "recv_task_agent": recv_task_agent,
            "shutdown_event": asyncio.Event(),
        }

    async def handle_audio_frame(
        self,
        session_id: str,
        ws_session: WebSocketSessionStorage,
        media: dict[str, Any],
        data: bytes,
    ) -> None:
        """Send incoming audio directly to both OpenAI websockets (customer and agent channels)."""
        speech_session = ws_session.speech_session
        if not speech_session:
            self.logger.error(
                "Speech session not initialized for session_id=%s", session_id
            )
            return
        try:
            ws_customer = speech_session["ws_customer"]
            ws_agent = speech_session["ws_agent"]
            # If stereo, split and send both channels
            if len(media["channels"]) > 1:
                customer, agent = split_stream(data)
                # Send customer (channel 0)
                audio_b64_cust = base64.b64encode(customer).decode("utf-8")
                await ws_customer.send(
                    json.dumps(
                        {"type": "input_audio_buffer.append", "audio": audio_b64_cust}
                    )
                )
                # Send agent (channel 1)
                audio_b64_agent = base64.b64encode(agent).decode("utf-8")
                await ws_agent.send(
                    json.dumps(
                        {"type": "input_audio_buffer.append", "audio": audio_b64_agent}
                    )
                )
            else:
                # Mono: send to customer only
                audio_b64 = base64.b64encode(data).decode("utf-8")
                await ws_customer.send(
                    json.dumps(
                        {"type": "input_audio_buffer.append", "audio": audio_b64}
                    )
                )
        except Exception as ex:
            self.logger.error("Error sending audio frame to OpenAI websocket: %s", ex)

    async def shutdown_session(
        self,
        session_id: str,
        ws_session: WebSocketSessionStorage,
    ) -> None:
        """Signal end of audio and close both websockets."""
        speech_session = ws_session.speech_session
        if not speech_session:
            return
        # Signal shutdown
        speech_session["shutdown_event"].set()
        # Send commit to both websockets
        try:
            await speech_session["ws_customer"].send(
                json.dumps({"type": "input_audio_buffer.commit"})
            )
            await speech_session["ws_agent"].send(
                json.dumps({"type": "input_audio_buffer.commit"})
            )
        except Exception as ex:
            self.logger.error("Error sending commit to OpenAI websocket: %s", ex)
        # Wait for both receive tasks to finish
        await asyncio.gather(
            speech_session["recv_task_customer"],
            speech_session["recv_task_agent"],
            return_exceptions=True,
        )
        # Close both websockets
        try:
            await speech_session["ws_customer"].close()
            await speech_session["ws_agent"].close()
        except Exception as ex:
            self.logger.error("Error closing OpenAI websocket: %s", ex)
        ws_session.speech_session = None

    async def close(self) -> None:
        """No global cleanup needed."""
        return None

    async def _receive_events(
        self, session_id: str, ws_session: WebSocketSessionStorage, ws, channel: int
    ) -> None:
        """Receive events from OpenAI and emit to conversation store/callback. Channel is 0 (customer) or 1 (agent)."""
        try:
            async for message in ws:
                try:
                    event = json.loads(message)
                    event_type = event.get("type")

                    if event_type == "input_audio_buffer.speech_stopped":
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
                            channel=channel,
                        )
                    elif (
                        event_type
                        == "conversation.item.input_audio_transcription.completed"
                    ):
                        transcript = event["transcript"]
                        item = TranscriptItem(
                            channel=channel,
                            text=transcript,
                            start=None,
                            end=None,
                        )
                        await self.conversations_store.append_transcript(
                            ws_session.conversation_id, item
                        )

                        self.logger.debug(
                            "Transcript completed for session_id=%s channel=%d: %s",
                            session_id,
                            channel,
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
