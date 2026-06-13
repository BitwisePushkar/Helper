import json
from typing import AsyncGenerator
import redis.asyncio as aioredis
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential
from config import get_settings

settings = get_settings()

_fallback_store: dict[str, list[str]] = {}
_use_fallback: bool = False
_pool: aioredis.ConnectionPool | None = None

def _get_pool() -> aioredis.ConnectionPool:
    global _pool
    if _pool is None:
        _pool = aioredis.ConnectionPool.from_url(
            f"redis://{settings.redis_host}:{settings.redis_port}",
            max_connections=20,
            decode_responses=True,
        )
    return _pool

def get_redis() -> aioredis.Redis:
    return aioredis.Redis(connection_pool=_get_pool())

def _transcript_key(session_id: str) -> str:
    return f"session:{session_id}:transcript"

def _channel_key(session_id: str) -> str:
    return f"session:{session_id}:channel"

def _meta_key(session_id: str) -> str:
    return f"session:{session_id}:meta"

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.3))
async def append_transcript(session_id: str, text: str, speaker: str = "unknown") -> None:
    if not text.strip():
        return
    entry = json.dumps({"text": text.strip(), "speaker": speaker})
    key = _transcript_key(session_id)

    global _use_fallback
    if _use_fallback:
        if key not in _fallback_store:
            _fallback_store[key] = []
        _fallback_store[key].append(entry)
        _fallback_store[key] = _fallback_store[key][-settings.session_max_transcript_lines:]
        logger.debug(f"[{session_id}] transcript appended (fallback): {text[:60]}...")
        return

    try:
        r = get_redis()
        pipe = r.pipeline()
        pipe.rpush(key, entry)
        pipe.ltrim(key, -settings.session_max_transcript_lines, -1)
        pipe.expire(key, settings.redis_ttl_seconds)
        pipe.publish(_channel_key(session_id), entry)
        await pipe.execute()
    except Exception as e:
        logger.error(f"Redis append failed, switching to fallback: {e}")
        _use_fallback = True
        if key not in _fallback_store:
            _fallback_store[key] = []
        _fallback_store[key].append(entry)

    logger.debug(f"[{session_id}] transcript appended: {text[:60]}...")

async def get_context(session_id: str, last_n: int = 20) -> str:
    key = _transcript_key(session_id)
    
    global _use_fallback
    if _use_fallback:
        raw_lines = _fallback_store.get(key, [])[-last_n:]
    else:
        try:
            r = get_redis()
            raw_lines = await r.lrange(key, -last_n, -1)
        except Exception:
            _use_fallback = True
            raw_lines = _fallback_store.get(key, [])[-last_n:]

    lines = []
    for raw in raw_lines:
        try:
            obj = json.loads(raw)
            speaker = obj.get("speaker", "unknown").capitalize()
            lines.append(f"{speaker}: {obj['text']}")
        except (json.JSONDecodeError, KeyError):
            lines.append(raw)

    return "\n".join(lines)

async def clear_session(session_id: str) -> None:
    global _use_fallback
    key = _transcript_key(session_id)
    
    if _use_fallback:
        _fallback_store.pop(key, None)
    else:
        try:
            r = get_redis()
            keys = [key, _meta_key(session_id)]
            await r.delete(*keys)
        except Exception:
            _use_fallback = True
            _fallback_store.pop(key, None)
    logger.info(f"[{session_id}] session cleared")

async def subscribe_transcript(session_id: str) -> AsyncGenerator[dict, None]:
    global _use_fallback
    if _use_fallback:
        return
        
    try:
        r = get_redis()
        pubsub = r.pubsub()
        await pubsub.subscribe(_channel_key(session_id))
        logger.info(f"[{session_id}] subscribed to transcript channel")

        async for message in pubsub.listen():
            if message["type"] == "message":
                try:
                    yield json.loads(message["data"])
                except json.JSONDecodeError:
                    yield {"text": message["data"], "speaker": "unknown"}
    except Exception as e:
        logger.error(f"subscribe_transcript failed: {e}")
        _use_fallback = True
    finally:
        try:
            await pubsub.unsubscribe(_channel_key(session_id))
            await pubsub.close()
        except:
            pass

async def redis_ping() -> bool:
    try:
        r = get_redis()
        return await r.ping()
    except Exception as e:
        logger.error(f"Redis ping failed: {e}")
        return False