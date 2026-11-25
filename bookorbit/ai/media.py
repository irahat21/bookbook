"""Tiny stdlib-only helpers for PNG and WAV files.

Used by seed.py to generate book covers and demo biometric samples locally
(no downloads, no Pillow), and by the MOCK biometric engine to read them.
"""
import io
import struct
import wave
import zlib

import numpy as np

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC = b"\xff\xd8"


def is_image(data: bytes) -> bool:
    """True for PNG or JPEG bytes (the formats UC-04 E3 accepts)."""
    return data.startswith(PNG_MAGIC) or data.startswith(JPEG_MAGIC)


def _chunk(kind: bytes, payload: bytes) -> bytes:
    crc = zlib.crc32(kind + payload) & 0xFFFFFFFF
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", crc)


def encode_png(pixels: np.ndarray, text: dict | None = None) -> bytes:
    """pixels: H x W x 3 uint8 array. text: optional tEXt key/value chunks."""
    h, w, _ = pixels.shape
    raw = b"".join(b"\x00" + pixels[y].astype(np.uint8).tobytes() for y in range(h))
    out = PNG_MAGIC + _chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
    for key, value in (text or {}).items():
        out += _chunk(b"tEXt", key.encode("latin-1") + b"\x00" + str(value).encode("latin-1"))
    out += _chunk(b"IDAT", zlib.compress(raw, 9)) + _chunk(b"IEND", b"")
    return out


def read_png_text(data: bytes) -> dict:
    """Return the tEXt chunks of a PNG ({} for JPEG or PNGs without text)."""
    if not data.startswith(PNG_MAGIC):
        return {}
    out, pos = {}, len(PNG_MAGIC)
    while pos + 8 <= len(data):
        length, kind = struct.unpack(">I4s", data[pos:pos + 8])
        payload = data[pos + 8:pos + 8 + length]
        if kind == b"tEXt" and b"\x00" in payload:
            k, v = payload.split(b"\x00", 1)
            out[k.decode("latin-1")] = v.decode("latin-1")
        if kind == b"IEND":
            break
        pos += 12 + length
    return out


def encode_wav(samples: np.ndarray, rate: int = 16000) -> bytes:
    """Mono 16-bit WAV from float samples in [-1, 1]."""
    pcm = (np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(pcm)
    return buf.getvalue()


def decode_wav(data: bytes) -> tuple[np.ndarray, int]:
    """Return (mono float samples, sample rate). Raises wave.Error / EOFError if unreadable."""
    with wave.open(io.BytesIO(data), "rb") as wf:
        rate, width, channels = wf.getframerate(), wf.getsampwidth(), wf.getnchannels()
        frames = wf.readframes(wf.getnframes())
    if width != 2:
        raise wave.Error("only 16-bit WAV is supported")
    samples = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    return samples, rate
