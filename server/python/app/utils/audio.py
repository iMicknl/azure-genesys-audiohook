"""Audio utilities for the server."""

import audioop
import io
import wave

from ..enums import MediaFormat


def convert_to_wav(
    format: MediaFormat,
    audio_data: bytes,
    channels: int,
    sample_width: int,
    frame_rate: int,
) -> bytes:
    """Convert audio data to WAV format and return as bytes."""

    if format == MediaFormat.PCMU:
        # Convert sound fragments in u-LAW encoding to linearly encoded sound fragments.
        # u-LAW encoding always uses 8 bits samples, so *width* refers only to the sample
        # width of the output fragment here.
        # TODO DeprecationWarning: 'audioop' is deprecated and slated for removal in Python 3.13.
        audio_data = audioop.ulaw2lin(audio_data, sample_width)

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(sample_width)
        wav_file.setframerate(frame_rate)
        wav_file.writeframes(audio_data)

    return buffer.getvalue()
