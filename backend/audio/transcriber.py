import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Optional
import numpy as np
from faster_whisper import WhisperModel
from loguru import logger
from config import get_settings

settings = get_settings()

_model: Optional[WhisperModel] = None
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="whisper")

def _load_model() -> WhisperModel:
    global _model
    if _model is None:
        logger.info(
            f"Loading Whisper model '{settings.whisper_model_size}' "
            f"on {settings.whisper_device} ({settings.whisper_compute_type})"
        )
        try:
            _model = WhisperModel(
                settings.whisper_model_size,
                device=settings.whisper_device,
                compute_type=settings.whisper_compute_type,
                download_root="/tmp/whisper_models",
            )
            logger.info("Whisper model loaded ✓")
        except Exception as e:
            logger.critical(f"Failed to load Whisper model: {e}")
            raise RuntimeError(f"Whisper model load failed: {e}") from e
    return _model

def _transcribe_sync(audio: np.ndarray) -> str:
    model = _load_model()
    try:
        segments, info = model.transcribe(
            audio,
            beam_size=1,
            best_of=1,
            temperature=0.0,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 300},
            language=None,           
            condition_on_previous_text=False, 
        )
        text = " ".join(s.text.strip() for s in segments).strip()
        if text:
            logger.debug(f"Transcribed [{info.language}]: {text[:80]}")
        return text
    except Exception as e:
        logger.error(f"Transcription error: {e}")
        return ""


async def transcribe_chunk(audio: np.ndarray) -> str:
    min_samples = int(settings.audio_sample_rate * settings.audio_min_speech_duration)
    if len(audio) < min_samples:
        return ""
    rms = float(np.sqrt(np.mean(audio ** 2)))
    if rms < 0.003:
        return ""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_executor, _transcribe_sync, audio)

async def warmup() -> None:
    silence = np.zeros(settings.audio_sample_rate, dtype=np.float32)
    await transcribe_chunk(silence)
    logger.info("Whisper warmup complete")
