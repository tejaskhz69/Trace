"""Synthetic scan fixtures: every frame generated, none photographed.

WHY SYNTHETIC AND NOT A PHOTO CORPUS
A real photo of a real packet in a real kitchen is somebody's data. Even a
"safe" one carries EXIF, a background, and whatever else was on the counter,
and once it is in the repository it is in every clone forever. These are drawn
with Pillow at call time, so nothing is stored, nothing is copyrighted, and
every case is reproducible byte-for-byte on any machine.

WHAT THAT COSTS, STATED PLAINLY
A drawn rectangle is not a photograph. These exercise the DECISION BOUNDARIES
of `image_quality` -- is this dark, is this flat, is this too small -- and they
do it reliably. They do NOT tell you how the thresholds behave on a real
phone camera pointed at foil under a kitchen light. That needs a device and a
human, and it is listed as an outstanding measurement rather than pretended
away here.
"""

from __future__ import annotations

import io


def _encode(img, fmt: str = "JPEG", quality: int = 92) -> bytes:
    buf = io.BytesIO()
    img.save(buf, fmt, quality=quality)
    return buf.getvalue()


def nutrition_label(size: tuple[int, int] = (800, 800)):
    """A legible panel: dark rows on a light box, with rules between them.

    Stands in for the everyday good case -- enough edge energy to be clearly
    in focus, enough light background to be realistically bright.
    """
    from PIL import Image, ImageDraw

    img = Image.new("RGB", size, (245, 245, 242))
    d = ImageDraw.Draw(img)
    rows = max(4, size[1] // 57)
    for r in range(rows):
        y = 60 + r * 48
        if y + 34 > size[1]:
            break
        d.rectangle([60, y, min(440, size[0] - 40), y + 16], fill=(30, 30, 30))
        if size[0] > 700:
            d.rectangle([520, y, 670, y + 16], fill=(60, 60, 60))
        d.line([50, y + 34, size[0] - 50, y + 34], fill=(200, 200, 200), width=2)
    return img


# --- the fixture set ------------------------------------------------------
#
# Each returns encoded bytes, ready to hand to `assess_image`.


def clear_label() -> bytes:
    return _encode(nutrition_label())


def blurry_label(radius: int = 9) -> bytes:
    from PIL import ImageFilter

    return _encode(nutrition_label().filter(ImageFilter.GaussianBlur(radius)))


def dark_image() -> bytes:
    """Under-lit to the point a camera is recording mostly noise."""
    from PIL import Image

    return _encode(Image.eval(nutrition_label(), lambda p: int(p * 0.10)))


def overexposed_image() -> bytes:
    """Highlights gone -- a phone torch straight onto a glossy box."""
    from PIL import Image

    return _encode(Image.eval(nutrition_label(), lambda p: min(255, int(p * 0.3 + 225))))


def reflective_packaging() -> bytes:
    """Foil: specular highlights clipped to white, structure elsewhere intact.

    The interesting case, because it clips heavily while remaining readable --
    which is exactly why clipping alone must not condemn a frame.
    """
    from PIL import Image

    return _encode(Image.eval(nutrition_label(), lambda p: 255 if p > 150 else p))


def rotated_label(degrees: int = 37) -> bytes:
    """Rotation is not a defect. Included to prove it is not treated as one."""
    return _encode(
        nutrition_label().rotate(degrees, expand=True, fillcolor=(245, 245, 242))
    )


def multilingual_label() -> bytes:
    """Two columns of text, as on a bilingual EU or Indian pack.

    Drawn rather than typeset: no font file is bundled, and the quality checks
    are measuring gradient energy rather than reading glyphs.
    """
    from PIL import Image, ImageDraw

    img = nutrition_label()
    d = ImageDraw.Draw(img)
    for r in range(12):
        y = 70 + r * 48
        d.rectangle([690, y, 770, y + 14], fill=(45, 45, 45))
    return _encode(img)


def multiple_food_items() -> bytes:
    """Several distinct regions -- a thali or a packed lunch."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (800, 800), (200, 195, 185))
    d = ImageDraw.Draw(img)
    for cx, cy, r, fill in (
        (230, 250, 130, (190, 140, 60)),
        (560, 240, 110, (220, 210, 170)),
        (250, 570, 120, (150, 170, 90)),
        (570, 580, 100, (210, 120, 90)),
    ):
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fill, outline=(90, 80, 70), width=4)
    return _encode(img)


def missing_nutrition_panel() -> bytes:
    """The front of a pack: a big block of colour, no printed table."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (800, 800), (180, 40, 50))
    d = ImageDraw.Draw(img)
    d.ellipse([220, 260, 580, 540], fill=(240, 230, 200))
    return _encode(img)


def empty_frame() -> bytes:
    """A wall, a table, a lens cap, or a hand over the camera."""
    from PIL import Image

    return _encode(Image.new("RGB", (800, 800), (128, 128, 128)))


def tiny_image() -> bytes:
    """Smaller than any real capture: a thumbnail or a cropped fragment."""
    return _encode(nutrition_label((120, 120)))


def not_an_image() -> bytes:
    return b"this is not an image at all"


#: Everything above, for parametrised sweeps. The value is the expected
#: `should_upload`: only frames that CANNOT contain the answer are refused.
ALL_FIXTURES: dict[str, tuple] = {
    "clear_label": (clear_label, True),
    "blurry_label": (blurry_label, True),
    "dark_image": (dark_image, True),
    "overexposed_image": (overexposed_image, True),
    "reflective_packaging": (reflective_packaging, True),
    "rotated_label": (rotated_label, True),
    "multilingual_label": (multilingual_label, True),
    "multiple_food_items": (multiple_food_items, True),
    "missing_nutrition_panel": (missing_nutrition_panel, True),
    "empty_frame": (empty_frame, False),
    "tiny_image": (tiny_image, False),
    "not_an_image": (not_an_image, False),
}
