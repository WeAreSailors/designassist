"""annotate.py, PDF logos into the brand kit, rgb() percentages, web --root serving, one size per carousel."""
from __future__ import annotations

import shutil
import urllib.request

import pytest

from designassist import annotate as A
from designassist import colors as C


def test_rgb_percentages_scale_to_255():
    # pdftocairo/Illustrator SVGs: rgb(0%, 29%, 67%) was read as (0, 29, 67), a near-black instead of the blue
    assert C.parse("rgb(0%, 29.019165%, 67.451477%)").hex == "#004AAC"
    assert C.parse("rgb(255, 0, 0)").hex == "#FF0000"
    assert C.parse("rgba(10, 20, 30, 50%)").a == pytest.approx(0.5)


def test_crop_maps_source_regions_to_the_artboard():
    g, at, h = A.crop("s", "work/x.png", (100, 200, 1000, 500), 50, 60, 500, (2560, 1720), {"grayscale": 1})
    assert h == 250 and g["clip"] and g["layers"][0]["w"] == 1280 and g["layers"][0]["x"] == -50
    assert at(100, 200, 1000, 500) == pytest.approx((50, 60, 500, 250))
    assert at(600, 450, 100, 50) == pytest.approx((300, 185, 50, 25))
    box, label = A.track("t", 10, 100, 40, 80, "chat")
    assert box["fill"] == "none" and box["stroke"]["color"] == "$primary"
    assert label["y"] < 100 and label["highlight"]["color"] == "$primary" and label["case"] == "upper"
    assert A.track("t", 10, 100, 40, 80, "x", below=True)[1]["y"] > 180


@pytest.mark.skipif(not shutil.which("pdftocairo"), reason="needs poppler's pdftocairo")
def test_pdf_logo_becomes_a_cropped_svg_without_the_page_background(isolated, tmp_path):
    from reportlab.pdfgen import canvas

    from designassist import brand as B
    from designassist import svgflat

    pdf = tmp_path / "logo.pdf"
    c = canvas.Canvas(str(pdf), pagesize=(1920, 1080))
    c.setFillColorRGB(0.97, 0.96, 0.95)
    c.rect(0, 0, 1920, 1080, stroke=0, fill=1)  # artboard background
    c.setFillColorRGB(0, 74 / 255, 172 / 255)
    c.rect(100, 100, 400, 120, stroke=0, fill=1)  # the "logo"
    c.showPage()
    c.save()
    svg = B.pdf_logo_svg(pdf, 1)
    assert svg.count("<path") == 1 and "#004AAC" in svg
    vb = [float(v) for v in svg.split('viewBox="')[1].split('"')[0].split()]
    assert vb[2:] == pytest.approx([400, 120], abs=1)
    B.save("acme", {"name": "Acme", "colors": {}, "fonts": {}, "logos": {}})
    res = B.add_logo("acme", pdf, "wordmark")
    assert res["file"].endswith("wordmark.svg") and res["use_as"] == "brand:wordmark"
    assert svgflat.flatten_file(open(res["file"]).read(), 0, 0, 400, 120)


def test_root_server_serves_root_relative_assets(tmp_path):
    from designassist import web

    (tmp_path / "css").mkdir()
    (tmp_path / "css" / "a.css").write_text("body{}")
    page = tmp_path / "p" / "index.html"
    page.parent.mkdir()
    page.write_text('<link href="/css/a.css" rel="stylesheet"><img src="img/x.png">')
    assert web._absolute_refs(page) == ["/css/a.css"]  # a file:// load would miss it: warn
    url, stop = web._serve(tmp_path)
    try:
        assert urllib.request.urlopen(f"{url}/css/a.css").read() == b"body{}"
    finally:
        stop()


def test_max_gives_every_slide_of_a_set_the_same_size(sample):
    from designassist import design as D
    from designassist import settings as ST
    from designassist.export import export

    ST.save("resolution", "max")
    d = D.load(sample)
    post = d["artboards"][0]
    plain = {**post, "id": "post2", "layers": [l for l in post["layers"] if l["type"] != "image"]}
    d["artboards"].insert(1, plain)
    D.save(sample, d)
    res = export(sample, ["png"], ["post", "post2"])
    sizes = {tuple(r["px"]) for r in res["png"]}
    assert len(sizes) == 1 and next(iter(sizes))[0] < 3072  # capped by the slide with the photo


def test_around_hugs_the_ink_of_a_text_layer(sample):
    from designassist import design as D

    ctx = D.context(sample, D.load(sample))
    word = {"id": "w", "type": "text", "text": "ROTEIRO", "x": 100, "y": 200, "font": "$display", "size": 100}
    x, y, w, h = A.around(word, ctx, pad=10)
    # the box starts just left of the first glyph and sits on the caps, not on the line box (ascender/descender)
    assert 90 <= x <= 110 and 200 < y + 10 < 240
    assert 60 < h - 20 < 80 and w > 300
    x2, _, w2, _ = A.around(word, ctx, pad=(30, 0))
    assert abs((x + 10) - (x2 + 30)) < 0.01 and abs((w - 20) - (w2 - 60)) < 0.01


def test_screen_crops_only_resample_what_the_clip_shows(sample):
    """A crop places the whole capture far bigger than the slide and lets the group clip hide the rest; the
    exporter must resample only the visible part (a 10k px screenshot made exports take minutes)."""
    from designassist import design as D
    from designassist import svg as S

    d = D.load(sample)
    ctx = D.context(sample, d)
    shot, at, h = A.crop("shot", "input/photo.jpg", (400, 300, 400, 300), x=100, y=100, w=600, src_size=(1600, 1200))
    ab = {**d["artboards"][0], "layers": [shot]}
    _, rep = S.artboard_svg(ctx, ab, "export", 2.0)
    img = rep.images["shot-img"]
    assert img["out_px"] == [1200, round(h * 2)]  # the 600 x 450 window at 2x, not the 2400 x 1800 whole image
    assert img["source_px"] == [400, 300]  # cut from the region of the source that shows
    assert at(400, 300, 400, 300) == (100, 100, 600, 450)
