"""Compare plugin impulse responses against the ideal SM58 -> U 87 transfer.

    python3 -I tools/compare.py <dir with *_imp*.f32>

The ideal transfer is the ratio of the published curves (Neumann U 87 Ai
cardioid / Shure SM58), both far field, normalized at 1 kHz.
"""
import csv
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
SR, N, IMP_AT, AMP = 48000.0, 1 << 16, 1000, 0.01


def curve(name):
    rows = list(csv.DictReader(open(ROOT / "research" / "data" / f"{name}.csv")))
    return np.array([float(r["freq_hz"]) for r in rows]), np.array([float(r["db"]) for r in rows])


def response(path, latency=0):
    y = np.fromfile(path, np.float32).reshape(-1, 2)[:, 0]
    h = y[IMP_AT + latency: IMP_AT + latency + N] / AMP
    f = np.fft.rfftfreq(N, 1 / SR)
    return f, 20 * np.log10(np.abs(np.fft.rfft(h, N)) + 1e-12)


def at(f, d, fr):
    return float(np.interp(np.log10(fr), np.log10(f[1:]), d[1:]))


def main(d):
    d = Path(d)
    fu, du = curve("cardioid")
    fs, ds = curve("sm58")
    grid = np.geomspace(55, 14500, 200)  # range covered by both published curves
    ideal = np.array([at(fu, du, g) - at(fs, ds, g) for g in grid])
    ideal -= at(grid, ideal, 1000)
    runs = {
        "BESURE-N87": response(d / "b_imp.f32"),
        "Shu87 (neutral distance)": response(d / "s_imp_neutral.f32", 31),
        "Shu87 (default 5 cm -> 20 cm)": response(d / "s_imp.f32", 31),
    }
    out = {"ideal": ideal}
    print(f"{'Hz':>7} {'ideal':>7}" + "".join(f" {k[:12]:>13}" for k in runs))
    for name, (f, m) in runs.items():
        v = np.array([at(f, m, g) for g in grid])
        out[name] = v - at(grid, v, 1000)
    for fr in (60, 100, 200, 500, 1000, 2000, 3000, 4000, 5000, 6000, 7500, 9000, 10000, 12000, 14000):
        i = np.argmin(abs(grid - fr))
        print(f"{fr:7d} {ideal[i]:+7.1f}" + "".join(f" {out[k][i]:+13.1f}" for k in runs))
    band = (grid >= 100) & (grid <= 12000)
    for k in runs:
        e = out[k][band] - ideal[band]
        print(f"{k:32s} vs ideal (100 Hz-12 kHz): max {np.abs(e).max():.1f} dB, rms {np.sqrt(np.mean(e**2)):.1f} dB")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.semilogx(grid, ideal, "k", lw=3, alpha=0.4, label="ideal: U 87 Ai / SM58 (published curves)")
    for k in runs:
        ax.semilogx(grid, out[k], label=k)
    ax.set_xlim(50, 15000); ax.set_ylim(-15, 12); ax.grid(True, which="both", alpha=0.3)
    ax.set_xlabel("Hz"); ax.set_ylabel("dB (0 @ 1 kHz)"); ax.legend(fontsize=8)
    ax.set_title("SM58 -> U 87 transfer: measured plugins vs ideal")
    fig.tight_layout(); fig.savefig(ROOT / "docs" / "compare_besure.png", dpi=110)


if __name__ == "__main__":
    main(sys.argv[1])
