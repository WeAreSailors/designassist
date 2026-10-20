"""Affinity builder: the plan (ops in document pixels) is tested offline; the runtime is syntax-checked
with node; one live test runs only when Affinity's AI connector is reachable (DA_AFFINITY_LIVE=1)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess

import pytest

from designassist import affinity as A
from designassist import affinity_build as B
from designassist import design as D
from designassist import svgflat


@pytest.fixture
def planned(sample, tmp_path):
    d = D.load(sample)
    post = d["artboards"][0]
    post["layers"] += [
        {"id": "ic", "type": "icon", "name": "x", "x": 10, "y": 10, "w": 24, "h": 24, "color": "$accent"},
        {"id": "rule", "type": "line", "x": 80, "y": 1170, "x2": 1000, "y2": 1170, "stroke": {"color": "$paper", "width": 2}},
        {"id": "tri", "type": "path", "d": "M0 0 L10 0 L5 10 Z", "viewbox": [0, 0, 10, 10], "x": 100, "y": 100, "w": 50,
         "h": 50, "fill": "$primary", "blend": "multiply", "rotation": 15, "opacity": 0.5},
        {"id": "tag", "type": "text", "text": "NOVO\nlinha 2", "x": 80, "y": 820, "size": 28, "weight": 700,
         "highlight": {"color": "$accent"}},
    ]
    D.save(sample, d)
    # icon without network: a fake cached Lucide file
    from designassist import icons

    icons.DIR.mkdir(parents=True, exist_ok=True)
    fake = icons.DIR / "x.svg"
    created = not fake.exists()
    if created:
        fake.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
                        'stroke-width="2"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>', encoding="utf-8")
    p = B.plan(sample, stage=tmp_path / "stage")
    yield p
    if created:
        fake.unlink()


def _ops(p, doc_index=0):
    return {o["id"]: o for o in p["spec"]["docs"][doc_index]["ops"]}


def test_plan_documents_and_artboards(planned):
    docs = planned["spec"]["docs"]
    assert [d["name"] for d in docs] == ["sample-post", "sample-card"]
    post, card = docs
    assert post["units"] == "px" and post["artboards"][0]["id"] == "post"
    assert card["units"] == "mm" and card["dpi"] == 300 and card["bleed"] == 3 and card["artboards"] is None
    assert "Montserrat-ExtraBold" in planned["spec"]["fonts"]


def test_plan_shapes_text_and_effects(planned):
    ops = _ops(planned)
    assert ops["post-background"]["op"] == "rect" and ops["post-background"]["parent"] == "post"
    cta = ops["cta-bg"]
    assert cta["op"] == "rect" and cta["parent"] == "cta" and cta["radius"] == [40, 40, 40, 40]
    assert (cta["x"], cta["y"], cta["w"], cta["h"]) == (80, 1190, 360, 80)  # group offset applied
    assert cta["shadow"]["dy"] == 8 and cta["fill"]["rgba"][:3] == [227, 6, 19]
    g = ops["shade"]["fill"]["gradient"]  # 90 degrees = top to bottom over the box
    assert (g["x1"], g["y1"], g["x2"], g["y2"]) == pytest.approx((540, 500, 540, 900))
    assert g["stops"][0][1][3] == 0  # $ink/0
    title = ops["title"]
    runs = title["paragraphs"][0]
    assert [r["text"] for r in runs] == ["Até ", "50% off", " na linha de verão"]
    assert runs[1]["rgba"][:3] == [255, 212, 0] and runs[0]["ps"] == "Montserrat-ExtraBold"
    assert title["leading"] == pytest.approx(runs[0]["size"] * 1.0)
    tri = ops["tri"]
    assert tri["blend"] == "multiply" and tri["opacity"] == 0.5 and tri["rotation"] == 15
    pts = tri["shapes"][0]["subpaths"][0]
    assert pts[0] == ["M", 100, 100] and pts[2] == ["L", 125, 150]
    assert ops["tri"]["shapes"][0]["fill_desc"]["rgba"][:3] == [227, 6, 19]
    rule = ops["rule"]["shapes"][0]
    assert rule["fill"] is None and rule["stroke"][:3] == [255, 255, 255] and rule["stroke_width"] == 2
    ic = ops["ic"]["shapes"]
    assert len(ic) == 2 and ic[0]["stroke"][:3] == [255, 212, 0] and ic[0]["stroke_width"] == 2


def test_plan_text_paragraphs_and_highlights(planned):
    ops = _ops(planned)
    tag = ops["tag"]
    assert [p[0]["text"] for p in tag["paragraphs"]] == ["NOVO", "linha 2"]
    hl = [o for i, o in ops.items() if i.startswith("tag-highlight-")]
    assert len(hl) == 2 and all(o["fill"]["rgba"][:3] == [255, 212, 0] for o in hl)
    ids = list(ops)
    assert ids.index("tag-highlight-1") < ids.index("tag")  # highlight boxes sit under the text


def test_plan_print_document_in_pixels_with_bleed(planned):
    ops = _ops(planned, 1)
    k = 300 / 25.4
    bg = ops["card-background"]
    assert bg["x"] == pytest.approx(-3 * k) and bg["w"] == pytest.approx(96 * k)
    mark = ops["mark"]
    assert (mark["x"], mark["y"], mark["w"]) == pytest.approx((70 * k, 30 * k, 14 * k))
    name = ops["name"]
    assert name["paragraphs"][0][0]["size"] == pytest.approx(14 / 72 * 300)  # 14pt at 300 dpi


def test_plan_images_staged_on_the_desktop_folder(planned):
    img = _ops(planned)["photo"]
    from pathlib import Path

    f = Path(img["file"])
    assert f.exists() and f.parent.name == "stage"
    assert (img["w"], img["h"]) == (1080, 860)


def test_unsupported_svg_falls_back_to_a_bitmap(sample, tmp_path):
    sample.path("input", "grad.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><defs><linearGradient id="a"><stop offset="0"/>'
        '</linearGradient></defs><rect width="10" height="10" fill="url(#a)"/></svg>', encoding="utf-8")
    d = D.load(sample)
    d["artboards"][0]["layers"].append({"id": "g", "type": "svg", "src": "input/grad.svg", "x": 0, "y": 0, "w": 100, "h": 100})
    D.save(sample, d)
    p = B.plan(sample, ["post"], stage=tmp_path / "s")
    g = _ops(p)["g"]
    assert g["op"] == "image" and g["file"].endswith(".png")
    assert any("bitmap" in n for n in p["notes"])


def test_svgflat_transforms_shapes_and_recolor():
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 50"><g transform="translate(10 0)">'
           '<rect x="0" y="0" width="20" height="20" fill="#E30613"/><circle cx="50" cy="25" r="10" fill="#111"/></g>'
           '<polygon points="0,50 10,40 20,50" fill="none" stroke="#000" stroke-width="2"/></svg>')
    shapes = svgflat.flatten_file(svg, 0, 0, 200, 100)
    assert len(shapes) == 3
    assert shapes[0].subpaths[0][0] == ("M", 20.0, 0.0)  # translate 10 then scale 2
    assert shapes[0].fill[:3] == (227, 6, 19)
    assert shapes[2].fill is None and shapes[2].stroke_width == 4
    mono = svgflat.flatten_file(svg, 0, 0, 200, 100, recolor=(255, 255, 255, 1))
    assert all((s.fill or s.stroke)[:3] == (255, 255, 255) for s in mono)
    with pytest.raises(svgflat.Unsupported):
        svgflat.flatten_file('<svg xmlns="http://www.w3.org/2000/svg"><text>x</text></svg>', 0, 0, 10, 10)


def test_remark_puts_accent_back():
    assert B.remark("Até **50% off** hoje", "Até 50% off amanhã") == ("Até **50% off** amanhã", [])
    assert B.remark("Até **50% off** hoje", "Até 30% off") == ("Até 30% off", ["50% off"])


def test_pull_maps_moves_text_and_fill(sample, tmp_path, monkeypatch):
    p = B.plan(sample, stage=tmp_path / "s")
    snap = {
        "cta": {"box": [80, 1190, 360, 80]}, "cta-bg": {"box": [80, 1190, 360, 80], "fill": [227, 6, 19, 1]},
        "title": {"box": [80, 910, 920, 300], "text": "Até 50% off na linha de verão"},
        "logo": {"box": [840, 70, 160, 64]},
    }
    from designassist.project import write_json

    write_json(sample.path("output", "affinity", "sample-affinity-built.json"),
               {"docs": [{"name": "sample-post", "uuid": "U1", "artboards": ["post"], "snapshot": snap}],
                "layers": p["layers"]})
    live = json.loads(json.dumps(snap))
    live["cta"]["box"][1] -= 30
    live["cta-bg"]["box"][1] -= 30
    live["cta-bg"]["fill"] = [0, 180, 120, 1]
    live["logo"]["box"][0] += 40
    live["logo"]["box"][2] += 20
    live["title"]["text"] = "Até 50% off só hoje"
    monkeypatch.setattr(B, "read_docs", lambda uuids: {"docs": [{"uuid": "U1", "layers": live}]})
    res = B.pull(sample)
    by = {c["layer"]: c for c in res["changes"]}
    assert by["post/cta"]["moved"] == [0, -30]
    assert "moved" not in by["post/cta-bg"] and by["post/cta-bg"]["fill"][1] == "#00B478"  # moved with its group
    assert by["post/logo"]["size"][0] == 180 and by["post/logo"]["moved"] == [40, 0]
    d = D.load(sample)
    assert D.find_layer(d["artboards"][0]["layers"], "title")["text"] == "Até **50% off** só hoje"
    assert D.find_layer(d["artboards"][0]["layers"], "cta")["y"] == 1160
    again = B.pull(sample)  # baseline refreshed: nothing applied twice
    assert again["changes"] == []


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_runtime_script_is_valid_javascript(planned, tmp_path):
    js = B.script(planned["spec"])
    f = tmp_path / "build.js"
    f.write_text(js, encoding="utf-8")
    r = subprocess.run(["node", "--check", str(f)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    rd = tmp_path / "read.js"
    rd.write_text("const DA_READ = {uuids: []};\n" + B.READER.read_text(encoding="utf-8"), encoding="utf-8")
    assert subprocess.run(["node", "--check", str(rd)], capture_output=True).returncode == 0


def test_status_without_connector(monkeypatch):
    monkeypatch.setattr(A, "reachable", lambda: False)
    res = A.cmd_affinity(type("a", (), {"action": "status"})())
    assert res["connector"] is False and "AI connector" in res["next"]


@pytest.mark.skipif(os.environ.get("DA_AFFINITY_LIVE") != "1" or not A.reachable(),
                    reason="live Affinity test: set DA_AFFINITY_LIVE=1 with the AI connector on")
def test_live_build_matches_preview(sample):
    from PIL import Image
    import numpy as np

    from designassist import render

    res = B.build(sample, ["post"], live=True, save=False)
    assert not res["warnings"], res["warnings"]
    shot = Image.open(sample.path(res["renders"][0])).convert("RGB")
    render.render(sample, ["post"], sheet=False)
    prev = Image.open(sample.path("output", "preview", "post.png")).convert("RGB").resize(shot.size)
    diff = np.abs(np.asarray(prev, float) - np.asarray(shot, float)).mean()
    c = A.session(60)
    try:
        c.run("const { app } = require('/application'); const mine = " + json.dumps(res["uuids"]) + ";"
              " for (const d of [...app.documents.all]) if (mine.includes(d.sessionUuid)) d.close();")
    finally:
        c.close()
    assert diff < 6, f"Affinity render differs from the preview (mean {diff:.1f}/255)"


def test_close_script_targets_only_given_documents(tmp_path):
    js = A.close_script(["U1", "U2"])
    assert '["U1", "U2"]' in js and "d.close()" in js and "mine.includes(d.sessionUuid)" in js
    if shutil.which("node"):
        f = tmp_path / "c.js"
        f.write_text(js, encoding="utf-8")
        assert subprocess.run(["node", "--check", str(f)], capture_output=True).returncode == 0


def test_plan_carries_font_requests_for_affinity_names(planned):
    req = planned["spec"]["font_requests"]
    assert req["Montserrat-ExtraBold"] == {"family": "Montserrat", "style": "ExtraBold"}
    assert set(req) == set(planned["spec"]["fonts"])


def test_export_presets_map_to_affinity_names():
    assert B.PRESETS["print"] == "PDF (press ready)" and B.PRESETS["canva"] == "Canva Design"


def test_bitmap_fallback_keeps_opacity_live_not_baked(sample, tmp_path):
    d = D.load(sample)
    d["artboards"][0]["layers"].append({"id": "grain", "type": "noise", "x": 0, "y": 0, "w": 1080, "h": 1350, "opacity": 0.3})
    D.save(sample, d)
    p = B.plan(sample, ["post"], stage=tmp_path / "s")
    g = _ops(p)["grain"]
    assert g["op"] == "image" and g["opacity"] == 0.3
    from PIL import Image

    a = Image.open(g["file"]).getchannel("A")
    assert a.getextrema()[1] == 255  # bitmap at full strength; the 0.3 is applied once, by Affinity


def test_cli_reports_a_dead_connector_without_a_traceback(sample, monkeypatch):
    from designassist import cli

    def refuse(self):
        raise A.AffinityError(A.NOT_RUNNING + " ([Errno 61] Connection refused)")

    monkeypatch.setattr(A.Client, "connect", refuse)
    with pytest.raises(SystemExit) as e:
        cli.main(["affinity", "open", "sample"])
    assert "AI connector" in str(e.value) and "Traceback" not in str(e.value)


def test_export_writes_one_file_per_artboard_when_layer_ids_repeat(sample, monkeypatch, tmp_path):
    # 16 thumbs reusing layer ids ("guest", "bg-photo") came out as 2 files: the artboard list was read from
    # the built layer map, which is keyed by layer id and keeps only the last artboard of each id
    from designassist.project import write_json

    d = D.load(sample)
    ab = {"id": "a", "width": 100, "height": 100, "unit": "px", "dpi": 72, "bleed": 0, "background": "#fff",
          "layers": [{"id": "guest", "type": "rect", "x": 0, "y": 0, "w": 10, "h": 10, "fill": "#000"}]}
    d["artboards"] = [ab, {**ab, "id": "b"}, {**ab, "id": "c"}]
    D.save(sample, d)
    write_json(sample.path("output", "affinity", "sample-affinity-built.json"), {
        "docs": [{"name": "sample", "uuid": "U1", "snapshot": {"a": {}, "b": {}, "c": {}, "guest": {}}}],
        "layers": {"guest": {"artboard": "c"}}})
    written = []

    class Fake:
        def export(self, uuid, path, preset, artboard_id=None):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"x")
            written.append(artboard_id)
            return path

        def close(self):
            pass

    monkeypatch.setattr(A, "session", lambda timeout=0: Fake())
    monkeypatch.setattr(B, "read_docs", lambda uuids: {"docs": [{"uuid": "U1"}]})
    monkeypatch.setattr(B.Path, "home", lambda: tmp_path)
    res = B.export(sample, "jpg")
    assert written == ["a", "b", "c"]
    assert [f.split("/")[-1] for f in res["files"]] == ["a.jpg", "b.jpg", "c.jpg"]


def test_pull_keeps_edits_on_their_own_artboard_when_layer_ids_repeat(sample, tmp_path, monkeypatch):
    # 16 thumbs share layer ids ("headline-2"); a text edit on one artboard was about to be written into
    # all 16, because the snapshot and the layer map were keyed by the bare layer id
    from designassist.project import write_json

    d = D.load(sample)
    ab = {"id": "a", "width": 400, "height": 200, "unit": "px", "dpi": 72, "bleed": 0, "background": "#fff",
          "layers": [{"id": "headline-2", "type": "text", "text": "UM", "x": 10, "y": 10, "w": 300, "size": 40}]}
    d["artboards"] = [ab, {**ab, "id": "b", "layers": [{**ab["layers"][0], "text": "DOIS"}]}]
    D.save(sample, d)
    p = B.plan(sample, stage=tmp_path / "s")
    assert set(p["layers"]) == {"a/headline-2", "b/headline-2"}
    assert all(o.get("ab") in ("a", "b") for o in p["spec"]["docs"][0]["ops"])
    snap = {"a": {"box": [0, 0, 400, 200]}, "b": {"box": [440, 0, 400, 200]},
            "a/headline-2": {"box": [10, 10, 300, 48], "text": "UM"},
            "b/headline-2": {"box": [450, 10, 300, 48], "text": "DOIS"}}
    write_json(sample.path("output", "affinity", "sample-affinity-built.json"),
               {"docs": [{"name": "sample", "uuid": "U1", "artboards": ["a", "b"], "snapshot": snap}],
                "layers": p["layers"]})
    live = json.loads(json.dumps(snap))
    live["b/headline-2"]["text"] = "TRES"
    monkeypatch.setattr(B, "read_docs", lambda uuids: {"docs": [{"uuid": "U1", "layers": live}]})
    res = B.pull(sample)
    assert [c["layer"] for c in res["changes"]] == ["b/headline-2"]
    d = D.load(sample)
    assert [ab["layers"][0]["text"] for ab in d["artboards"]] == ["UM", "TRES"]


def test_pull_refuses_builds_keyed_by_bare_layer_ids(sample, monkeypatch):
    from designassist.project import write_json

    write_json(sample.path("output", "affinity", "sample-affinity-built.json"),
               {"docs": [{"name": "sample", "uuid": "U1", "snapshot": {}}], "layers": {"title": {"artboard": "post"}}})
    monkeypatch.setattr(B, "read_docs", lambda uuids: {"docs": [{"uuid": "U1", "layers": {}}]})
    with pytest.raises(SystemExit, match="rebuild"):
        B.pull(sample)


def test_scoped_snapshot_prefixes_print_documents():
    assert B.scoped({"card": {}, "title": {}, "card/x": {}}, ["card"]) == {"card": {}, "card/title": {}, "card/x": {}}
    assert B.scoped({"a/t": {}, "t": {}}, ["a", "b"]) == {"a/t": {}, "t": {}}


def test_radial_gradient_is_elliptical_on_wide_boxes(sample, tmp_path):
    # the SVG preview scales a radial fill with its box (objectBoundingBox); Affinity used max(w, h)
    # as a circular radius, so on a 1080x500 scrim the top edge stayed visible as a hard line
    d = D.load(sample)
    d["artboards"][0]["layers"].append(
        {"id": "scrim", "type": "rect", "x": 0, "y": 850, "w": 1080, "h": 500,
         "fill": {"type": "radial", "cx": 0.5, "cy": 0.5, "r": 0.5, "stops": [[0, "#FFFFFF"], [1, "#FFFFFF00"]]}})
    D.save(sample, d)
    g = _ops(B.plan(sample, stage=tmp_path / "stage"))["scrim"]["fill"]["gradient"]
    assert (g["cx"], g["cy"], g["rx"], g["ry"]) == pytest.approx((540, 1100, 540, 250))


def test_svgflat_drops_lone_movetos():
    # PDF-extracted logos end paths with "Z M x y"; Affinity's createCurve fails (INVALID_OP) on a
    # subpath without segments, which dropped the whole logo
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
           '<path d="M0 0 L10 0 L10 10 Z M0 0" fill="#000"/><path d="M5 5" fill="#000"/></svg>')
    shapes = svgflat.flatten_file(svg, 0, 0, 10, 10)
    assert len(shapes) == 1 and len(shapes[0].subpaths) == 1
    assert all(any(seg[0] in "LC" for seg in sp) for s in shapes for sp in s.subpaths)


def test_close_discard_refuses_while_affinity_holds_unpulled_edits(sample, monkeypatch):
    # a rebuild ran `close --discard` on a document whose pull --dry-run listed a changed layer,
    # and the edit was lost with no backup (2026-10-20)
    from designassist import cli
    from designassist.project import write_json

    write_json(sample.path("output", "affinity", "sample-affinity-built.json"), {"docs": [{"uuid": "U1"}], "layers": {}})
    monkeypatch.setattr(B, "pull", lambda pr, dry_run=False: {"changes": [{"layer": "post/title", "moved": [4, 0]}]})
    sent = []

    class Fake:
        def run_json(self, js):
            sent.append(js)
            return {"closed": 1}

        def close(self):
            pass

    monkeypatch.setattr(A, "session", lambda timeout=60: Fake())
    with pytest.raises(SystemExit, match="post/title moved.*affinity pull sample"):
        cli.main(["affinity", "close", "sample", "--discard"])
    assert not sent
    cli.main(["affinity", "close", "sample", "--discard", "--force"])
    assert sent and '"U1"' in sent[0]


def test_pull_brings_back_text_colour_and_layers_copied_between_artboards(sample, tmp_path, monkeypatch):
    # the user turned the cover title orange and pasted the closing slide's logo onto the cover in
    # Affinity; pull reported no changes, so `close --discard` would have dropped both (2026-10-20)
    d = D.load(sample)
    post = d["artboards"][0]
    d["artboards"] = [post, {**json.loads(json.dumps(post)), "id": "post2",
                             "layers": [l for l in post["layers"] if l["id"] == "title"]}]
    post["layers"] = [l for l in post["layers"] if l["id"] in ("logo", "title")]
    D.save(sample, d)
    p = B.plan(sample, stage=tmp_path / "s")
    snap = {"post": {"box": [0, 0, 1080, 1350]}, "post2": {"box": [1180, 0, 1080, 1350]},
            "post/logo": {"box": [840, 70, 160, 64]}, "post/title": {"box": [80, 910, 920, 300], "text": "x"},
            "post2/title": {"box": [1260, 910, 920, 300], "text": "x"}}
    from designassist.project import write_json

    write_json(sample.path("output", "affinity", "sample-affinity-built.json"),
               {"docs": [{"name": "sample", "uuid": "U1", "artboards": ["post", "post2"], "snapshot": snap}],
                "layers": p["layers"]})
    live = json.loads(json.dumps(snap))
    live["post2/title"]["text_fill"] = [255, 212, 0, 1]   # $accent in the sample tokens
    live["post2/logo"] = {"box": [1180 + 100, 200, 160, 64]}
    live["post2/logo-1"] = {"box": [1180 + 100, 200, 20, 20]}  # curve inside the pasted group: not a design id
    monkeypatch.setattr(B, "read_docs", lambda uuids: {"docs": [{"uuid": "U1", "layers": live}]})
    res = B.pull(sample, dry_run=True)
    by = {c["layer"]: c for c in res["changes"]}
    assert by["post2/title"]["color"][1] == "$accent"
    assert by["post2/logo"]["added"] == "copy of post/logo" and "post2/logo-1" not in by
    B.pull(sample)
    d = D.load(sample)
    logo2 = D.find_layer(D.artboard(d, "post2")["layers"], "logo")
    src = D.find_layer(D.artboard(d, "post")["layers"], "logo")
    assert logo2["x"] == pytest.approx(src["x"] - 740) and logo2["y"] == pytest.approx(src["y"] + 130)
    assert D.find_layer(D.artboard(d, "post2")["layers"], "title")["color"] == "$accent"
