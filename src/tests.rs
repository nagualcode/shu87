use super::*;
use std::f64::consts::PI;
use std::time::Duration;

const FS2: f64 = 96_000.0;

/// Steady-state gain (dB) of a linear-ish chain at `f`, small signal.
fn chain_gain_db(chain: &mut Chain, f: f64) -> f64 {
    chain.reset();
    let amp = 0.01;
    let n = (FS2 * 0.6) as usize;
    let (mut re, mut im, mut m) = (0.0, 0.0, 0usize);
    for i in 0..n {
        let ph = 2.0 * PI * f * i as f64 / FS2;
        let y = chain.run(amp * ph.sin(), 1.0, 1.0);
        if i > n / 3 {
            re += y * ph.sin();
            im += y * ph.cos();
            m += 1;
        }
    }
    let a = 2.0 * (re * re + im * im).sqrt() / m as f64;
    20.0 * (a / amp).log10()
}

fn csv(text: &str) -> Vec<(f64, f64)> {
    text.lines()
        .skip(1)
        .filter_map(|l| {
            let mut it = l.split(',');
            Some((it.next()?.parse().ok()?, it.next()?.parse().ok()?))
        })
        .collect()
}

fn interp(pts: &[(f64, f64)], f: f64) -> f64 {
    let lf = f.log10();
    for w in pts.windows(2) {
        let (a, b) = (w[0].0.log10(), w[1].0.log10());
        if lf >= a && lf <= b {
            return w[0].1 + (w[1].1 - w[0].1) * (lf - a) / (b - a);
        }
    }
    f64::NAN
}

fn chain_for(pattern: Pattern, version: Version, sm58_cm: f64, u87_cm: f64) -> Chain {
    let mut c = Chain::default();
    c.configure(Discrete { pattern, version, low_cut: false }, FS2);
    c.set_proximity(sm58_cm, u87_cm, FS2);
    c
}

/// End to end: the Shure-published SM58 curve run through the plugin must
/// land on the Neumann-published U 87 Ai curve. Distances chosen so the
/// proximity re-map is neutral (equal effective distance, both cardioid).
#[test]
fn sm58_curve_maps_onto_u87_curve() {
    let sm58 = csv(include_str!("../research/data/sm58.csv"));
    for (pattern, data) in [
        (Pattern::Cardioid, include_str!("../research/data/cardioid.csv")),
        (Pattern::Omni, include_str!("../research/data/omni.csv")),
        (Pattern::Figure8, include_str!("../research/data/fig8.csv")),
    ] {
        let u87 = csv(data);
        let mut c = chain_for(pattern, Version::Ai, 100.0 * (2.0 - 0.015), 100.0 * (2.0 - 0.02));
        // At 2 m the proximity terms are negligible above ~100 Hz for any
        // pattern, so compare there.
        let r1k = interp(&sm58, 1000.0) + chain_gain_db(&mut c, 1000.0) - interp(&u87, 1000.0);
        let mut worst: f64 = 0.0;
        for f in [150.0, 300.0, 600.0, 1500.0, 3000.0, 4500.0, 6000.0, 8000.0, 10_000.0, 12_000.0] {
            let got = interp(&sm58, f) + chain_gain_db(&mut c, f) - r1k;
            let want = interp(&u87, f);
            worst = worst.max((got - want).abs());
        }
        assert!(worst < 2.0, "{pattern:?}: worst deviation {worst:.2} dB");
    }
}

#[test]
fn vintage_has_less_air_and_less_low_end_than_ai() {
    let mut ai = chain_for(Pattern::Cardioid, Version::Ai, 5.0, 20.0);
    let mut vt = chain_for(Pattern::Cardioid, Version::Vintage, 5.0, 20.0);
    let mut d = |f| chain_gain_db(&mut ai, f) - chain_gain_db(&mut vt, f);
    let hi = d(16_000.0);
    let lo = d(40.0);
    assert!(hi > 0.3 && hi < 2.0, "Ai-vintage @16k = {hi:.2}");
    assert!(lo > 0.2 && lo < 2.0, "Ai-vintage @40 Hz = {lo:.2}");
}

#[test]
fn close_sm58_gets_its_proximity_bass_removed() {
    // SM58 lips-on (2 cm) re-mapped to U 87 at 30 cm must cut the low end
    // relative to the mids by roughly the ideal cardioid proximity ratio.
    let mut close = chain_for(Pattern::Cardioid, Version::Ai, 2.0, 30.0);
    let mut far = chain_for(Pattern::Cardioid, Version::Ai, 28.5, 30.0);
    let cut = |c: &mut Chain| chain_gain_db(c, 100.0) - chain_gain_db(c, 2000.0);
    let delta = cut(&mut close) - cut(&mut far);
    assert!(delta < -8.0 && delta > -20.0, "proximity cut {delta:.2} dB");
}

#[test]
fn omni_has_no_proximity_lift() {
    // Omni U 87 at 10 cm vs at 100 cm: identical (pressure capsule).
    let mut a = chain_for(Pattern::Omni, Version::Ai, 5.0, 10.0);
    let mut b = chain_for(Pattern::Omni, Version::Ai, 5.0, 100.0);
    let d = chain_gain_db(&mut a, 80.0) - chain_gain_db(&mut b, 80.0);
    assert!(d.abs() < 0.05, "omni distance dependence {d:.3} dB");
}

#[test]
fn renders_clean_output() {
    use truce_test::{InputSource, assertions, driver};
    let result = driver!(Plugin)
        .duration(Duration::from_millis(200))
        .input(InputSource::Constant(0.25))
        .run();
    assertions::assert_no_nans(&result);
}

#[test]
fn switching_does_not_click() {
    // A 1 kHz tone while every switch is flipped; the sample-to-sample step
    // must stay within what the tone itself produces.
    use truce_test::{InputSource, driver};
    let result = driver!(Plugin)
        .duration(Duration::from_millis(600))
        .input(InputSource::Generator(Box::new(|i, sr| {
            (0.5 * (2.0 * PI * 1000.0 * i as f64 / sr).sin()) as f32
        })))
        .script(|s| {
            s.wait_ms(150);
            s.set_param(P::Pattern, 1.0);
            s.wait_ms(80);
            s.set_param(P::Version, 1.0);
            s.wait_ms(5);
            s.set_param(P::LowCut, 1.0);
            s.wait_ms(80);
            s.set_param(P::Pattern, 0.5);
            s.wait_ms(80);
            s.set_param(P::Sm58Dist, 0.0);
            s.wait_ms(80);
            s.set_param(P::U87Dist, 1.0);
        })
        .run();
    let out = &result.output[0];
    let skip = 9600; // settle
    let max_step = out[skip..]
        .windows(2)
        .map(|w| (w[1] - w[0]).abs())
        .fold(0.0f32, f32::max);
    // 1 kHz, amplitude <= ~0.6 at 48 kHz -> max step 2*pi*1000/48000*0.6 = 0.079
    assert!(max_step < 0.1, "max step {max_step}");
}

#[test]
fn process_is_allocation_free() {
    use truce_test::{InputSource, assert_no_audio_alloc, driver};
    assert_no_audio_alloc(|| {
        driver!(Plugin)
            .duration(Duration::from_millis(40))
            .input(InputSource::Constant(0.25))
            .script(|s| {
                s.set_param(P::Pattern, 1.0);
                s.wait_ms(15);
                s.set_param(P::Sm58Dist, 0.1);
            })
            .run()
    });
}

#[test]
fn info_is_valid() {
    truce_test::assert_valid_info::<Plugin>();
}

#[test]
fn state_round_trips() {
    truce_test::assert_state_round_trip::<Plugin>();
}

#[test]
fn au_type_codes_ascii() {
    truce_test::assert_au_type_codes_ascii::<Plugin>();
}

#[test]
fn bus_config_effect() {
    truce_test::assert_bus_config_effect::<Plugin>();
}

#[test]
fn param_defaults_match() {
    truce_test::assert_param_defaults_match::<Plugin>();
}

#[test]
fn has_editor() {
    truce_test::assert_has_editor::<Plugin>();
}
