"""Isometric blocks for design.json: build them in a script, they come out as plain `path` layers (so every
export and Affinity keeps them as editable curves).

    from designassist import iso
    layers += iso.tile("t1", 540, 600, 80, 24, top="$orange", left="$rust", right="$navy")
    layers += iso.prism("band", [(0, 900), (700, 550), (820, 610), (120, 960)], 40, top=..., left=..., right=...)
    fx, fy = iso.on_top(540, 600, 20, -10)  # a point on that tile's top (where a figure's feet go)

2:1 dimetric (edges slope 0.5, like most flat isometric illustration). A prism is a top face (any convex
polygon, screen points) extruded down by `h` px; only the side faces that point down the screen are drawn,
coloured by which way they face (left or right). `tile`/`block` are prisms with a diamond top.
"""
from __future__ import annotations

ARTBOARD = (1080, 1350)


def _path(id: str, pts: list, fill, size=ARTBOARD) -> dict:
    d = "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in pts) + " Z"
    return {"id": id, "type": "path", "d": d, "viewbox": [0, 0, size[0], size[1]], "x": 0, "y": 0, "w": size[0],
            "h": size[1], "fill": fill}


def prism(id: str, top: list, h: float, top_fill, left=None, right=None, size=ARTBOARD) -> list[dict]:
    """Side faces first (under), then the top. left/right default to the top colour."""
    n = len(top)
    area = sum(top[i][0] * top[(i + 1) % n][1] - top[(i + 1) % n][0] * top[i][1] for i in range(n))
    sign = 1 if area > 0 else -1  # screen y points down: area > 0 = clockwise on screen
    sides = []
    for i in range(n):
        (x0, y0), (x1, y1) = top[i], top[(i + 1) % n]
        # outward normal of the edge; visible when it points down the screen
        nx, ny = (y1 - y0) * sign, -(x1 - x0) * sign
        if ny <= 1e-6:
            continue
        fill = (left if nx < 0 else right) or top_fill
        sides.append(_path(f"{id}-{'l' if nx < 0 else 'r'}{i}", [(x0, y0), (x1, y1), (x1, y1 + h), (x0, y0 + h)], fill, size))
    return sides + [_path(f"{id}-top", top, top_fill, size)]


# iso axes on screen: R runs down-right, L down-left (2:1, edges slope 0.5)
R, L = (1.0, 0.5), (-1.0, 0.5)


def diamond(cx: float, cy: float, a: float, b: float | None = None) -> list:
    """Top face centred at (cx, cy): a units along R, b along L each way (a = b: a diamond 4a wide, 2a tall)."""
    b = a if b is None else b
    return [(cx - a + b, cy - (a + b) / 2), (cx + a + b, cy + (a - b) / 2), (cx + a - b, cy + (a + b) / 2),
            (cx - a - b, cy + (b - a) / 2)]


def tile(id: str, cx: float, cy: float, a: float, h: float, top, left=None, right=None, b: float | None = None,
         size=ARTBOARD) -> list[dict]:
    return prism(id, diamond(cx, cy, a, b), h, top, left, right, size)


def on_top(cx: float, cy: float, dx: float = 0, dy: float = 0) -> tuple[float, float]:
    """A point on a top face: dx units along R and dy along L from (cx, cy)."""
    return cx + dx - dy, cy + (dx + dy) / 2


def band(p0: tuple, p1: tuple, width: float) -> list:
    """Top face of a straight band whose back edge runs p0 -> p1 along one iso axis, `width` units deep along
    the other one, towards the viewer."""
    (x0, y0), (x1, y1) = p0, p1
    ox, oy = (L if (x1 - x0) * (y1 - y0) > 0 else R)
    ox, oy = ox * width, oy * width
    return [(x0, y0), (x1, y1), (x1 + ox, y1 + oy), (x0 + ox, y0 + oy)]
