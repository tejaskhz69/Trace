"""AI Trainer -- the quick-question box on the login screen.

Deliberately unauthenticated: there is no user session yet at login time.
See `app/services/chat.py` for why this stays a single stateless Q&A rather
than a persisted conversation.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from ..config import get_settings
from ..schemas import ChatAskRequest, ChatAskResponse
from ..services import chat as chat_svc

log = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("/ask", response_model=ChatAskResponse)
async def ask_trainer(payload: ChatAskRequest) -> ChatAskResponse:
    try:
        question = chat_svc.validate_question(payload.question)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    if not settings.GEMINI_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="The AI Trainer isn't configured yet. Set GEMINI_API_KEY to enable it.",
        )

    try:
        result = await chat_svc.ask(question)
    except Exception:
        log.exception("AI Trainer ask failed")
        raise HTTPException(
            status_code=502, detail="Couldn't reach the AI Trainer. Try again."
        )

    return ChatAskResponse(answer=result.answer)
