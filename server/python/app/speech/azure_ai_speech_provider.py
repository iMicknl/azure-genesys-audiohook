import asyncio
import json
import os
from typing import Any

import azure.cognitiveservices.speech as speechsdk

from ..enums import AzureGenesysEvent
from ..models import WebSocketSessionStorage
from ..utils.identity import get_speech_token
from .speech_provider import SpeechProvider


class AzureAISpeechProvider(SpeechProvider):
    """Azure AI Speech implementation of SpeechProvider."""

    def __init__(
        self,
        conversations_store,
        send_event_callback,
        logger,
    ):
        self.conversations_store = conversations_store
        self.send_event = send_event_callback
        self.logger = logger

        # Load configuration from environment
        self.region = os.getenv("AZURE_SPEECH_REGION")
        self.speech_key = os.getenv("AZURE_SPEECH_KEY")
        self.speech_resource_id = os.getenv("AZURE_SPEECH_RESOURCE_ID")
        languages = os.getenv("AZURE_SPEECH_LANGUAGES", "en-US")
        self.languages = languages.split(",") if languages else ["en-US"]

    async def initialize_session(
        self,
        session_id: str,
        ws_session: Any,
        media: dict[str, Any],
    ) -> None:
        """Initialize speech session resources for a new conversation."""
        # Create audio stream format and buffer
        audio_format = speechsdk.audio.AudioStreamFormat(
            samples_per_second=media["rate"],
            bits_per_sample=8,
            channels=len(media["channels"]),
            wave_stream_format=speechsdk.AudioStreamWaveFormat.MULAW,
        )
        stream = speechsdk.audio.PushAudioInputStream(stream_format=audio_format)

        # Store provider-specific session info
        ws_session.speech_session = {
            "audio_buffer": stream,
            "raw_audio": bytearray(),
            "media": media,
            "recognize_task": None,
        }

        # Start recognition task in background
        ws_session.speech_session["recognize_task"] = asyncio.create_task(
            self._recognize_speech(session_id, ws_session)
        )

    async def handle_audio_frame(
        self,
        session_id: str,
        ws_session: Any,
        media: dict[str, Any],
        data: bytes,
    ) -> None:
        """Handle incoming audio frames by writing to buffer and storing raw audio."""
        session = getattr(ws_session, "speech_session", None)
        if not session:
            self.logger.error(f"[{session_id}] Speech session not initialized.")
            return

        # Append frame to stream and raw buffer
        try:
            session["audio_buffer"].write(data)
            session["raw_audio"] += data
        except Exception as ex:
            self.logger.error(f"[{session_id}] Failed to write audio frame: {ex}")

    async def shutdown_session(
        self, session_id: str, ws_session: WebSocketSessionStorage
    ) -> None:
        """Shutdown and cleanup speech session after conversation ends."""
        session = getattr(ws_session, "speech_session", None)
        if not session:
            return

        # Close the push stream to signal end of audio
        try:
            session["audio_buffer"].close()
        except Exception as ex:
            self.logger.warning(f"[{session_id}] Error closing audio buffer: {ex}")

        # Await recognition completion
        recognize_task = session.get("recognize_task")
        if recognize_task:
            try:
                await recognize_task
            except Exception as ex:
                self.logger.error(
                    f"[{session_id}] Error awaiting recognition task: {ex}"
                )

    async def close(self) -> None:
        """Cleanup any global resources when server shuts down."""
        # No global resources to clean up for Azure AI Speech provider
        return

    async def _recognize_speech(
        self, session_id: str, ws_session: WebSocketSessionStorage
    ) -> None:
        """Internal method to perform continuous speech recognition."""
        session = ws_session.speech_session
        media = session.get("media")

        # Determine multichannel based on media channels
        # conversation = await self.conversations_store.get(ws_session.conversation_id)
        is_multichannel = len(media.get("channels", [])) > 1 if media else False

        # Configure speech
        region = self.region
        endpoint = None
        if is_multichannel and region:
            endpoint = (
                f"wss://{region}.stt.speech.microsoft.com"
                "/speech/recognition/conversation/cognitiveservices/v1?setfeature=multichannel2"
            )

        # Create SpeechConfig
        if self.speech_key:
            speech_config = speechsdk.SpeechConfig(
                subscription=self.speech_key,
                region=None if is_multichannel else region,
                endpoint=endpoint,
            )
        else:
            auth_token = get_speech_token(self.speech_resource_id)
            speech_config = speechsdk.SpeechConfig(
                auth_token=auth_token,
                region=None if is_multichannel else region,
                endpoint=endpoint,
            )

        # Language detection/configuration
        if len(self.languages) > 1:
            auto_detect = None
            speech_config.speech_recognition_language = self.languages[0]
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
            speechsdk.PropertyId.Speech_SegmentationStrategy,
            "Semantic",
        )

        # Configure audio input from push stream
        audio_config = speechsdk.audio.AudioConfig(stream=session["audio_buffer"])
        recognizer = speechsdk.SpeechRecognizer(
            speech_config=speech_config,
            audio_config=audio_config,
            auto_detect_source_language_config=auto_detect,
        )

        # Setup event callbacks and synchronization
        loop = asyncio.get_running_loop()
        recognition_done = asyncio.Event()

        def recognizing_cb(evt):
            self.logger.info(f"[{session_id}] Recognizing: {evt.result.text}")

        def recognized_cb(evt):
            result_json = json.loads(evt.result.json)
            status = result_json.get("RecognitionStatus")
            if status == "InitialSilenceTimeout":
                self.logger.warning(f"[{session_id}] Initial silence timeout.")
                return

            text = evt.result.text
            # Ensure sentence punctuation
            if text and text[-1] not in ".!?":
                text = text[0].upper() + text[1:] + "."
            elif text and not text[0].isupper():
                text = text[0].upper() + text[1:]

            # Timestamps
            offset = result_json.get("Offset", 0)
            duration = result_json.get("Duration", 0)
            start = f"PT{offset / 10_000_000:.2f}S"
            end = f"PT{(offset + duration) / 10_000_000:.2f}S"

            # Update transcript store
            async def update_transcript():
                transcript_item = {
                    "channel": result_json.get("Channel") if is_multichannel else None,
                    "text": text,
                    "start": start,
                    "end": end,
                }
                await self.conversations_store.append_transcript(
                    ws_session.conversation_id, transcript_item
                )

            asyncio.run_coroutine_threadsafe(update_transcript(), loop)

            # Send partial transcript event
            asyncio.run_coroutine_threadsafe(
                self.send_event(
                    event=AzureGenesysEvent.PARTIAL_TRANSCRIPT,
                    session_id=session_id,
                    message={
                        "text": text,
                        "channel": result_json.get("Channel")
                        if is_multichannel
                        else None,
                        "start": start,
                        "end": end,
                        "data": result_json,
                    },
                ),
                loop,
            )

        def session_stopped_cb(evt):
            self.logger.info(f"[{session_id}] Session stopped: {evt.session_id}")
            recognition_done.set()

        # Connect callbacks
        recognizer.recognizing.connect(
            lambda evt: loop.call_soon_threadsafe(recognizing_cb, evt)
        )
        recognizer.recognized.connect(
            lambda evt: loop.call_soon_threadsafe(recognized_cb, evt)
        )
        recognizer.session_stopped.connect(
            lambda evt: loop.call_soon_threadsafe(session_stopped_cb, evt)
        )

        # Start recognition
        self.logger.info(f"[{session_id}] Starting continuous recognition.")
        await asyncio.to_thread(recognizer.start_continuous_recognition_async().get)

        # Wait until done
        await recognition_done.wait()

        # Stop the recognizer
        await asyncio.to_thread(recognizer.stop_continuous_recognition_async().get)
        self.logger.info(f"[{session_id}] Continuous recognition stopped.")
