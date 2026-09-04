"""A refusal has to survive the HTTP boundary.

WHY THIS FILE EXISTS
--------------------
`vision._sanitize()` has set `refused` for a while, `eval_vision.py` writes it
into results.json, and `eval/score.py` grades the adversarial rows on it. But
`RecognitionResponse` did not declare the field, so Pydantic dropped it on
serialisation and the phone received `refused: null` on every scan — including
the ones where the model had explicitly refused.

The consequence is not cosmetic. A refusal and a low-confidence guess both
arrive with few or no items, so with the field missing the client cannot tell
them apart and shows "no food found" for a photo the model has already said is
unusable. The user then retries the same photo, gets the same non-answer, and
learns nothing. Product invariant 3 says refusing to answer beats answering
wrong — that only holds if the refusal actually reaches the person.

`vision.recognize` is monkeypatched throughout. These tests make no network
call and need no GEMINI_API_KEY, which is why they run in CI where
`test_integration_core.py`'s recognize test is skipped.
"""
from __future__ import annotations

import uuid
from typing import Any

import pytest

from app.services import vision


def _unique_email() -> str:
    return f"refusal-{uuid.uuid4().hex[:12]}@example.com"


async def _register(client) -> dict:
    r = await client.post(
        "/api/auth/register",
        json={"email": _unique_email(), "password": "RefusalTest!2026"},
    )
    assert r.status_code in (200, 201), r.text
    return r.json()


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _result(payload: dict[str, Any]) -> vision.VisionResult:
    """A real `VisionResult`, not a stand-in.

    An earlier version of this used a hand-rolled fake carrying only the
    attributes the router happened to read. It broke the moment the router
    touched `image_hash`, and it would have gone on breaking every time the
    dataclass grew a field. Constructing the real thing means the test fails
    at the constructor -- loudly, in one place -- if the shape ever changes.
    """
    return vision.VisionResult(
        payload=payload,
        model_used="gemini-3.5-flash-lite",
        input_tokens=100,
        output_tokens=50,
        latency_ms=1234,
        cost_usd=0.004,
        image_hash="a" * 32,
    )


REFUSAL_PAYLOAD = {
    "items": [],
    "hidden_ingredients": [],
    "overall_confidence": 0.0,
    "review_required": False,
    "refused": True,
    "refusal_reason": "The food is in an opaque takeaway container.",
}

# Same emptiness, no refusal. If the two responses are indistinguishable over
# HTTP, this file has failed at its job.
EMPTY_PAYLOAD = {
    "items": [],
    "hidden_ingredients": [],
    "overall_confidence": 0.2,
    "review_required": False,
    "refused": False,
    "refusal_reason": "",
}

# The endpoint runs `assess_image` BEFORE the vision call and 422s anything
# below MIN_EDGE_PX (200), under the luma stddev floor, or too dark. So this
# has to be an image with real STRUCTURE -- a flat or tiny placeholder never
# reaches the code under test, which is how the first version of this file
# silently tested the quality gate instead of the refusal path.
#
# Per-pixel random noise does NOT work, and that is worth knowing: uniform
# noise averages out to a near-constant luma (measured stddev 5.1, against a
# floor of 12) so the gate reports "empty". Large blocks of contrasting tone
# are what a photograph actually looks like to this check.
def _test_image() -> bytes:
    import io

    from PIL import Image, ImageDraw

    w, h = 640, 480
    im = Image.new("RGB", (w, h), (24, 26, 30))
    d = ImageDraw.Draw(im)
    # Coarse light/dark blocks: high luma variance at low spatial frequency,
    # which is the signature the gate is looking for.
    tones = [(232, 226, 210), (48, 52, 58), (198, 150, 74), (86, 96, 104)]
    for i in range(4):
        for j in range(3):
            d.rectangle(
                [i * 160, j * 160, i * 160 + 150, j * 160 + 150],
                fill=tones[(i + j) % len(tones)],
            )
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    return buf.getvalue()


async def _scan(client, token, monkeypatch, payload) -> Any:
    async def fake_recognize(raw, hint=None, **kw):
        return _result(payload)

    monkeypatch.setattr(vision, "recognize", fake_recognize)
    return await client.post(
        "/api/foods/recognize",
        headers=_headers(token),
        files={"image": ("meal.jpg", _test_image(), "image/jpeg")},
    )


class TestRefusalRoundTrip:
    async def test_refusal_reaches_the_client(self, client, monkeypatch):
        """THE regression test. `refused: true` must survive serialisation."""
        auth = await _register(client)
        r = await _scan(client, auth["access_token"], monkeypatch, REFUSAL_PAYLOAD)

        assert r.status_code == 200, r.text
        body = r.json()
        assert body["refused"] is True, (
            "RecognitionResponse dropped `refused`; the phone cannot tell a "
            "refusal from an empty result"
        )

    async def test_the_models_own_wording_is_passed_through_verbatim(
        self, client, monkeypatch
    ):
        """The reason is the actionable part. It must not be reworded.

        A canned "couldn't read that photo" tells the user nothing they can
        act on. "The food is in an opaque takeaway container" tells them to
        open the box.
        """
        auth = await _register(client)
        r = await _scan(client, auth["access_token"], monkeypatch, REFUSAL_PAYLOAD)

        assert (
            r.json()["refusal_reason"]
            == "The food is in an opaque takeaway container."
        )

    async def test_empty_result_is_distinguishable_from_a_refusal(
        self, client, monkeypatch
    ):
        """Both have zero items. Only one is a refusal.

        This is the pair that matters: if these two responses ever look the
        same to the client, the field is not doing its job even when present.
        """
        auth = await _register(client)
        r = await _scan(client, auth["access_token"], monkeypatch, EMPTY_PAYLOAD)

        body = r.json()
        assert body["refused"] is False
        assert body["refusal_reason"] == ""
        assert body["items"] == []

    async def test_a_normal_scan_defaults_to_not_refused(self, client, monkeypatch):
        """A model that never mentions refusing has not refused.

        The default must be False rather than None: None serialises to JSON
        null, which reads as a third state the client has no branch for.
        """
        auth = await _register(client)
        payload = {
            "items": [],
            "hidden_ingredients": ["tempering oil"],
            "overall_confidence": 0.7,
            "review_required": False,
        }
        r = await _scan(client, auth["access_token"], monkeypatch, payload)

        body = r.json()
        assert body["refused"] is False
        assert body["refusal_reason"] == ""

    @pytest.mark.parametrize("field", ["refused", "refusal_reason"])
    async def test_fields_are_always_present_in_the_schema(
        self, client, monkeypatch, field
    ):
        """Present on every response, not only refusals.

        A field that appears conditionally forces the client into
        `body.get(...)` defensiveness, and that is where the null-versus-false
        confusion started.
        """
        auth = await _register(client)
        r = await _scan(client, auth["access_token"], monkeypatch, EMPTY_PAYLOAD)
        assert field in r.json()
