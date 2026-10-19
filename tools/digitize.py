"""Digitize the published frequency-response charts into CSV.

Traces the thick black curve column by column. Axis calibration comes
from the chart grid (pixel positions measured on the rendered images in
research/data/).
"""
import csv
import numpy as np
from PIL import Image
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "research" / "data"


def runs(col):
    """Centers of consecutive dark-pixel runs in a boolean column."""
    out, start = [], None
    for i, v in enumerate(col):
        if v and start is None:
            start = i
        elif not v and start is not None:
            out.append(((start + i - 1) / 2, i - start))
            start = None
    if start is not None:
        out.append(((start + len(col) - 1) / 2, len(col) - start))
    return out


def trace(img, x0, x1, y0, y1, fx, fy, thr=70, minw=3, skip=None, pick="top"):
    """Return [(freq, dB)] for columns x0..x1, rows y0..y1."""
    a = np.asarray(img.convert("L"))
    pts = []
    for x in range(x0, x1):
        if skip and skip[0] <= x <= skip[1]:
            continue
        rs = [r for r in runs(a[y0:y1, x] < thr) if r[1] >= minw]
        if not rs:
            continue
        y = (rs[0] if pick == "top" else rs[-1])[0] + y0
        if pick == "bottom" and len(rs) < 2:
            continue
        pts.append((fx(x), fy(y)))
    return pts


def resample(pts, freqs):
    f = np.array([p[0] for p in pts])
    d = np.array([p[1] for p in pts])
    o = np.argsort(f)
    lf, dd = np.log10(f[o]), d[o]
    lo, hi = lf[0], lf[-1]
    return [(fq, float(np.interp(np.log10(fq), lf, dd)))
            for fq in freqs if lo <= np.log10(fq) <= hi]


def main():
    freqs = np.geomspace(20, 20000, 241)

    # Neumann U 87 Ai product information, page 4 (300 dpi render).
    u87 = Image.open(DATA / "u87_all.png")
    fx = lambda x: 20 * 10 ** ((x - 85) / 416.0)
    charts = {"omni": 213, "cardioid": 887, "fig8": 1575}
    out = {}
    for name, y0db in charts.items():
        fy = lambda y, y0db=y0db: -(y - y0db) / 7.6
        top, bot = y0db - 90, y0db + 160
        main_c = trace(u87, 88, 1331, top, bot, fx, fy)
        lc = trace(u87, 88, 790, top, bot, fx, fy, skip=(540, 632), pick="bottom")
        out[name] = resample(main_c, freqs)
        out[name + "_lowcut"] = resample(lc + [p for p in main_c if p[0] >= 1000], freqs)

    # Shure SM58 user guide, typical frequency response (500 dpi render).
    sm = Image.open(DATA / "sm58.png")
    fx = lambda x: 20 * 10 ** ((x - 308) / 434.0)
    fy = lambda y: -(y - 1256) / 16.6
    out["sm58"] = resample(trace(sm, 330, 1600, 935, 1580, fx, fy, thr=60, minw=5), freqs)

    for name, pts in out.items():
        with open(DATA / f"{name}.csv", "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["freq_hz", "db"])
            for f, d in pts:
                w.writerow([f"{f:.1f}", f"{d:.2f}"])
        print(name, " ".join(f"{f:.0f}:{d:+.1f}" for f, d in pts[::4]))


if __name__ == "__main__":
    main()
