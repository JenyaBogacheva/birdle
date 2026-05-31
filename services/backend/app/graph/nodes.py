"""Graph nodes: guardrail, resolve_inputs, investigate, ask_user, terminals."""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

import anthropic
from anthropic.types import TextBlock
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.config import get_stream_writer
from langgraph.types import interrupt

from ..helpers.ebird_client import ebird_client
from ..settings import settings
from . import prompts
from .state import BirdState
from .tools import ALL_TOOLS

logger = logging.getLogger(__name__)

# Raw Anthropic client for the cheap Haiku guardrail + resolve parse.
_raw_anthropic = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key, max_retries=1)


def _first_text(message: Any) -> str:
    """First text block of a raw Anthropic message, or ''."""
    return next((b.text for b in message.content if isinstance(b, TextBlock)), "")


def _emit(event: dict[str, Any]) -> None:
    try:
        writer = get_stream_writer()
    except Exception:
        return
    if writer is not None:
        writer(event)


async def guardrail(state: BirdState) -> dict[str, Any]:
    """Cheap Haiku check: is this about birds? Non-bird -> set final (polite bail)."""
    description = state.get("description", "")
    try:
        resp = await _raw_anthropic.messages.create(
            model=prompts.GUARDRAIL_MODEL,
            max_tokens=10,
            messages=[{"role": "user", "content": f"{prompts.GUARDRAIL_PROMPT}\n\n{description}"}],
        )
        text = _first_text(resp) or "YES"
        if "YES" not in text.upper():
            logger.info(
                "Non-bird query rejected",
                extra={"operation": "graph_guardrail", "status": "rejected"},
            )
            return {"final": dict(prompts.NOT_BIRD_RESPONSE)}
    except Exception as e:  # fail open
        logger.warning(f"Guardrail failed, allowing request: {e}")
    return {"final": None}
