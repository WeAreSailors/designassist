from __future__ import annotations

import json
import re
import zlib

import pytest
from PIL import Image

from designassist import design as D
from designassist import export as E
from designassist import pdf as PDF
from designassist.cli import main

MM = 72 / 25.4


def _streams(pdf_bytes: bytes) -> bytes:
    """All streams of a PDF (content streams and images), inflated when Flate-compressed."""
    out = []
    for m in re.finditer(rb"/Length (\d+)[^>]*>>\s*stream\r?\n", pdf_bytes):
        raw = pdf_bytes[m.end():m.end() + int(m.group(1))]
        try:
            out.append(zlib.decompress(raw))
        except zlib.error:
            out.append(raw)
    return b"\n".join(out)


def _box(pdf_bytes: bytes, name: bytes) -> list[float]:
    m = re.search(rb"/" + name + rb" \[ ([^\]]+) \]", pdf_bytes)
    return [float(v) for v in m.group(1).split()]


def test_print_pdf_boxes_and_cmyk(sample):
    res = E.export(sample, ["print"], ["card"])
    r = res["print"][0]
    data = sample.path(r["file"]).read_bytes()
    trim_w, trim_h, bleed = 90 * MM, 50 * MM, 3 * MM
    off = bleed + PDF.SLUG_MM * MM
    media = _box(data, b"MediaBox")
    assert media[2] == pytest.approx((90 + 2 * 3 + 2 * PDF.SLUG_MM) * MM, abs=0.05)
    assert media[3] == pytest.approx((50 + 2 * 3 + 2 * PDF.SLUG_MM) * MM, abs=0.05)
    trim = _box(data, b"TrimBox")
    assert trim == pytest.approx([off, off, off + trim_w, off + trim_h], abs=0.05)
    bl = _box(data, b"BleedBox")
    assert bl == pytest.approx([off - bleed, off - bleed, off + trim_w + bleed, off + trim_h + bleed], abs=0.05)
    content = _streams(data)
    # authored CMYK of $primary (0 100 95 0) reaches the PDF untouched, as a fill operator
    assert re.search(rb"(^|\s)0 1 \.95 0 k", content), content[:400]
    assert not re.search(rb"\srg(\s|$)", content) and not re.search(rb"\sRG(\s|$)", content)
    assert re.search(rb"\sK(\s|$)", content)  # crop marks stroke in registration CMYK
    assert r["preflight"]["errors"] == []


def test_print_pdf_preflight_flags_low_dpi_and_bleed(sample):
    d = D.load(sample)
    card = D.artboard(d, "card")
    # a photo that touches the left/top trim without extending into the bleed, at low resolution
    card["layers"].insert(0, {"id": "pic", "type": "image", "src": "input/photo.jpg", "x": 0, "y": 0, "w": 45, "h": 50})
    card["layers"].append({"id": "edge", "type": "text", "text": "Rodapé", "x": 1, "y": 46, "w": 40, "size": "8pt"})
    D.save(sample, d)
    pf = E.export(sample, ["print"], ["card"])["print"][0]["preflight"]
    assert any("pic" in w and "bleed" in w for w in pf["warnings"]), pf
    assert any("edge" in w and "trim" in w for w in pf["warnings"]), pf
    img = [i for i in pf["images"] if i["layer"] == "pic"][0]
    assert img["effective_dpi"] < 1000 and img["verdict"] in ("ok", "low", "too low")


def test_print_rasterized_layers_stay_cmyk(sample):
    """Shadows / transparent gradients are bitmaps in print: CMYK pixels with a soft mask, not RGB."""
    res = E.export(sample, ["print"], ["post"])["print"][0]
    data = sample.path(res["file"]).read_bytes()
    why = {r["layer"]: r["why"] for r in res["preflight"]["rasterized"]}
    assert why.get("cta-bg") == "drop shadow" and why.get("logo") == "svg artwork"
    assert b"/SMask" in data
    assert b"/DeviceRGB" not in data
    assert b"/DeviceCMYK" in data


def test_screen_pdf_multipage(sample):
    r = E.export(sample, ["pdf"])["pdf"]
    data = sample.path(r["file"]).read_bytes()
    assert r["file"] == "output/sample.pdf"
    assert len(r["pages"]) == 2
    assert r["pages"][0]["page_pt"] == [1080.0, 1350.0]
    assert data.count(b"/Type /Page\n") + data.count(b"/Type /Page ") >= 2 or data.count(b"/Page") >= 2
    content = _streams(data)
    assert re.search(rb"\srg(\s|$)", content)  # RGB fills in screen mode
    assert "TrimBox" not in data.decode("latin-1")


def test_psd_layers_and_canvas(sample):
    from psd_tools import PSDImage

    r = E.export(sample, ["psd"], ["post"], scale=0.5)["psd"][0]
    assert r["file"] == "output/post@0.5x.psd"
    psd = PSDImage.open(sample.path(r["file"]))
    assert psd.size == (540, 675)
    names = [l.name for l in psd.descendants()]
    for n in ("background", "photo", "shade", "title", "cta", "cta-bg", "cta-tx", "logo"):
        assert n in names, names
    group = [l for l in psd.descendants() if l.name == "cta"][0]
    assert group.is_group()
    title = [l for l in psd.descendants() if l.name == "title"][0]
    assert title.bbox[0] >= 38 and title.bbox[1] >= 445  # cropped to its own bounds (80, 900 at 0.5x)


def test_psd_opacity_and_blend_are_layer_properties(sample):
    from psd_tools import PSDImage
    from psd_tools.constants import BlendMode

    d = D.load(sample)
    post = D.artboard(d, "post")
    post["layers"].append({"id": "glow", "type": "ellipse", "x": 100, "y": 100, "w": 200, "h": 200, "fill": "$accent",
                           "opacity": 0.5, "blend": "screen"})
    D.save(sample, d)
    r = E.export(sample, ["psd"], ["post"], scale=0.25)["psd"][0]
    glow = [l for l in PSDImage.open(sample.path(r["file"])).descendants() if l.name == "glow"][0]
    assert glow.opacity == 128 and glow.blend_mode == BlendMode.SCREEN
    px = glow.topil().convert("RGBA").getpixel((25, 25))
    assert px[3] == 255  # pixels at full strength; opacity lives on the layer


def test_svg_editable_vs_outlined(sample):
    r = E.export(sample, ["svg", "svg-outlined"], ["post"])
    ed = sample.path(r["svg"][0]["file"]).read_text(encoding="utf-8")
    ol = sample.path(r["svg-outlined"][0]["file"]).read_text(encoding="utf-8")
    assert "<text" in ed and "Montserrat" in ed
    assert "<text" not in ol
    assert "data:image/jpeg;base64," in ol  # self-contained
    assert r["svg-outlined"][0]["file"] == "output/post-outlined.svg"


def test_raster_formats_and_scale(sample):
    r = E.export(sample, ["png", "jpg", "webp"], ["post"], scale=0.5, quality=80)
    for fmt in ("png", "jpg", "webp"):
        f = sample.path(r[fmt][0]["file"])
        assert f.name == f"post@0.5x.{fmt}"
        im = Image.open(f)
        assert im.size == (540, 675)
    assert Image.open(sample.path(r["jpg"][0]["file"])).mode == "RGB"


def test_package_readme_lists_colours_and_fonts(sample):
    res = E.package(sample, zip_=True, targets=["png", "pdf"])
    readme = sample.path("output", "package", "README.txt").read_text(encoding="utf-8")
    assert "$primary" in readme and "#E30613" in readme and "CMYK 0/100/95/0 (authored)" in readme
    assert "Montserrat 800" in readme and "fonts.google.com" in readme
    assert "card: 90 x 50 mm (1063x591 px at 300 dpi), bleed 3 mm" in readme
    assert sample.path(res["zip"]).exists()
    assert "post.png" in res["files"] and "sample.pdf" in res["files"]


def test_package_purpose_print_includes_print_pdf(sample):
    sample.update_settings(purpose="print")
    d = D.load(sample)
    d["artboards"] = [D.artboard(d, "card")]
    D.save(sample, d)
    res = E.package(sample)
    assert res["purpose"] == "print"
    assert "print/card-print.pdf" in res["files"]


def test_adobe_targets_degrade_or_delegate(sample):
    r = E.export(sample, ["illustrator"], ["post"])["illustrator"]
    assert isinstance(r, dict)  # either the script result (fork adobe.py) or a clear error


def test_cli_export(sample, capsys):
    main(["export", "sample", "--to", "png", "--artboard", "card"])
    out = json.loads(capsys.readouterr().out)
    assert out["png"][0]["file"] == "output/card.png"


def test_svg_path_parser_handles_relative_arcs_and_smooth_curves():
    class Rec:
        def __init__(self):
            self.ops = []

        def __getattr__(self, name):
            return lambda *a: self.ops.append((name, a))

    p = Rec()
    PDF.svg_path_to(p, "M10 10 h20 v20 a10 10 0 0 1 -10 10 s-5 -5 -10 -10 q5 -5 10 0 t10 0 z")
    names = [o[0] for o in p.ops]
    assert names[0] == "moveTo" and names[-1] == "close"
    assert "curveTo" in names and names.count("lineTo") == 2
    # arc ends exactly at (20, 40)
    arc_end = [o for o in p.ops if o[0] == "curveTo"][0][1][-2:]
    assert arc_end == pytest.approx((20, 40), abs=1e-6)


def test_print_skips_px_artboards_in_mixed_projects(sample):
    from designassist.export import export

    res = export(sample, ["print"])
    assert [p["pages"][0]["artboard"] for p in res["print"]] == ["card"]
    res = export(sample, ["print"], artboards=["post"])  # asked explicitly: still allowed
    assert res["print"][0]["pages"][0]["artboard"] == "post"
