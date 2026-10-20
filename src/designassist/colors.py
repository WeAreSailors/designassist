"""Colour values used in design.json, and the maths around them.

Accepted forms (anywhere a colour goes):
  "#RGB" "#RRGGBB" "#RRGGBBAA"      hex, optional alpha
  "rgb(255, 0, 0)" "rgba(255,0,0,0.5)"
  "$primary"                        a token from design.json `tokens.colors` or the brand kit
  "$primary/40"  "#E30613/40"       same colour at 40% opacity
  "none" / "transparent"
A token value can be a plain colour or {"hex": "#E30613", "cmyk": [0, 100, 95, 0], "pantone": "485 C"};
`cmyk` (0-100) is used as-is by print exports instead of a converted value.
"""
from __future__ import annotations

import colorsys
import os
import re
from dataclasses import dataclass
from pathlib import Path

NAMED = {"white": "#FFFFFF", "black": "#000000", "red": "#FF0000", "green": "#00FF00", "blue": "#0000FF"}


@dataclass(frozen=True)
class Color:
    r: int
    g: int
    b: int
    a: float = 1.0
    cmyk: tuple[float, float, float, float] | None = None  # authored CMYK (0-100), print only
    name: str | None = None  # token name it came from

    @property
    def hex(self) -> str:
        return f"#{self.r:02X}{self.g:02X}{self.b:02X}"

    @property
    def rgba(self) -> tuple[int, int, int, int]:
        return (self.r, self.g, self.b, round(self.a * 255))

    def with_alpha(self, a: float) -> "Color":
        return Color(self.r, self.g, self.b, a, self.cmyk, self.name)

    def svg(self) -> tuple[str, float]:
        """(fill colour, opacity) for SVG attributes."""
        return self.hex, self.a


class ColorError(ValueError):
    pass


def _hex(s: str) -> tuple[int, int, int, float]:
    h = s.lstrip("#")
    if len(h) in (3, 4):
        h = "".join(c * 2 for c in h)
    if len(h) not in (6, 8) or not re.fullmatch(r"[0-9a-fA-F]+", h):
        raise ColorError(f"bad hex colour {s!r}")
    a = int(h[6:8], 16) / 255 if len(h) == 8 else 1.0
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), a


def parse(value, tokens: dict | None = None, _depth: int = 0) -> Color | None:
    """Colour value -> Color, or None for none/transparent."""
    if value is None:
        return None
    if isinstance(value, Color):
        return value
    if isinstance(value, dict):
        base = parse(value.get("hex") or value.get("color"), tokens, _depth + 1)
        if base is None:
            return None
        cm = value.get("cmyk")
        a = float(value.get("alpha", base.a))
        return Color(base.r, base.g, base.b, a, tuple(float(x) for x in cm) if cm else base.cmyk, base.name)
    s = str(value).strip()
    if s.lower() in ("none", "transparent", ""):
        return None
    alpha = None
    m = re.fullmatch(r"(.+?)/(\d{1,3})", s)
    if m and not s.startswith("rgb"):
        s, alpha = m.group(1), int(m.group(2)) / 100
    if s.startswith("$"):
        if _depth > 8:
            raise ColorError(f"token loop at {s}")
        name = s[1:]
        tv = (tokens or {}).get(name)
        if tv is None:
            raise ColorError(f"unknown colour token {s} (define it in design.json tokens.colors or the brand kit)")
        c = parse(tv, tokens, _depth + 1)
        if c is None:
            return None
        c = Color(c.r, c.g, c.b, c.a, c.cmyk, name)
    elif s.lower() in NAMED:
        c = Color(*_hex(NAMED[s.lower()]))
    elif s.startswith("#"):
        c = Color(*_hex(s))
    elif s.startswith("rgb"):
        parts = re.findall(r"([\d.]+)(%?)", s)
        if len(parts) not in (3, 4):
            raise ColorError(f"bad rgb colour {s!r}")
        # percentages (pdftocairo / Illustrator SVGs write rgb(0%, 29.0%, 67.4%)) scale to 0-255 / 0-1
        ch = [round(float(v) * 2.55) if pc else int(float(v)) for v, pc in parts[:3]]
        a = (float(parts[3][0]) / 100 if parts[3][1] else float(parts[3][0])) if len(parts) == 4 else 1.0
        c = Color(*[max(0, min(255, v)) for v in ch], a)
    else:
        raise ColorError(f"bad colour {value!r} (use #RRGGBB, rgb(), or $token)")
    if alpha is not None:
        c = c.with_alpha(c.a * alpha)
    return c


# --- contrast (WCAG 2.x) -----------------------------------------------------------------

def _lin(v: float) -> float:
    v /= 255
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4


def luminance(c: Color) -> float:
    return 0.2126 * _lin(c.r) + 0.7152 * _lin(c.g) + 0.0722 * _lin(c.b)


def blend_over(top: Color, bottom: Color) -> Color:
    a = top.a
    return Color(round(top.r * a + bottom.r * (1 - a)), round(top.g * a + bottom.g * (1 - a)),
                 round(top.b * a + bottom.b * (1 - a)))


def contrast(fg: Color, bg: Color) -> float:
    if fg.a < 1:
        fg = blend_over(fg, bg)
    l1, l2 = sorted((luminance(fg), luminance(bg)), reverse=True)
    return round((l1 + 0.05) / (l2 + 0.05), 2)


def wcag(ratio: float, large: bool) -> str:
    """Grade for text: AAA / AA / fail. Large = >= 24 px regular or >= 18.66 px bold."""
    if ratio >= (4.5 if large else 7):
        return "AAA"
    if ratio >= (3 if large else 4.5):
        return "AA"
    return "fail"


# --- conversions ----------------------------------------------------------------------------

def to_hsl(c: Color) -> tuple[float, float, float]:
    h, l, s = colorsys.rgb_to_hls(c.r / 255, c.g / 255, c.b / 255)
    return h * 360, s * 100, l * 100


def from_hsl(h: float, s: float, l: float) -> Color:
    r, g, b = colorsys.hls_to_rgb((h % 360) / 360, max(0, min(100, l)) / 100, max(0, min(100, s)) / 100)
    return Color(round(r * 255), round(g * 255), round(b * 255))


def _cmyk_formula(c: Color) -> tuple[float, float, float, float]:
    r, g, b = c.r / 255, c.g / 255, c.b / 255
    k = 1 - max(r, g, b)
    if k >= 1:
        return (0.0, 0.0, 0.0, 100.0)
    return tuple(round(x * 100, 1) for x in ((1 - r - k) / (1 - k), (1 - g - k) / (1 - k), (1 - b - k) / (1 - k), k))


ICC_CANDIDATES = [
    # Adobe Creative Cloud installs these (the common print standard in Brazil/Europe is FOGRA39)
    "/Library/Application Support/Adobe/Color/Profiles/Recommended/CoatedFOGRA39.icc",
    "/Library/Application Support/Adobe/Color/Profiles/Recommended/USWebCoatedSWOP.icc",
    "C:/Program Files (x86)/Common Files/Adobe/Color/Profiles/Recommended/CoatedFOGRA39.icc",
    "C:/Program Files/Common Files/Adobe/Color/Profiles/Recommended/CoatedFOGRA39.icc",
    "C:/Windows/System32/spool/drivers/color/CoatedFOGRA39.icc",
    "/System/Library/ColorSync/Profiles/Generic CMYK Profile.icc",
    "/usr/share/color/icc/ghostscript/default_cmyk.icc",
]


def cmyk_profile() -> Path | None:
    env = os.environ.get("DA_CMYK_ICC")
    if env and Path(env).expanduser().is_file():
        return Path(env).expanduser()
    for p in ICC_CANDIDATES:
        if Path(p).is_file():
            return Path(p)
    return None


_TRANSFORM = None


def _icc_transform():
    global _TRANSFORM
    if _TRANSFORM is None:
        prof = cmyk_profile()
        if prof is None:
            _TRANSFORM = False
        else:
            from PIL import ImageCms

            try:
                _TRANSFORM = ImageCms.buildTransform(ImageCms.createProfile("sRGB"), str(prof), "RGB", "CMYK",
                                                     renderingIntent=ImageCms.Intent.RELATIVE_COLORIMETRIC)
            except Exception:  # unreadable profile: fall back to the formula
                _TRANSFORM = False
    return _TRANSFORM or None


def to_cmyk(c: Color) -> tuple[float, float, float, float]:
    """CMYK 0-100 for print: the authored value when the token has one, else the ICC profile
    (see cmyk_profile), else the naive formula. Pure black text stays K-only."""
    if c.cmyk:
        return c.cmyk
    if (c.r, c.g, c.b) == (0, 0, 0):
        return (0.0, 0.0, 0.0, 100.0)
    t = _icc_transform()
    if t is None:
        return _cmyk_formula(c)
    from PIL import Image, ImageCms

    px = ImageCms.applyTransform(Image.new("RGB", (1, 1), (c.r, c.g, c.b)), t).getpixel((0, 0))
    return tuple(round(v / 255 * 100, 1) for v in px)


def rgb_image_to_cmyk(img):
    """PIL RGB(A) image -> CMYK image through the same profile (alpha flattened on white)."""
    from PIL import Image, ImageCms

    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[-1])
        img = bg
    else:
        img = img.convert("RGB")
    t = _icc_transform()
    return ImageCms.applyTransform(img, t) if t else img.convert("CMYK")
