#!/usr/bin/env python3
"""Draw the cutest picture — make.fun bounty cutest-picture-01.

A deterministic program (Python 3.13, standard library only) that draws one
cute baby panda and writes it to $MAKEFUN_OUTPUT_DIR/entry.png
(default /output).

The panda is drawn with a tiny span-based rasterizer: circles, ellipses,
rotated ellipses, polygons and thick bezier strokes, with 1-pixel edge
antialiasing. No randomness, no wall clock, no network: two runs write
identical bytes.
"""
import math
import os
import struct
import zlib

W = H = 1024

# ---------------------------------------------------------------- palette
BG_TOP = (234, 247, 238)
BG_BOT = (255, 244, 224)
WHITE = (253, 253, 250)
HEAD_EDGE = (222, 224, 226)
BODY = (250, 250, 248)
BLACK = (28, 28, 34)
PATCH = (34, 34, 42)
EAR_FLUFF = (62, 62, 72)
EYE = (28, 20, 16)
NOSE = (40, 40, 48)
MOUTH = (60, 60, 70)
BLUSH = (245, 150, 165)
BAMBOO = (110, 168, 105)
BAMBOO_DARK = (84, 138, 80)
TOE = (120, 120, 128)


def clamp(v, a, b):
    return a if v < a else b if v > b else v


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


class Canvas:
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.px = bytearray(w * h * 3)

    def set(self, x, y, color, alpha=1.0):
        if 0 <= x < self.w and 0 <= y < self.h:
            i = (y * self.w + x) * 3
            if alpha >= 1.0:
                self.px[i:i + 3] = bytes(color)
            else:
                for c in range(3):
                    self.px[i + c] = int(self.px[i + c] * (1 - alpha) + color[c] * alpha)

    def hspan(self, x0, x1, y, color, alpha=1.0):
        if y < 0 or y >= self.h:
            return
        x0 = max(0, x0)
        x1 = min(self.w - 1, x1)
        if x1 < x0:
            return
        if alpha >= 1.0:
            row = bytes(color) * (x1 - x0 + 1)
            i = (y * self.w + x0) * 3
            self.px[i:i + len(row)] = row
        else:
            for x in range(x0, x1 + 1):
                self.set(x, y, color, alpha)

    def circle(self, cx, cy, r, color, alpha=1.0):
        y0 = max(0, int(math.ceil(cy - r)))
        y1 = min(self.h - 1, int(math.floor(cy + r)))
        for y in range(y0, y1 + 1):
            dy = y - cy
            dx = math.sqrt(max(0.0, r * r - dy * dy))
            fx0, fx1 = cx - dx, cx + dx
            ix0, ix1 = int(math.ceil(fx0)), int(math.floor(fx1))
            self.hspan(ix0, ix1, y, color, alpha)
            lx = ix0 - 1
            if lx >= 0:
                self.set(lx, y, color, alpha * clamp(ix0 - fx0, 0, 1))
            rx = ix1 + 1
            if rx < self.w:
                self.set(rx, y, color, alpha * clamp(fx1 - ix1, 0, 1))

    def ellipse(self, cx, cy, rx, ry, color, alpha=1.0):
        y0 = max(0, int(math.ceil(cy - ry)))
        y1 = min(self.h - 1, int(math.floor(cy + ry)))
        for y in range(y0, y1 + 1):
            dy = (y - cy) / ry
            dx = rx * math.sqrt(max(0.0, 1.0 - dy * dy))
            fx0, fx1 = cx - dx, cx + dx
            ix0, ix1 = int(math.ceil(fx0)), int(math.floor(fx1))
            self.hspan(ix0, ix1, y, color, alpha)
            lx = ix0 - 1
            if lx >= 0:
                self.set(lx, y, color, alpha * clamp(ix0 - fx0, 0, 1))
            rxp = ix1 + 1
            if rxp < self.w:
                self.set(rxp, y, color, alpha * clamp(fx1 - ix1, 0, 1))

    def rellipse(self, cx, cy, rx, ry, ang, color, alpha=1.0, steps=72):
        """A rotated ellipse, filled via its sampled polygon outline."""
        pts = []
        c, s = math.cos(ang), math.sin(ang)
        for i in range(steps):
            t = 2 * math.pi * i / steps
            ex, ey = rx * math.cos(t), ry * math.sin(t)
            pts.append((cx + ex * c - ey * s, cy + ex * s + ey * c))
        self.polygon(pts, color, alpha)

    def polygon(self, pts, color, alpha=1.0):
        ys = [p[1] for p in pts]
        y0 = max(0, int(math.ceil(min(ys))))
        y1 = min(self.h - 1, int(math.floor(max(ys))))
        n = len(pts)
        for y in range(y0, y1 + 1):
            xs = []
            for i in range(n):
                x1, y1p = pts[i]
                x2, y2p = pts[(i + 1) % n]
                if (y1p <= y < y2p) or (y2p <= y < y1p):
                    xs.append(x1 + (y - y1p) * (x2 - x1) / (y2p - y1p))
            xs.sort()
            for k in range(0, len(xs) - 1, 2):
                self.hspan(int(math.ceil(xs[k])), int(math.floor(xs[k + 1])), y, color, alpha)

    def bezier(self, p0, p1, p2, thick, color, alpha=1.0, steps=48):
        for i in range(steps + 1):
            t = i / steps
            x = (1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t * t * p2[0]
            y = (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t * t * p2[1]
            self.circle(x, y, thick / 2.0, color, alpha)

    def thick_line(self, p0, p1, thick, color, alpha=1.0):
        self.bezier(p0, ((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2), p1, thick, color, alpha, steps=24)


def rot(x, y, ang, cx=512, cy=500):
    c, s = math.cos(ang), math.sin(ang)
    dx, dy = x - cx, y - cy
    return (cx + dx * c - dy * s, cy + dx * s + dy * c)


def draw():
    cv = Canvas(W, H)
    # background: soft mint-to-cream gradient
    for y in range(H):
        cv.hspan(0, W - 1, y, lerp(BG_TOP, BG_BOT, y / (H - 1)))
    # soft pastel bokeh, very faint
    for (x, y, r, col) in [
        (150, 170, 90, (255, 183, 197)), (880, 150, 70, (255, 214, 140)),
        (120, 850, 110, (255, 214, 140)), (900, 860, 90, (186, 232, 200)),
        (512, 90, 60, (255, 183, 197)),
    ]:
        cv.circle(x, y, r, col, alpha=0.13)

    # body and chest, white and fluffy
    cv.ellipse(512, 1080, 400, 260, BODY)
    cv.ellipse(512, 1020, 215, 185, WHITE)

    # front paws at the bottom edge
    for px in (390, 634):
        cv.ellipse(px, 950, 105, 50, WHITE)
        for tx in (px - 30, px + 30):
            cv.thick_line((tx, 928), (tx, 966), 4, TOE, alpha=0.5)

    # ---- head group, tilted -3.5 degrees for charm ----
    ang = -0.06
    P = lambda x, y: rot(x, y, ang)

    # round black ears, fluffy grey rim behind
    for ex, ey in [(322, 268), (702, 268)]:
        cx, cy = P(ex, ey)
        cv.circle(cx, cy, 98, EAR_FLUFF)
        cv.circle(cx, cy, 90, BLACK)

    # head outline + head
    cv.circle(512, 500, 308, HEAD_EDGE)
    cv.circle(512, 500, 300, WHITE)

    # signature black eye patches, tilted outward
    for (px, py, tilt) in [(400, 468, -0.42), (624, 468, 0.42)]:
        cx, cy = P(px, py)
        cv.rellipse(cx, cy, 88, 118, tilt, PATCH)

    # big bright eyes inside the patches
    for ex, ey in [(400, 468), (624, 468)]:
        cx, cy = P(ex, ey)
        cv.circle(cx, cy, 44, EYE)
        hx, hy = P(ex - 15, ey - 16)
        cv.circle(hx, hy, 15, WHITE)
        hx2, hy2 = P(ex + 14, ey + 14)
        cv.circle(hx2, hy2, 6, WHITE)

    # blush cheeks
    for bx, by in [(368, 600), (656, 600)]:
        cx, cy = P(bx, by)
        cv.ellipse(cx, cy, 46, 26, BLUSH, alpha=0.5)

    # little black nose, one smooth oval so it reads as a nose, not dots
    nx, ny = P(512, 610)
    cv.ellipse(nx, ny, 34, 20, NOSE)
    sx, sy = P(502, 604)
    cv.circle(sx, sy, 5, WHITE, alpha=0.8)

    # little "w" mouth below the nose
    m0 = P(512, 636)
    cv.bezier(m0, P(492, 654), P(474, 660), 5, MOUTH, alpha=0.85)
    cv.bezier(m0, P(532, 654), P(550, 660), 5, MOUTH, alpha=0.85)

    return cv


def write_png(path, cv):
    raw = bytearray()
    for y in range(cv.h):
        raw.append(0)
        raw += cv.px[y * cv.w * 3:(y + 1) * cv.w * 3]
    comp = zlib.compress(bytes(raw), 9)

    def chunk(typ, data):
        out = struct.pack(">I", len(data)) + typ + data
        return out + struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", cv.w, cv.h, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", comp)
    png += chunk(b"IEND", b"")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(png)
    return len(png)


def main():
    outdir = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")
    path = os.path.join(outdir, "entry.png")
    size = write_png(path, draw())
    print(f"wrote {path} ({size} bytes)")


if __name__ == "__main__":
    main()
