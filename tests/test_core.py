from __future__ import annotations

import json

import pytest
from PIL import Image

from designassist import colors as C
from designassist import design as D
from designassist import fonts as F
from designassist import text as T
from designassist.cli import main
from designassist.project import Project


def test_colors_parse_tokens_alpha_and_cmyk():
    toks = {"primary": {"hex": "#E30613", "cmyk": [0, 100, 95, 0]}, "brand": "$primary"}
    c = C.parse("$brand/40", toks)
    assert c.hex == "#E30613" and abs(c.a - 0.4) < 1e-9 and c.cmyk == (0, 100, 95, 0)
    assert C.parse("#0008").a == pytest.approx(0x88 / 255)
    assert C.parse("none") is None
    assert C.to_cmyk(C.parse("#000000")) == (0, 0, 0, 100)
    with pytest.raises(C.ColorError):
        C.parse("$missing", toks)


def test_contrast_matches_wcag_reference():
    assert C.contrast(C.parse("#000"), C.parse("#fff")) == 21.0
    assert C.contrast(C.parse("#777777"), C.parse("#ffffff")) == pytest.approx(4.48, abs=0.01)
    assert C.wcag(4.5, large=False) == "AA" and C.wcag(3.1, large=True) == "AA" and C.wcag(2, True) == "fail"


def test_lengths_convert_between_units():
    assert D.length("12pt", "mm") == pytest.approx(4.2333, abs=1e-3)
    assert D.length("3mm", "px", dpi=300) == pytest.approx(35.43, abs=0.01)
    assert D.length(10, "mm") == 10
    assert D.px_per_unit({"unit": "mm", "dpi": 300}) == pytest.approx(11.811, abs=1e-3)


def test_font_resolution_variable_and_static():
    r = F.resolve("montserrat", 650)
    assert r.family == "Montserrat"
    assert ("wght", 650.0) in r.location or r.weight in (600, 700)
    bold = F.resolve("Montserrat", 900)
    assert bold.weight == 900
    with pytest.raises(LookupError):
        F.resolve("No Such Family Xyz")
    fb = F.resolve_or_fallback("No Such Family Xyz", 400)
    assert fb.fallback and fb.family == "Montserrat"


def _ctx(sample):
    d = D.load(sample)
    return D.context(sample, d), d


def test_text_wraps_and_autofits_inside_box(sample):
    ctx, d = _ctx(sample)
    title = D.find_layer(d["artboards"][0]["layers"], "title")
    lay = T.layout(title, ctx)
    assert not lay.overflow
    long = T.layout({**title, "text": title["text"] + " e muito mais para toda a família"}, ctx)
    assert not long.overflow and long.size < 110  # shrunk to fit 920x260
    assert long.content_h <= 260 + 1e-6
    assert lay.content_h <= 260 + 1e-6
    assert all(ln.width <= 920 + 1e-6 for ln in lay.lines)
    assert "".join(r.text for ln in lay.lines for r in ln.runs).replace(" ", "") == "Até50%offnalinhadeverão"
    # accent span carries its own colour
    colors = {r.style.color.hex for ln in lay.lines for r in ln.runs}
    assert "#FFD400" in colors and "#FFFFFF" in colors


def test_text_overflow_flagged_without_autofit(sample):
    ctx, _ = _ctx(sample)
    lay = T.layout({"id": "t", "type": "text", "text": "palavra " * 40, "x": 0, "y": 0, "w": 300, "h": 100, "size": 40}, ctx)
    assert lay.overflow
    lay2 = T.layout({"id": "t", "type": "text", "text": "a b c d e f g h", "x": 0, "y": 0, "w": 60, "size": 40,
                     "max_lines": 2}, ctx)
    assert lay2.truncated and len(lay2.lines) == 2


def test_alignment_and_justify(sample):
    ctx, _ = _ctx(sample)
    base = {"id": "t", "type": "text", "text": "um dois três quatro cinco seis sete oito nove dez", "x": 10, "y": 0,
            "w": 400, "size": 40}
    right = T.layout({**base, "align": "right"}, ctx)
    assert all(abs(ln.x + ln.width - 410) < 0.01 for ln in right.lines)
    just = T.layout({**base, "align": "justify"}, ctx)
    assert len(just.lines) > 1
    for ln in just.lines[:-1]:
        last = ln.runs[-1]
        end = last.glyphs[-1].x + last.glyphs[-1].adv - last.style.track
        assert end == pytest.approx(410, abs=0.5)


def test_render_png_and_sheet(sample):
    from designassist import render

    res = render.render(sample)
    files = {r["artboard"]: sample.path(r["file"]) for r in res["rendered"]}
    post = Image.open(files["post"])
    assert post.size == (1080, 1350)
    card = Image.open(files["card"])
    assert card.size == (1063, 591)  # 90x50 mm at 300 dpi
    assert sample.path(res["sheet"]).exists()
    assert all(not r["problems"] for r in res["rendered"]), res
    # the CTA pill is the primary red
    px = post.convert("RGB").getpixel((80 + 30, 1190 + 40))
    assert px[0] > 200 and px[1] < 40
    # bleed adds 3 mm per side
    res_b = render.render(sample, ["card"], bleed=True, sheet=False)
    assert Image.open(sample.path(res_b["rendered"][0]["file"])).size == (1134, 661)


def test_image_cover_focus_on_face(sample):
    from designassist import images as I

    im = I.open_image(sample.path("input", "photo.jpg"))
    fx, fy = I.focus_point(im, "face")
    # the synthetic disc is at (0.7, 0.35); YuNet may not see a disc as a face, then default (0.5, 0.4)
    assert 0 <= fx <= 1 and 0 <= fy <= 1
    box = I.crop_box(1600, 1200, 1080, 1350, 0.7, 0.35)
    assert box[2] - box[0] == pytest.approx(960, abs=1) and box[3] - box[1] == 1200
    assert box[0] == round(0.7 * 1600 - 480)


def test_validate_catches_errors(sample):
    d = D.load(sample)
    d["artboards"][0]["layers"].append({"id": "title", "type": "text", "text": "dup"})
    d["artboards"][0]["layers"].append({"id": "x", "type": "blob"})
    d["artboards"][0]["layers"].append({"id": "img", "type": "image", "src": "input/nope.png", "w": 1, "h": 1})
    res = D.validate(d, D.context(sample, d))
    errs = "\n".join(res["errors"])
    assert "duplicated layer id" in errs and "unknown type" in errs and "source not found" in errs


def test_validate_warns_on_highlight_pad_in_pixels(sample):
    # pad [14, 2] meant pixels but is read as 14x the font size: a box over the whole artboard
    d = D.load(sample)
    d["artboards"][0]["layers"].append({"id": "hook", "type": "text", "text": "**OI**", "x": 0, "y": 0, "size": 80,
                                        "accent": {"highlight": {"color": "#fff", "pad": [14, 2]}}})
    d["artboards"][0]["layers"].append({"id": "ok", "type": "text", "text": "OI", "x": 0, "y": 0, "size": 80,
                                        "highlight": {"color": "#fff", "pad": [0.15, "4px"]}})
    warns = "\n".join(D.validate(d)["warnings"])
    assert "post/hook: highlight pad" in warns and "post/ok" not in warns


def test_cli_new_with_presets_and_render(isolated, capsys):
    main(["new", "promo", "--preset", "ig-post", "ig-story", "--client", "Vulcano Motors"])
    out = json.loads(capsys.readouterr().out)
    assert out["artboards"] == ["ig-post", "ig-story"] and out["client"]["client"] == "vulcano-motors"
    pr = Project("promo")
    d = D.load(pr)
    assert d["brand"] == "vulcano-motors" and d["artboards"][1]["safe"]
    main(["render", "promo"])
    res = json.loads(capsys.readouterr().out)
    assert len(res["rendered"]) == 2


def test_cli_version_roundtrip(sample, capsys):
    main(["version", "sample", "save", "first"])
    d = D.load(sample)
    d["artboards"].pop()
    D.save(sample, d)
    main(["version", "sample", "restore", "v1"])
    assert len(D.load(sample)["artboards"]) == 2


def test_face_focus_is_cached_per_source(sample, monkeypatch):
    from designassist import images as I

    calls = []
    real = I.focus_point
    monkeypatch.setattr(I, "focus_point", lambda im, f: calls.append(f) or real(im, f))
    layer = {"fit": "cover", "focus": "face"}
    src = sample.path("input", "photo.jpg")
    cache = sample.path("work", "cache")
    I.prepare(layer, src, 400, 500, cache, None)
    I.prepare(layer, src, 800, 1000, cache, None)
    assert calls == ["face"]


def test_optical_alignment_puts_ink_on_x(sample):
    ctx, _ = _ctx(sample)
    base = {"id": "n", "type": "text", "text": "1 grade", "x": 100, "y": 0, "size": 150}
    plain = T.layout(base, ctx)
    opt = T.layout({**base, "optical": True}, ctx)
    assert T.ink_box(plain)[0] > 100.5  # the "1" has a wide left side bearing
    assert T.ink_box(opt)[0] == pytest.approx(100, abs=0.05)


def test_grain_and_texture_effects_render(sample):
    """noise layers must actually show grain (a whole-number turbulence frequency renders flat), texture keeps
    the text's colour, blur spreads a shape."""
    import numpy as np

    from designassist import render

    d = D.load(sample)
    ab = d["artboards"][0]
    ab["layers"] = [
        {"id": "g", "type": "noise", "x": 0, "y": 0, "w": 1080, "h": 600, "size": 1.0, "opacity": 1},
        {"id": "t", "type": "text", "text": "TINTA", "x": 80, "y": 700, "size": 160, "weight": 900, "color": "#FFFFFF",
         "texture": {"spread": 3, "size": 4}},
        {"id": "b", "type": "ellipse", "x": 400, "y": 1000, "w": 200, "h": 200, "fill": "#FF611A", "blur": 80},
    ]
    D.save(sample, d)
    res = render.render(sample, ["post"], sheet=False)
    im = np.asarray(Image.open(sample.path(res["rendered"][0]["file"])).convert("RGB"), float)
    assert im[50:550, 50:1000].std() > 20  # grain visible
    txt = im[720:860, 90:600]
    assert (txt.min(axis=2) > 240).mean() > 0.2  # white letters stay white
    assert im[1100, 300].tolist() != im[1100, 150].tolist()  # blur reaches beyond the circle's own box edge


def test_highlight_box_covers_accents_above_capitals(sample):
    # "SUBMISSÃO" in a highlight box: the tilde sits above cap height; a cap-height box left it on the
    # background (navy tilde on a navy thumb = the word read "SUBMISSAO")
    ctx, _ = _ctx(sample)
    hl = {"color": "#B1C1DB", "pad": [0.14, 0.05]}
    base = {"id": "t", "type": "text", "x": 0, "y": 0, "w": 1200, "size": 100, "font": "Montserrat", "weight": 900}
    plain = T.layout({**base, "text": "SUBMISSAO", "highlight": hl}, ctx)
    acc = T.layout({**base, "text": "SUBMISSÃO", "highlight": hl}, ctx)
    L = lambda v: float(v)  # noqa: E731
    def box(lay):
        ln = lay.lines[0]
        return T.highlight_box(hl, ln.x, ln.baseline, ln.width, lay.size, ln.runs[0].style.ref,
                               T.highlight_runs(lay)[0], L)
    ink_top = T.ink_box(acc)[1]
    _, top_plain, _, h_plain = box(plain)
    _, top_acc, _, h_acc = box(acc)
    assert top_acc < ink_top  # the tilde is inside the box
    assert top_plain > ink_top and h_acc > h_plain  # unaccented text keeps the cap-height box
    # accent spans: every highlighted run shares one height, so lines stay even
    two = T.layout({**base, "text": "**SUBMISSÃO**\n**SIM**", "accent": {"highlight": hl}}, ctx)
    runs = T.highlight_runs(two)[1]
    hs = [T.highlight_box(hl, r.x, ln.baseline, r.width, r.style.size, r.style.ref, runs, L)[3]
          for ln in two.lines for r in ln.runs if r.style.highlight]
    assert len(hs) == 2 and abs(hs[0] - hs[1]) < 1e-6
