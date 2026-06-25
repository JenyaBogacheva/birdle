"""
Hero-photo focal point via Claude Opus vision.

The species lead photo is shown as a tall portrait hero using CSS
``background-size: cover; background-position: X% Y%``. A wide landscape photo
cropped to that column with a fixed position routinely throws an off-centre
bird's head out of frame. Here Opus looks at the photo and returns the focal
point that keeps the head and beak framed; we then open a little breathing room
on the side the head faces so the beak never sits against an edge.

The result is just a ``background-position`` percentage — applied as-is on the
client, resolution-independent, no head-detection or geometry math downstream.
One call per hero photo, cached per image URL, and entirely optional: any
failure returns ``None`` and the frontend falls back to its static position.
"""

import base64
import json
import logging
import math
import time
from typing import Optional

import anthropic
import httpx
from anthropic.types import TextBlock

from ..settings import settings

logger = logging.getLogger(__name__)

# Opus is the strongest vision model; the focal point needs accurate perception
# of where the eye/beak sit, which cheaper models judge less reliably.
FOCUS_MODEL = "claude-opus-4-8"
# Wikimedia asks all clients to send a descriptive User-Agent.
_UA = "BirdleAI/1.0 (bird identification; https://github.com/birdle-ai)"
_TIMEOUT = 12.0
# Anthropic accepts jpeg/png/gif/webp base64 image sources.
_ALLOWED_MEDIA = {"image/jpeg", "image/png", "image/gif", "image/webp"}

_SCHEMA = {
    "type": "object",
    "properties": {
        "reasoning": {
            "type": "string",
            "description": "one short sentence: where the head/beak sit and how you'll frame",
        },
        "x": {"type": "number", "description": "horizontal focal point, 0 (left) to 100 (right)"},
        "y": {"type": "number", "description": "vertical focal point, 0 (top) to 100 (bottom)"},
    },
    "required": ["reasoning", "x", "y"],
    "additionalProperties": False,
}

_PROMPT = (
    "This species photo is shown as a TALL PORTRAIT hero (roughly 2:3, taller than wide) using CSS "
    "`background-size: cover; background-position: X% Y%`. The image is scaled to fill the tall "
    "frame; X%/Y% choose which part stays visible. X=0 anchors the photo's LEFT edge, X=100 the "
    "RIGHT edge, X=50 centers; Y=0 top, Y=100 bottom. (For a wide landscape photo the full height "
    "is always visible, so Y barely matters; for a tall photo X barely matters.)\n\n"
    "Pick X and Y so the MAIN bird (largest / most prominent if several) is well composed with its "
    "whole head — eye, crown, and the FULL beak tip — clearly in frame. If the head is off to one "
    "side, bias X toward that side so the head stays safe. Then show as much of the body as "
    "naturally fits; it is fine to crop the tail to keep the head clean. Return X, Y as percentages."
)

# Deterministic breathing room. Birds the model frames near centre are left
# exactly as chosen; birds whose focal is far from centre (head jammed near an
# edge) get a proportional nudge further toward that edge so the beak lifts off
# it — the more off-centre, the more air. Pure transform on the percentage,
# direction-preserving (a right-facing head can never flip left).
_DEADZONE = 12.0
_GAIN = 1.5


def _round_pct(v: float) -> int:
    """Round half-up and clamp to 0–100 (matches JS ``Math.round`` semantics)."""
    return int(math.floor(min(100.0, max(0.0, v)) + 0.5))


def _breathe(x: float) -> int:
    """Open breathing room on the side the head faces; clamp to 0–100."""
    d = x - 50.0
    if abs(d) <= _DEADZONE:
        return _round_pct(x)
    sign = -1.0 if d < 0 else 1.0
    return _round_pct(50.0 + sign * (_DEADZONE + (abs(d) - _DEADZONE) * _GAIN))


_anthropic = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key, max_retries=1)
_http = httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True)
# Focal point is stable per image; cache so follow-up turns don't re-call Opus.
_focus_cache: dict[str, Optional[dict[str, int]]] = {}


async def get_image_focus(image_url: Optional[str]) -> Optional[dict[str, int]]:
    """Return ``{"x", "y"}`` background-position for the hero, or None on any error.

    Downloads the image, asks Opus for the focal point, applies breathing room.
    Optional by design: a failure (no key, fetch error, bad image, API error)
    logs and returns None so the caller can fall back to a static position.
    """
    if not image_url:
        return None
    if image_url in _focus_cache:
        return _focus_cache[image_url]

    start_time = time.time()
    try:
        img = await _http.get(image_url, headers={"User-Agent": _UA})
        img.raise_for_status()
        media_type = img.headers.get("content-type", "image/jpeg").split(";")[0].strip().lower()
        if media_type not in _ALLOWED_MEDIA:
            logger.info(
                "Skipping focal point for non-image response",
                extra={
                    "operation": "get_image_focus",
                    "media_type": media_type,
                    "status": "skipped",
                },
            )
            _focus_cache[image_url] = None
            return None

        data = base64.standard_b64encode(img.content).decode()
        resp = await _anthropic.messages.create(
            model=FOCUS_MODEL,
            max_tokens=300,
            output_config={"format": {"type": "json_schema", "schema": _SCHEMA}},
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {"type": "base64", "media_type": media_type, "data": data},
                        },
                        {"type": "text", "text": _PROMPT},
                    ],
                }
            ],
        )
        text = next((b.text for b in resp.content if isinstance(b, TextBlock)), "")
        parsed = json.loads(text)
        focus = {"x": _breathe(float(parsed["x"])), "y": _round_pct(float(parsed["y"]))}

        logger.info(
            "Hero focal point resolved",
            extra={
                "operation": "get_image_focus",
                "focus": focus,
                "latency_ms": round((time.time() - start_time) * 1000, 2),
                "status": "success",
            },
        )
        _focus_cache[image_url] = focus
        return focus

    except Exception as e:
        logger.warning(
            f"Hero focal point failed, falling back to static position: {e}",
            extra={
                "operation": "get_image_focus",
                "latency_ms": round((time.time() - start_time) * 1000, 2),
                "status": "error",
                "error_type": type(e).__name__,
            },
        )
        return None
