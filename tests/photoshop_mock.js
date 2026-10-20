// Minimal Photoshop scripting mock: runs a designassist .jsx and reports the documents/layers it built.
// Usage: node tests/photoshop_mock.js output/adobe/x-photoshop.jsx  -> JSON; exit 1 on error.
// Placing reads the PNG header for its size and centres it on the canvas, as Photoshop does.
const fs = require("fs");

function enumOf(name, keys) {
  const o = {};
  for (const k of keys) o[k] = `${name}.${k}`;
  return new Proxy(o, { get(t, k) {
    if (typeof k !== "string" || k === "toJSON" || k === "then") return undefined;
    if (!(k in t)) throw new Error(`Invalid enumeration value ${name}.${k}`);
    return t[k];
  } });
}
global.Units = enumOf("Units", ["PIXELS", "POINTS", "MM", "CM", "INCHES", "PERCENT"]);
global.TypeUnits = enumOf("TypeUnits", ["PIXELS", "POINTS", "MM"]);
global.DialogModes = enumOf("DialogModes", ["NO", "ERROR", "ALL"]);
global.NewDocumentMode = enumOf("NewDocumentMode", ["RGB", "CMYK", "GRAYSCALE"]);
global.DocumentFill = enumOf("DocumentFill", ["TRANSPARENT", "WHITE", "BACKGROUNDCOLOR"]);
global.LayerKind = enumOf("LayerKind", ["NORMAL", "TEXT", "SMARTOBJECT"]);
global.TextType = enumOf("TextType", ["POINTTEXT", "PARAGRAPHTEXT"]);
global.Justification = enumOf("Justification", ["LEFT", "CENTER", "RIGHT", "LEFTJUSTIFIED", "CENTERJUSTIFIED",
  "RIGHTJUSTIFIED", "FULLYJUSTIFIED"]);
global.BlendMode = enumOf("BlendMode", ["NORMAL", "MULTIPLY", "SCREEN", "OVERLAY", "DARKEN", "LIGHTEN", "COLORDODGE",
  "COLORBURN", "HARDLIGHT", "SOFTLIGHT", "DIFFERENCE", "EXCLUSION", "HUE", "SATURATION", "COLOR", "LUMINOSITY"]);
global.ElementPlacement = enumOf("ElementPlacement", ["PLACEATBEGINNING", "PLACEATEND", "PLACEBEFORE", "PLACEAFTER", "INSIDE"]);

function UnitValue(v, u) {
  if (!(this instanceof UnitValue)) return new UnitValue(v, u);
  if (typeof v !== "number" || isNaN(v)) throw new Error("bad UnitValue " + v);
  if (u !== "px") throw new Error("mock expects px units, got " + u);
  this.value = v; this.type = u;
}
UnitValue.prototype.as = function (u) { return this.value; };
global.UnitValue = UnitValue;
global.SolidColor = function () { this.rgb = { red: 0, green: 0, blue: 0 }; };
global.File = function (p) { this.fsName = p; this.exists = fs.existsSync(p); };
global.PhotoshopSaveOptions = function () {};
global.charIDToTypeID = (s) => s;
global.ActionDescriptor = function () {
  this.v = {};
  this.putPath = (k, f) => { this.v[k] = f; };
  this.putEnumerated = (k, t, e) => { this.v[k] = e; };
  this.putUnitDouble = (k, t, n) => { this.v[k] = n; };
  this.putObject = (k, t, o) => { this.v[k] = o; };
};

const log = { docs: [] };
let cur = null;

function pngSize(p) {
  const b = fs.readFileSync(p);
  if (b.toString("ascii", 1, 4) !== "PNG") throw new Error("not a png: " + p);
  return [b.readUInt32BE(16), b.readUInt32BE(20)];
}

function layer(parent, kind) {
  const L = { kind, name: "", opacity: 100, parent, bounds: null, file: null,
    translate(dx, dy) { const x = dx.value, y = dy.value; const b = this.bounds.map((u) => u.value);
      this.bounds = [b[0] + x, b[1] + y, b[2] + x, b[3] + y].map((v) => new UnitValue(v, "px")); },
    move(target, where) { if (!String(where).startsWith("ElementPlacement.")) throw new Error("move");
      const a = this.parent.layers; a.splice(a.indexOf(this), 1);
      if (where === "ElementPlacement.PLACEBEFORE") { const b = target.parent.layers; b.splice(b.indexOf(target), 0, this); this.parent = target.parent; }
      else if (where === "ElementPlacement.PLACEATBEGINNING") { target.layers.unshift(this); this.parent = target; }
      else throw new Error("mock: unsupported placement " + where); },
    remove() { const a = this.parent.layers; a.splice(a.indexOf(this), 1); },
    set blendMode(b) { if (!String(b).startsWith("BlendMode.")) throw new Error("blend"); this._blend = b; },
    get blendMode() { return this._blend; } };
  parent.layers.unshift(L);
  return L;
}

function holder(obj) {
  obj.layers = [];
  obj.artLayers = { add: () => { const act = cur.activeLayer; const into = obj === cur && act && act.parent && act.parent !== cur ? act.parent : obj;
    const L = layer(into, "art"); cur.activeLayer = L;
    Object.defineProperty(L, "kind", { set(k) { if (!String(k).startsWith("LayerKind.")) throw new Error("kind");
      if (k === "LayerKind.TEXT") this.textItem = { _set: true }; this._kind = k; }, get() { return this._kind; } });
    return L; } };
  obj.layerSets = { add: () => { const S = holder(layer(obj, "set")); return S; } };
  return obj;
}

global.app = {
  preferences: { rulerUnits: "Units.POINTS", typeUnits: "TypeUnits.POINTS" },
  displayDialogs: null,
  documents: { add(w, h, res, name, mode, fill) {
    const d = holder({ name, w: w.value, h: h.value, res, mode, fill, saved: null });
    cur = d;
    const bg = layer(d, "art"); bg.name = "Layer 1";
    d.artLayers[0] = bg;
    d.selection = { selectAll() {}, deselect() {}, fill(c) { if (!c.rgb) throw new Error("fill colour"); d.bgFill = [c.rgb.red, c.rgb.green, c.rgb.blue]; } };
    d.activeLayer = bg;
    d.saveAs = (f, o, copy) => { d.saved = f.fsName; };
    log.docs.push(d);
    return d;
  } },
};
global.executeAction = (id, desc) => {
  if (id !== "Plc ") throw new Error("unexpected action " + id);
  const f = desc.v["null"];
  if (!f.exists) throw new Error("placed file missing: " + f.fsName);
  const [w, h] = pngSize(f.fsName);
  const parent = cur.activeLayer && cur.activeLayer.parent && cur.activeLayer.parent !== cur ? cur.activeLayer.parent : cur;
  const L = layer(parent, "smartobject");
  const x = (cur.w - w) / 2, y = (cur.h - h) / 2;
  L.bounds = [x, y, x + w, y + h].map((v) => new UnitValue(v, "px"));
  L.file = f.fsName; L.size = [w, h];
  cur.activeLayer = L;
};

const src = fs.readFileSync(process.argv[2], "utf8").replace(/^﻿/, "").replace(/^#.*$/m, "");
const result = eval(src);
function dump(L) {
  const o = { name: L.name, kind: L.kind === "set" ? "set" : (L.textItem ? "text" : L.kind), opacity: L.opacity, blend: L._blend || null };
  if (L.bounds) o.bounds = L.bounds.map((u) => u.value);
  if (L.file) o.file = L.file;
  if (L.textItem) { const t = L.textItem; o.text = { contents: t.contents, font: t.font, size: t.size && t.size.value,
    leading: t.leading && t.leading.value, tracking: t.tracking, kind: t.kind, justification: t.justification,
    position: t.position && t.position.map((u) => u.value), width: t.width && t.width.value, height: t.height && t.height.value,
    color: t.color && [t.color.rgb.red, t.color.rgb.green, t.color.rgb.blue] }; }
  if (L.kind === "set") o.layers = L.layers.map(dump);
  return o;
}
console.log(JSON.stringify({ result: JSON.parse(result), prefs: app.preferences,
  docs: log.docs.map((d) => ({ name: d.name, w: d.w, h: d.h, res: d.res, bgFill: d.bgFill || null, saved: d.saved, layers: d.layers.map(dump) })) }));
