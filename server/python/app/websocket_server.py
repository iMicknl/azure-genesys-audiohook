import asyncio
import dataclasses
import threading
from quart import Quart, websocket
import json
import logging
import os
from azure.storage.blob.aio import BlobServiceClient

from .storage import upload_blob_file
from .audio import convert_to_wav
from .identity import get_azure_credential_async, get_speech_token

from .enums import (
    CloseReason,
    DisconnectReason,
    ClientMessageType,
    ServerMessageType,
)
from .models import ClientSession, HealthCheckResponse

import azure.cognitiveservices.speech as speechsdk


class WebsocketServer:
    """Websocket server class"""

    clients: dict[
        str, ClientSession
    ] = {}  # TODO make app stateless, keep state in CosmosDB?
    logger: logging.Logger = logging.getLogger(__name__)
    blob_service_client: BlobServiceClient | None = None

    def __init__(self):
        """Initialize the server"""
        self.app = Quart(__name__)
        self.setup_routes()

        if connection_string := os.getenv("AZURE_STORAGE_CONNECTION_STRING"):
            self.blob_service_client = BlobServiceClient.from_connection_string(
                connection_string
            )
        elif account_url := os.getenv("AZURE_STORAGE_ACCOUNT_URL"):
            self.blob_service_client = BlobServiceClient(
                account_url, credential=get_azure_credential_async()
            )  # TODO cache DefaultAzureCredential

    def setup_routes(self):
        """Setup the routes for the server"""
        self.app.route("/")(self.health_check)
        self.app.websocket("/ws")(self.ws)

    async def health_check(self):
        """Health check endpoint"""
        # TODO this won't show the right details when used with multiple workers (each worker will have its own memory storage)
        # Remove audio buffer from the response to avoid serialization issues
        connected_clients = {
            session_id: dataclasses.replace(
                client, audio_buffer=None, raw_audio_buffer=None
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

        # Open the websocket connection and start receiving data (messages / audio)
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
        self, type: ServerMessageType, client_message: dict, parameters: dict = {}
    ):
        """Send a message to the client."""
        session_id = client_message["id"]
        self.clients[session_id].server_seq += 1

        self.logger.info(f"[{session_id}] Server sending message with type {type}")
        await websocket.send_json(
            {
                "version": "2",
                "type": type,
                "seq": self.clients[session_id].server_seq,
                "clientseq": client_message["seq"],
                "id": session_id,
                "parameters": parameters,
            }
        )

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
        ani_name = parameters["participant"]["aniName"]
        dnis = parameters["participant"]["dnis"]
        session_id = message["id"]
        media = parameters["media"]
        position = message["position"]

        # Handle connection probe
        # See https://developer.genesys.cloud/devapps/audiohook/patterns-and-practices#connection-probe
        if conversation_id == "00000000-0000-0000-0000-000000000000":
            self.handle_connection_probe(message)
            return

        self.logger.info(
            f"[{session_id}] Session opened with conversation ID: {conversation_id}, ANI Name: {ani_name}, DNIS: {dnis}, Position: {position}"
        )
        self.logger.info(f"[{session_id}] Available media: {media}")

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
        self.clients[session_id].audio_buffer.close()

        if parameters["reason"] == CloseReason.END:
            self.logger.info(self.clients[session_id].transcript)

            await self.send_message(
                type=ServerMessageType.CLOSED, client_message=message
            )
            await websocket.close(1000)

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

            # TODO store session history in database, before removing
            del self.clients[session_id]

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

        await self.send_message(
            type=ClientMessageType.CLOSE,
            client_message=message,
            parameters={
                "reason": CloseReason.END,
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
                f"[{session_id}] type {media["type"]}, format {media["format"]}, rate {media["rate"]}, channels {len(media["channels"])}"
            )

            audio_format = speechsdk.audio.AudioStreamFormat(
                samples_per_second=media["rate"],
                bits_per_sample=8,
                channels=1,
                wave_stream_format=speechsdk.AudioStreamWaveFormat.PCM,
            )

            stream = speechsdk.audio.PushAudioInputStream(stream_format=audio_format)
            self.clients[session_id].audio_buffer = stream
            self.clients[session_id].raw_audio_buffer = bytearray()

            # Start the speech recognition in a separate thread (background)
            threading.Thread(
                target=asyncio.run, args=(self.recognize_speech(session_id),)
            ).start()

        # Append the buffers to the audio stream
        self.clients[session_id].audio_buffer.write(data)
        self.clients[session_id].raw_audio_buffer += data

    async def recognize_speech(self, session_id: str):
        """Recognize speech from audio buffer using Azure Speech to Text."""

        if os.getenv("AZURE_SPEECH_KEY"):
            speech_config = speechsdk.SpeechConfig(
                subscription=os.environ["AZURE_SPEECH_KEY"],
                region=os.environ["AZURE_SPEECH_REGION"],
            )
        else:
            speech_config = speechsdk.SpeechConfig(
                auth_token=get_speech_token(os.environ["AZURE_SPEECH_RESOURCE_ID"]),
                region=os.environ["AZURE_SPEECH_REGION"],
            )

        # Speech configuration
        speech_config.output_format = speechsdk.OutputFormat.Detailed
        speech_config.speech_recognition_language = "en-US"  # TODO add continuous LID
        speech_config.request_word_level_timestamps()
        speech_config.enable_audio_logging()
        speech_config.enable_dictation()
        speech_config.set_profanity(speechsdk.ProfanityOption.Removed)

        # TODO implement conversation transcriber for mono streams
        # speech_config.set_property(property_id=speechsdk.PropertyId.SpeechServiceResponse_DiarizeIntermediateResults, value='true')

        audio_config = speechsdk.audio.AudioConfig(
            stream=self.clients[session_id].audio_buffer
        )
        speech_recognizer = speechsdk.SpeechRecognizer(
            speech_config=speech_config, audio_config=audio_config
        )

        # Phrase list
        phrase_list_grammar = speechsdk.PhraseListGrammar.from_recognizer(
            speech_recognizer
        )
        phrase_list_grammar.addPhrase("Contoso")

        recognition_done = threading.Event()

        # Connect callbacks to the events fired by the speech recognizer
        def recognizing_cb(event: speechsdk.SpeechRecognitionEventArgs):
            """Callback that continuously logs the recognized speech."""
            self.logger.info(f"[{session_id}] Recognizing {event}")

        def recognized_cb(event: speechsdk.SpeechRecognitionEventArgs):
            """Callback that logs the recognized speech once the recognition is done."""
            self.logger.info(f"[{session_id}] Recognized {event}")
            self.clients[session_id].transcript += event.result.text

        def session_stopped_cb(event):
            """Callback that signals to stop continuous recognition upon receiving an event."""
            self.logger.info(f"[{session_id}] Session stopped: {event.session_id}")
            recognition_done.set()

        # Connect callbacks to the events fired by the speech recognizer
        speech_recognizer.recognizing.connect(recognizing_cb)
        speech_recognizer.recognized.connect(recognized_cb)
        speech_recognizer.session_stopped.connect(session_stopped_cb)

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
        speech_recognizer.start_continuous_recognition()  # TODO or use _async version

        # Wait until all input processed
        recognition_done.wait()

        # Stop recognition and clean up
        speech_recognizer.stop_continuous_recognition()

        self.logger.info(f"[{session_id}] Stopped continuous recognition.")
