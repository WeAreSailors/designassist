// designassist ExtendScript helpers shared by the Illustrator and Photoshop builders.
// ExtendScript is ES3: no JSON object, no Array.prototype.indexOf. Keep it that way.

function daJSON(v) {
  var t = typeof v;
  if (v === null || v === undefined) return "null";
  if (t == "number") return isFinite(v) ? String(v) : "null";
  if (t == "boolean") return v ? "true" : "false";
  if (t == "string") {
    var s = "";
    for (var i = 0; i < v.length; i++) {
      var c = v.charAt(i), n = v.charCodeAt(i);
      if (c == "\\") s += "\\\\";
      else if (c == '"') s += '\\"';
      else if (c == "\n") s += "\\n";
      else if (c == "\r") s += "\\r";
      else if (c == "\t") s += "\\t";
      else if (n < 32 || n > 126) s += "\\u" + ("0000" + n.toString(16)).slice(-4);
      else s += c;
    }
    return '"' + s + '"';
  }
  if (v instanceof Array) {
    var a = [];
    for (var j = 0; j < v.length; j++) a.push(daJSON(v[j]));
    return "[" + a.join(",") + "]";
  }
  var o = [];
  for (var k in v) {
    if (v.hasOwnProperty(k) && typeof v[k] != "function") o.push(daJSON(String(k)) + ":" + daJSON(v[k]));
  }
  return "{" + o.join(",") + "}";
}

function daTry(out, what, fn) {
  try { return fn(); } catch (e) { out.errors.push(what + ": " + e); return null; }
}
