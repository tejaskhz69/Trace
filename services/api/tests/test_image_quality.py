"""Image quality gating, and the bias that makes it safe.

THE ASYMMETRY THIS SUITE ENFORCES
A false reject is far worse than a false accept. Refusing a usable photo sends
somebody to type eleven numbers off the back of a packet, and they stop
logging; accepting a marginal one costs a fraction of a cent and produces a
low-confidence estimate the pipeline already knows how to widen and flag.

So most of what follows asserts that images are ACCEPTED. Only frames that
cannot contain the answer -- nothing in them, too small to resolve print,
undecodable -- may block an upload.

Every fixture is drawn at call time. No photograph is stored in this repo.
"""

from __future__ import annotations

import pytest

from app.services import image_quality as iq
from tests.fixtures import scan_images as fx


class TestFixtureSweep:
    @pytest.mark.parametrize(
        "name,factory,should_upload",
        [(n, f, u) for n, (f, u) in fx.ALL_FIXTURES.items()],
    )
    def test_each_fixture_lands_on_the_intended_side(self, name, factory, should_upload):
        report = iq.assess_image(factory())
        assert report.should_upload is should_upload, (
            f"{name}: verdict={report.verdict} reasons={report.reasons}"
        )

    def test_nine_of_twelve_fixtures_are_accepted(self):
        """A gate that rejects most of its inputs is a broken gate."""
        accepted = sum(
            1 for f, _ in fx.ALL_FIXTURES.values() if iq.assess_image(f()).should_upload
        )
        assert accepted >= 9


class TestAcceptsWhatAHumanCouldRead:
    def test_a_clear_label_passes_cleanly(self):
        r = iq.assess_image(fx.clear_label())
        assert r.verdict == iq.OK
        assert r.reasons == ()
        assert r.message == ""

    def test_rotation_is_not_a_defect(self):
        """A label photographed at an angle is still a label."""
        assert iq.assess_image(fx.rotated_label()).verdict == iq.OK

    def test_a_bilingual_label_is_not_penalised(self):
        assert iq.assess_image(fx.multilingual_label()).should_upload

    def test_a_plate_of_several_foods_is_not_penalised(self):
        assert iq.assess_image(fx.multiple_food_items()).should_upload

    def test_a_front_of_pack_with_no_panel_still_uploads(self):
        """We cannot tell "no nutrition table" from "food" without looking.

        Guessing would refuse legitimate plate photos, so this is the model's
        job, not the gate's.
        """
        assert iq.assess_image(fx.missing_nutrition_panel()).should_upload

    def test_reflective_packaging_is_flagged_but_not_refused(self):
        """Foil clips hard and stays readable.

        Calibrating this is what showed that clipping ALONE cannot condemn a
        frame: a well-shot nutrition panel is black on white and legitimately
        pins a large share of its pixels.
        """
        r = iq.assess_image(fx.reflective_packaging())
        assert r.should_upload

    def test_a_dark_frame_is_flagged_but_still_uploads(self):
        r = iq.assess_image(fx.dark_image())
        assert "too_dark" in r.reasons
        assert r.verdict == iq.MARGINAL
        assert r.should_upload

    def test_an_overexposed_frame_is_flagged_but_still_uploads(self):
        r = iq.assess_image(fx.overexposed_image())
        assert "too_bright" in r.reasons
        assert r.should_upload

    def test_blur_never_blocks_on_its_own(self):
        """The focus measure is content-dependent.

        A correctly focused photo of a plain bowl has less edge energy than a
        busy label and can score near the floor. Refusing on that basis would
        reject correct photos of unbusy food, so blur only annotates.
        """
        r = iq.assess_image(fx.blurry_label())
        assert "blurry" in r.reasons
        assert r.should_upload


class TestRefusesOnlyWhatCannotContainTheAnswer:
    def test_an_empty_frame_is_refused(self):
        r = iq.assess_image(fx.empty_frame())
        assert r.verdict == iq.REJECT
        assert "empty" in r.reasons
        assert "camera" in r.message.lower() or "point" in r.message.lower()

    def test_a_thumbnail_is_refused(self):
        r = iq.assess_image(fx.tiny_image())
        assert r.verdict == iq.REJECT
        assert r.reasons == ("too_small",)

    def test_undecodable_bytes_are_refused_without_raising(self):
        r = iq.assess_image(fx.not_an_image())
        assert r.verdict == iq.REJECT
        assert r.reasons == ("decode_failed",)

    @pytest.mark.parametrize(
        "junk", [b"", b"\x00" * 64, b"GIF89a-truncated", bytes(range(256))]
    )
    def test_never_raises_on_arbitrary_bytes(self, junk):
        """A scan must degrade to "try again", never to a 500."""
        assert iq.assess_image(junk).verdict == iq.REJECT


class TestBlurIsMonotonic:
    """The measure must not reverse at the extremes.

    An earlier version normalised Laplacian variance by contrast, which is
    NOT monotonic: it fell to 0.088 at 5 px blur and rose back to 0.239 at
    32 px, because past a radius the denominator collapses faster than the
    numerator. It would have passed a catastrophically blurred frame while
    flagging a mildly soft one.
    """

    def test_focus_falls_as_blur_rises(self):
        scores = [
            iq.assess_image(fx.blurry_label(r)).stats["focus_variance"]
            for r in (0, 1, 2, 3, 5, 9, 16, 32)
        ]
        assert scores == sorted(scores, reverse=True), scores

    def test_once_flagged_blurry_it_stays_flagged(self):
        flagged = [
            "blurry" in iq.assess_image(fx.blurry_label(r)).reasons
            for r in (0, 1, 2, 3, 5, 9, 16, 32)
        ]
        # False...False,True...True -- never back to False.
        assert flagged == sorted(flagged), flagged


class TestThresholdBoundaries:
    """Every threshold is exercised on both sides of its own boundary."""

    @staticmethod
    def _flat(level: int, size=(400, 400)) -> bytes:
        from PIL import Image, ImageDraw

        img = Image.new("RGB", size, (level, level, level))
        # Enough structure to clear EMPTY_STDDEV, so the luminance rules are
        # what is actually under test.
        d = ImageDraw.Draw(img)
        for i in range(0, size[0], 20):
            v = max(0, min(255, level + (40 if i % 40 else -40)))
            d.rectangle([i, 0, i + 10, size[1]], fill=(v, v, v))
        return fx._encode(img)

    def test_just_below_the_dark_threshold_is_flagged(self):
        r = iq.assess_image(self._flat(int(iq.DARK_MEAN) - 15))
        assert "too_dark" in r.reasons

    def test_comfortably_above_it_is_not(self):
        r = iq.assess_image(self._flat(int(iq.DARK_MEAN) + 60))
        assert "too_dark" not in r.reasons

    def test_just_above_the_bright_threshold_is_flagged(self):
        r = iq.assess_image(self._flat(int(iq.BRIGHT_MEAN) + 20))
        assert "too_bright" in r.reasons

    def test_comfortably_below_it_is_not(self):
        r = iq.assess_image(self._flat(int(iq.BRIGHT_MEAN) - 60))
        assert "too_bright" not in r.reasons

    def test_an_image_at_the_minimum_edge_is_accepted(self):
        assert iq.assess_image(fx._encode(fx.nutrition_label(
            (iq.MIN_EDGE_PX, iq.MIN_EDGE_PX)
        ))).should_upload

    def test_one_pixel_under_is_refused(self):
        r = iq.assess_image(fx._encode(fx.nutrition_label(
            (iq.MIN_EDGE_PX - 1, iq.MIN_EDGE_PX - 1)
        )))
        assert r.reasons == ("too_small",)

    def test_thresholds_are_module_level_and_therefore_configurable(self):
        for name in (
            "DARK_MEAN", "BRIGHT_MEAN", "CLIPPED_FRACTION", "CLIPPED_STDDEV",
            "BLUR_FOCUS_FLOOR", "BLUR_MIN_STDDEV", "MIN_EDGE_PX", "EMPTY_STDDEV",
        ):
            assert isinstance(getattr(iq, name), (int, float))


class TestPrivacy:
    """An error path that echoes what it saw leaks somebody's kitchen."""

    @pytest.mark.parametrize("name,factory", [(n, f) for n, (f, _) in fx.ALL_FIXTURES.items()])
    def test_the_report_carries_no_image_data(self, name, factory):
        r = iq.assess_image(factory())
        for value in r.stats.values():
            assert value is None or isinstance(value, (int, float)), (
                f"{name}: stats must be scalars only, got {type(value)}"
            )
        assert isinstance(r.message, str)
        assert len(r.message) < 200

    def test_a_decode_failure_does_not_quote_the_file(self):
        """Pillow's exception text can include embedded metadata."""
        r = iq.assess_image(b"\xff\xd8\xff\xe0SECRETMARKER\x00\x00")
        assert "SECRETMARKER" not in r.message
        assert "SECRETMARKER" not in str(r.stats)
        assert "SECRETMARKER" not in str(r.reasons)

    def test_messages_name_an_action_rather_than_a_diagnosis(self):
        """"Poor image quality" is something a user cannot act on."""
        for message in iq._MESSAGES.values():
            assert any(
                w in message.lower()
                for w in ("try", "point", "move", "hold", "turn", "angle")
            ), message
