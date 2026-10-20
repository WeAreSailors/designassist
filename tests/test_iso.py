"""iso.py: flat isometric blocks as plain path layers."""
from __future__ import annotations

import pytest

from designassist import iso


def test_tile_draws_the_two_front_faces_under_the_top():
    layers = iso.tile("t", 500, 400, 30, 20, "$orange", "$rust", "$navy")
    assert [l["id"] for l in layers] == ["t-r1", "t-l2", "t-top"]  # sides first, top last
    fills = {l["id"]: l["fill"] for l in layers}
    assert fills == {"t-r1": "$navy", "t-l2": "$rust", "t-top": "$orange"}
    assert all(l["type"] == "path" and l["viewbox"] == [0, 0, 1080, 1350] for l in layers)
    # 2:1 diamond: 4a wide, 2a tall, centred
    assert iso.diamond(500, 400, 30) == [(500, 370), (560, 400), (500, 430), (440, 400)]


def test_on_top_follows_the_iso_axes():
    top, right, bottom, left = iso.diamond(0, 0, 10, 6)
    assert iso.on_top(0, 0, 10, -6) == pytest.approx(right)
    assert iso.on_top(0, 0, 10, 6) == pytest.approx(bottom)
    assert iso.on_top(0, 0, -10, 6) == pytest.approx(left)


def test_band_widens_towards_the_viewer_and_shows_its_long_side():
    top = iso.band((0, 600), (400, 400), 50)  # back edge going up-right (along -L): depth goes down-right
    assert top[3] == (50, 625) and top[2] == (450, 425)
    layers = iso.prism("b", top, 30, "#f00", "#0f0", "#00f")
    ids = [l["id"] for l in layers]
    assert ids[-1] == "b-top" and any(i.startswith("b-r") for i in ids)  # the long front face faces down-right
    assert not any(i.startswith("b-l") and "b-l0" == i for i in ids)  # the back edge is never drawn
