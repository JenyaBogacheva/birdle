"""Tests for the hero-photo focal point helper."""

import httpx
import pytest

from services.backend.app.helpers import image_focus


def test_breathe_leaves_centered_birds_untouched():
    # Within the deadzone (|x-50| <= 12) the model's framing is kept as-is.
    assert image_focus._breathe(50) == 50
    assert image_focus._breathe(58) == 58  # great spotted woodpecker
    assert image_focus._breathe(38) == 38  # bald eagle
    assert image_focus._breathe(62) == 62  # mallard


def test_breathe_opens_room_for_edge_jammed_birds():
    # Far off-centre heads get nudged further toward their edge (more air),
    # never past it — direction is always preserved.
    assert image_focus._breathe(25) == 19  # herring gull, left-facing
    assert image_focus._breathe(28) == 23  # barn swallow, left-facing
    assert image_focus._breathe(72) == 77  # magpie, right-facing — stays right
    swallow = image_focus._breathe(28)
    magpie = image_focus._breathe(72)
    assert swallow < 50 < magpie


def test_breathe_clamps_to_range():
    assert image_focus._breathe(0) == 0
    assert image_focus._breathe(100) == 100
    assert 0 <= image_focus._breathe(2) <= 100
    assert 0 <= image_focus._breathe(98) <= 100


@pytest.mark.asyncio
async def test_get_image_focus_none_for_blank_url():
    assert await image_focus.get_image_focus(None) is None
    assert await image_focus.get_image_focus("") is None


@pytest.mark.asyncio
async def test_get_image_focus_returns_none_on_fetch_error(monkeypatch):
    # A download failure degrades gracefully to a static crop, not an exception.
    image_focus._focus_cache.clear()

    async def boom(*a, **k):
        raise httpx.ConnectError("no network")

    monkeypatch.setattr(image_focus._http, "get", boom)
    assert await image_focus.get_image_focus("https://example.org/x.jpg") is None


@pytest.mark.asyncio
async def test_get_image_focus_skips_non_image_response(monkeypatch):
    # Wikimedia occasionally serves an HTML error page; never send it to vision.
    image_focus._focus_cache.clear()
    calls = {"vision": 0}

    class FakeResp:
        headers = {"content-type": "text/html; charset=utf-8"}
        content = b"<html>rate limited</html>"

        def raise_for_status(self):
            return None

    async def fake_get(*a, **k):
        return FakeResp()

    async def fake_vision(*a, **k):
        calls["vision"] += 1

    monkeypatch.setattr(image_focus._http, "get", fake_get)
    monkeypatch.setattr(image_focus._anthropic.messages, "create", fake_vision)
    assert await image_focus.get_image_focus("https://example.org/x.html") is None
    assert calls["vision"] == 0  # vision call short-circuited


@pytest.mark.asyncio
async def test_get_image_focus_applies_breathing_and_caches(monkeypatch):
    image_focus._focus_cache.clear()
    fetches = {"img": 0, "vision": 0}

    class FakeResp:
        headers = {"content-type": "image/jpeg"}
        content = b"\xff\xd8\xff\xe0fakejpeg"

        def raise_for_status(self):
            return None

    async def fake_get(*a, **k):
        fetches["img"] += 1
        return FakeResp()

    class FakeText:
        type = "text"
        # Gull leans left at 25 → breathing pulls it to 19; y passes through.
        text = '{"reasoning": "head upper-left", "x": 25, "y": 38}'

    class FakeMessage:
        content = [FakeText()]

    async def fake_vision(*a, **k):
        fetches["vision"] += 1
        return FakeMessage()

    # isinstance(b, TextBlock) must hold for the parse path.
    monkeypatch.setattr(image_focus, "TextBlock", FakeText)
    monkeypatch.setattr(image_focus._http, "get", fake_get)
    monkeypatch.setattr(image_focus._anthropic.messages, "create", fake_vision)

    url = "https://example.org/gull.jpg"
    focus = await image_focus.get_image_focus(url)
    assert focus == {"x": 19, "y": 38}

    # Second call for the same URL is served from cache — no re-fetch, no re-call.
    again = await image_focus.get_image_focus(url)
    assert again == {"x": 19, "y": 38}
    assert fetches == {"img": 1, "vision": 1}
