import asyncio
import json
import logging
import os
from typing import Any, Awaitable, Callable, cast

import azure.cognitiveservices.speech as speechsdk

from ..enums import AzureGenesysEvent
from ..models import AzureAISpeechSession, WebSocketSessionStorage
from ..storage.base_conversation_store import ConversationStore
from ..utils.identity import get_speech_token
from .speech_provider import SpeechProvider


class AzureAISpeechProvider(SpeechProvider):
    """Azure AI Speech implementation of SpeechProvider."""

    def __init__(
        self,
        conversations_store: ConversationStore,
        send_event_callback: Callable[..., Awaitable[None]],
        logger: logging.Logger,
    ) -> None:
        self.conversations_store = conversations_store
        self.send_event = send_event_callback
        self.logger = logger

        # Load configuration from environment
        self.region: str | None = os.getenv("AZURE_SPEECH_REGION")
        self.speech_key: str | None = os.getenv("AZURE_SPEECH_KEY")
        self.speech_resource_id: str | None = os.getenv("AZURE_SPEECH_RESOURCE_ID")
        languages = os.getenv("AZURE_SPEECH_LANGUAGES", "en-US")
        self.languages: list[str] = languages.split(",") if languages else ["en-US"]

    async def initialize_session(
        self,
        session_id: str,
        ws_session: WebSocketSessionStorage,
        media: dict[str, Any],
    ) -> None:
        """Prepare audio push stream and launch recognition task."""
        audio_format = speechsdk.audio.AudioStreamFormat(
            samples_per_second=media["rate"],
            bits_per_sample=8,
            channels=len(media["channels"]),
            wave_stream_format=speechsdk.AudioStreamWaveFormat.MULAW,
        )
        stream = speechsdk.audio.PushAudioInputStream(stream_format=audio_format)

        ws_session.speech_session = AzureAISpeechSession(
            audio_buffer=stream,
            raw_audio=bytearray(),
            media=media,
            recognize_task=asyncio.create_task(
                self._recognize_speech(session_id, ws_session)
            ),
        )

    async def handle_audio_frame(
        self,
        session_id: str,
        ws_session: WebSocketSessionStorage,
        media: dict[str, Any],
        data: bytes,
    ) -> None:
        """Feed incoming chunks into the push stream and raw buffer."""
        if ws_session.speech_session is None:
            self.logger.error(f"[{session_id}] Session not initialized.")
            return

        try:
            speech_session = cast(AzureAISpeechSession, ws_session.speech_session)
            speech_session.audio_buffer.write(data)
        except Exception as ex:
            self.logger.error(f"[{session_id}] Write error: {ex}")

    async def shutdown_session(
        self,
        session_id: str,
        ws_session: WebSocketSessionStorage,
    ) -> None:
        """Signal end of audio and await recognition finish."""
        if ws_session.speech_session is None:
            self.logger.error(f"[{session_id}] Session not initialized.")
            return

        try:
            speech_session = cast(AzureAISpeechSession, ws_session.speech_session)
            speech_session.audio_buffer.close()
        except Exception as ex:
            self.logger.warning(f"[{session_id}] Close error: {ex}")

        task = speech_session.recognize_task
        if task:
            try:
                await task
            except Exception as ex:
                self.logger.error(f"[{session_id}] Recognition error: {ex}")

    async def close(self) -> None:
        """No global cleanup needed for Azure Speech."""
        return None

    async def _recognize_speech(
        self,
        session_id: str,
        ws_session: WebSocketSessionStorage,
    ) -> None:
        """
        Configure SpeechRecognizer, wire callbacks, and drive the
        continuous-recognition loop until the audio stream is closed.
        """

        speech_session = cast(AzureAISpeechSession, ws_session.speech_session)
        media = speech_session.media
        is_multichannel = bool(media.get("channels", []) and len(media["channels"]) > 1)

        region = self.region
        endpoint = None
        if is_multichannel and region:
            endpoint = (
                f"wss://{region}.stt.speech.microsoft.com"
                "/speech/recognition/conversation/cognitiveservices/v1?setfeature=multichannel2"
            )

        if self.speech_key:
            speech_config = speechsdk.SpeechConfig(
                subscription=self.speech_key,
                region=None if is_multichannel else region,
                endpoint=endpoint,
            )
        else:
            token = get_speech_token(self.speech_resource_id)
            speech_config = speechsdk.SpeechConfig(
                auth_token=token,
                region=None if is_multichannel else region,
                endpoint=endpoint,
            )

        if len(self.languages) > 1:
            speech_config.speech_recognition_language = self.languages[0]
            auto_detect = None
        else:
            auto_detect = speechsdk.languageconfig.AutoDetectSourceLanguageConfig(
                languages=self.languages
            )
            speech_config.set_property(
                speechsdk.PropertyId.SpeechServiceConnection_LanguageIdMode,
                "Continuous",
            )

        speech_config.output_format = speechsdk.OutputFormat.Detailed
        speech_config.request_word_level_timestamps()
        speech_config.enable_audio_logging()
        speech_config.set_profanity(speechsdk.ProfanityOption.Masked)
        speech_config.set_property(
            speechsdk.PropertyId.Speech_SegmentationStrategy, "Semantic"
        )

        audio_in = speechsdk.audio.AudioConfig(stream=speech_session.audio_buffer)
        recognizer = speechsdk.SpeechRecognizer(
            speech_config=speech_config,
            audio_config=audio_in,
            auto_detect_source_language_config=auto_detect,
        )

        loop = asyncio.get_running_loop()
        done_event = asyncio.Event()

        recognizer.recognizing.connect(
            lambda evt: loop.call_soon_threadsafe(self._on_recognizing, session_id, evt)
        )
        recognizer.recognized.connect(
            lambda evt: loop.call_soon_threadsafe(
                self._on_recognized,
                session_id,
                ws_session,
                is_multichannel,
                loop,
                evt,
            )
        )
        recognizer.session_stopped.connect(
            lambda evt: loop.call_soon_threadsafe(
                self._on_session_stopped, session_id, done_event, evt
            )
        )

        self.logger.info(f"[{session_id}] Starting continuous recognition.")
        await asyncio.to_thread(recognizer.start_continuous_recognition_async().get)
        await done_event.wait()
        await asyncio.to_thread(recognizer.stop_continuous_recognition_async().get)
        self.logger.info(f"[{session_id}] Recognition stopped.")

    def _on_recognizing(
        self, session_id: str, evt: speechsdk.SpeechRecognitionEventArgs
    ) -> None:
        """Log intermediate (partial) recognition results."""
        self.logger.info(f"[{session_id}] Recognizing: {evt.result.text}")

    def _on_recognized(
        self,
        session_id: str,
        ws_session: WebSocketSessionStorage,
        is_multichannel: bool,
        loop: asyncio.AbstractEventLoop,
        evt: speechsdk.SpeechRecognitionEventArgs,
    ) -> None:
        """Handle final recognition, update store, and emit partial transcript."""
        result = json.loads(evt.result.json)
        status = result.get("RecognitionStatus")
        if status == "InitialSilenceTimeout":
            self.logger.warning(f"[{session_id}] Initial silence timeout.")
            return

        text = evt.result.text or ""
        if text and text[-1] not in ".!?":
            text = text[0].upper() + text[1:] + "."
        elif text and not text[0].isupper():
            text = text[0].upper() + text[1:]

        offset = result.get("Offset", 0)
        duration = result.get("Duration", 0)
        start = f"PT{offset / 10_000_000:.2f}S"
        end = f"PT{(offset + duration) / 10_000_000:.2f}S"

        async def _update() -> None:
            item: dict[str, Any] = {
                "channel": result.get("Channel") if is_multichannel else None,
                "text": text,
                "start": start,
                "end": end,
            }
            await self.conversations_store.append_transcript(
                ws_session.conversation_id, item
            )

        asyncio.run_coroutine_threadsafe(_update(), loop)
        asyncio.run_coroutine_threadsafe(
            self.send_event(
                event=AzureGenesysEvent.PARTIAL_TRANSCRIPT,
                session_id=session_id,
                message={
                    "text": text,
                    "channel": result.get("Channel") if is_multichannel else None,
                    "start": start,
                    "end": end,
                    "data": result,
                },
            ),
            loop,
        )

    def _on_session_stopped(
        self,
        session_id: str,
        done_event: asyncio.Event,
        evt: speechsdk.SessionEventArgs,
    ) -> None:
        """Signal that continuous recognition has finished."""
        self.logger.info(f"[{session_id}] Session stopped: {evt.session_id}")
        done_event.set()
