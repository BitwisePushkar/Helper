import asyncio
import json
import uuid
import base64
import subprocess
from concurrent.futures import ThreadPoolExecutor
import numpy as np
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from config import get_settings
from ai import is_question, stream_answer, gemini_health
from audio.transcriber import warmup
from audio.capture import AudioCapture
from session import append_transcript, get_context, clear_session, redis_ping

settings = get_settings()

_ffmpeg_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="ffmpeg")


def _decode_audio_chunk(b64_data: str) -> np.ndarray:
    try:
        audio_bytes = base64.b64decode(b64_data)
        cmd = [
            "ffmpeg", "-i", "pipe:0",
            "-f", "f32le", "-acodec", "pcm_f32le",
            "-ar", "16000", "-ac", "1",
            "pipe:1"
        ]
        process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout, stderr = process.communicate(input=audio_bytes, timeout=10)
        if process.returncode != 0:
            logger.error(f"FFmpeg decoding failed: {stderr.decode()}")
            return np.array([], dtype=np.float32)
        return np.frombuffer(stdout, dtype=np.float32)
    except subprocess.TimeoutExpired:
        process.kill()
        logger.error("FFmpeg decode timed out")
        return np.array([], dtype=np.float32)
    except Exception as decode_err:
        logger.error(f"Failed to decode audio chunk: {decode_err}")
        return np.array([], dtype=np.float32)


_audio_capture: AudioCapture | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up — warming Whisper model...")
    await warmup()
    logger.info("Server ready ✓")
    yield
    global _audio_capture
    if _audio_capture is not None:
        _audio_capture.stop()
        _audio_capture = None
    logger.info("Shutting down")

app = FastAPI(
    title="Meeting AI Backend",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ConnectionManager:
    def __init__(self):
        self._connections: dict[str, WebSocket] = {}

    def add(self, session_id: str, ws: WebSocket):
        self._connections[session_id] = ws

    def remove(self, session_id: str):
        self._connections.pop(session_id, None)

    @property
    def count(self) -> int:
        return len(self._connections)


manager = ConnectionManager()

async def _send(ws: WebSocket, payload: dict) -> bool:
    try:
        await ws.send_text(json.dumps(payload))
        return True
    except Exception:
        return False

@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    await websocket.accept()
    manager.add(session_id, websocket)
    logger.info(f"[{session_id}] Client connected (total: {manager.count})")
    question_queue: asyncio.Queue[str] = asyncio.Queue()
    streaming_task: asyncio.Task | None = None

    async def _question_worker():
        nonlocal streaming_task
        while True:
            question = await question_queue.get()
            if question is None: 
                if streaming_task and not streaming_task.done():
                    streaming_task.cancel()
                break
            
            try:
                context = await get_context(session_id, last_n=20)
                if await is_question(question, context):
                    if streaming_task and not streaming_task.done():
                        streaming_task.cancel()
                        await asyncio.sleep(0)
                    
                    async def _stream_it(q, c):
                        logger.info(f"[{session_id}] Question detected: {q[:80]}")
                        await _send(websocket, {"type": "question_detected", "text": q})
                        try:
                            async for token in stream_answer(q, c):
                                if not await _send(websocket, {"type": "answer_token", "token": token}):
                                    break
                        except asyncio.CancelledError:
                            logger.info(f"[{session_id}] Answer cancelled for newer question")
                        finally:
                            await _send(websocket, {"type": "answer_done"})
                    
                    streaming_task = asyncio.create_task(_stream_it(question, context))
            except Exception as e:
                logger.error(f"[{session_id}] Question worker error: {e}")
                await _send(websocket, {"type": "error", "message": str(e)})
            finally:
                question_queue.task_done()

    worker_task = asyncio.create_task(_question_worker())

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                frame = json.loads(raw)
            except json.JSONDecodeError:
                await _send(websocket, {"type": "error", "message": "Invalid JSON"})
                continue

            frame_type = frame.get("type", "")

            if frame_type == "ping":
                await _send(websocket, {"type": "pong"})

            elif frame_type == "transcript":
                text = (frame.get("text") or "").strip()
                speaker = frame.get("speaker", "unknown")

                if not text:
                    await _send(websocket, {"type": "transcript_ack", "text": text})
                    continue

                await append_transcript(session_id, text, speaker)
                await _send(websocket, {"type": "transcript_ack", "text": text})

                if len(text.split()) >= 3:
                    await question_queue.put(text)

            elif frame_type == "question":
                text = (frame.get("text") or "").strip()
                if text:
                    await append_transcript(session_id, text, "user")
                    await _send(websocket, {"type": "transcript_ack", "text": text})
                    context = await get_context(session_id, last_n=20)
                    if streaming_task and not streaming_task.done():
                        streaming_task.cancel()
                        await asyncio.sleep(0)

                    async def _direct_stream(q, c):
                        logger.info(f"[{session_id}] Direct question: {q[:80]}")
                        await _send(websocket, {"type": "question_detected", "text": q})
                        try:
                            async for token in stream_answer(q, c):
                                if not await _send(websocket, {"type": "answer_token", "token": token}):
                                    break
                        except asyncio.CancelledError:
                            pass
                        finally:
                            await _send(websocket, {"type": "answer_done"})

                    streaming_task = asyncio.create_task(_direct_stream(text, context))

            elif frame_type == "audio_chunk":
                data = frame.get("data", "")
                if data:
                    loop = asyncio.get_running_loop()
                    pcm_data = await loop.run_in_executor(
                        _ffmpeg_pool, _decode_audio_chunk, data
                    )

                    if len(pcm_data) > 0:
                        from audio.transcriber import transcribe_chunk
                        text = await transcribe_chunk(pcm_data)
                        if text:
                            logger.info(f"[{session_id}] Transcribed mic audio: {text}")
                            await append_transcript(session_id, text, "user")
                            await _send(websocket, {"type": "transcript_ack", "text": text})
                            await question_queue.put(text)

            else:
                await _send(
                    websocket,
                    {"type": "error", "message": f"Unknown frame type: {frame_type}"},
                )

    except WebSocketDisconnect:
        logger.info(f"[{session_id}] Client disconnected")
    except Exception as e:
        logger.error(f"[{session_id}] Unexpected error: {e}")
    finally:
        await question_queue.put(None)
        await worker_task

        manager.remove(session_id)
        logger.info(f"[{session_id}] Connection cleaned up (total: {manager.count})")

@app.get("/health")
async def health():
    redis_ok = await redis_ping()
    ai_info = await gemini_health()
    status = "ok" if (redis_ok and ai_info["model_ready"]) else "degraded"
    return {
        "status": status,
        "redis": redis_ok,
        "ai": ai_info,
        "active_sessions": manager.count,
    }

@app.post("/capture/start")
async def capture_start():
    global _audio_capture
    if _audio_capture is not None:
        return {"status": "already_running"}
    try:
        loop = asyncio.get_running_loop()
        _audio_capture = AudioCapture(loop)
        _audio_capture.start()
        return {"status": "started"}
    except Exception as e:
        logger.error(f"Failed to start audio capture: {e}")
        _audio_capture = None
        return {"status": "error", "message": str(e)}


@app.post("/capture/stop")
async def capture_stop():
    global _audio_capture
    if _audio_capture is None:
        return {"status": "not_running"}
    try:
        _audio_capture.stop()
    except Exception as e:
        logger.error(f"Error stopping audio capture: {e}")
    finally:
        _audio_capture = None
    return {"status": "stopped"}


@app.get("/session/{session_id}/context")
async def get_session_context(session_id: str, last_n: int = 20):
    context = await get_context(session_id, last_n=last_n)
    return {"session_id": session_id, "context": context}


@app.delete("/session/{session_id}")
async def delete_session(session_id: str):
    await clear_session(session_id)
    return {"session_id": session_id, "cleared": True}


@app.get("/new-session")
async def new_session():
    return {"session_id": str(uuid.uuid4())}
