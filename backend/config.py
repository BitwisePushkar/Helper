from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    # Redis
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_ttl_seconds: int = 7200

    # Gemini / LangChain
    gemini_api_key: str = ""
    gemini_model: str = "gemini-1.5-flash"

    # Whisper
    whisper_model_size: str = "base"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"

    # Audio capture
    audio_sample_rate: int = 16000
    audio_chunk_duration: float = 2.0
    audio_min_speech_duration: float = 0.5

    # Session
    session_max_transcript_lines: int = 50
    question_confidence_threshold: float = 0.7

    # App
    log_level: str = "INFO"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
