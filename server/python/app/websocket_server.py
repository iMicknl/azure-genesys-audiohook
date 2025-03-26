import asyncio
import dataclasses
import json
import logging
import os
from typing import Any

import azure.cognitiveservices.speech as speechsdk
from azure.eventhub import EventData
from azure.eventhub.aio import EventHubProducerClient
from azure.storage.blob.aio import BlobServiceClient
from quart import Quart, websocket

from .audio import convert_to_wav
from .enums import (
    AzureGenesysEvent,
    ClientMessageType,
    CloseReason,
    DisconnectReason,
    ServerMessageType,
)
from .identity import get_azure_credential_async, get_speech_token
from .models import ClientSession, HealthCheckResponse
from .storage import upload_blob_file


class WebsocketServer:
    """Websocket server class"""

    clients: dict[
        str, ClientSession
    ] = {}  # TODO make app stateless, keep state in CosmosDB?
    logger: logging.Logger = logging.getLogger(__name__)
    blob_service_client: BlobServiceClient | None = None
    producer_client: EventHubProducerClient | None = None

    def __init__(self):
        """Initialize the server"""
        self.app = Quart(__name__)
        self.setup_routes()
        self.app.before_serving(self.create_connections)
        self.app.after_serving(self.close_connections)

    def setup_routes(self):
        """Setup the routes for the server"""
        self.app.route("/")(self.health_check)
        self.app.route("/conversation/<conversation_id>")(self.get_conversation)
        self.app.websocket("/ws")(self.ws)

    async def create_connections(self):
        """Create connections before serving"""
        if connection_string := os.getenv("AZURE_STORAGE_CONNECTION_STRING"):
            self.blob_service_client = BlobServiceClient.from_connection_string(
                connection_string
            )
        elif account_url := os.getenv("AZURE_STORAGE_ACCOUNT_URL"):
            self.blob_service_client = BlobServiceClient(
                account_url, credential=get_azure_credential_async()
            )  # TODO cache DefaultAzureCredential

        if fully_qualified_namespace := os.getenv("AZURE_EVENT_HUB_HOSTNAME"):
            self.producer_client = EventHubProducerClient(
                fully_qualified_namespace=fully_qualified_namespace,
                eventhub_name=os.environ["AZURE_EVENT_HUB_NAME"],
                credential=get_azure_credential_async(),
            )
        elif connection_string := os.getenv("AZURE_EVENT_HUB_CONNECTION_STRING"):
            self.producer_client = EventHubProducerClient.from_connection_string(
                conn_str=connection_string,
                eventhub_name=os.environ["AZURE_EVENT_HUB_NAME"],
            )

    async def close_connections(self):
        """Close connections after serving"""
        if self.blob_service_client:
            await self.blob_service_client.close()

        if self.producer_client:
            await self.producer_client.close()

    async def health_check(self):
        """Health check endpoint"""
        # TODO this won't show the right details when used with multiple workers (each worker will have its own memory storage)
        # Remove audio buffer from the response to avoid serialization issues
        connected_clients = {
            session_id: dataclasses.replace(
                client, audio_buffer=None, raw_audio_buffer=None, recognize_task=None
            )
            for session_id, client in self.clients.items()
        }

        return dataclasses.asdict(
            HealthCheckResponse(
                status="online",
                connected_clients=len(connected_clients),
                client_sessions=connected_clients,
            )
        )

    async def get_conversation(self, conversation_id):
        """Get client session by conversation ID"""
        # Look for client session with matching conversation_id
        for session_id, client in self.clients.items():
            if getattr(client, "conversation_id", None) == conversation_id:
                # Return a single session object without audio buffers and tasks
                clean_session = dataclasses.replace(
                    client,
                    audio_buffer=None,
                    raw_audio_buffer=None,
                    recognize_task=None,
                )
                return dataclasses.asdict(clean_session), 200

        # Return 404 if no matching session is found
        return {"error": "Conversation not found"}, 404

    async def ws(self):
        """Websocket endpoint"""
        headers = websocket.headers
        remote = websocket.remote_addr

        if headers["X-Api-Key"] != os.getenv("WEBSOCKET_SERVER_API_KEY"):
            return await self.disconnect(
                reason=DisconnectReason.UNAUTHORIZED,
                message="Invalid API Key",
                code=3000,
            )

        await websocket.accept()

        session_id = headers["Audiohook-Session-Id"]
        if not session_id:
            return await self.disconnect(
                reason=DisconnectReason.ERROR,
                message="No session ID provided",
                code=1008,
            )

        self.logger.debug(headers)

        # Save new client in memory storage
        self.clients[session_id] = ClientSession()

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
            )

        self.logger.debug("opening websocket")

        # Open the websocket connection and start receiving data (messages / audio)
        try:
            while True:
                data = await websocket.receive()

                if isinstance(data, str):
                    self.logger.debug(f"RECEIVING {data}")
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
            # TODO should we delete self.clients[session_id]?
            raise

    async def disconnect(self, reason: DisconnectReason, message: str, code: int):
        """Disconnect the websocket connection gracefully."""
        self.logger.warning(message)
        await websocket.send_json(
            {
                "type": ServerMessageType.DISCONNECT,
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
        position: str | None = None,
    ):
        """Send a message to the client."""
        session_id = client_message["id"]
        self.clients[session_id].server_seq += 1

        server_message = {
            "version": "2",
            "type": type,
            "seq": self.clients[session_id].server_seq,
            "clientseq": client_message["seq"],
            "id": session_id,
            "parameters": parameters,
        }

        if position:
            server_message["position"] = position

        self.logger.info(f"[{session_id}] Server sending message with type {type}.")
        self.logger.debug(server_message)
        await websocket.send_json(server_message)

    async def handle_incoming_message(self, message: dict):
        """Handle incoming messages (JSON)."""
        session_id = message["id"]
        message_type = message["type"]

        # Validate sequence number
        if message["seq"] != self.clients[session_id].client_seq + 1:
            self.disconnect(
                reason=DisconnectReason.ERROR,
                message=f"Sequence number mismatch: received {message['seq']}, expected {self.clients[session_id].client_seq + 1}",
                code=3000,
            )

        # Store new sequence number
        self.clients[session_id].client_seq = message["seq"]

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
        parameters = message["parameters"]
        session_id = message["id"]

        if parameters.get("rtt"):
            self.logger.info(
                f"[{session_id}] Received ping with RTT: {parameters['rtt']}"
            )
            self.clients[session_id].rtt.append(parameters["rtt"])
            self.clients[session_id].last_rtt = parameters["rtt"]

        await self.send_message(type=ServerMessageType.PONG, client_message=message)

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

        # Handle connection probe
        # See https://developer.genesys.cloud/devapps/audiohook/patterns-and-practices#connection-probe
        if conversation_id == "00000000-0000-0000-0000-000000000000":
            await self.handle_connection_probe(message)
            return

        self.logger.info(
            f"[{session_id}] Session opened with conversation ID: {conversation_id}, ani: {ani}, ANI Name: {ani_name}, DNIS: {dnis}, Position: {position}"
        )
        self.logger.info(f"[{session_id}] Available media: {media}")

        self.clients[session_id].ani = ani
        self.clients[session_id].ani_name = ani_name
        self.clients[session_id].dnis = dnis
        self.clients[session_id].conversation_id = conversation_id

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

        await self.send_message(
            type=ServerMessageType.OPENED,
            client_message=message,
            parameters={
                "startPaused": False,
                "media": [selected_media],
            },
        )

        self.logger.info(f"[{session_id}] Session opened with media: {selected_media}")
        self.clients[session_id].media = selected_media

        await self.send_event(
            event=AzureGenesysEvent.SESSION_STARTED,
            session_id=session_id,
            message={
                "ani-name": ani_name,
                "conversation-id": conversation_id,
                "dnis": dnis,
                "media": selected_media,
                "position": position,
            },
            properties={},
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

        # Close audio buffer (and recognition) if the session is ended
        if self.clients[session_id].audio_buffer:
            self.clients[session_id].audio_buffer.close()

        if (
            parameters["reason"] == CloseReason.END
        ):  # TODO Fix check for connection probe
            if self.clients[session_id].media:
                self.logger.info(self.clients[session_id].transcript)

                await self.send_event(
                    event=AzureGenesysEvent.TRANSCRIPT_AVAILABLE,
                    session_id=session_id,
                    message={"transcript": self.clients[session_id].transcript},
                )

                # Save WAV file from raw audio buffer
                # TODO retrieve raw bytes from PushAudioInputStream to avoid saving two buffers
                wav_file = convert_to_wav(
                    format=self.clients[session_id].media["format"],
                    audio_data=self.clients[session_id].raw_audio_buffer,
                    channels=len(self.clients[session_id].media["channels"]),
                    sample_width=2,  # 16 bits per sample
                    frame_rate=self.clients[session_id].media["rate"],
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

            # TODO store session history in database, before removing
            # del self.clients[session_id]

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
        self.logger.debug(f"[{session_id}] Received audio data. Byte size: {len(data)}")
        media = self.clients[session_id].media

        # Initialize the audio buffer for the session
        if self.clients[session_id].audio_buffer is None:
            self.logger.info(
                f"[{session_id}] type {media['type']}, format {media['format']}, rate {media['rate']}, channels {len(media['channels'])}"
            )

            audio_format = speechsdk.audio.AudioStreamFormat(
                samples_per_second=media["rate"],
                bits_per_sample=8,
                channels=len(media["channels"]),
                wave_stream_format=speechsdk.AudioStreamWaveFormat.PCM,
            )

            stream = speechsdk.audio.PushAudioInputStream(stream_format=audio_format)
            self.clients[session_id].audio_buffer = stream
            self.clients[session_id].raw_audio_buffer = bytearray()

            # Start the synchronous speech recognition as a asyncio task
            self.clients[session_id].recognize_task = asyncio.create_task(
                self.recognize_speech(session_id)
            )

        # Append the buffers to the audio stream
        self.clients[session_id].audio_buffer.write(data)
        self.clients[session_id].raw_audio_buffer += data

    async def send_event(
        self,
        event: AzureGenesysEvent,
        session_id: str,
        message: dict[str, Any],
        properties: dict[str, str] | None = {},
    ):
        """Send an JSON event to Azure Event Hub."""
        if self.producer_client:
            event_data_batch = await self.producer_client.create_batch()
            event_data = EventData(json.dumps(message))
            event_data.properties = {
                "event-type": f"azure-genesys-audiohook.{event}",
                "session-id": session_id,
            }

            if properties:
                event_data.properties.update(properties)

            event_data_batch.add(event_data)
            await self.producer_client.send_batch(event_data_batch)

            self.logger.debug(f"[{session_id}] Sending event: {event_data}")

    async def recognize_speech(self, session_id: str):
        """Recognize speech from audio buffer using Azure Speech to Text."""

        # Determine speech configuration based on channel count and authentication method
        # Use multichannel (preview) for stereo calls
        is_multichannel = len(self.clients[session_id].media["channels"]) > 1
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
                    languages=["en-US", "nl-NL"]
                )
            )
            speech_config.set_property(
                property_id=speechsdk.PropertyId.SpeechServiceConnection_LanguageIdMode,
                value="Continuous",
            )

        speech_config.output_format = speechsdk.OutputFormat.Detailed
        speech_config.request_word_level_timestamps()
        speech_config.enable_audio_logging()
        speech_config.set_profanity(speechsdk.ProfanityOption.Removed)
        # speech_config.set_property(
        #     speechsdk.PropertyId.SpeechServiceConnection_InitialSilenceTimeoutMs,
        #     "45000",
        # )

        # Preview: only supported for en-us
        speech_config.set_property(
            speechsdk.PropertyId.Speech_SegmentationStrategy, "Semantic"
        )

        audio_config = speechsdk.audio.AudioConfig(
            stream=self.clients[session_id].audio_buffer
        )
        speech_recognizer = speechsdk.SpeechRecognizer(
            speech_config=speech_config,
            audio_config=audio_config,
            auto_detect_source_language_config=auto_detect_source_language_config,
        )

        # Phrase list
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

            # Store transcript in local memory
            self.clients[session_id].transcript.append(
                {
                    "channel": json_data["Channel"] if is_multichannel else None,
                    "text": text,
                }
            )

            # Send transcript to Event Hub
            asyncio.run_coroutine_threadsafe(
                self.send_event(
                    event=AzureGenesysEvent.PARTIAL_TRANSCRIPT,
                    session_id=session_id,
                    message={
                        "transcript": text,
                        "channel": json_data["Channel"] if is_multichannel else None,
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
