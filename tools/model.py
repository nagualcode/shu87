"""SM58 -> U 87 model: circuit analysis, curve fitting and code generation.

Run from the repo root:  python3 -I tools/model.py

Produces
  src/coeffs.rs            analog-prototype section tables used by the plugin
  research/data/fit.json   fitted parameters (for inspection)
  docs/*.png               verification plots

Every filter is expressed as an analog prototype H(s) = (b0 s^2 + b1 s + b2) /
(a0 s^2 + a1 s + a2); the plugin discretizes them with a pre-warped bilinear
transform at the (oversampled) running rate.
"""
import csv
import json
from pathlib import Path

import numpy as np
from scipy.optimize import least_squares

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "research" / "data"
DOCS = ROOT / "docs"
SRC = ROOT / "src"
TAU = 2 * np.pi


def load(name):
    with open(DATA / f"{name}.csv") as fh:
        rows = list(csv.DictReader(fh))
    f = np.array([float(r["freq_hz"]) for r in rows])
    d = np.array([float(r["db"]) for r in rows])
    ref = np.interp(np.log10(1000.0), np.log10(f), d)
    return f, d - ref  # normalize to 0 dB @ 1 kHz (removes line-thickness bias)


# ---------------------------------------------------------------- sections
# Each section is (b0, b1, b2, a0, a1, a2) in s, with s in rad/s.

def sec_eval(sec, f):
    s = 1j * TAU * f
    b0, b1, b2, a0, a1, a2 = sec
    return (b0 * s * s + b1 * s + b2) / (a0 * s * s + a1 * s + a2)


def chain_db(secs, f):
    h = np.ones_like(f, dtype=complex)
    for sec in secs:
        h *= sec_eval(sec, f)
    return 20 * np.log10(np.abs(h))


def hp2(fc, q):
    w = TAU * fc
    return (1.0, 0.0, 0.0, 1.0, w / q, w * w)


def lp2(fc, q):
    w = TAU * fc
    return (0.0, 0.0, w * w, 1.0, w / q, w * w)


def hp1(fc):
    w = TAU * fc
    return (0.0, 1.0, 0.0, 0.0, 1.0, w)


def peak(fc, gain_db, q):
    """RBJ analog peaking EQ. peak(f, -g, q) is the exact inverse of peak(f, g, q)."""
    w = TAU * fc
    a = 10 ** (gain_db / 40)
    return (1.0, a * w / q, w * w, 1.0, w / (a * q), w * w)


def invert(sec):
    b0, b1, b2, a0, a1, a2 = sec
    return (a0, a1, a2, b0, b1, b2)


def scale_sec(sec, k):
    b0, b1, b2, a0, a1, a2 = sec
    return (b0 * k, b1 * k, b2 * k, a0, a1, a2)


# ------------------------------------------------- U 87 FET stage (circuit)
# Schematic 10241-901-21.7 (U 87 i, 1980): the FET drain signal returns via
# C9 to the capsule-bias rail, then through R8 || C6 to the capsule backplate
# node, which is tied to ground through C5 + R9 + R10. The capsule (2 x 50 pF)
# against C1 (470 pF) + C3 (10 pF) + Cgs couples a fraction k of the backplate
# voltage onto the gate, so the capsule itself sits inside the negative
# feedback loop:
#     beta(s) = Zbot / (Ztop + Zbot),  Ztop = R8 || C6,  Zbot = R9 + R10 + 1/(s C5)
#     G(s)    = A / (1 + A k beta(s))
# U 87 Ai: C6 220p -> 160p (more highs), C5 33n -> 47n (more lows) [GroupDIY].
R8, R9, R10 = 1e6, 6.8e3, 560.0
LOOP_AK = 3.4  # open-loop gain x capsule coupling; see docs/MODEL.md (estimated)

VERSIONS = {"ai": (160e-12, 47e-9), "vintage": (220e-12, 33e-9)}


def fet_stage(c6, c5, ak=LOOP_AK):
    """Closed-loop FET stage as one analog biquad, unity gain at DC-free mid band.

    With t1 = (R9+R10) C5, t2 = R8 C6, N = (1 + s t1)(1 + s t2), D = s C5 R8 + N:
        G ∝ D / ((1 + Ak) N + s C5 R8)
    """
    t1, t2 = (R9 + R10) * c5, R8 * c6
    n2, n1, n0 = t1 * t2, t1 + t2, 1.0
    c = c5 * R8
    num = (n2, n1 + c, n0)
    den = ((1 + ak) * n2, (1 + ak) * n1 + c, (1 + ak) * n0)
    sec = (*num, *den)
    g1k = np.abs(sec_eval(sec, np.array([1000.0])))[0]
    return scale_sec(sec, 1 / g1k)


# How far the SM58 inverse extends the band. Below ~45 Hz and above
# ~16 kHz the SM58 delivers mostly handling noise / hiss, so boosting
# further only amplifies that.
LF_EXT_HZ = lambda fl: fl / 2
HF_EXT_HZ = 16500.0


# ------------------------------------------------------------- fitting
def fit(f, target, model, x0, lo, hi, fmin=25, fmax=19000, w=None):
    m = (f >= fmin) & (f <= fmax)
    ff, tt = f[m], target[m]
    ww = np.ones_like(ff) if w is None else w(ff)

    def resid(x):
        return (chain_db(model(x), ff) - tt) * ww

    r = least_squares(resid, x0, bounds=(lo, hi))
    err = np.abs(chain_db(model(r.x), ff) - tt)
    return r.x, float(err.max()), float(np.sqrt(np.mean(err ** 2)))


def capsule_model(x):
    fl, ql, f1, g1, q1, f2, g2, q2, fh, qh = x
    return [hp2(fl, ql), peak(f1, g1, q1), peak(f2, g2, q2), lp2(fh, qh)]


def sm58_model(x):
    fl, ql, f1, g1, q1, f2, g2, q2, f3, g3, q3, f4, g4, q4, fh, qh = x
    return [hp2(fl, ql), peak(f1, g1, q1), peak(f2, g2, q2), peak(f3, g3, q3),
            peak(f4, g4, q4), lp2(fh, qh)]


def lowcut_model(x):
    f1, f2 = x
    return [hp1(f1), hp1(f2)]


def main():
    DOCS.mkdir(exist_ok=True)
    results = {}

    fet = {k: fet_stage(*v) for k, v in VERSIONS.items()}
    fgrid = np.geomspace(20, 20000, 400)
    for k, sec in fet.items():
        d = chain_db([sec], np.array([20, 50, 100, 1000, 5000, 10000, 20000.0]))
        print(f"FET stage {k:8s}", " ".join(f"{x:+.2f}" for x in d))

    # --- K87 capsule per pattern: published (Ai) / FET stage (Ai)
    caps = {}
    for pat in ["cardioid", "omni", "fig8"]:
        f, d = load(pat)
        target = d - chain_db([fet["ai"]], f)
        x0 = [60, 0.6, 9000, 4, 1.2, 3000, 0.5, 1.0, 17000, 0.8]
        lo = [15, 0.3, 3000, -6, 0.3, 800, -4, 0.3, 8000, 0.4]
        hi = [200, 1.5, 14000, 10, 4, 8000, 4, 4, 30000, 2.5]
        x, emax, erms = fit(f, target, capsule_model, x0, lo, hi)
        caps[pat] = capsule_model(x)
        results[f"capsule_{pat}"] = {"params": list(x), "max_err_db": emax, "rms_err_db": erms}
        print(f"capsule {pat:8s} max {emax:.2f} dB rms {erms:.2f} dB  {np.round(x, 2)}")

    # --- low cut (electrical, at the amplifier input): fitted on cardioid,
    # the cleanest of the three published low-cut curves.
    f, d = load("cardioid")
    fl, dl = load("cardioid_lowcut")
    delta = dl - np.interp(np.log10(fl), np.log10(f), d)
    x, emax, erms = fit(fl, delta, lowcut_model, [200, 50], [20, 5], [1000, 400], fmin=50, fmax=1000)
    lowcut = lowcut_model(x)
    results["lowcut"] = {"params": list(x), "max_err_db": emax, "rms_err_db": erms}
    print(f"lowcut  max {emax:.2f} rms {erms:.2f}  {np.round(x, 1)}")

    # --- SM58 (far field) fit
    f, d = load("sm58")
    x0 = [90, 0.7, 5000, 4, 1.0, 7600, -4, 6, 10000, 3, 3, 2000, 1, 0.7, 13000, 1.0]
    lo = [40, 0.3, 3000, 0, 0.3, 6500, -12, 2, 8500, 0, 1, 800, -3, 0.3, 10000, 0.4]
    hi = [160, 1.5, 7000, 9, 3, 8500, 0, 15, 11500, 8, 8, 4000, 4, 3, 17000, 3]
    x, emax, erms = fit(f, d, sm58_model, x0, lo, hi, fmin=52, fmax=15000)
    sm = sm58_model(x)
    results["sm58"] = {"params": list(x), "max_err_db": emax, "rms_err_db": erms}
    print(f"sm58    max {emax:.2f} rms {erms:.2f}  {np.round(x, 2)}")

    # Regularized inverse: peaks invert exactly; the band edges are replaced
    # by a new, wider band edge (LF one octave lower, HF up to 16.5 kHz) so the
    # inverse never has unbounded gain.
    fl_, ql_ = x[0], x[1]
    fh_, qh_ = x[14], x[15]
    inv = [
        _ratio(hp2(LF_EXT_HZ(fl_), 0.707), hp2(fl_, ql_)),
        *[invert(s) for s in sm[1:5]],
        _ratio(lp2(HF_EXT_HZ, 0.707), lp2(fh_, qh_)),
    ]
    results["sm58_inverse_edges"] = {"lf_hz": LF_EXT_HZ(fl_), "hf_hz": HF_EXT_HZ}

    # --- verify complete linear chain in far field (no proximity), Ai, cardioid
    f, d = load("cardioid")
    f_sm, d_sm = load("sm58")
    sm_on_grid = np.interp(np.log10(f), np.log10(f_sm), d_sm)
    total = sm_on_grid + chain_db(inv + caps["cardioid"] + [fet["ai"]], f)
    m = (f > 60) & (f < 14000)
    print(f"chain check (SM58 curve -> U87 cardioid) 60 Hz-14 kHz max err "
          f"{np.max(np.abs(total[m] - d[m])):.2f} dB")

    (DATA / "fit.json").write_text(json.dumps(results, indent=2))
    write_rust(inv, caps, lowcut, fet)
    plots(inv, caps, lowcut, fet, sm)


def _ratio(new, old):
    """new / old as one section: numerator of new x denominator of old, etc."""
    nb0, nb1, nb2, na0, na1, na2 = new
    ob0, ob1, ob2, oa0, oa1, oa2 = old
    # new/old = (nb/na) * (oa/ob). Both are 2nd-order with identical
    # numerator shapes (hp: s^2, lp: const), so the numerators cancel up to
    # a constant and only (oa / na) remains.
    k = (nb0 / ob0) if ob0 else (nb2 / ob2)
    return (k * oa0, k * oa1, k * oa2, na0, na1, na2)


def write_rust(inv, caps, lowcut, fet):
    def arr(secs):
        rows = ",\n    ".join("[" + ", ".join(f"{v:.10e}" for v in s) + "]" for s in secs)
        return f"[\n    {rows},\n]"

    out = [
        "// @generated by tools/model.py - do not edit by hand.",
        "//",
        "// Analog prototypes H(s) = (b0 s^2 + b1 s + b2) / (a0 s^2 + a1 s + a2),",
        "// one row per section: [b0, b1, b2, a0, a1, a2]. s in rad/s.",
        "",
        "pub type Section = [f64; 6];",
        "",
        "/// Regularized inverse of the SM58 far-field response (Shure user guide).",
        f"pub const SM58_INVERSE: [Section; {len(inv)}] = {arr(inv)};",
        "",
    ]
    for pat, name in [("cardioid", "CARDIOID"), ("omni", "OMNI"), ("fig8", "FIG8")]:
        out.append(f"/// K87 capsule, {pat} (Neumann U 87 Ai curve / FET stage).")
        out.append(f"pub const CAPSULE_{name}: [Section; {len(caps[pat])}] = {arr(caps[pat])};")
        out.append("")
    out.append("/// Switchable low cut (two first-order sections).")
    out.append(f"pub const LOW_CUT: [Section; {len(lowcut)}] = {arr(lowcut)};")
    out.append("")
    out.append("/// FET stage with capsule feedback (C6 = 160 pF, C5 = 47 nF), unity @ 1 kHz.")
    out.append(f"pub const FET_AI: Section = {arr([fet['ai']])[1:-2].strip().rstrip(',')};")
    out.append("/// FET stage, 1967-86 values (C6 = 220 pF, C5 = 33 nF), unity @ 1 kHz.")
    out.append(f"pub const FET_VINTAGE: Section = {arr([fet['vintage']])[1:-2].strip().rstrip(',')};")
    (SRC / "coeffs.rs").write_text("\n".join(out) + "\n")


def plots(inv, caps, lowcut, fet, sm):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    f = np.geomspace(20, 20000, 600)
    fig, axs = plt.subplots(3, 1, figsize=(10, 12))

    ax = axs[0]
    fs_, ds_ = load("sm58")
    ax.semilogx(fs_, ds_, "k.", ms=3, label="SM58 (Shure, digitized)")
    ax.semilogx(f, chain_db(sm, f), label="SM58 fit")
    ax.semilogx(f, chain_db(inv, f), label="regularized inverse")
    ax.set_title("SM58 de-embedding")

    ax = axs[1]
    for pat in ["cardioid", "omni", "fig8"]:
        fp, dp = load(pat)
        line, = ax.semilogx(fp, dp, ".", ms=3, label=f"U 87 Ai {pat} (Neumann)")
        ax.semilogx(f, chain_db(caps[pat] + [fet["ai"]], f), color=line.get_color())
    fp, dp = load("cardioid_lowcut")
    ax.semilogx(fp, dp, "k.", ms=3, label="cardioid + low cut (Neumann)")
    ax.semilogx(f, chain_db(caps["cardioid"] + lowcut + [fet["ai"]], f), "k")
    ax.set_title("U 87 model (capsule x FET stage) vs published curves")

    ax = axs[2]
    ax.semilogx(f, chain_db([fet["ai"]], f), label="FET stage Ai (C6 160p, C5 47n)")
    ax.semilogx(f, chain_db([fet["vintage"]], f), label="FET stage vintage (C6 220p, C5 33n)")
    ax.set_title("FET stage with capsule feedback (circuit model)")

    for ax in axs:
        ax.set_xlim(20, 20000)
        ax.set_ylim(-20, 15)
        ax.grid(True, which="both", alpha=0.3)
        ax.legend(fontsize=8)
        ax.set_ylabel("dB")
    axs[-1].set_xlabel("Hz")
    fig.tight_layout()
    fig.savefig(DOCS / "model_fit.png", dpi=110)


if __name__ == "__main__":
    main()
