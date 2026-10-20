// Minimal Illustrator scripting mock: runs a designassist .jsx and reports what it built.
// Usage: node tests/illustrator_mock.js output/adobe/x-illustrator.jsx  -> JSON {result, log}; exit 1 on error.
// Enumerations throw on unknown names, like Illustrator does ("Invalid enumeration value").
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

const log = { artboards: [], items: [], swatches: [], spots: [], fonts: [], saved: null, placed: [], svgs: [], effects: 0 };
global.UserInteractionLevel = enumOf("UserInteractionLevel", ["DONTDISPLAYALERTS", "DISPLAYALERTS"]);
global.CoordinateSystem = enumOf("CoordinateSystem", ["DOCUMENTCOORDINATESYSTEM", "ARTBOARDCOORDINATESYSTEM"]);
global.DocumentColorSpace = enumOf("DocumentColorSpace", ["RGB", "CMYK"]);
global.RulerUnits = enumOf("RulerUnits", ["Points", "Pixels", "Millimeters", "Inches", "Centimeters"]);
global.ColorModel = enumOf("ColorModel", ["SPOT", "PROCESS", "REGISTRATION"]);
global.Justification = enumOf("Justification", ["LEFT", "CENTER", "RIGHT", "FULLJUSTIFY", "FULLJUSTIFYLASTLINELEFT",
  "FULLJUSTIFYLASTLINECENTER", "FULLJUSTIFYLASTLINERIGHT"]);
global.FirstBaselineType = enumOf("FirstBaselineType", ["BASELINEASCENT", "BASELINECAPHEIGHT", "BASELINEEMBOXHEIGHT",
  "BASELINEFIXED", "BASELINELEADING", "BASELINELEGACY", "BASELINEXHEIGHT"]);
global.BlendModes = enumOf("BlendModes", ["NORMAL", "MULTIPLY", "SCREEN", "OVERLAY", "DARKEN", "LIGHTEN", "COLORDODGE",
  "COLORBURN", "HARDLIGHT", "SOFTLIGHT", "DIFFERENCE", "EXCLUSION", "HUE", "SATURATIONBLEND", "COLORBLEND", "LUMINOSITY"]);
global.ZOrderMethod = enumOf("ZOrderMethod", ["BRINGTOFRONT", "BRINGFORWARD", "SENDBACKWARD", "SENDTOBACK"]);
global.SaveOptions = enumOf("SaveOptions", ["DONOTSAVECHANGES", "SAVECHANGES", "PROMPTTOSAVECHANGES"]);
global.TextType = enumOf("TextType", ["POINTTEXT", "AREATEXT", "PATHTEXT"]);
global.NoColor = function () { this.typename = "NoColor"; };
global.RGBColor = function () { this.typename = "RGBColor"; this.red = 0; this.green = 0; this.blue = 0; };
global.CMYKColor = function () { this.typename = "CMYKColor"; this.cyan = 0; this.magenta = 0; this.yellow = 0; this.black = 0; };
global.SpotColor = function () { this.typename = "SpotColor"; };
global.DocumentPreset = function () {};
global.IllustratorSaveOptions = function () {};
global.File = function (p) { this.fsName = p; this.exists = fs.existsSync(p); };

function num(v, what) { if (typeof v !== "number" || isNaN(v)) throw new Error(`bad number for ${what}: ${v}`); return v; }
function checkColor(c, what) {
  if (!c || !c.typename) throw new Error(`${what}: not a colour`);
  for (const k of ["red", "green", "blue", "cyan", "magenta", "yellow", "black"]) if (k in c) num(c[k], `${what}.${k}`);
}

function item(kind, parent, geo) {
  const it = { typename: kind, kind: geo.kind || kind, name: "", opacity: 100, geo, parent, filled: true, stroked: false,
    rotateBy: 0, effects: [],
    rotate(d) { this.rotateBy += num(d, "rotate"); },
    remove() { const a = this.parent.pageItems; a.splice(a.indexOf(this), 1); log.items.splice(log.items.indexOf(this), 1); },
    applyEffect(xml) { if (!/<LiveEffect name="[^"]+"><Dict data="[^"]*"\/><\/LiveEffect>/.test(xml)) throw new Error("bad effect xml"); this.effects.push(xml); log.effects++; },
    set fillColor(c) { checkColor(c, "fillColor"); this._fill = c; }, get fillColor() { return this._fill; },
    set strokeColor(c) { checkColor(c, "strokeColor"); this._stroke = c; }, get strokeColor() { return this._stroke; },
    set blendingMode(b) { if (!String(b).startsWith("BlendModes.")) throw new Error("bad blend"); this._blend = b; },
    get blendingMode() { return this._blend; },
  };
  if (kind === "GroupItem") container(it);
  parent.pageItems.unshift(it); // newest on top, index 0
  log.items.push(it);
  return it;
}

function textFrame(parent, geo) {
  const tf = item("TextFrame", parent, geo);
  const ca = {}; const pa = {};
  tf.textRange = { characterAttributes: ca, paragraphAttributes: pa };
  Object.defineProperty(ca, "textFont", { set(f) { if (!f || !f.name) throw new Error("textFont"); this._f = f; }, get() { return this._f; } });
  tf._chars = [];
  Object.defineProperty(tf, "contents", { set(s) {
    if (typeof s !== "string") throw new Error("contents must be a string");
    this._contents = s; this._chars = Array.from(s).map(() => ({ characterAttributes: {} }));
  }, get() { return this._contents; } });
  Object.defineProperty(tf, "characters", { get() { return Object.assign(this._chars.slice(), { length: this._chars.length }); } });
  Object.defineProperty(tf, "lines", { get() { return { length: (this._contents || "").split("\r").length }; } });
  Object.defineProperty(tf, "firstBaseline", { set(v) { if (!String(v).startsWith("FirstBaselineType.")) throw new Error("bad firstBaseline"); this._fb = v; }, get() { return this._fb; } });
  return tf;
}

function container(c = {}) {
  c.pageItems = [];
  c.pathItems = {
    rectangle: (top, left, w, h) => item("PathItem", c, { kind: "rect", top: num(top, "top"), left: num(left, "left"), w: num(w, "w"), h: num(h, "h") }),
    roundedRectangle: (top, left, w, h, rx, ry) => item("PathItem", c, { kind: "roundrect", top: num(top, "top"), left: num(left, "left"), w: num(w, "w"), h: num(h, "h"), r: num(rx, "r") }),
    ellipse: (top, left, w, h) => item("PathItem", c, { kind: "ellipse", top: num(top, "top"), left: num(left, "left"), w: num(w, "w"), h: num(h, "h") }),
    add: () => { const p = item("PathItem", c, { kind: "path" }); p.setEntirePath = (pts) => { pts.forEach((q) => { num(q[0], "x"); num(q[1], "y"); }); p.geo.points = pts; }; return p; },
  };
  c.textFrames = {
    areaText: (path) => { path.remove(); return textFrame(c, { kind: "area", top: path.geo.top, left: path.geo.left, w: path.geo.w, h: path.geo.h }); },
    pointText: (pt) => textFrame(c, { kind: "point", x: num(pt[0], "x"), y: num(pt[1], "y") }),
  };
  c.placedItems = { add: () => {
    const p = item("PlacedItem", c, { kind: "placed" });
    Object.defineProperty(p, "file", { set(f) { if (!f.exists) throw new Error("placed file missing: " + f.fsName); log.placed.push(f.fsName); this._file = f; }, get() { return this._file; } });
    p.embed = () => { const g = p.geo; p.remove(); const r = item("RasterItem", c, { kind: "raster" }); Object.assign(r.geo, g, { kind: "raster", left: p.position[0], top: p.position[1], w: p.width, h: p.height }); };
    return p;
  } };
  c.groupItems = {
    add: () => item("GroupItem", c, { kind: "group" }),
    createFromFile: (f) => {
      if (!f.exists) throw new Error("svg missing: " + f.fsName);
      const svg = fs.readFileSync(f.fsName, "utf8");
      if (!/^<svg[^>]*\swidth="[\d.]+"/.test(svg)) throw new Error("svg has no width");
      log.svgs.push(f.fsName);
      const g = item("GroupItem", c, { kind: "svg", file: f.fsName });
      if (/id="daframe"/.test(svg)) { const fr = item("PathItem", g, { kind: "frame" }); fr.name = "daframe"; }
      return g;
    },
  };
  return c;
}

function makeDoc(mode, preset) {
  const doc = container();
  doc.name = (preset && preset.title) || "Untitled-1";
  doc.mode = mode;
  doc.preset = preset;
  doc.selection = [];
  const board = (rect) => ({ _rect: rect, name: "", set artboardRect(r) { r.forEach((v) => num(v, "rect")); this._rect = r; }, get artboardRect() { return this._rect; } });
  doc.artboards = [board([0, 612, 792, 0])];
  doc.artboards.add = (r) => { const b = board(r); doc.artboards.push(b); return b; };
  const layer = () => Object.assign(container(), { name: "", zOrder(m) { if (!String(m).startsWith("ZOrderMethod.")) throw new Error("zOrder"); } });
  doc.layers = [layer()];
  doc.layers.add = () => { const L = layer(); doc.layers.unshift(L); return L; };
  doc.layers.getByName = (n) => { const L = doc.layers.find((x) => x.name === n); if (!L) throw new Error("no layer " + n); return L; };
  doc.swatchGroups = { add: () => ({ name: "", addSwatch(s) { this.n = (this.n || 0) + 1; }, addSpot(s) { this.n = (this.n || 0) + 1; } }) };
  doc.swatches = { add: () => { const s = { name: "" }; log.swatches.push(s); return s; } };
  doc.spots = { add: () => { const s = { name: "", colorType: null }; log.spots.push(s); return s; } };
  doc.saveAs = (f) => { log.saved = f.fsName; };
  log.doc = doc;
  return doc;
}

global.app = {
  documents: {
    addDocument(startup, preset) { return makeDoc(preset.colorMode, preset); },
    add(mode) { return makeDoc(mode, null); },
  },
  textFonts: { getByName(n) { log.fonts.push(n); if (/^Missing/.test(n)) throw new Error("No such element"); return { name: n }; } },
};

const src = fs.readFileSync(process.argv[2], "utf8").replace(/^﻿/, "").replace(/^#.*$/m, "");
const result = eval(src);
const doc = log.doc;
const items = log.items.map((it) => ({ name: it.name, type: it.typename, kind: it.geo.kind, geo: it.geo, opacity: it.opacity,
  blend: it._blend || null, rotate: it.rotateBy, effects: it.effects.length,
  contents: it._contents, font: it.textRange && it.textRange.characterAttributes._f ? it.textRange.characterAttributes._f.name : undefined,
  size: it.textRange ? it.textRange.characterAttributes.size : undefined,
  leading: it.textRange ? it.textRange.characterAttributes.leading : undefined,
  tracking: it.textRange ? it.textRange.characterAttributes.tracking : undefined,
  justification: it.textRange ? it.textRange.paragraphAttributes.justification : undefined,
  firstBaselineMin: it.firstBaselineMin, position: it.position, width: it.width, height: it.height,
  accent: it._chars ? it._chars.filter((ch) => ch.characterAttributes.fillColor).length : undefined,
  parent: it.parent && it.parent.typename === "GroupItem" ? it.parent.name : null }));
console.log(JSON.stringify({ result: JSON.parse(result), mode: doc.mode, bleed: doc.preset ? doc.preset.documentBleedOffsetRect || null : null,
  artboards: doc.artboards.map((b) => ({ name: b.name, rect: b.artboardRect })), layers: doc.layers.map((l) => l.name),
  items, swatches: log.swatches.map((s) => s.name), spots: log.spots.map((s) => s.name), fonts: log.fonts,
  placed: log.placed, svgs: log.svgs, saved: log.saved, effects: log.effects }));
