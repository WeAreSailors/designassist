"""figure:<pose> silhouettes and the `cast` ground shadow (preview, PDF, Affinity plan)."""
from __future__ import annotations

import math
import re

import pytest

from designassist import affinity_build as B
from designassist import cast as CS
from designassist import design as D
from designassist import figures as F
from designassist import svgflat


@pytest.fixture
def fig_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(F, "CACHE", tmp_path / "figures")
    return tmp_path / "figures"


def _bounds(svg_text):
    vb = [float(v) for v in re.search(r'viewBox="([^"]+)"', svg_text).group(1).split()]
    shapes = svgflat.flatten_file(svg_text, 0, 0, vb[2], vb[3], "fill")
    return vb, CS._bounds([sp for s in shapes for sp in s.subpaths])


def test_figure_is_one_solid_outline_standing_on_the_bottom_edge(fig_cache):
    # the old hand-drawn figures were separate limb shapes: seams showed as white slits between arm/torso/legs
    text = F.figure_file("walk").read_text(encoding="utf-8")
    assert text.count("<path") == 1 and 'fill-rule="nonzero"' in text
    vb, (x0, y0, x1, y1) = _bounds(text)
    # (bounds include bezier control points, which overshoot the outline by a few units)
    assert y1 == pytest.approx(vb[3], abs=8) and y0 == pytest.approx(0, abs=8)  # soles = ground = bottom
    assert 0.3 < vb[2] / vb[3] < 0.6  # a stride is wider than a standing figure
    assert F.aspect("stand") < F.aspect("walk")
    # proportions of a clothed adult, not a stick figure: the silhouette covers a good part of its box
    from PIL import Image

    from designassist.render import svg_to_image

    im = svg_to_image(text.replace("<svg ", '<svg width="200" height="400" ', 1).replace(
        f'width="{vb[2]}" height="{vb[3]}"', ""), fig_cache)
    alpha = sum(1 for a in im.getchannel("A").getdata() if a > 128) / (im.width * im.height)
    assert alpha > 0.12


def test_figure_left_is_mirrored_and_unknown_pose_fails(fig_cache):
    right, left = F.figure_file("point"), F.figure_file("point-left")
    assert "scale(-1 1)" in left.read_text() and "scale(-1 1)" not in right.read_text()
    with pytest.raises(SystemExit, match="unknown pose"):
        F.figure_file("dance")


def test_cast_projection_keeps_feet_and_throws_the_head_along_the_light():
    # a 10 x 100 bar standing on y = 100
    bar = [[("M", 0, 0), ("L", 10, 0), ("L", 10, 100), ("L", 0, 100), ("Z",)]]
    p = {"a": math.radians(30), "n": 1.5, "width": 0.6}
    out = CS.project(bar, p)[0]
    assert out[2][1:] == pytest.approx((10, 100)) and out[3][1:] == pytest.approx((0, 100))  # feet fixed
    tip = ((out[0][1] + out[1][1]) / 2, (out[0][2] + out[1][2]) / 2)
    assert tip == pytest.approx((5 + 150 * math.cos(p["a"]), 100 + 150 * math.sin(p["a"])), abs=0.01)
    # widened across the light: a true projection would keep only sin(30) = 0.5 of the width
    across = abs((out[0][1] - out[1][1]) * -math.sin(p["a"]) + (out[0][2] - out[1][2]) * math.cos(p["a"]))
    assert across == pytest.approx(10 * 0.6, rel=0.01)


@pytest.fixture
def scene(sample, fig_cache):
    d = D.load(sample)
    d["artboards"][0]["background"] = "#FFFFFF"
    d["artboards"][0]["layers"] = [
        {"id": "man", "type": "svg", "src": "figure:stand", "x": 500, "y": 600, "w": 60, "h": 200, "color": "#141922",
         "cast": {"angle": 25, "length": 1.4, "blur": 4, "color": "#141922CC"}},
        {"id": "box", "type": "rect", "x": 100, "y": 100, "w": 50, "h": 80, "fill": "$primary", "cast": {}},
    ]
    D.save(sample, d)
    return sample


def test_cast_renders_behind_the_layer_from_its_feet(scene):
    from designassist.render import render

    from designassist import svg as S

    ctx = D.context(scene)
    ab = D.load(scene)["artboards"][0]
    svg, _ = S.artboard_svg(ctx, ab, "preview", 1.0)
    assert svg.index('id="man-cast"') < svg.index('id="man"')  # shadow under the figure
    render(scene, ["post"])
    from PIL import Image

    im = Image.open(scene.path("output", "preview", "post.png")).convert("RGB")
    # the figure is 200 tall and contain-fitted in a 60-wide box: its feet are at y = 800 (box bottom),
    # so the shadow runs from there down-right, about 1.4 * 200 long
    dark = lambda p: sum(p) < 400  # white background = 765
    assert dark(im.getpixel((int(530 + 140 * math.cos(math.radians(25))), int(800 + 140 * math.sin(math.radians(25))))))
    assert not dark(im.getpixel((470, 900)))  # nothing on the other side
    # the rect has no vector outline source: affine fallback still casts a shadow below it
    assert any(dark(im.getpixel((x, 200))) for x in range(150, 260, 4))


def test_cast_in_affinity_is_an_editable_curve_with_live_blur(scene, tmp_path):
    p = B.plan(scene, stage=tmp_path / "stage")
    ops = p["spec"]["docs"][0]["ops"]
    ids = [o["id"] for o in ops]
    cast = ops[ids.index("man-cast")]
    assert ids.index("man-cast") < ids.index("man")
    assert cast["op"] == "curves" and cast["blur"] > 0 and cast["shapes"][0]["fill_desc"]["rgba"][:3] == [20, 25, 34]
    assert ops[ids.index("man")]["op"] == "curves" and "blur" not in ops[ids.index("man")]
    assert ops[ids.index("box-cast")]["op"] == "image"  # non-vector layer: shadow placed as a bitmap


def test_pdf_rasterises_cast_layers(scene):
    from designassist import pdf

    w = pdf.Painter.__new__(pdf.Painter)
    assert w.needs_raster({"type": "rect", "cast": {}}) == "cast shadow"


def test_cast_keeps_its_width_when_the_light_is_horizontal():
    # sin(0) = 0: a pure projection squashed the shadow into a zero-height line (invisible)
    bar = [[("M", 0, 0), ("L", 10, 0), ("L", 10, 100), ("L", 0, 100), ("Z",)]]
    out = CS.project(bar, {"a": 0.0, "n": 1.0, "width": 0.6})[0]
    assert abs(out[0][2] - out[1][2]) == pytest.approx(6, rel=0.01)  # 0.6 x the 10-unit width, across
    assert out[2][1:] == pytest.approx((10, 100)) and out[3][1:] == pytest.approx((0, 100))
