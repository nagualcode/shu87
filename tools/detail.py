"""Analyze the U 87 "micro-resonance" detail in the IR pack.

    python3 -I tools/detail.py

Input: research/impulse_response/U87 {05,1,2,4,5}inch.wav (96 kHz, vintage
U 87, unknown reference microphone - see docs/IR_PACK_ANALYSIS.md).

Method
  1. Window each IR to 5 ms after its peak (drops room reflections / noise).
  2. Magnitude minus its 1/3-octave smoothing = fine structure.
  3. Group files whose fine structure is identical (correlation > 0.99): those
     are one capture with different low-end EQ, not separate measurements.
  4. Compare independent captures in 3-15 kHz. Detail that is a property of
     the microphone must repeat across captures; detail that does not is the
     measurement setup.

Output: printed statistics and docs/detail.png. Nothing is fed to the plugin.
"""
from pathlib import Path

import numpy as np
from scipy.io import wavfile

ROOT = Path(__file__).resolve().parent.parent
PACK = ROOT / "research" / "impulse_response"
DISTANCES = ["05", "1", "2", "4", "5"]
WINDOW_S = 0.005
N = 1 << 16
BAND = (2000.0, 3000.0, 15000.0, 18000.0)  # fade-in start/end, fade-out start/end


def fine_structure(path):
    sr, x = wavfile.read(path)
    x = x[:, 0].astype(float) if x.ndim > 1 else x.astype(float)
    p = int(np.abs(x).argmax())
    w = x[max(0, p - 64): p + int(WINDOW_S * sr)]
    taper = np.ones(len(w))
    taper[-200:] = np.hanning(400)[200:]
    w = w * taper
    f = np.fft.rfftfreq(N, 1 / sr)
    mag = 20 * np.log10(np.abs(np.fft.rfft(w, N)) + 1e-15)
    lf = np.log10(np.maximum(f, 1.0))
    # 1/3-octave smoothing via cumulative sums over log-frequency windows
    half = np.log10(2) / 6
    lo = np.searchsorted(lf, lf - half)
    hi = np.searchsorted(lf, lf + half, side="right")
    cs = np.concatenate([[0.0], np.cumsum(mag)])
    smooth = (cs[hi] - cs[lo]) / np.maximum(hi - lo, 1)
    return f, mag - smooth


def band_weight(f):
    a, b, c, d = BAND
    w = np.zeros_like(f)
    up = (f >= a) & (f < b)
    w[up] = 0.5 - 0.5 * np.cos(np.pi * (f[up] - a) / (b - a))
    w[(f >= b) & (f <= c)] = 1.0
    dn = (f > c) & (f <= d)
    w[dn] = 0.5 + 0.5 * np.cos(np.pi * (f[dn] - c) / (d - c))
    return w


def main():
    files = {d: fine_structure(PACK / f"U87 {d}inch.wav") for d in DISTANCES}
    f = files[DISTANCES[0]][0]
    m = (f >= 3000) & (f <= 15000)

    captures = []  # lists of distances sharing one capture
    for d in DISTANCES:
        for c in captures:
            if np.corrcoef(files[c[0]][1][m], files[d][1][m])[0, 1] > 0.99:
                c.append(d)
                break
        else:
            captures.append([d])
    print("independent captures:", captures)

    w = band_weight(f)
    reps = [files[c[0]][1] * w for c in captures]
    for c, r in zip(captures, reps):
        print(f"  capture {'/'.join(c)} in: detail 3-15 kHz rms {np.sqrt(np.mean(r[m]**2)):.2f} dB")
    if len(reps) >= 2:
        a, b = reps[0], reps[1]
        print(f"  correlation between captures: {np.corrcoef(a[m], b[m])[0, 1]:+.3f}; "
              f"sign agreement {100 * np.mean(np.sign(a[m]) == np.sign(b[m])):.0f}% (chance = 50%)")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(10, 4.5))
    sel = (f > 1000) & (f < 22000)
    for c, r in zip(captures, reps):
        ax.semilogx(f[sel], r[sel], lw=1, label=f"capture {'/'.join(c)} in")
    ax.set_xlim(1000, 22000); ax.set_ylim(-4, 4); ax.grid(True, which="both", alpha=0.3)
    ax.set_xlabel("Hz"); ax.set_ylabel("dB"); ax.legend(fontsize=8)
    ax.set_title("U 87 IR pack: fine structure of the independent captures (3-15 kHz band)")
    fig.tight_layout(); fig.savefig(ROOT / "docs" / "detail.png", dpi=110)


if __name__ == "__main__":
    main()
