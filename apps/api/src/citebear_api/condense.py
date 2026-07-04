"""Standalone-question rewrite for multi-turn retrieval (SPEC §5.3, §5.5).

A follow-up like "what about on Linux?" elides its subject, so retrieving on
those words alone collapses recall. When the session has history, one LLM call
rewrites the latest message into a self-contained question; that rewrite feeds
retrieval only (embedding, keyword search, rerank) — the generator still sees
the user's original words plus the history.

The first message of a session has no history and skips the call entirely
(SPEC §5.5 fast path) — a purely structural check, not a semantic judgement.
"""

import logging

from langchain_core.messages import HumanMessage, SystemMessage

from citebear_api.gateway import get_chat_model, with_retry

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You rewrite a user's latest message into a standalone question \
for a document search.

Using the conversation, resolve any pronouns or references ("it", "that", "the
previous one") so the question stands on its own. If the latest message is
already self-contained, return it unchanged. Return ONLY the question — no
preamble, no quotes."""


def _format_history(history: list[tuple[str, str]]) -> str:
    labels = {"user": "User", "assistant": "Assistant"}
    return "\n".join(f"{labels.get(role, role)}: {content}" for role, content in history)


async def condense_question(message: str, history: list[tuple[str, str]]) -> str:
    """Rewrite ``message`` into a standalone question, or return it unchanged
    when the session has no history."""
    if not history:
        return message
    prompt = (
        f"Conversation:\n{_format_history(history)}\n\n"
        f"Latest message: {message}\n\nStandalone question:"
    )
    try:
        response = await with_retry(
            lambda: get_chat_model().ainvoke([SystemMessage(SYSTEM_PROMPT), HumanMessage(prompt)])
        )
    except Exception:
        # a condense-call blip must not sink the whole turn: retrieval can still
        # proceed on the raw message (this is exactly the M1 fast path)
        logger.warning("condense failed; falling back to the raw message")
        return message
    return response.text.strip() or message
