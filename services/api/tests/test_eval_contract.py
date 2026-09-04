"""The contract between the scan pipeline and the offline evaluation harness.

WHY THIS FILE EXISTS
--------------------
`eval/score.py` grades the four adversarial rows -- the ones whose true calorie
count is deliberately unknowable -- on behaviour rather than accuracy, and the
first clause of that grade is the literal key `refused`:

    good = got.get("refused") or band > 0.4 * kcal or conf < 0.6

For a long time nothing in the pipeline ever produced that key. `.get()`
returned None, the clause fell through to band-and-confidence, and a model that
correctly refused to guess scored exactly the same as one that guessed
confidently. Product invariant 3 says refusing to answer beats answering wrong;
the harness could not see the difference.

The chain is four links long and crosses a directory boundary:

    model  ->  vision._sanitize()  ->  eval_vision.py  ->  eval/score.py

Any one of them can be broken by an edit that looks harmless in isolation, and
nothing else would fail. These tests are the thing that notices.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import ClassVar

import pytest

from app.services import vision

# eval/ is not a package and sits outside services/api, so it is loaded by
# path rather than imported. Deliberate: the scorer must stay a standalone
# script that a person can run with plain python, and this test must not be
# the reason that changes.
EVAL_DIR = Path(__file__).resolve().parents[3] / "eval"


@pytest.fixture(scope="module")
def score_mod():
    path = EVAL_DIR / "score.py"
    if not path.exists():
        pytest.skip(f"eval harness not present at {path}")
    spec = importlib.util.spec_from_file_location("eval_score", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["eval_score"] = mod
    spec.loader.exec_module(mod)
    return mod


def _payload(**overrides) -> dict:
    """A minimal well-formed model response, before sanitizing."""
    base = {
        "items": [
            {
                "name": "dal tadka",
                "portion_unit": "katori",
                "portion_count": 1,
                "grams_est": 150,
                "grams_range": [130, 170],
                "kcal_point": 180,
                "kcal_low": 150,
                "kcal_high": 220,
                "protein_g": 9,
                "carbs_g": 20,
                "fat_g": 7,
                "confidence": 0.7,
            }
        ],
        "hidden_ingredients": ["tempering oil"],
        "overall_confidence": 0.7,
    }
    base.update(overrides)
    return base


class TestSanitizeCarriesRefusal:
    def test_absent_refusal_defaults_to_false(self):
        """A model that says nothing about refusing has not refused.

        The default must be False and not None: `bool(None)` is falsey either
        way, but None serialises to JSON null and reads as "unknown", which is
        a third state the scorer has no branch for.
        """
        out = vision._sanitize(_payload())
        assert out["refused"] is False
        assert out["refusal_reason"] == ""

    def test_refusal_survives_sanitize(self):
        out = vision._sanitize(
            _payload(
                items=[],
                refused=True,
                refusal_reason="Food is in an opaque takeaway box.",
            )
        )
        assert out["refused"] is True
        assert out["refusal_reason"] == "Food is in an opaque takeaway box."

    def test_refusal_reason_is_bounded_and_never_none(self):
        """It reaches a results file and a log line, so it cannot be unbounded."""
        out = vision._sanitize(_payload(refused=True, refusal_reason="x" * 500))
        assert len(out["refusal_reason"]) == 200
        assert vision._sanitize(_payload(refusal_reason=None))["refusal_reason"] == ""


class TestScorerCreditsRefusal:
    """The clause that was dead. Each of these fails if a link breaks."""

    CONFIDENT_AND_TIGHT: ClassVar[dict] = {
        "kcal": 500.0,
        "kcal_low": 480.0,
        "kcal_high": 520.0,  # band is 8% of the point estimate
        "confidence": 0.9,
    }

    def test_refusal_passes_despite_a_tight_confident_band(self, score_mod):
        """THE regression test.

        These numbers fail every other clause on purpose: the band is far
        inside the 40% threshold and the confidence is far above 0.6. The row
        can only pass on `refused`, so if the key stops arriving this flips.
        """
        got = {**self.CONFIDENT_AND_TIGHT, "refused": True}
        assert score_mod.adversarial_ok(got) is True

    def test_same_numbers_without_the_key_fail(self, score_mod):
        assert score_mod.adversarial_ok(dict(self.CONFIDENT_AND_TIGHT)) is False

    def test_explicit_false_is_not_a_refusal(self, score_mod):
        """`refused: False` must not pass through truthiness by accident."""
        got = {**self.CONFIDENT_AND_TIGHT, "refused": False}
        assert score_mod.adversarial_ok(got) is False

    def test_widened_band_still_passes_without_refusing(self, score_mod):
        """The old behaviour has to keep working -- this is additive."""
        assert score_mod.adversarial_ok(
            {"kcal": 500.0, "kcal_low": 300.0, "kcal_high": 800.0, "confidence": 0.9}
        ) is True

    def test_low_confidence_still_passes_without_refusing(self, score_mod):
        assert score_mod.adversarial_ok(
            {**self.CONFIDENT_AND_TIGHT, "confidence": 0.4}
        ) is True


class TestRunnerWritesTheKey:
    """The middle link: eval_vision.py must copy it out of the payload.

    Asserted against the source rather than by running the script, because
    running it would call a paid vision API. A source-level check is weak, but
    a silently-dropped key is exactly the failure mode that got us here, and
    this costs nothing.
    """

    def test_eval_vision_persists_refused(self):
        src = (
            Path(vision.__file__).resolve().parents[1] / "scripts" / "eval_vision.py"
        ).read_text(encoding="utf-8")
        assert '"refused"' in src, (
            "eval_vision.py no longer writes `refused` into results.json; "
            "eval/score.py grades the adversarial rows on that key"
        )
        assert '"refusal_reason"' in src


class TestPlaceholderDetection:
    """The check that a photo count is not a photograph count.

    Twenty-five generated cards sat in `eval/photos/` and passed a
    `Path.exists()` check for months. The set reported 25/25 photos present
    while containing no photograph of food at all -- the validator answered
    "is there a file" when the question was "is there a photograph".

    These use synthetic images rather than fixtures on disk, so the test
    cannot itself rot into checking a file that is no longer representative.
    """

    @staticmethod
    def _write(tmp_path, name, pixels, size=(200, 200)):
        from PIL import Image

        im = Image.new("RGB", size)
        im.putdata(pixels)
        path = tmp_path / name
        # PNG, not JPEG: JPEG's lossy compression perturbs a flat field into
        # thousands of near-identical triples, which would defeat the exact
        # match and make this test pass for the wrong reason.
        im.save(path, "PNG")
        return path

    def test_flat_card_is_a_placeholder(self, score_mod, tmp_path):
        """The shipped cards' actual background triple, at their coverage."""
        n = 200 * 200
        flat = int(n * 0.55)
        px = [(21, 26, 32)] * flat + [(200, 200, 200)] * (n - flat)
        path = self._write(tmp_path, "card.png", px)
        assert score_mod.is_placeholder(path) is True

    def test_noisy_photograph_is_not(self, score_mod, tmp_path):
        """A real sensor never repeats one exact triple across 40% of a frame."""
        import random

        rng = random.Random(7)
        px = [
            (rng.randint(90, 190), rng.randint(80, 180), rng.randint(70, 170))
            for _ in range(200 * 200)
        ]
        path = self._write(tmp_path, "photo.png", px)
        assert score_mod.is_placeholder(path) is False

    def test_dim_photograph_is_not(self, score_mod, tmp_path):
        """ad-002 is deliberately underexposed. A dark photo is still a photo.

        The failure this guards against is a threshold tuned so tightly that
        the adversarial low-light row gets thrown out as fake.
        """
        import random

        rng = random.Random(11)
        px = [
            (rng.randint(8, 26), rng.randint(8, 26), rng.randint(10, 30))
            for _ in range(200 * 200)
        ]
        path = self._write(tmp_path, "dim.png", px)
        assert score_mod.is_placeholder(path) is False

    def test_unreadable_file_is_not_called_fake(self, score_mod, tmp_path):
        """A missing library or a corrupt file must not condemn real work.

        Wrong direction of failure: reporting a real photo as a placeholder
        deletes somebody's shopping trip. Reporting a placeholder as real only
        costs one eval run.
        """
        path = tmp_path / "broken.png"
        path.write_bytes(b"not an image")
        assert score_mod.is_placeholder(path) is False
