"""
AI module — LangChain + Ollama integration.

Two responsibilities:
  1. Question detection: classify whether the latest transcript line is a
     question directed at the user.
  2. Answer generation: stream a concise answer given the rolling context.

Uses langchain_ollama (OllamaLLM) so all inference stays local.
Includes retry logic and health-check for Ollama availability.

Edge cases:
  - Ollama not running → clear error, not a silent hang
  - Empty context → still produces an answer (model's own knowledge)
  - Streaming interrupted → caller catches StopAsyncIteration cleanly
  - Model not pulled yet → surfaces actionable error message
"""

import asyncio
import re
from typing import AsyncGenerator

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from loguru import logger
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
    RetryError,
)
import logging

from config import get_settings

settings = get_settings()

# ── LLM singleton ──────────────────────────────────────────────────────────────

_llm: ChatGoogleGenerativeAI | None = None


def _get_llm() -> ChatGoogleGenerativeAI:
    global _llm
    if _llm is None:
        _llm = ChatGoogleGenerativeAI(
            model=settings.gemini_model,
            temperature=0.3,
            max_tokens=300,
            google_api_key=settings.gemini_api_key,
        )
        logger.info(
            f"LLM initialised → Gemini API with model {settings.gemini_model}"
        )
    return _llm


# ── prompt templates ───────────────────────────────────────────────────────────

_QUESTION_DETECT_PROMPT = PromptTemplate.from_template(
    """You are an assistant that detects whether the last line of a meeting transcript
is a question directed at a specific participant.

Transcript context:
{context}

Last line: "{last_line}"

Respond with ONLY one of: YES or NO.
Is the last line a question directed at someone?"""
)

_ANSWER_PROMPT = PromptTemplate.from_template(
    """You are a real-time meeting assistant helping a participant answer questions clearly and concisely.

Meeting transcript so far:
{context}

Question asked: {question}

Provide a concise, helpful answer in 2-4 sentences. Be direct. Do not repeat the question."""
)


# ── question detector ──────────────────────────────────────────────────────────

_QUESTION_PATTERNS = re.compile(
    r"(^|\s)(who|what|where|when|why|how|can you|could you|would you|do you|"
    r"is there|are there|have you|did you|will you|should we)[^\w]",
    re.IGNORECASE,
)


def _heuristic_is_question(text: str) -> bool:
    """Fast regex pre-filter to avoid LLM call for obvious non-questions."""
    text = text.strip()
    if text.endswith("?"):
        return True
    if _QUESTION_PATTERNS.search(text):
        return True
    return False


@retry(
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=0.5),
    retry=retry_if_exception_type(Exception),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=False,
)
async def is_question(text: str, context: str) -> bool:
    """
    Returns True if the text is a question directed at the user.
    Uses regex pre-filter first, then LLM for ambiguous cases.
    """
    if not text.strip():
        return False

    # Fast path — obvious questions
    if _heuristic_is_question(text):
        logger.debug(f"Heuristic detected question: {text[:60]}")
        return True

    # Slow path — ask the LLM for ambiguous sentences
    try:
        llm = _get_llm()
        chain = _QUESTION_DETECT_PROMPT | llm | StrOutputParser()
        result = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: chain.invoke({"context": context[-500:], "last_line": text}),
        )
        detected = result.strip().upper().startswith("YES")
        logger.debug(f"LLM question detection: '{text[:60]}' → {detected}")
        return detected
    except RetryError:
        # Fall back to heuristic if LLM fails
        logger.warning("LLM question detection failed — falling back to heuristic")
        return _heuristic_is_question(text)


# ── answer generator ───────────────────────────────────────────────────────────

async def stream_answer(
    question: str, context: str
) -> AsyncGenerator[str, None]:
    """
    Async generator that yields answer tokens one by one.
    Streams directly from Ollama via LangChain's astream interface.
    """
    if not question.strip():
        return

    llm = _get_llm()
    chain = _ANSWER_PROMPT | llm | StrOutputParser()

    logger.info(f"Streaming answer for: {question[:80]}")
    try:
        async for chunk in chain.astream(
            {"context": context, "question": question}
        ):
            if chunk:
                yield chunk
    except Exception as e:
        logger.error(f"Error streaming answer: {e}")
        yield f"\n\n[Error generating answer: {e}]"


# ── Gemini health check ────────────────────────────────────────────────────────

async def gemini_health() -> dict:
    """Check if Gemini API key is configured."""
    has_key = bool(settings.gemini_api_key)
    return {
        "api_reachable": has_key,
        "model_ready": has_key,
        "configured_model": settings.gemini_model,
        "hint": None if has_key else "Please set GEMINI_API_KEY in backend/.env",
    }
