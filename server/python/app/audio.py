"""Audio utilities for the server."""

import numpy as np
import wave

from .enums import MediaFormat


def ulaw2linear(ulaw):
    """Convert u-Law encoded bytes to Linear-16 PCM values"""
    ulaw = np.frombuffer(ulaw, dtype=np.uint8)
    ulaw = ulaw.astype(np.int16)
    ulaw = ulaw ^ 0xFF
    sign = ulaw & 0x80
    exponent = (ulaw & 0x70) >> 4
    mantissa = ulaw & 0x0F
    linear = (mantissa << 4) + 0x08
    linear = linear << exponent
    linear = np.where(sign != 0, linear - 0x84, 0x84 - linear)

    return linear


def save_to_wav(filename, format, audio_data, channels, sample_width, frame_rate):
    """Save audio data to a WAV file."""

    # Convert the linear PCMU data to bytes
    if format == MediaFormat.PCMU:
        linear_pcm = ulaw2linear(audio_data)
        audio_data = linear_pcm.tobytes()

    with wave.open(filename, "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(sample_width)
        wav_file.setframerate(frame_rate)
        wav_file.writeframes(audio_data)
