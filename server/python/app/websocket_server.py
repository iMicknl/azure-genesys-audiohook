import asyncio
import functools
import json
import logging
import os
from typing import Any

import azure.cognitiveservices.speech as speechsdk
from azure.storage.blob.aio import BlobServiceClient
from quart import Quart, request, websocket

from .enums import (
    AzureGenesysEvent,
    ClientMessageType,
    CloseReason,
    DisconnectReason,
    ServerMessageType,
)
from .events.event_publisher import EventPublisher
from .models import (
    Conversation,
    ConversationsResponse,
    Error,
    HealthCheckResponse,
    WebSocketSessionStorage,
)
from .storage.base_conversation_store import ConversationStore
from .storage.conversation_store import get_conversation_store
from .storage.in_memory_conversation_store import (
    InMemoryConversationStore,
)
from .utils.audio import convert_to_wav
from .utils.identity import get_azure_credential_async, get_speech_token
from .utils.storage import upload_blob_file


class WebsocketServer:
    """Websocket server class"""

    active_ws_sessions: dict[str, WebSocketSessionStorage] = {}
    logger: logging.Logger = logging.getLogger(__name__)
    blob_service_client: BlobServiceClient | None = None
    conversations_store: ConversationStore | None = None
    event_publisher: EventPublisher | None = None

    def __init__(self):
        """Initialize the server"""
        self.app = Quart(__name__)
        self.setup_routes()
        self.app.before_serving(self.create_connections)
        self.app.after_serving(self.close_connections)

    def require_api_key(self, func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            api_key = os.getenv("WEBSOCKET_SERVER_API_KEY")
            header_key = request.headers.get("X-Api-Key")
            param_key = request.args.get("key")
            if api_key and (header_key == api_key or param_key == api_key):
                return await func(*args, **kwargs)
            return {
                "error": {
                    "code": "unauthorized",
                    "message": "Invalid or missing API key.",
                }
            }, 401

        return wrapper

    def setup_routes(self):
        """Setup the routes for the server"""
        self.app.route("/")(self.health_check)

        self.app.route("/api/conversations")(
            self.require_api_key(self.get_conversations)
        )
        self.app.route("/api/conversation/<conversation_id>")(
            self.require_api_key(self.get_conversation)
        )

        self.app.websocket("/audiohook/ws")(self.ws)

    async def create_connections(self):
        """Create connections before serving"""
        if connection_string := os.getenv("AZURE_STORAGE_CONNECTION_STRING"):
            self.blob_service_client = BlobServiceClient.from_connection_string(
                connection_string
            )
        elif account_url := os.getenv("AZURE_STORAGE_ACCOUNT_URL"):
            self.blob_service_client = BlobServiceClient(
                account_url, credential=get_azure_credential_async()
            )

        self.conversations_store = get_conversation_store()

        if os.getenv("AZURE_EVENT_HUB_HOSTNAME") or os.getenv(
            "AZURE_EVENT_HUB_CONNECTION_STRING"
        ):
            self.event_publisher = EventPublisher()

    async def close_connections(self):
        """Close connections after serving"""
        if self.blob_service_client:
            await self.blob_service_client.close()

        if self.event_publisher:
            await self.event_publisher.close()

        if self.conversations_store:
            await self.conversations_store.close()

    async def health_check(self):
        """
        Health check endpoint

        https://learn.microsoft.com/en-us/azure/container-apps/health-probes
        """

        # TODO abstract this to a health check class

        # Check conversations store (CosmosDB or in-memory)
        try:
            # InMemoryConversationStore is always healthy
            if isinstance(self.conversations_store, InMemoryConversationStore):
                pass
            else:
                # Try a simple list operation (should raise if CosmosDB is unreachable or misconfigured)
                await asyncio.wait_for(
                    self.conversations_store.list(active=None), timeout=5
                )
        except Exception as e:
            self.logger.error(
                f"Health check failed: Conversations store unhealthy: {e}"
            )

            return HealthCheckResponse(
                status="unhealthy",
                error=Error(
                    code="conversations_store",
                    message=f"Conversations store is unhealthy. {str(e)}.",
                ),
            ).model_dump(), 503

        # Check Azure Blob Storage (if configured)
        if self.blob_service_client:
            try:
                # get_service_properties is a lightweight call
                await asyncio.wait_for(
                    self.blob_service_client.get_service_properties(), timeout=5
                )
            except Exception as e:
                self.logger.error(f"Health check failed: Blob Storage unhealthy: {e}")

                return HealthCheckResponse(
                    status="unhealthy",
                    error=Error(
                        code="blob_storage",
                        message=f"Blob storage is unhealthy. {str(e)}.",
                    ),
                ).model_dump(), 503

        # Check Azure Event Hub (if configured)
        if self.event_publisher:
            try:
                # Try to create a batch (does not send, but checks connection/permissions)
                await asyncio.wait_for(
                    self.event_publisher.producer_client.create_batch(), timeout=5
                )
            except Exception as e:
                self.logger.error(f"Health check failed: Event Hub unhealthy: {e}")

                return HealthCheckResponse(
                    status="unhealthy",
                    error=Error(
                        code="event_hub",
                        message=f"Event Hub is unhealthy. {str(e)}.",
                    ),
                ).model_dump(), 503

        # TODO check Azure Speech Service (if configured)

        return HealthCheckResponse(status="healthy").model_dump(exclude_none=True), 200

    async def get_conversations(self) -> Any:
        """
        Retrieve a list of conversations.
        """
        # TODO implement pagination
        active = request.args.get("active")
        if isinstance(active, str):
            active = {"true": True, "false": False}.get(active.lower())

        conversations = await self.conversations_store.list(active=active)

        return ConversationsResponse(
            count=len(conversations),
            conversations=conversations,
        ).model_dump(exclude_none=True), 200

    async def get_conversation(self, conversation_id) -> Any:
        """
        Retrieve a client session by its conversation ID.
        """
        conversation = await self.conversations_store.get(conversation_id)
        if conversation:
            return conversation.model_dump(exclude_none=True), 200
        return {
            "error": {
                "code": "unknown_conversation",
                "message": f"No conversation found for conversation ID '{conversation_id}'. Please verify the ID and try again.",
            }
        }, 404

    async def ws(self):
        """Websocket endpoint"""
        headers = websocket.headers
        remote = websocket.remote_addr
        session_id = headers["Audiohook-Session-Id"]

        if not session_id:
            return await self.disconnect(
                reason=DisconnectReason.ERROR,
                message="No session ID provided",
                code=1008,
                session_id=None,
            )

        if headers["X-Api-Key"] != os.getenv("WEBSOCKET_SERVER_API_KEY"):
            return await self.disconnect(
                reason=DisconnectReason.UNAUTHORIZED,
                message="Invalid API Key",
                code=3000,
                session_id=session_id,
            )

        await websocket.accept()

        # Save new client in persistent storage
        self.active_ws_sessions[session_id] = WebSocketSessionStorage()

        correlation_id = headers["Audiohook-Correlation-Id"]
        self.logger.info(f"[{session_id}] Accepted websocket connection from {remote}")
        self.logger.info(f"[{session_id}] Correlation ID: {correlation_id}")

        signature_input = headers["Signature-Input"]
        signature = headers["Signature"]
        client_secret = os.getenv("WEBSOCKET_SERVER_CLIENT_SECRET")

        # TODO implement signature validation
        if not signature_input and not signature and not client_secret:
            return await self.disconnect(
                reason=DisconnectReason.UNAUTHORIZED,
                message="Invalid signature",
                code=3000,
                session_id=session_id,
            )

        # Open the websocket connection and start receiving data (messages / audio)
        try:
            while True:
                data = await websocket.receive()

                if isinstance(data, str):
                    await self.handle_incoming_message(json.loads(data))
                elif isinstance(data, bytes):
                    await self.handle_bytes(data, session_id)
                else:
                    self.logger.debug(
                        f"[{session_id}] Received unknown data type: {type(data)}: {data}"
                    )
        except asyncio.CancelledError:
            self.logger.warning(
                f"[{session_id}] Websocket connection cancelled/disconnected."
            )

            # Note: AudioHook currently does not support re-establishing session connections.
            # Set the client session to inactive and remove the temporary client session
            if session_id in self.active_ws_sessions:
                ws_session = self.active_ws_sessions[session_id]
                await self.conversations_store.set_active(
                    ws_session.conversation_id, False
                )
                del self.active_ws_sessions[session_id]

    async def disconnect(
        self, reason: DisconnectReason, message: str, code: int, session_id: str | None
    ):
        """
        Disconnect the websocket connection gracefully.

        Using sequence number 1 for the disconnect message as per the protocol specification,
        since the client did not send an open message.
        """
        self.logger.warning(message)
        await websocket.send_json(
            {
                "version": "2",
                "type": ServerMessageType.DISCONNECT,
                "seq": 1,
                "clientseq": 1,
                "id": session_id,
                "parameters": {
                    "reason": reason,
                    "info": message,
                },
            }
        )
        return await websocket.close(code)

    async def send_message(
        self,
        type: ServerMessageType,
        client_message: dict,
        parameters: dict = {},
    ):
        """Send a message to the client."""
        session_id = client_message["id"]
        ws_session = self.active_ws_sessions[session_id]
        ws_session.server_seq += 1

        server_message = {
            "version": "2",
            "type": type,
            "seq": ws_session.server_seq,
            "clientseq": client_message["seq"],
            "id": session_id,
            "parameters": parameters,
        }
        self.logger.info(f"[{session_id}] Server sending message with type {type}.")
        self.logger.debug(server_message)
        await websocket.send_json(server_message)

    async def handle_incoming_message(self, message: dict):
        """Handle incoming messages (JSON)."""
        session_id = message["id"]
        message_type = message["type"]

        # Validate sequence number
        ws_session = self.active_ws_sessions[session_id]
        if message["seq"] != ws_session.client_seq + 1:
            await self.disconnect(
                reason=DisconnectReason.ERROR,
                message=f"Sequence number mismatch: received {message['seq']}, expected {ws_session.client_seq + 1}",
                code=3000,
                session_id=session_id,
            )

        # Store new sequence number
        ws_session.client_seq = message["seq"]

        match message_type:
            case ClientMessageType.OPEN:
                await self.handle_open_message(message)
            case ClientMessageType.PING:
                await self.handle_ping_message(message)
            case ClientMessageType.UPDATE:
                await self.handle_update_message(message)
            case ClientMessageType.CLOSE:
                await self.handle_close_message(message)
            case _:
                self.logger.info(
                    f"[{session_id}] Unknown message type: {message['type']} : {message}"
                )

    async def handle_ping_message(self, message: dict):
        """
        Handle a ping message from the client. Note that these ping/pong messages are a protocol feature distinct from the WebSocket
        ping/pong messages (which are not used).

        See https://developer.genesys.cloud/devapps/audiohook/protocol-reference#ping
        """
        await self.send_message(type=ServerMessageType.PONG, client_message=message)

        session_id = message["id"]
        ws_session = self.active_ws_sessions[session_id]

        if message["parameters"].get("rtt"):
            await self.conversations_store.append_rtt(
                ws_session.conversation_id, message["parameters"]["rtt"]
            )

    async def handle_open_message(self, message: dict):
        """
        Reply to an open message from the client. The server must respond to an open message with an "opened" message.

        Once the WebSocket connection has been established, the client initiates an open transaction. It provides the server with session information and negotiates the media format.
        The client will not send audio until the server completes the open transaction by responding with and "opened" message.

        See https://developer.genesys.cloud/devapps/audiohook/session-walkthrough#open-transaction
        """
        parameters = message["parameters"]
        conversation_id = parameters["conversationId"]
        ani = parameters["participant"]["ani"]
        ani_name = parameters["participant"]["aniName"]
        dnis = parameters["participant"]["dnis"]
        session_id = message["id"]
        media = parameters["media"]
        position = message["position"]

        # Store conversation_id in the temp session storage
        ws_session = self.active_ws_sessions[session_id]
        ws_session.conversation_id = conversation_id

        # Handle connection probe
        # See https://developer.genesys.cloud/devapps/audiohook/patterns-and-practices#connection-probe
        if conversation_id == "00000000-0000-0000-0000-000000000000":
            await self.handle_connection_probe(message)
            return

        self.logger.info(
            f"[{session_id}] Session opened with conversation ID: {conversation_id}, ani: {ani}, ANI Name: {ani_name}, DNIS: {dnis}, Position: {position}"
        )
        self.logger.info(f"[{session_id}] Available media: {media}")

        # Select stereo media if available, otherwise fallback to the first media format
        selected_media = next(
            (
                m
                for m in media
                if len(m["channels"]) == 2
                and {"internal", "external"}.issubset(m["channels"])
            ),
            media[0],
        )

        # Save/update persistent state
        conversation = Conversation(
            id=conversation_id,
            session_id=session_id,
            ani=ani,
            ani_name=ani_name,
            dnis=dnis,
            media=selected_media,
            position=position,
        )
        await self.conversations_store.set(conversation)

        await self.send_message(
            type=ServerMessageType.OPENED,
            client_message=message,
            parameters={
                "startPaused": False,
                "media": [selected_media],
            },
        )

        self.logger.info(f"[{session_id}] Session opened with media: {selected_media}")

        asyncio.create_task(
            self.send_event(
                event=AzureGenesysEvent.SESSION_STARTED,
                session_id=session_id,
                message={
                    "ani": ani,
                    "ani-name": ani_name,
                    "conversation-id": conversation_id,
                    "dnis": dnis,
                    "media": selected_media,
                    "position": position,
                },
                properties={},
            )
        )

    async def handle_update_message(self, message: dict):
        """Handle update message"""
        parameters = message["parameters"]
        language = parameters["language"]
        session_id = message["id"]

        self.logger.info(f"[{session_id}] Received update: language {language}")

    async def handle_close_message(self, message: dict):
        """Handle close message"""
        parameters = message["parameters"]
        session_id = message["id"]
        ws_session = self.active_ws_sessions[session_id]
        conversation_id = ws_session.conversation_id

        # Handle connection probe
        # See https://developer.genesys.cloud/devapps/audiohook/patterns-and-practices#connection-probe
        if conversation_id == "00000000-0000-0000-0000-000000000000":
            await self.send_message(
                type=ServerMessageType.CLOSED, client_message=message
            )

            if session_id in self.active_ws_sessions:
                del self.active_ws_sessions[session_id]

            return

        conversation = await self.conversations_store.get(conversation_id)

        # Close audio buffer (and recognition) if the session is ended
        if ws_session and ws_session.audio_buffer:
            ws_session.audio_buffer.close()

        if parameters["reason"] == CloseReason.END:
            if conversation and conversation.media:
                await self.send_event(
                    event=AzureGenesysEvent.TRANSCRIPT_AVAILABLE,
                    session_id=session_id,
                    message={"transcript": conversation.transcript},
                )

                # Save WAV file from raw audio buffer
                # TODO retrieve raw bytes from PushAudioInputStream to avoid saving two buffers
                wav_file = convert_to_wav(
                    format=conversation.media["format"],
                    audio_data=ws_session.raw_audio_buffer,
                    channels=len(conversation.media["channels"]),
                    sample_width=2,
                    frame_rate=conversation.media["rate"],
                )

                # Upload the WAV file to Azure Blob Storage
                if self.blob_service_client:
                    self.logger.debug(
                        f"[{session_id}] Saving WAV file to Azure Blob Storage ({session_id}.wav)."
                    )

                    try:
                        await upload_blob_file(
                            blob_service_client=self.blob_service_client,
                            container_name=os.getenv(
                                "AZURE_STORAGE_ACCOUNT_CONTAINER", "audio"
                            ),
                            file_name=f"{session_id}.wav",
                            data=wav_file,
                            content_type="audio/wav",
                        )

                        self.logger.info(
                            f"[{session_id}] WAV file saved to Azure Blob Storage: {session_id}.wav"
                        )

                        await self.send_event(
                            event=AzureGenesysEvent.RECORDING_AVAILABLE,
                            session_id=session_id,
                            message={"filename": f"{session_id}.wav"},
                        )
                    except Exception as e:
                        self.logger.error(
                            f"[{session_id}] Failed to upload WAV file to Azure Blob Storage: {e}"
                        )

            await self.send_message(
                type=ServerMessageType.CLOSED, client_message=message
            )

            await websocket.close(1000)

            # Set the client session to inactive and remove the temporary client session
            await self.conversations_store.set_active(conversation_id, False)
            if session_id in self.active_ws_sessions:
                del self.active_ws_sessions[session_id]

    async def handle_connection_probe(self, message: dict):
        """
        Handle connection probe

        To verify configuration settings before they are committed in the administration interface, the Genesys Cloud client attempts to establish a WebSocket connection to the configured URI followed by a synthetic AudioHook session.
        This connection probe and synthetic session helps flagging integration configuration issues and verify minimal server compliance without needing manual test calls.
        """
        session_id = message["id"]

        self.logger.info(
            f"[{session_id}] Connection probe. Conversation should not be logged and transcribed."
        )

        await self.send_message(
            type=ServerMessageType.OPENED,
            client_message=message,
            parameters={
                "startPaused": False,
                "media": [],
            },
        )

    async def handle_bytes(self, data: bytes, session_id: str):
        """
        Handles audio stream in u-Law ("PCMU")

        The audio in the frames for PCMU are headerless and the samples of two-channel streams are interleaved. For example, a 100ms audio frame in the format negotiated in the above example (PCMU, two channels, 8000Hz sample rate) would comprise 1600 bytes and have the following layout:
        The number of samples per frame is variable and is up to the client. There is a tradeoff between higher latency (larger frames) and higher overhead (smaller frames). The client will guarantee that frames only contain whole samples for all channels (i.e. the bytes of individual samples will not be split across frames). The server must not make any assumptions about audio frame sizes and maintain a timeline of the audio stream by counting the samples.
        The position property in the message header represents the current position in the audio stream from the client's perspective when it sent the message. It is reported as time represented as ISO8601 Duration to avoid sample-rate dependence. It is computed as:

        position=\frac{samplesProcessed}{sampleRate}
        """
        ws_session = self.active_ws_sessions[session_id]
        conversation_id = ws_session.conversation_id
        conversation = await self.conversations_store.get(conversation_id)
        media = conversation.media

        self.logger.debug(f"[{session_id}] Received {len(data)} bytes of audio data.")

        if ws_session.audio_buffer is None:
            self.logger.info(
                f"[{session_id}] type {media['type']}, format {media['format']}, rate {media['rate']}, channels {len(media['channels'])}"
            )

            audio_format = speechsdk.audio.AudioStreamFormat(
                samples_per_second=media["rate"],
                bits_per_sample=8,
                channels=len(media["channels"]),
                wave_stream_format=speechsdk.AudioStreamWaveFormat.MULAW,
            )

            stream = speechsdk.audio.PushAudioInputStream(stream_format=audio_format)
            ws_session.audio_buffer = stream
            ws_session.raw_audio_buffer = bytearray()

            # Start the synchronous speech recognition as a asyncio task
            ws_session.recognize_task = asyncio.create_task(
                self.recognize_speech(session_id)
            )

        # Append the buffers to the audio stream
        ws_session.audio_buffer.write(data)
        ws_session.raw_audio_buffer += data

    async def send_event(
        self,
        event: AzureGenesysEvent,
        session_id: str,
        message: dict[str, Any],
        properties: dict[str, str] | None = {},
    ):
        """Send an JSON event to Azure Event Hub using the EventPublisher abstraction."""
        if not self.event_publisher:
            return

        if session_id in self.active_ws_sessions:
            # Get the conversation ID from the active WebSocket session
            ws_session = self.active_ws_sessions[session_id]
            await self.event_publisher.send_event(
                event_type=f"azure-genesys-audiohook.{event}",
                conversation_id=ws_session.conversation_id,
                message=message,
                properties=properties,
            )
            self.logger.debug(f"[{session_id}] Sending event: {event} {message}")

    async def recognize_speech(self, session_id: str):
        """Recognize speech from audio buffer using Azure Speech to Text."""

        # Determine speech configuration based on channel count and authentication method
        # Use multichannel (preview) for stereo calls
        ws_session = self.active_ws_sessions[session_id]
        conversation_id = ws_session.conversation_id
        conversation = await self.conversations_store.get(conversation_id)

        is_multichannel = (
            len(conversation.media["channels"]) > 1
            if conversation and conversation.media
            else False
        )
        region = os.environ["AZURE_SPEECH_REGION"]
        endpoint = (
            f"wss://{region}.stt.speech.microsoft.com/speech/recognition/conversation/cognitiveservices/v1?setfeature=multichannel2"
            if is_multichannel
            else None
        )

        # Create speech config with appropriate authentication (speech key vs managed identity)
        if speech_key := os.getenv("AZURE_SPEECH_KEY"):
            speech_config = speechsdk.SpeechConfig(
                subscription=speech_key,
                region=None if is_multichannel else region,
                endpoint=endpoint,
            )
        else:
            auth_token = get_speech_token(os.environ["AZURE_SPEECH_RESOURCE_ID"])
            speech_config = speechsdk.SpeechConfig(
                auth_token=auth_token,
                region=None if is_multichannel else region,
                endpoint=endpoint,
            )

        loop = asyncio.get_running_loop()
        recognition_done = asyncio.Event()

        # Speech configuration
        languages = os.getenv("AZURE_SPEECH_LANGUAGES", "en-US").split(",")

        if len(languages) > 1:
            auto_detect_source_language_config = None
            speech_config.speech_recognition_language = languages[
                0
            ]  # Set to the only available language
        else:
            auto_detect_source_language_config = (
                speechsdk.languageconfig.AutoDetectSourceLanguageConfig(
                    languages=languages
                )
            )
            speech_config.set_property(
                property_id=speechsdk.PropertyId.SpeechServiceConnection_LanguageIdMode,
                value="Continuous",
            )

        speech_config.output_format = speechsdk.OutputFormat.Detailed
        speech_config.request_word_level_timestamps()
        speech_config.enable_audio_logging()
        speech_config.set_profanity(speechsdk.ProfanityOption.Masked)

        # Enable Semantic Segmentation (preview) (en-us only)
        # https://learn.microsoft.com/en-us/azure/ai-services/speech-service/how-to-recognize-speech?pivots=programming-language-python#semantic-segmentation
        speech_config.set_property(
            speechsdk.PropertyId.Speech_SegmentationStrategy, "Semantic"
        )

        audio_config = speechsdk.audio.AudioConfig(
            stream=self.active_ws_sessions[session_id].audio_buffer
        )
        speech_recognizer = speechsdk.SpeechRecognizer(
            speech_config=speech_config,
            audio_config=audio_config,
            auto_detect_source_language_config=auto_detect_source_language_config,
        )

        # Enable phrase list
        # https://learn.microsoft.com/en-us/azure/ai-services/speech-service/improve-accuracy-phrase-list?tabs=terminal&pivots=programming-language-python
        phrase_list_grammar = speechsdk.PhraseListGrammar.from_recognizer(
            speech_recognizer
        )
        phrase_list_grammar.addPhrase("Contoso")

        # Connect callbacks to the events fired by the speech recognizer
        def recognizing_cb(event: speechsdk.SpeechRecognitionEventArgs):
            """Callback that continuously logs the recognized speech."""
            self.logger.info(f"[{session_id}] Recognizing: {event.result.text}")
            self.logger.debug(f"[{session_id}] Recognizing JSON: {event.result.json}")

        def recognized_cb(event: speechsdk.SpeechRecognitionEventArgs):
            """Callback that logs the recognized speech once the recognition is done."""
            self.logger.info(f"[{session_id}] Recognized: {event.result.text}")
            self.logger.debug(f"[{session_id}] Recognized JSON: {event.result.json}")
            json_data = json.loads(event.result.json)

            if json_data["RecognitionStatus"] == "InitialSilenceTimeout":
                self.logger.warning(
                    f"[{session_id}] Initial silence timeout. No speech detected."
                )
                return

            text = event.result.text

            # Capitalize first letter and add period if missing proper sentence ending
            if text and not any(
                text.endswith(end) for end in [".", "!", "?", ":", ";"]
            ):
                text = text[0].upper() + text[1:] + "."
            elif text and not text[0].isupper():
                text = text[0].upper() + text[1:]

            # Calculate start and end time in seconds
            offset_100ns = json_data.get("Offset", 0)
            duration_100ns = json_data.get("Duration", 0)
            start_sec = offset_100ns / 10_000_000
            end_sec = (offset_100ns + duration_100ns) / 10_000_000

            def to_iso8601(seconds):
                return f"PT{seconds:.2f}S"

            # Store transcript in persistent storage
            async def update_transcript():
                ws_session = self.active_ws_sessions[session_id]
                transcript_item = {
                    "channel": json_data["Channel"] if is_multichannel else None,
                    "text": text,
                    "start": to_iso8601(start_sec),
                    "end": to_iso8601(end_sec),
                }

                await self.conversations_store.append_transcript(
                    ws_session.conversation_id, transcript_item
                )

            asyncio.run_coroutine_threadsafe(update_transcript(), loop)

            # Send transcript to Event Hub (add start/end in ISO 8601)
            asyncio.run_coroutine_threadsafe(
                self.send_event(
                    event=AzureGenesysEvent.PARTIAL_TRANSCRIPT,
                    session_id=session_id,
                    message={
                        "text": text,
                        "channel": json_data["Channel"] if is_multichannel else None,
                        "start": to_iso8601(start_sec),
                        "end": to_iso8601(end_sec),
                        "data": json_data,
                    },
                ),
                loop,
            )

        def session_stopped_cb(event: speechsdk.SpeechRecognitionCanceledEventArgs):
            """Callback that signals to stop continuous recognition upon receiving an event."""
            self.logger.info(f"[{session_id}] Session stopped: {event.session_id}")
            recognition_done.set()

        # Connect callbacks to the events fired by the speech recognizer
        speech_recognizer.recognizing.connect(
            lambda event: loop.call_soon_threadsafe(recognizing_cb, event)
        )
        speech_recognizer.recognized.connect(
            lambda event: loop.call_soon_threadsafe(recognized_cb, event)
        )
        speech_recognizer.session_stopped.connect(
            lambda event: loop.call_soon_threadsafe(session_stopped_cb, event)
        )

        speech_recognizer.session_started.connect(
            lambda event: self.logger.info(
                f"[{session_id}] Session started: {event.session_id}"
            )
        )

        speech_recognizer.canceled.connect(
            lambda event: self.logger.info(
                f"[{session_id}] Canceled: {event.session_id}"
            )
        )

        self.logger.info(f"[{session_id}] Starting continuous recognition.")

        # Start continuous speech recognition
        await asyncio.to_thread(
            speech_recognizer.start_continuous_recognition_async().get
        )

        # Wait until all input processed without blocking the event loop
        await recognition_done.wait()

        # Stop recognition and clean up without blocking the event loop
        await asyncio.to_thread(
            speech_recognizer.stop_continuous_recognition_async().get
        )

        self.logger.info(f"[{session_id}] Stopped continuous recognition.")
