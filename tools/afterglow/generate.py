#!/usr/bin/env python3
"""Generate the menu afterglow curve: a button cooling like a black body.

Temperature falls exponentially (Newton's law of cooling):

    T(t) = T_ambient + (T_hot - T_ambient) * exp(-t / tau)

The colour at each temperature comes from blackbody_2deg.csv, interpolated with a
monotone cubic so no overshoot or kinks appear between the 100 K table rows. Below
the table's 1000 K limit the trend is extrapolated. Brightness follows the logarithm
of the table's power column, because the eye responds roughly to log intensity.

Browsers cannot evaluate this at runtime, so the curve is sampled and written out as
CSS linear() easing functions, one per colour channel.

Usage:  python3 tools/afterglow/generate.py
Writes: assets/scss/components/_afterglow-curve.scss
"""
import csv
import math
from pathlib import Path

# --- Tunable values ----------------------------------------------------------
COOL_MS = 500          # sets the cooling rate: T reaches T_DRAPER at this time
DURATION_MS = 800      # total length, including the fading tail
TAIL_START_MS = 400    # from here brightness decays exponentially instead of hitting zero
SAMPLES = 97           # curve points: 8.3 ms apart, one per 120 Hz frame
T_AMBIENT = 293.0      # K, room temperature the button cools towards
T_DRAPER = 798.0       # K, Draper point: where a hot body starts to glow visibly
HOT_RGB = (255, 224, 138)   # $arc-gold, the lit button colour
# -----------------------------------------------------------------------------

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
OUTPUT = ROOT / "assets/scss/components/_afterglow-curve.scss"
VARIABLES = ROOT / "assets/scss/_bootstrap-variables.scss"


def load_table():
    with open(HERE / "blackbody_2deg.csv") as f:
        rows = csv.DictReader(line for line in f if not line.startswith("#"))
        return [
            (float(r["K"]), float(r["P"]), float(r["R"]), float(r["G"]), float(r["B"]))
            for r in rows
        ]


class MonotoneCubic:
    """Fritsch-Carlson interpolation: passes through every point, never overshoots."""

    def __init__(self, xs, ys):
        self.xs, self.ys = xs, ys
        n = len(xs)
        d = [(ys[i + 1] - ys[i]) / (xs[i + 1] - xs[i]) for i in range(n - 1)]
        m = [d[0]] + [
            0.0 if d[i - 1] * d[i] <= 0 else (d[i - 1] + d[i]) / 2 for i in range(1, n - 1)
        ] + [d[-1]]
        for i in range(n - 1):
            if d[i] == 0:
                m[i] = m[i + 1] = 0.0
                continue
            a, b = m[i] / d[i], m[i + 1] / d[i]
            s = a * a + b * b
            if s > 9:
                k = 3 / math.sqrt(s)
                m[i], m[i + 1] = k * a * d[i], k * b * d[i]
        self.m = m

    def __call__(self, x):
        xs, ys, m = self.xs, self.ys, self.m
        lo, hi = 0, len(xs) - 1
        while hi - lo > 1:
            mid = (lo + hi) // 2
            lo, hi = (mid, hi) if x >= xs[mid] else (lo, mid)
        h = xs[hi] - xs[lo]
        u = (x - xs[lo]) / h
        return (
            (2 * u**3 - 3 * u**2 + 1) * ys[lo]
            + (u**3 - 2 * u**2 + u) * h * m[lo]
            + (-2 * u**3 + 3 * u**2) * ys[hi]
            + (u**3 - u**2) * h * m[hi]
        )


def to_linear(c):
    c /= 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def to_srgb(v):
    v = max(0.0, min(1.0, v))
    return 255 * (12.92 * v if v <= 0.0031308 else 1.055 * v ** (1 / 2.4) - 0.055)


def lab(rgb):
    """CIE Lab (D65) of an 8-bit sRGB colour, used only to measure colour steps."""
    r, g, b = (to_linear(c) for c in rgb)
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883
    f = lambda t: t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116
    return 116 * f(y) - 16, 500 * (f(x) - f(y)), 200 * (f(y) - f(z))


def delta_e(c1, c2):
    return math.dist(lab(c1), lab(c2))


def build_colour_model():
    table = load_table()
    temps = [row[0] for row in table]
    spline = [MonotoneCubic(temps, [row[i] for row in table]) for i in (2, 3, 4)]
    # ln P is nearly straight against 1/T (Wien's law), so interpolate it that way
    inv = [1 / t for t in reversed(temps)]
    log_p = [math.log(row[1]) for row in reversed(table)]
    power = MonotoneCubic(inv, log_p)

    t0, t1 = temps[0], temps[1]
    g0, g1 = table[0][3], table[1][3]
    g_slope = math.log(g1 / g0) / (1 / t1 - 1 / t0)
    p_slope = (log_p[-1] - log_p[-2]) / (inv[-1] - inv[-2])

    def linear_rgb(t):
        if t >= t0:
            return tuple(s(t) for s in spline)
        return (1.0, g0 * math.exp(g_slope * (1 / t - 1 / t0)), 0.0)

    def ln_power(t):
        if t >= t0:
            return power(1 / t)
        return log_p[-1] + p_slope * (1 / t - 1 / t0)

    return temps, linear_rgb, ln_power


def main():
    text = VARIABLES.read_text()
    hex_value = text.split("$graphite-neel:")[1].split(";")[0].strip()
    bg = tuple(int(hex_value[i : i + 2], 16) for i in (1, 3, 5))

    temps, linear_rgb, ln_power = build_colour_model()
    hot_linear = tuple(to_linear(c) for c in HOT_RGB)

    # The brand gold sits just off the black-body line: start at the nearest temperature
    t_hot = min(
        (t for t in range(1000, 6001, 10)),
        key=lambda t: delta_e(HOT_RGB, tuple(to_srgb(v) for v in linear_rgb(t))),
    )
    tau = COOL_MS / math.log((t_hot - T_AMBIENT) / (T_DRAPER - T_AMBIENT))

    lp_hot, lp_draper = ln_power(t_hot), ln_power(T_DRAPER)

    def temperature(ms):
        return T_AMBIENT + (t_hot - T_AMBIENT) * math.exp(-ms / tau)

    def level(ms):
        return (ln_power(temperature(ms)) - lp_draper) / (lp_hot - lp_draper)

    # Tail: an exponential that continues the curve with the same value and slope, so
    # there is no visible join. A tiny ramp lands it on exactly zero at the end.
    tail_level = level(TAIL_START_MS)
    tail_slope = (level(TAIL_START_MS + 0.5) - level(TAIL_START_MS - 0.5))
    tail_tau = tail_level / -tail_slope
    tail_span = DURATION_MS - TAIL_START_MS
    tail_end = tail_level * math.exp(-tail_span / tail_tau)

    def state(ms):
        temp = temperature(ms)
        # Fade the small gold offset out quickly, so the path starts exactly on brand
        weight = math.exp(-ms / (tau / 3))
        body = linear_rgb(temp)
        rgb = tuple(
            to_srgb(weight * h + (1 - weight) * b) for h, b in zip(hot_linear, body)
        )
        if ms <= TAIL_START_MS:
            alpha = level(ms)
        else:
            into = ms - TAIL_START_MS
            alpha = tail_level * math.exp(-into / tail_tau) - tail_end * into / tail_span
        return temp, rgb, alpha

    # End exactly at the resting value: off, at the colour of the coolest glow
    rest = state(DURATION_MS)[1]
    times = [DURATION_MS * i / (SAMPLES - 1) for i in range(SAMPLES)]
    points = [state(t) for t in times]

    def easing(values, start, end):
        span = end - start
        stops = [0.0 if span == 0 else (v - start) / span for v in values]
        stops[0], stops[-1] = 0.0, 1.0
        return "linear(" + ", ".join(f"{s:.4f}".rstrip("0").rstrip(".") or "0" for s in stops) + ")"

    ease_g = easing([p[1][1] for p in points], HOT_RGB[1], rest[1])
    ease_b = easing([p[1][2] for p in points], HOT_RGB[2], rest[2])
    ease_a = easing([p[2] for p in points], 1.0, 0.0)

    OUTPUT.write_text(
        "// GENERATED by tools/afterglow/generate.py. Do not edit by hand.\n"
        f"// Cooling from {t_hot} K over {DURATION_MS} ms, tau = {tau:.1f} ms, brightness tail"
        f" from {TAIL_START_MS} ms with tau = {tail_tau:.1f} ms, {SAMPLES} samples.\n"
        f"$afterglow-duration: {DURATION_MS}ms;\n"
        f"$afterglow-rest-r: {rest[0]:.2f};\n"
        f"$afterglow-rest-g: {rest[1]:.2f};\n"
        f"$afterglow-rest-b: {rest[2]:.2f};\n"
        f'$afterglow-ease-g: "{ease_g}";\n'
        f'$afterglow-ease-b: "{ease_b}";\n'
        f'$afterglow-ease-a: "{ease_a}";\n'
    )

    # Report: what the eye gets, frame by frame, over the real header colour
    def shown(ms):
        _, rgb, alpha = state(ms)
        return tuple(alpha * c + (1 - alpha) * b for c, b in zip(rgb, bg))

    print(f"Hot temperature {t_hot} K, tau {tau:.1f} ms, background {hex_value}")
    print(f"Brightness tail from {TAIL_START_MS} ms, tau {tail_tau:.1f} ms, residual at end {tail_end:.4f}")
    print(f"Rest channels r,g,b = {rest[0]:.1f}, {rest[1]:.1f}, {rest[2]:.1f}")
    print(f"Gold vs nearest black body: dE = {delta_e(HOT_RGB, tuple(to_srgb(v) for v in linear_rgb(t_hot))):.1f}")
    print("\n  ms      T(K)    rgb                 alpha")
    for ms in range(0, DURATION_MS + 1, 50):
        t, rgb, a = state(ms)
        print(f"{ms:4d}  {t:8.0f}    {rgb[0]:3.0f} {rgb[1]:5.1f} {rgb[2]:5.1f}     {a:.3f}")

    for hz in (60, 120):
        n = int(DURATION_MS * hz / 1000)
        steps = [
            delta_e(shown(i * 1000 / hz), shown((i + 1) * 1000 / hz)) for i in range(n)
        ]
        print(f"{hz:3d} Hz: {n} frames, colour step per frame max dE {max(steps):.2f}, mean {sum(steps) / n:.2f}")

    # How far the 65-point linear() curve strays from the true curve
    worst = 0.0
    for i in range(SAMPLES - 1):
        mid = (times[i] + times[i + 1]) / 2
        _, rgb, a = state(mid)
        approx = tuple((p + q) / 2 for p, q in zip(points[i][1], points[i + 1][1]))
        worst = max(worst, *(abs(u - v) for u, v in zip(rgb, approx)),
                    abs(a - (points[i][2] + points[i + 1][2]) / 2) * 255)
    print(f"Largest error of the sampled curve: {worst:.2f} of 255")
    print("Last frames on screen at 60 Hz (the part that looked abrupt):")
    for i in range(int(DURATION_MS * 60 / 1000) - 6, int(DURATION_MS * 60 / 1000)):
        a, b = shown(i * 1000 / 60), shown((i + 1) * 1000 / 60)
        print(f"  {i * 1000 / 60:5.0f} ms  shown {a[0]:5.1f} {a[1]:5.1f} {a[2]:5.1f}  step dE {delta_e(a, b):.3f}")
    print(f"Wrote {OUTPUT.relative_to(ROOT)} ({OUTPUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
