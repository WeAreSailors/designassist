"""Shared fixtures: every test runs against a throwaway projects/ folder and design memory, with
synthetic images only (no API keys, no network unless a test is marked `network`)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image, ImageDraw


def pytest_configure(config):
    config.addinivalue_line("markers", "network: needs internet (skipped with -m 'not network')")


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """projects/ and the design memory live in tmp_path for every test."""
    import designassist.project as P

    monkeypatch.setattr(P, "PROJECTS", tmp_path / "projects")
    monkeypatch.setenv("DA_MEMORY_DIR", str(tmp_path / "memory"))
    (tmp_path / "projects").mkdir()
    return tmp_path


def make_photo(path: Path, size=(1600, 1200), face_at=(0.7, 0.35)) -> Path:
    """A synthetic 'photo': vertical gradient plus a skin-coloured disc."""
    im = Image.new("RGB", size)
    d = ImageDraw.Draw(im)
    for y in range(size[1]):
        d.line([(0, y), (size[0], y)], fill=(30 + y * 120 // size[1], 60 + y * 80 // size[1], 120))
    cx, cy, r = size[0] * face_at[0], size[1] * face_at[1], min(size) * 0.15
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(235, 195, 160))
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path, quality=92)
    return path


SAMPLE_SVG = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 40"><rect width="40" height="40" fill="#E30613"/>'
              '<circle cx="70" cy="20" r="18" fill="#111111"/></svg>')


@pytest.fixture
def sample(isolated):
    """A project with a photo, a logo SVG and a two-artboard design (social px + print mm)."""
    from designassist.project import Project

    pr = Project.create("sample")
    make_photo(pr.path("input", "photo.jpg"))
    pr.path("input", "logo.svg").write_text(SAMPLE_SVG, encoding="utf-8")
    design = {
        "version": 1, "name": "sample", "brand": None,
        "tokens": {"colors": {"primary": {"hex": "#E30613", "cmyk": [0, 100, 95, 0]}, "accent": "#FFD400"},
                   "fonts": {"display": {"family": "Montserrat", "weight": 800}}},
        "artboards": [
            {"id": "post", "preset": "ig-post", "width": 1080, "height": 1350, "unit": "px", "dpi": 72, "bleed": 0,
             "safe": [60, 60, 60, 60], "background": "$ink", "layers": [
                {"id": "photo", "type": "image", "src": "input/photo.jpg", "x": 0, "y": 0, "w": 1080, "h": 860,
                 "fit": "cover", "focus": "face", "role": "photo"},
                {"id": "shade", "type": "rect", "x": 0, "y": 500, "w": 1080, "h": 400,
                 "fill": {"type": "linear", "angle": 90, "stops": [[0, "$ink/0"], [1, "$ink"]]}},
                {"id": "title", "type": "text", "text": "Até **50% off** na linha de verão", "x": 80, "y": 900,
                 "w": 920, "h": 260, "autofit": True, "font": "$display", "size": 110, "line_height": 1.0,
                 "color": "$paper", "accent": {"color": "$accent"}, "role": "headline"},
                {"id": "cta", "type": "group", "x": 80, "y": 1190, "layers": [
                    {"id": "cta-bg", "type": "rect", "x": 0, "y": 0, "w": 360, "h": 80, "radius": 40, "fill": "$primary",
                     "shadow": {"y": 8, "blur": 20, "color": "#00000066"}},
                    {"id": "cta-tx", "type": "text", "text": "Compre já", "x": 0, "y": 0, "w": 360, "h": 80,
                     "align": "center", "valign": "middle", "weight": 700, "size": 32, "color": "$paper", "role": "cta"}]},
                {"id": "logo", "type": "svg", "src": "input/logo.svg", "x": 840, "y": 70, "w": 160, "h": 64,
                 "color": "$paper", "role": "logo"},
            ]},
            {"id": "card", "preset": "card-br", "width": 90, "height": 50, "unit": "mm", "dpi": 300, "bleed": 3,
             "margin": 4, "background": "$primary", "layers": [
                {"id": "name", "type": "text", "text": "Ana Souza", "x": 6, "y": 8, "w": 70, "size": "14pt",
                 "font": "$display", "color": "$paper"},
                {"id": "role", "type": "text", "text": "Diretora de arte", "x": 6, "y": 15, "w": 70, "size": "8pt",
                 "color": "$paper"},
                {"id": "mark", "type": "ellipse", "x": 70, "y": 30, "w": 14, "h": 14, "fill": "$paper"},
            ]},
        ],
    }
    pr.path("design.json").write_text(json.dumps(design, ensure_ascii=False, indent=2), encoding="utf-8")
    return pr
