"""Format presets: canvas size, unit, resolution and the safe zone platforms cover with their UI.

`safe` is [top, right, bottom, left] in the preset's unit: keep text and logos inside it.
Print presets are trim size in mm with bleed; `da qa` checks text against `margin` from the trim.
"""
from __future__ import annotations

PRESETS: dict[str, dict] = {
    # --- social (px) ---
    "ig-post": {"width": 1080, "height": 1350, "unit": "px", "kind": "social", "label": "Instagram post 4:5", "safe": [60, 60, 60, 60]},
    "ig-square": {"width": 1080, "height": 1080, "unit": "px", "kind": "social", "label": "Instagram square 1:1", "safe": [60, 60, 60, 60]},
    "ig-story": {"width": 1080, "height": 1920, "unit": "px", "kind": "social", "label": "Instagram/Facebook story, Reels/TikTok cover 9:16", "safe": [250, 80, 340, 80]},
    "ig-grid": {"width": 1080, "height": 1440, "unit": "px", "kind": "social", "label": "Instagram profile grid 3:4", "safe": [60, 60, 60, 60]},
    "carousel": {"width": 1080, "height": 1350, "unit": "px", "kind": "social", "label": "carousel slide 4:5", "safe": [60, 60, 100, 60]},
    "yt-thumb": {"width": 1280, "height": 720, "unit": "px", "kind": "social", "label": "YouTube thumbnail", "safe": [40, 220, 90, 40]},
    "yt-banner": {"width": 2560, "height": 1440, "unit": "px", "kind": "social", "label": "YouTube channel banner (safe 1546x423 centre)", "safe": [508, 507, 509, 507]},
    "li-post": {"width": 1200, "height": 1200, "unit": "px", "kind": "social", "label": "LinkedIn post 1:1", "safe": [60, 60, 60, 60]},
    "li-carousel": {"width": 1080, "height": 1350, "unit": "px", "kind": "social", "label": "LinkedIn document carousel (export PDF)", "safe": [60, 60, 60, 60]},
    "li-banner": {"width": 1584, "height": 396, "unit": "px", "kind": "social", "label": "LinkedIn profile banner", "safe": [40, 40, 40, 420]},
    "fb-cover": {"width": 1640, "height": 624, "unit": "px", "kind": "social", "label": "Facebook page cover", "safe": [40, 120, 40, 120]},
    "x-post": {"width": 1600, "height": 900, "unit": "px", "kind": "social", "label": "X / Twitter post 16:9", "safe": [40, 40, 40, 40]},
    "x-header": {"width": 1500, "height": 500, "unit": "px", "kind": "social", "label": "X / Twitter header", "safe": [60, 60, 60, 60]},
    "pin": {"width": 1000, "height": 1500, "unit": "px", "kind": "social", "label": "Pinterest pin 2:3", "safe": [50, 50, 50, 50]},
    "wa-status": {"width": 1080, "height": 1920, "unit": "px", "kind": "social", "label": "WhatsApp status", "safe": [200, 60, 200, 60]},
    "og-image": {"width": 1200, "height": 630, "unit": "px", "kind": "web", "label": "link preview (Open Graph)", "safe": [40, 60, 40, 60]},
    # --- ads ---
    "ad-feed": {"width": 1080, "height": 1350, "unit": "px", "kind": "social", "label": "Meta feed ad 4:5", "safe": [60, 60, 60, 60]},
    "ad-story": {"width": 1080, "height": 1920, "unit": "px", "kind": "social", "label": "Meta story/reels ad 9:16", "safe": [270, 65, 380, 65]},
    "ad-landscape": {"width": 1200, "height": 628, "unit": "px", "kind": "social", "label": "landscape ad 1.91:1", "safe": [40, 40, 40, 40]},
    "gdn-rect": {"width": 300, "height": 250, "unit": "px", "kind": "web", "label": "Google display medium rectangle", "safe": [8, 8, 8, 8]},
    "gdn-leader": {"width": 728, "height": 90, "unit": "px", "kind": "web", "label": "Google display leaderboard", "safe": [6, 6, 6, 6]},
    "gdn-sky": {"width": 160, "height": 600, "unit": "px", "kind": "web", "label": "Google display wide skyscraper", "safe": [8, 8, 8, 8]},
    # --- web / UI (px) ---
    "desktop": {"width": 1440, "height": 900, "unit": "px", "kind": "web", "label": "desktop screen"},
    "laptop": {"width": 1280, "height": 800, "unit": "px", "kind": "web", "label": "laptop screen"},
    "tablet": {"width": 834, "height": 1194, "unit": "px", "kind": "web", "label": "tablet portrait"},
    "mobile": {"width": 390, "height": 844, "unit": "px", "kind": "web", "label": "mobile (iPhone 14/15)", "safe": [47, 0, 34, 0]},
    "email": {"width": 600, "height": 1200, "unit": "px", "kind": "web", "label": "email body 600 wide"},
    "slide": {"width": 1920, "height": 1080, "unit": "px", "kind": "web", "label": "presentation slide 16:9", "safe": [60, 80, 60, 80]},
    # --- identity ---
    "logo": {"width": 1000, "height": 1000, "unit": "px", "kind": "identity", "label": "logo artboard"},
    "logo-wide": {"width": 1600, "height": 800, "unit": "px", "kind": "identity", "label": "horizontal logo artboard"},
    "avatar": {"width": 1080, "height": 1080, "unit": "px", "kind": "identity", "label": "profile picture (circle crop)", "safe": [158, 158, 158, 158]},
    "favicon": {"width": 512, "height": 512, "unit": "px", "kind": "identity", "label": "app icon / favicon master"},
    "brand-board": {"width": 1920, "height": 1080, "unit": "px", "kind": "identity", "label": "brand presentation board"},
    # --- print (mm, trim size) ---
    "card-br": {"width": 90, "height": 50, "unit": "mm", "kind": "print", "label": "business card (Brazil 9x5 cm)", "bleed": 3, "margin": 4},
    "card-us": {"width": 88.9, "height": 50.8, "unit": "mm", "kind": "print", "label": "business card (US 3.5x2 in)", "bleed": 3, "margin": 4},
    "card-eu": {"width": 85, "height": 55, "unit": "mm", "kind": "print", "label": "business card (EU 85x55)", "bleed": 3, "margin": 4},
    "a6": {"width": 105, "height": 148, "unit": "mm", "kind": "print", "label": "A6 flyer", "bleed": 3, "margin": 6},
    "a5": {"width": 148, "height": 210, "unit": "mm", "kind": "print", "label": "A5 flyer", "bleed": 3, "margin": 8},
    "a4": {"width": 210, "height": 297, "unit": "mm", "kind": "print", "label": "A4", "bleed": 3, "margin": 10},
    "a3": {"width": 297, "height": 420, "unit": "mm", "kind": "print", "label": "A3 poster", "bleed": 3, "margin": 12},
    "a2": {"width": 420, "height": 594, "unit": "mm", "kind": "print", "label": "A2 poster", "bleed": 3, "margin": 15},
    "letter": {"width": 215.9, "height": 279.4, "unit": "mm", "kind": "print", "label": "US Letter", "bleed": 3, "margin": 10},
    "dl": {"width": 99, "height": 210, "unit": "mm", "kind": "print", "label": "DL flyer (1/3 A4)", "bleed": 3, "margin": 6},
    "trifold-a4": {"width": 297, "height": 210, "unit": "mm", "kind": "print", "label": "A4 tri-fold brochure (one side, 3 panels)", "bleed": 3, "margin": 8},
    "poster-50x70": {"width": 500, "height": 700, "unit": "mm", "kind": "print", "label": "poster 50x70 cm", "bleed": 5, "margin": 20},
    "banner-80x120": {"width": 800, "height": 1200, "unit": "mm", "kind": "print", "label": "roll-up / lona 80x120 cm", "bleed": 10, "margin": 40, "dpi": 150},
    "sticker-5": {"width": 50, "height": 50, "unit": "mm", "kind": "print", "label": "sticker 5x5 cm", "bleed": 2, "margin": 3},
    "letterhead": {"width": 210, "height": 297, "unit": "mm", "kind": "print", "label": "letterhead A4", "bleed": 3, "margin": 15},
    "envelope-c5": {"width": 229, "height": 162, "unit": "mm", "kind": "print", "label": "envelope C5", "bleed": 3, "margin": 10},
}


def get(name: str) -> dict:
    if name not in PRESETS:
        close = [k for k in PRESETS if name.split("-")[0] in k]
        raise SystemExit(f"unknown preset {name!r}" + (f"; did you mean {', '.join(close)}?" if close else "")
                         + " (`da presets` lists them)")
    p = dict(PRESETS[name])
    p.setdefault("dpi", 300 if p["unit"] == "mm" else 72)
    p.setdefault("bleed", 0)
    return p


def listing(kind: str | None = None) -> list[dict]:
    return [{"preset": k, **v} for k, v in PRESETS.items() if kind is None or v["kind"] == kind]
