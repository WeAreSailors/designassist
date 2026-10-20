"""`da batch`: one artboard per data row from a template artboard (price lists, event line-ups,
quote cards, per-store variations). `{{field}}` placeholders are replaced in every string value
of the template (text, src, colours, ids...). Rows come from a CSV (header = field names) or a
JSON list of objects."""
from __future__ import annotations

import copy
import csv
import json
import re
from pathlib import Path

from . import design as D
from .project import Project, slug

PLACEHOLDER = re.compile(r"\{\{\s*([\w.-]+)\s*\}\}")


def read_rows(path: Path) -> list[dict]:
    if path.suffix.lower() == ".json":
        rows = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(rows, dict):
            rows = rows.get("rows", [])
        return [{str(k): ("" if v is None else str(v)) for k, v in r.items()} for r in rows]
    text = path.read_text(encoding="utf-8-sig")  # Excel writes a BOM
    dialect = csv.Sniffer().sniff(text.splitlines()[0] if text else ",", delimiters=",;\t")
    return [{(k or "").strip(): (v or "").strip() for k, v in r.items()} for r in csv.DictReader(text.splitlines(), dialect=dialect)]


def fill(value, row: dict, missing: set):
    if isinstance(value, str):
        def sub(m):
            k = m.group(1)
            if k not in row:
                missing.add(k)
                return m.group(0)
            return row[k]
        return PLACEHOLDER.sub(sub, value)
    if isinstance(value, list):
        return [fill(v, row, missing) for v in value]
    if isinstance(value, dict):
        return {k: fill(v, row, missing) for k, v in value.items()}
    return value


def batch(project: Project, template: str, data: Path, id_field: str | None = None, render: bool = False,
          replace: bool = False) -> dict:
    d = D.load(project)
    tpl = D.artboard(d, template)
    data = data if data.is_absolute() else (project.path(str(data)) if project.path(str(data)).exists() else data.resolve())
    if not data.exists():
        raise SystemExit(f"data file not found: {data}")
    rows = read_rows(data)
    if not rows:
        raise SystemExit(f"{data.name}: no rows")
    used = set(PLACEHOLDER.findall(json.dumps(tpl, ensure_ascii=False)))
    if not used:
        raise SystemExit(f"template {template} has no {{{{field}}}} placeholders")
    made, missing = [], set()
    existing = {a["id"] for a in d["artboards"]}
    for i, row in enumerate(rows, 1):
        ab = fill(copy.deepcopy(tpl), row, missing)
        key = row.get(id_field) if id_field else None
        ab["id"] = f"{template}-{slug(key)}" if key else f"{template}-{i:02d}"
        if ab["id"] in existing:
            if not replace:
                raise SystemExit(f"artboard {ab['id']} exists (pass --replace)")
            d["artboards"] = [a for a in d["artboards"] if a["id"] != ab["id"]]
        ab.pop("template", None)
        d["artboards"].append(ab)
        made.append(ab["id"])
    D.save(project, d)
    res: dict = {"template": template, "rows": len(rows), "made": made, "fields": sorted(used)}
    if missing:
        res["missing_fields"] = sorted(missing)
    if render:
        from . import render as R

        res["render"] = R.render(project, made)
    return res


def cmd_batch(a):
    return batch(Project(a.project), a.template, Path(a.data), a.id_field, a.render, a.replace)


def register(sub) -> None:
    p = sub.add_parser("batch", help="one artboard per CSV/JSON row from a template with {{field}} placeholders")
    p.add_argument("project")
    p.add_argument("--template", required=True, help="template artboard id")
    p.add_argument("--data", required=True, help="rows.csv or rows.json (project-relative or absolute)")
    p.add_argument("--id-field", help="column used for artboard ids (default numbered)")
    p.add_argument("--render", action="store_true", help="render the new artboards + sheet")
    p.add_argument("--replace", action="store_true")
    p.set_defaults(func=cmd_batch)
