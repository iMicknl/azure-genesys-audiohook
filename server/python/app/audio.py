"""Audio utilities for the server."""

import wave

from .enums import MediaFormat
import audioop
import io


def convert_to_wav(
    format: MediaFormat,
    audio_data: bytes,
    channels: int,
    sample_width: int,
    frame_rate: int,
) -> bytes:
    """Convert audio data to WAV format and return as bytes."""

    # Convert the linear PCMU data to bytes
    if format == MediaFormat.PCMU:
        # TODO DeprecationWarning: 'audioop' is deprecated and slated for removal in Python 3.13.
        audio_data = audioop.ulaw2lin(audio_data, sample_width)

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(sample_width)
        wav_file.setframerate(frame_rate)
        wav_file.writeframes(audio_data)

    return buffer.getvalue()
