//! Editor: flat, dark, orange-accented device panel in the spirit of
//! Ableton Live's built-in devices. Everything is painted by hand on egui.
//!
//! The graph shows the linear SM58 -> U 87 correction for the current
//! settings, evaluated from the same analog prototypes the DSP uses.

use crate::coeffs::{self, Section};
use crate::{Pattern, Shu87Params, Shu87ParamsParamId as P, Version, dsp, subsonic};
use egui::{Align2, Color32, CornerRadius, FontId, Pos2, Rect, Sense, Stroke, StrokeKind, pos2, vec2};
use std::f64::consts::PI;
use truce_core::editor::{PluginContext, PluginContextReadF32};
use truce_params::{FloatParamReadF64, Params};

pub const WINDOW: (u32, u32) = (680, 330);

const BG: Color32 = Color32::from_rgb(0x18, 0x18, 0x18);
const PANEL: Color32 = Color32::from_rgb(0x26, 0x26, 0x26);
const SUNKEN: Color32 = Color32::from_rgb(0x1d, 0x1d, 0x1d);
const LINE: Color32 = Color32::from_rgb(0x3a, 0x3a, 0x3a);
const GRID: Color32 = Color32::from_rgb(0x2c, 0x2c, 0x2c);
const TEXT: Color32 = Color32::from_rgb(0xd2, 0xd2, 0xd2);
const DIM: Color32 = Color32::from_rgb(0x8c, 0x8c, 0x8c);
const ACCENT: Color32 = Color32::from_rgb(0xff, 0x9f, 0x1a);
const ON_ACCENT: Color32 = Color32::from_rgb(0x14, 0x14, 0x14);
const RADIUS: u8 = 3;

fn font(size: f32) -> FontId {
    FontId::proportional(size)
}

// ------------------------------------------------------------- the editor

pub fn draw(ui: &mut egui::Ui, state: &PluginContext<Shu87Params>) {
    let full = ui.max_rect();
    let painter = ui.painter().clone();
    painter.rect_filled(full, 0.0, BG);

    // Header strip
    let header = Rect::from_min_size(full.min, vec2(full.width(), 30.0));
    painter.text(pos2(header.left() + 14.0, header.center().y), Align2::LEFT_CENTER, "SHU87", font(15.0), TEXT);
    titled_arrow(&painter, pos2(header.left() + 72.0, header.center().y + 1.0), "SM58", "U 87", font(11.0), DIM);
    painter.text(
        pos2(header.right() - 14.0, header.center().y + 1.0),
        Align2::RIGHT_CENTER,
        "JARDIM SONORO",
        font(10.0),
        DIM,
    );

    // Device panel
    let body = Rect::from_min_max(pos2(full.left() + 8.0, header.bottom()), pos2(full.right() - 8.0, full.bottom() - 8.0));
    painter.rect_filled(body, CornerRadius::same(RADIUS + 1), PANEL);

    let graph = Rect::from_min_size(body.min + vec2(12.0, 12.0), vec2(370.0, body.height() - 24.0));
    draw_graph(&painter, graph, state.params());

    // Controls column
    let x0 = graph.right() + 18.0;
    let w = body.right() - 12.0 - x0;
    let mut y = body.top() + 12.0;

    caption(&painter, pos2(x0, y), "PATTERN");
    y += 14.0;
    segmented(ui, state, P::Pattern, &["Cardioid", "Omni", "Figure-8"], Rect::from_min_size(pos2(x0, y), vec2(w, 22.0)));
    y += 32.0;

    caption(&painter, pos2(x0, y), "VERSION");
    y += 14.0;
    segmented(ui, state, P::Version, &["U 87 Ai", "U 87 i  ’67–86"], Rect::from_min_size(pos2(x0, y), vec2(w, 22.0)));
    y += 34.0;

    let half = (w - 8.0) / 2.0;
    toggle_button(ui, state, P::LowCut, "Low Cut", Rect::from_min_size(pos2(x0, y), vec2(half, 22.0)));
    toggle_button(ui, state, P::Pad, "Pad −10 dB", Rect::from_min_size(pos2(x0 + half + 8.0, y), vec2(half, 22.0)));
    y += 36.0;

    let kw = w / 4.0;
    for (i, (id, label)) in [(P::Sm58Dist, "SM58 cm"), (P::U87Dist, "U87 cm"), (P::Drive, "Drive"), (P::Output, "Output")]
        .into_iter()
        .enumerate()
    {
        knob(ui, state, id, label, Rect::from_min_size(pos2(x0 + kw * i as f32, y), vec2(kw, 78.0)));
    }
    painter.line_segment(
        [pos2(x0 + kw * 2.0, y + 8.0), pos2(x0 + kw * 2.0, y + 66.0)],
        Stroke::new(1.0_f32, LINE),
    );

    painter.text(
        pos2(x0, graph.bottom()),
        Align2::LEFT_BOTTOM,
        "Double-click: reset   ·   Shift + drag: fine",
        font(9.5),
        DIM,
    );
}

/// "LEFT -> RIGHT" with a painted arrow (the embedded font has no U+2192).
fn titled_arrow(painter: &egui::Painter, at: Pos2, left: &str, right: &str, f: FontId, color: Color32) {
    let r = painter.text(at, Align2::LEFT_CENTER, left, f.clone(), color);
    let (x0, x1, y) = (r.right() + 6.0, r.right() + 18.0, at.y);
    let s = Stroke::new(1.2_f32, color);
    painter.line_segment([pos2(x0, y), pos2(x1, y)], s);
    painter.line_segment([pos2(x1 - 4.0, y - 3.5), pos2(x1, y)], s);
    painter.line_segment([pos2(x1 - 4.0, y + 3.5), pos2(x1, y)], s);
    painter.text(pos2(x1 + 6.0, y), Align2::LEFT_CENTER, right, f, color);
}

fn caption(painter: &egui::Painter, at: Pos2, text: &str) {
    painter.text(at, Align2::LEFT_TOP, text, font(9.5), DIM);
}

// ------------------------------------------------------------- widgets

fn info(state: &PluginContext<Shu87Params>, id: u32) -> Option<truce_params::ParamInfo> {
    state.params().param_infos().into_iter().find(|i| i.id == id)
}

/// Row of mutually exclusive buttons bound to an enum parameter.
fn segmented(ui: &mut egui::Ui, state: &PluginContext<Shu87Params>, id: P, labels: &[&str], rect: Rect) {
    let id: u32 = id.into();
    let n = labels.len();
    let current = (state.get_param(id) * (n - 1) as f32).round() as usize;
    let seg_w = rect.width() / n as f32;
    let painter = ui.painter();
    painter.rect_filled(rect, CornerRadius::same(RADIUS), SUNKEN);
    for (i, label) in labels.iter().enumerate() {
        let r = Rect::from_min_size(pos2(rect.left() + seg_w * i as f32, rect.top()), vec2(seg_w, rect.height()));
        let resp = ui.interact(r, ui.make_persistent_id(("seg", id, i)), Sense::click());
        if resp.clicked() && i != current {
            state.automate(id, i as f64 / (n - 1) as f64);
        }
        let selected = i == current;
        let r_in = r.shrink(1.0);
        if selected {
            painter.rect_filled(r_in, CornerRadius::same(RADIUS - 1), ACCENT);
        } else if resp.hovered() {
            painter.rect_filled(r_in, CornerRadius::same(RADIUS - 1), LINE);
        }
        painter.text(r.center(), Align2::CENTER_CENTER, *label, font(11.0), if selected { ON_ACCENT } else { TEXT });
    }
    painter.rect_stroke(rect, CornerRadius::same(RADIUS), Stroke::new(1.0_f32, LINE), StrokeKind::Inside);
}

/// Rectangular on/off button bound to a bool parameter.
fn toggle_button(ui: &mut egui::Ui, state: &PluginContext<Shu87Params>, id: P, label: &str, rect: Rect) {
    let id: u32 = id.into();
    let on = state.get_param(id) > 0.5;
    let resp = ui.interact(rect, ui.make_persistent_id(("tog", id)), Sense::click());
    if resp.clicked() {
        state.automate(id, if on { 0.0 } else { 1.0 });
    }
    let painter = ui.painter();
    let fill = if on { ACCENT } else if resp.hovered() { LINE } else { SUNKEN };
    painter.rect_filled(rect, CornerRadius::same(RADIUS), fill);
    painter.rect_stroke(rect, CornerRadius::same(RADIUS), Stroke::new(1.0_f32, if on { ACCENT } else { LINE }), StrokeKind::Inside);
    painter.text(rect.center(), Align2::CENTER_CENTER, label, font(11.0), if on { ON_ACCENT } else { TEXT });
}

/// Small flat knob: label above, thin 270° arc, value below.
/// Drag vertically (Shift = fine), double-click resets to default.
fn knob(ui: &mut egui::Ui, state: &PluginContext<Shu87Params>, id: P, label: &str, rect: Rect) {
    let id: u32 = id.into();
    let resp = ui.interact(rect, ui.make_persistent_id(("knob", id)), Sense::click_and_drag());
    let mut v = state.get_param(id);
    if resp.double_clicked() {
        if let Some(i) = info(state, id) {
            state.automate(id, i.range.normalize(i.default_plain));
        }
    } else {
        if resp.drag_started() {
            state.begin_edit(id);
        }
        if resp.dragged() {
            let fine = ui.input(|i| i.modifiers.shift);
            let delta = -resp.drag_delta().y / if fine { 600.0 } else { 160.0 };
            v = (v + delta).clamp(0.0, 1.0);
            state.set_param(id, f64::from(v));
        }
        if resp.drag_stopped() {
            state.end_edit(id);
        }
    }

    let painter = ui.painter();
    let active = resp.hovered() || resp.dragged();
    painter.text(pos2(rect.center().x, rect.top()), Align2::CENTER_TOP, label, font(10.0), if active { TEXT } else { DIM });
    let c = pos2(rect.center().x, rect.top() + 36.0);
    let r = 15.0;
    let start = 0.75 * std::f32::consts::PI;
    let sweep = 1.5 * std::f32::consts::PI;
    painter.add(egui::Shape::line(arc(c, r, start, sweep), Stroke::new(3.0_f32, LINE)));
    if v > 0.002 {
        painter.add(egui::Shape::line(arc(c, r, start, sweep * v), Stroke::new(3.0_f32, ACCENT)));
    }
    let a = start + sweep * v;
    painter.line_segment(
        [c + vec2(a.cos(), a.sin()) * (r - 7.0), c + vec2(a.cos(), a.sin()) * (r + 1.0)],
        Stroke::new(2.0_f32, TEXT),
    );
    painter.text(pos2(c.x, c.y + r + 6.0), Align2::CENTER_TOP, state.format_param(id), font(10.5), TEXT);
}

fn arc(c: Pos2, r: f32, start: f32, sweep: f32) -> Vec<Pos2> {
    let n = ((sweep.abs() / std::f32::consts::TAU) * 64.0).ceil().max(2.0) as usize;
    (0..=n)
        .map(|i| {
            let a = start + sweep * i as f32 / n as f32;
            c + vec2(a.cos(), a.sin()) * r
        })
        .collect()
}

// ------------------------------------------------------------- graph

const F_MIN: f64 = 20.0;
const F_MAX: f64 = 20_000.0;
const DB_RANGE: f64 = 15.0;

fn draw_graph(painter: &egui::Painter, rect: Rect, p: &Shu87Params) {
    painter.rect_filled(rect, CornerRadius::same(RADIUS), SUNKEN);
    let x_of = |f: f64| rect.left() + rect.width() * ((f / F_MIN).log10() / (F_MAX / F_MIN).log10()) as f32;
    let y_of = |db: f64| rect.center().y - (rect.height() / 2.0 - 8.0) * (db / DB_RANGE).clamp(-1.1, 1.1) as f32;

    for (f, label) in [(100.0, "100"), (1000.0, "1k"), (10_000.0, "10k")] {
        let x = x_of(f);
        painter.line_segment([pos2(x, rect.top()), pos2(x, rect.bottom())], Stroke::new(1.0_f32, GRID));
        painter.text(pos2(x + 3.0, rect.bottom() - 3.0), Align2::LEFT_BOTTOM, label, font(9.0), DIM);
    }
    for f in [50.0, 200.0, 500.0, 2000.0, 5000.0] {
        let x = x_of(f);
        painter.line_segment([pos2(x, rect.top() + 4.0), pos2(x, rect.bottom() - 4.0)], Stroke::new(0.5_f32, GRID));
    }
    for db in [-12.0, -6.0, 6.0, 12.0] {
        let y = y_of(db);
        painter.line_segment([pos2(rect.left(), y), pos2(rect.right(), y)], Stroke::new(0.5_f32, GRID));
        painter.text(pos2(rect.left() + 3.0, y - 1.0), Align2::LEFT_BOTTOM, format!("{db:+.0}"), font(9.0), DIM);
    }
    let y0 = y_of(0.0);
    painter.line_segment([pos2(rect.left(), y0), pos2(rect.right(), y0)], Stroke::new(1.0_f32, LINE));

    let secs = sections(p);
    let n = 220;
    let pts: Vec<Pos2> = (0..=n)
        .map(|i| {
            let f = F_MIN * (F_MAX / F_MIN).powf(i as f64 / n as f64);
            pos2(x_of(f), y_of(chain_db(&secs, f)))
        })
        .collect();
    // Translucent fill between the curve and 0 dB, Live EQ style.
    let fill = Color32::from_rgba_unmultiplied(0xff, 0x9f, 0x1a, 28);
    for w in pts.windows(2) {
        let quad = vec![w[0], w[1], pos2(w[1].x, y0), pos2(w[0].x, y0)];
        painter.add(egui::Shape::convex_polygon(quad, fill, Stroke::NONE));
    }
    painter.add(egui::Shape::line(pts, Stroke::new(1.8_f32, ACCENT)));
    titled_arrow(painter, rect.left_top() + vec2(8.0, 12.0), "SM58", "U 87 CORRECTION", font(9.5), DIM);
    painter.rect_stroke(rect, CornerRadius::same(RADIUS), Stroke::new(1.0_f32, LINE), StrokeKind::Inside);
}

/// The linear part of the chain for the current settings (same analog
/// prototypes the DSP discretizes).
fn sections(p: &Shu87Params) -> Vec<Section> {
    let pattern = p.pattern.value();
    let mut s: Vec<Section> = vec![subsonic()];
    s.extend_from_slice(&coeffs::SM58_INVERSE);
    let g = match pattern {
        Pattern::Omni => 0.0,
        Pattern::Cardioid => 0.5,
        Pattern::Figure8 => 1.0,
    };
    s.push(dsp::proximity_section(
        0.5,
        p.sm58_dist.value() / 100.0 + crate::SM58_GRILLE_M,
        g,
        p.u87_dist.value() / 100.0 + crate::U87_GRILLE_M,
    ));
    s.extend_from_slice(match pattern {
        Pattern::Cardioid => &coeffs::CAPSULE_CARDIOID,
        Pattern::Omni => &coeffs::CAPSULE_OMNI,
        Pattern::Figure8 => &coeffs::CAPSULE_FIG8,
    });
    if p.low_cut.value() {
        s.extend_from_slice(&coeffs::LOW_CUT);
    }
    s.push(match p.version.value() {
        Version::Ai => coeffs::FET_AI,
        Version::Vintage => coeffs::FET_VINTAGE,
    });
    s
}

fn chain_db(secs: &[Section], f: f64) -> f64 {
    let w = 2.0 * PI * f;
    let mut re = 1.0;
    let mut im = 0.0;
    for &[b0, b1, b2, a0, a1, a2] in secs {
        // (b2 - b0 w^2 + j b1 w) / (a2 - a0 w^2 + j a1 w)
        let (nr, ni) = (b2 - b0 * w * w, b1 * w);
        let (dr, di) = (a2 - a0 * w * w, a1 * w);
        let den = dr * dr + di * di;
        let (hr, hi) = ((nr * dr + ni * di) / den, (ni * dr - nr * di) / den);
        let (r2, i2) = (re * hr - im * hi, re * hi + im * hr);
        re = r2;
        im = i2;
    }
    10.0 * (re * re + im * im).max(1e-20).log10()
}
