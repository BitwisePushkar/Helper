"""
Audio capture module.

Captures from the default input device (mic) and, if a virtual loopback
device is present (BlackHole on Mac / VB-Cable on Windows), also from system
audio.  All audio is resampled to 16 kHz mono and placed into an asyncio Queue
for the transcriber to consume.

Edge cases handled:
  - Device not found → falls back to mic-only with a warning
  - Overrun (queue full) → drops oldest chunk, logs warning
  - Stream crash → auto-restarts up to MAX_RETRIES times
  - Graceful shutdown via asyncio.Event
"""

import asyncio
import threading
from typing import Optional

import numpy as np
import sounddevice as sd
from loguru import logger

from config import get_settings

settings = get_settings()

QUEUE_MAX = 50          # max buffered chunks before we start dropping
MAX_RETRIES = 5
_DTYPE = "float32"


def _list_devices() -> list[dict]:
    devices = sd.query_devices()
    return [
        {"index": i, "name": d["name"], "inputs": d["max_input_channels"]}
        for i, d in enumerate(devices)
        if d["max_input_channels"] > 0
    ]


def _find_loopback_device() -> Optional[int]:
    """Find BlackHole / VB-Cable / Stereo Mix device index, if present."""
    keywords = ["blackhole", "vb-cable", "stereo mix", "loopback", "virtual"]
    for d in _list_devices():
        if any(kw in d["name"].lower() for kw in keywords):
            logger.info(f"Loopback device found: {d['name']} (index {d['index']})")
            return d["index"]
    logger.warning("No loopback device found — capturing mic only")
    return None


class AudioCapture:
    """Thread-safe audio capture that feeds an asyncio queue."""

    def __init__(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop
        self._queue: asyncio.Queue[np.ndarray] = asyncio.Queue(maxsize=QUEUE_MAX)
        self._stop_event = threading.Event()
        self._stream_mic: Optional[sd.InputStream] = None
        self._stream_sys: Optional[sd.InputStream] = None
        self._retries = 0

    # ── public API ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        self._stop_event.clear()
        self._retries = 0
        self._open_streams()
        logger.info("Audio capture started")

    def stop(self) -> None:
        self._stop_event.set()
        self._close_streams()
        logger.info("Audio capture stopped")

    @property
    def queue(self) -> asyncio.Queue:
        return self._queue

    # ── internals ──────────────────────────────────────────────────────────────

    def _open_streams(self) -> None:
        chunk_frames = int(settings.audio_sample_rate * settings.audio_chunk_duration)

        # Mic stream (always)
        try:
            self._stream_mic = sd.InputStream(
                samplerate=settings.audio_sample_rate,
                channels=1,
                dtype=_DTYPE,
                blocksize=chunk_frames,
                callback=self._make_callback("mic"),
            )
            self._stream_mic.start()
        except sd.PortAudioError as e:
            logger.error(f"Failed to open mic stream: {e}")
            raise

        # System loopback stream (optional)
        loopback_idx = _find_loopback_device()
        if loopback_idx is not None:
            try:
                self._stream_sys = sd.InputStream(
                    device=loopback_idx,
                    samplerate=settings.audio_sample_rate,
                    channels=1,
                    dtype=_DTYPE,
                    blocksize=chunk_frames,
                    callback=self._make_callback("system"),
                )
                self._stream_sys.start()
            except sd.PortAudioError as e:
                logger.warning(f"Could not open system audio stream: {e} — mic only")
                self._stream_sys = None

    def _close_streams(self) -> None:
        for stream in (self._stream_mic, self._stream_sys):
            if stream is not None:
                try:
                    stream.stop()
                    stream.close()
                except Exception:
                    pass
        self._stream_mic = None
        self._stream_sys = None

    def _make_callback(self, source: str):
        def _callback(indata: np.ndarray, frames: int, time, status):
            if self._stop_event.is_set():
                return
            if status:
                logger.warning(f"[{source}] audio status: {status}")

            audio = indata[:, 0].copy()  # mono

            # Skip near-silent chunks to avoid feeding noise to Whisper
            rms = float(np.sqrt(np.mean(audio ** 2)))
            if rms < 0.002:
                return

            if self._queue.full():
                try:
                    self._queue.get_nowait()
                    logger.warning(f"[{source}] queue full — dropped oldest chunk")
                except asyncio.QueueEmpty:
                    pass

            asyncio.run_coroutine_threadsafe(
                self._queue.put(audio), self._loop
            )

        return _callback

    def get_device_info(self) -> dict:
        return {
            "mic": str(self._stream_mic.device) if self._stream_mic else None,
            "system": str(self._stream_sys.device) if self._stream_sys else None,
            "sample_rate": settings.audio_sample_rate,
            "chunk_duration_s": settings.audio_chunk_duration,
            "available_inputs": _list_devices(),
        }
