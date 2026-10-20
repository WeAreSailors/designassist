from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from designassist import adobe as A
from designassist import design as D
from designassist import text as T
from designassist.cli import main

ROOT = Path(__file__).resolve().parents[1]
node = pytest.mark.skipif(not shutil.which("node"), reason="node not installed")


def run_mock(app: str, script: Path) -> dict:
    r = subprocess.run(["node", str(ROOT / "tests" / f"{app}_mock.js"), str(script)], capture_output=True, text=True,
                       encoding="utf-8")
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def _items(data: dict) -> dict:
    out = {}

    def walk(items):
        for it in items:
            out[it["name"]] = it
            walk(it.get("items", []))
    for ab in data["artboards"]:
        walk(ab["items"])
    return out


def test_units_to_points():
    assert A.pt_per_unit({"unit": "px"}) == 1
    assert A.pt_per_unit({"unit": "mm"}) == pytest.approx(2.8346, abs=1e-4)
    assert A.pt_per_unit({"unit": "in"}) == 72


def test_illustrator_data_coordinates_and_baseline(sample):
    d = D.load(sample)
    ctx = D.context(sample, d)
    data, ai = A._illustrator(sample, d, ctx, d["artboards"], sample.path("output", "adobe"))
    post, card = data["artboards"]
    assert post["rect"] == [0.0, 0.0, 1080.0, -1350.0]
    k = 72 / 25.4
    assert card["rect"][0] == pytest.approx(1080 + 72 + 3 * k)  # gap + bleed of the print card
    assert card["rect"][3] == pytest.approx(-50 * k)
    items = _items(data)
    title = items["title"]
    lay = T.layout(D.find_layer(d["artboards"][0]["layers"], "title"), ctx)
    assert title["area"] and title["left"] == 80 and title["top"] == -900
    assert title["first_baseline"] == pytest.approx(lay.lines[0].baseline - 900, abs=0.01)
    assert title["base"]["size"] == pytest.approx(lay.size, abs=1e-3)
    assert title["contents"] == "Até 50% off na linha de verão"
    assert title["ranges"] == [{**title["ranges"][0], "start": 4, "len": 7}]
    assert title["ranges"][0]["color"]["rgb"] == [255, 212, 0]
    # group children are absolute; mm converted to points; card background reaches into the bleed
    assert items["cta-bg"]["left"] == 80 and items["cta-bg"]["top"] == -1190 and items["cta-bg"]["radius"] == 40
    assert items["cta-bg"]["shadow"]["y"] == 8
    bg = [i for i in card["items"] if i["name"] == "background"][0]
    assert bg["left"] == pytest.approx(card["rect"][0] - 3 * k, abs=1e-3) and bg["top"] == pytest.approx(3 * k, abs=1e-3)
    assert items["name"]["base"]["size"] == pytest.approx(14, abs=0.01)  # 14pt stays 14pt
    assert data["doc"]["mode"] == "CMYK" and data["doc"]["bleed"] == pytest.approx(3 * k, abs=1e-3)
    primary = [s for s in data["doc"]["swatches"] if s["name"] == "primary"][0]
    assert primary["cmyk"] == [0, 100, 95, 0]  # authored CMYK wins


@node
def test_illustrator_script_runs_in_mock(sample):
    res = A.write_script(sample, "illustrator")
    assert res["artboards"] == ["post", "card"] and res["saves_to"] == ["output/adobe/sample.ai"]
    out = run_mock("illustrator", sample.path(res["script"]))
    assert out["result"]["errors"] == [] and out["result"]["texts"] == 4
    assert [a["name"] for a in out["artboards"]] == ["post", "card"]
    assert set(out["layers"]) == {"post", "card"}
    assert {"primary", "accent", "ink", "paper"} <= set(out["swatches"])
    assert "Montserrat-ExtraBold" in out["fonts"]
    assert out["mode"] == "DocumentColorSpace.CMYK"
    assert all(Path(p).exists() for p in out["placed"] + out["svgs"])
    by = {i["name"]: i for i in out["items"] if i["name"]}
    assert by["photo"]["type"] == "RasterItem" and by["photo"]["geo"]["w"] == 1080  # placed then embedded
    assert by["title"]["kind"] == "area" and by["title"]["justification"] == "Justification.LEFT"
    assert by["title"]["accent"] == 7
    assert by["cta-tx"]["parent"] == "cta" and by["cta-bg"]["parent"] == "cta"
    assert by["cta-bg"]["effects"] == 1  # drop shadow as a live effect
    assert by["logo"]["kind"] == "svg" and not any(i["name"] == "daframe" for i in out["items"])
    assert out["saved"].endswith("sample.ai")


@node
def test_screen_only_document_is_rgb_and_spot_colours(sample):
    d = D.load(sample)
    d["tokens"]["colors"]["primary"]["pantone"] = "485 C"
    D.save(sample, d)
    out = run_mock("illustrator", sample.path(A.write_script(sample, "illustrator", ["post"])["script"]))
    assert out["mode"] == "DocumentColorSpace.RGB" and out["bleed"] is None
    assert out["spots"] == ["PANTONE 485 C"]


@node
def test_photoshop_script_runs_in_mock(sample):
    res = A.write_script(sample, "photoshop")
    out = run_mock("photoshop", sample.path(res["script"]))
    assert out["result"]["errors"] == []
    assert out["prefs"] == {"rulerUnits": "Units.POINTS", "typeUnits": "TypeUnits.POINTS"}  # restored
    post, card = out["docs"]
    assert (post["w"], post["h"], post["res"]) == (1080, 1350, 72)
    assert (card["w"], card["h"], card["res"]) == (1134, 661, 300)  # 90x50 mm + 3 mm bleed at 300 dpi
    assert post["bgFill"] == [17, 17, 17]
    names = [l["name"] for l in post["layers"]]
    assert names == ["logo", "cta", "title", "shade", "photo", "background"]  # top to bottom
    cta = post["layers"][1]
    assert [l["name"] for l in cta["layers"]] == ["cta-tx", "cta-bg"]
    photo = post["layers"][4]
    assert photo["bounds"][:2] == [0, 0] and photo["bounds"][2] == 1080
    title = post["layers"][2]["text"]
    assert title["font"] == "Montserrat-ExtraBold" and title["kind"] == "TextType.PARAGRAPHTEXT"
    assert title["position"][0] == 80
    # print text: px at 300 dpi, offset by the bleed
    name = [l for l in card["layers"] if l["name"] == "name"][0]["text"]
    assert name["size"] == pytest.approx(14 / 72 * 300, abs=0.01)
    assert name["position"][0] == pytest.approx((6 + 3) / 25.4 * 300, abs=0.01)
    assert any("accent" in n for n in res["notes"])


def test_fonts_missing_reported(sample, monkeypatch):
    from designassist import fonts as F

    monkeypatch.setattr(F, "_installed_families", lambda: set())
    monkeypatch.setattr(F, "system_dirs", lambda: [])
    F._INDEX.clear()
    res = A.write_script(sample, "illustrator")
    assert any("Montserrat" in f for f in res["fonts_missing"])
    assert any("da fonts install" in n for n in res["notes"])
    F._INDEX.clear()


def _dump(sample, edits: dict | None = None) -> dict:
    """A fake `read` dump of the document we'd build for the sample (CMYK doc, post + card)."""
    k = 72 / 25.4
    card_left = 1080 + 72 + 3 * k
    items = [
        {"name": "title", "type": "TextFrame", "contents": "Até 50% off na linha de verão", "layer": "post",
         "bounds": [80, -900, 1003.68, -1198.5], "area": [80, -900, 1003.68, -1198.5]},
        {"name": "logo", "type": "GroupItem", "layer": "post", "bounds": [840, -70, 980.8, -134]},
        {"name": "logo", "type": "GroupItem", "layer": "post", "parent": "logo", "bounds": [840, -70, 980.8, -134]},
        {"name": "cta-bg", "type": "PathItem", "layer": "post", "parent": "cta", "bounds": [80, -1190, 440, -1270],
         "filled": True, "fill": {"cmyk": [0, 100, 95, 0]}},
        {"name": "mark", "type": "PathItem", "layer": "card", "filled": True, "fill": {"cmyk": [0, 0, 0, 0]},
         "bounds": [card_left + 70 * k, -30 * k, card_left + 84 * k, -44 * k]},
    ]
    for it in items:
        it.update((edits or {}).get(it["name"], {}) if it.get("parent") != it["name"] else {})
    return {"document": "sample.ai", "mode": "CMYK",
            "artboards": [{"name": "post", "rect": [0, 0, 1080, -1350]},
                          {"name": "card", "rect": [card_left, 0, card_left + 90 * k, -50 * k]}], "items": items}


def test_pull_without_changes_is_a_no_op(sample):
    res = A.pull(sample, _dump(sample), dry_run=True, base={})
    assert res["changes"] == []
    assert any("logo: geometry not pulled" in s for s in res["skipped"])


def test_pull_applies_text_move_and_colour(sample):
    k = 72 / 25.4
    card_left = 1080 + 72 + 3 * k
    dump = _dump(sample, {
        "title": {"contents": "Só hoje\r70% off"},
        "mark": {"bounds": [card_left + 50 * k, -30 * k, card_left + 64 * k, -44 * k], "fill": {"cmyk": [0, 0, 100, 0]}},
        "cta-bg": {"bounds": [100, -1190, 460, -1270]},
    })
    dry = A.pull(sample, dump, dry_run=True, base={})
    assert not dry["applied"] and D.find_layer(D.load(sample)["artboards"][1]["layers"], "mark")["x"] == 70
    res = A.pull(sample, dump, base={})
    got = {(c["layer"], c["field"]): c["to"] for c in res["changes"]}
    assert got[("post/title", "text")] == "Só hoje\n70% off"
    assert got[("card/mark", "x")] == pytest.approx(50, abs=0.01)
    assert got[("card/mark", "fill")] == "#FFFF00"
    assert got[("post/cta-bg", "x")] == pytest.approx(20, abs=0.01)  # group-relative
    d = D.load(sample)
    assert D.find_layer(d["artboards"][0]["layers"], "title")["text"] == "Só hoje\n70% off"
    assert D.find_layer(d["artboards"][1]["layers"], "mark")["fill"] == "#FFFF00"


def test_pull_svg_geometry_from_build_record(sample):
    base = _dump(sample)
    # moved left 100 pt, up 30, scaled 50% about its centre
    edited = _dump(sample, {"logo": {"bounds": [775.2, -56, 845.6, -88]}})
    res = A.pull(sample, edited, base=base)
    got = {c["field"]: c["to"] for c in res["changes"] if c["layer"] == "post/logo"}
    assert got == {"x": pytest.approx(775.2), "y": pytest.approx(56), "w": pytest.approx(80), "h": pytest.approx(32)}
    assert res["base"] == "build record"


def test_run_script_uses_osascript_on_macos(monkeypatch, tmp_path):
    calls = []

    class R:
        returncode, stdout, stderr = 0, '{"ok": true}', ""

    monkeypatch.setattr(A.sys, "platform", "darwin")
    monkeypatch.setattr(A, "installed", lambda app: ["/Applications/Adobe Illustrator 2026"])
    monkeypatch.setattr(A.subprocess, "run", lambda cmd, **kw: calls.append(cmd) or R())
    f = tmp_path / "x.jsx"
    f.write_text("1", encoding="utf-8")
    assert A.run_script("illustrator", f) == '{"ok": true}'
    cmd = calls[0]
    assert cmd[0] == "osascript" and cmd[-1] == str(f.resolve())
    assert any('application id "com.adobe.illustrator"' in c and "as alias" in c for c in cmd)


def test_cli_script(sample, capsys):
    main(["adobe", "script", "sample", "--app", "photoshop", "--artboard", "card"])
    out = json.loads(capsys.readouterr().out)
    assert out["artboards"] == ["card"] and out["saves_to"] == ["output/adobe/sample-card.psd"]
    script = sample.path(out["script"]).read_text(encoding="utf-8")
    assert script.startswith("﻿#target photoshop") and "var DA = " in script
