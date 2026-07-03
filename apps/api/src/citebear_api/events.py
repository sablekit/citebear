"""The SSE event contract for POST /chat (SPEC §5.4).

Every event name and payload shape is defined once here, so the emitter and the
Next.js proxy cannot drift on a field name or event label (issue #6). The
camelCase boundary is applied at this seam; the web side mirrors these shapes in
a single shared TypeScript type.
"""

import uuid
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

# Event names — the single source of truth on the api side.
TOKEN = "token"
SOURCES = "sources"
DONE = "done"
ERROR = "error"


@dataclass(frozen=True)
class ChatEvent:
    event: str
    data: dict[str, Any]


class Citation(BaseModel):
    """One entry in the sources event — everything the source panel renders."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    marker: int
    chunk_id: uuid.UUID
    doc_title: str
    page: int | None
    section_path: list[str]
    source_url: str
    snippet: str


def token_event(delta: str) -> ChatEvent:
    return ChatEvent(TOKEN, {"delta": delta})


def sources_event(citations: list[Citation], confidence: str) -> ChatEvent:
    return ChatEvent(
        SOURCES,
        {
            "citations": [c.model_dump(by_alias=True, mode="json") for c in citations],
            "confidence": confidence,
        },
    )


def done_event(message_id: uuid.UUID, grounded: bool) -> ChatEvent:
    return ChatEvent(DONE, {"messageId": str(message_id), "grounded": grounded})


def error_event(problem: dict[str, Any]) -> ChatEvent:
    return ChatEvent(ERROR, problem)
