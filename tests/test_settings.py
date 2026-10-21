"""`da settings`: the resolution knob every screen deliverable obeys (the owner works in 4K, always)."""
from __future__ import annotations

import pytest
from PIL import Image

from designassist import affinity_build as B
from designassist import settings as ST
from designassist.export import export


def test_resolution_4k_means_long_side_3840():
    assert ST.load()["resolution"] == "1x"
    ST.save("resolution", "4K")
    assert ST.load()["resolution"] == "4k"
    assert ST.scale_for({"unit": "px", "width": 1080, "height": 1350}) * 1350 == pytest.approx(3840)
    assert ST.scale_for({"unit": "px", "width": 1920, "height": 1080}) * 1920 == pytest.approx(3840)
    assert ST.scale_for({"unit": "mm", "width": 90, "height": 50}) == 1.0  # print keeps its dpi
    with pytest.raises(SystemExit):
        ST.save("resolution", "huge")


def test_export_follows_the_setting_without_a_scale(sample):
    ST.save("resolution", "4k")
    res = export(sample, ["png", "jpg"], ["post"])
    f = sample.path("output", "post.png")
    assert res["png"][0]["file"] == "output/post.png" and Image.open(f).size == (3072, 3840)
    assert res["jpg"][0]["px"] == [3072, 3840]
    # an explicit scale still wins, and names the file @Nx
    res = export(sample, ["png"], ["post"], scale=1.0)
    assert res["png"][0]["px"] == [1080, 1350]


def test_max_goes_as_high_as_the_photos_allow(sample):
    # the sample post has a 1600x1200 photo covering 1080x860: past ~1.74x it would be upscaled more than 1.25x
    ST.save("resolution", "max")
    res = export(sample, ["png"], ["post"])
    w, h = res["png"][0]["px"]
    k = 1.25 / max(1080 / 1600, 860 / 1200)
    assert w == round(1080 * k) or abs(w - 1080 * k) <= 1
    # without photos max = the full 3840 long side
    from designassist import design as D

    d = D.load(sample)
    d["artboards"][0]["layers"] = [l for l in d["artboards"][0]["layers"] if l["type"] != "image"]
    D.save(sample, d)
    assert export(sample, ["png"], ["post"])["png"][0]["px"] == [3072, 3840]


def test_affinity_document_stays_artboard_size_with_hi_res_bitmaps(sample, tmp_path):
    ST.save("resolution", "4k")
    p = B.plan(sample, stage=tmp_path / "stage")
    post = p["spec"]["docs"][0]
    assert post["artboards"][0]["w"] == 1080 and p["layers"]["post/photo"]["ppu"] == 1
    # doc_scale still builds a bigger document on request (pull divides by the recorded ppu)
    k = 3840 / 1350
    p2 = B.plan(sample, stage=tmp_path / "stage", doc_scale=k)
    assert p2["spec"]["docs"][0]["artboards"][0]["h"] == pytest.approx(3840)
    assert p2["layers"]["post/photo"]["ppu"] == pytest.approx(k)
    assert p2["spec"]["docs"][1]["units"] == "mm"  # print document untouched


def test_output_dir_moves_deliverables_and_keeps_previews(sample, tmp_path):
    # the user wants finished files on the Desktop, not inside projects/<p>/output (2026-10-21)
    from designassist import render

    ST.save("output_dir", str(tmp_path / "Desk"))
    try:
        assert sample.output_dir == tmp_path / "Desk" / "sample"
        res = export(sample, ["png"], ["post"])
        assert (tmp_path / "Desk" / "sample" / "post.png").exists(), res
        render.render(sample, ["post"], sheet=False)
        assert sample.dir.joinpath("output", "preview", "post.png").exists()  # previews stay with the project
        assert not (tmp_path / "Desk" / "sample" / "preview").exists()
    finally:
        ST.save("output_dir", "")
    assert sample.path("output", "x.png") == sample.dir / "output" / "x.png"
    with pytest.raises(SystemExit):
        ST.save("outptu_dir", "x")
