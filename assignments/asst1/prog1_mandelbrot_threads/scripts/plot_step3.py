#!/usr/bin/env python3
"""Parse the Program 1 step-3 sweep and render SVG figures.

Reads only:
    results/step3/raw/t{T}_v{V}_r{R}.log

Writes:
    results/step3/summary_all.csv
    results/step3/summary_best.csv
    results/step3/thread_busy.csv
    results/step3/report.md
    results/step3/charts/*.svg

The step-3 program is the contiguous-block decomposition.  No interleaved
data is read here; the old results/*.txt files are ignored on purpose.

No third-party dependencies.
"""

import csv
import html
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROG = os.path.dirname(HERE)
RES = os.path.join(PROG, "results", "step3")
RAW = os.path.join(RES, "raw")
CHARTS = os.path.join(RES, "charts")

# ---- palette (reference instance, light surface) -------------------------
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
BLUE = "#2a78d6"      # categorical slot 1
ORANGE = "#eb6834"    # categorical slot 2
FONT = "system-ui, -apple-system, 'Segoe UI', Arial, sans-serif"

# ---- log parsing ---------------------------------------------------------
LOG_RE = re.compile(r"^t(\d+)_v(\d+)_r(\d+)\.log$")
SERIAL_RE = re.compile(r"\[mandelbrot serial\]:\s*\[([0-9.]+)\]\s*ms")
THREAD_RE = re.compile(r"\[mandelbrot thread\]:\s*\[([0-9.]+)\]\s*ms")
SPEEDUP_RE = re.compile(r"\(([0-9.]+)x speedup from (\d+) threads\)")
BUSY_RE = re.compile(
    r"\[thread\s+(\d+)\]\s+rows=\s*(\d+),\s*busy=\s*([0-9.]+)\s*ms")


def parse_log(path, nthreads):
    with open(path, encoding="utf-8", errors="replace") as f:
        text = f.read()

    m_serial = SERIAL_RE.search(text)
    m_thread = THREAD_RE.search(text)
    m_speed = SPEEDUP_RE.search(text)
    if not (m_serial and m_thread and m_speed):
        return None

    busy_all = [(int(tid), int(rows), float(ms))
                for tid, rows, ms in BUSY_RE.findall(text)]

    # Every worker prints once per internal repetition.  There are five
    # repetitions, so group the busy lines into chunks of nthreads.  A chunk
    # is complete only if every thread id appears exactly once.
    groups = []
    for i in range(0, len(busy_all) - nthreads + 1, nthreads):
        group = busy_all[i:i + nthreads]
        if len({row[0] for row in group}) == nthreads:
            groups.append(group)
    if not groups:
        return None

    # The reported wall time is the minimum of the five internal runs.  The
    # group whose slowest thread is fastest is the matching run.
    best_group = min(groups, key=lambda g: max(row[2] for row in g))
    best_group.sort(key=lambda row: row[0])

    max_busy = max(row[2] for row in best_group)
    mean_busy = sum(row[2] for row in best_group) / len(best_group)

    return {
        "serial_ms": float(m_serial.group(1)),
        "thread_ms": float(m_thread.group(1)),
        "speedup": float(m_speed.group(1)),
        "max_busy": max_busy,
        "mean_busy": mean_busy,
        "ratio": max_busy / mean_busy,
        "busy": best_group,
    }


def collect():
    if not os.path.isdir(RAW):
        sys.exit("raw log directory not found: %s" % RAW)

    rows = []
    best = {}
    for fn in sorted(os.listdir(RAW)):
        m = LOG_RE.match(fn)
        if not m:
            continue
        nthreads, view, rep = (int(x) for x in m.groups())
        parsed = parse_log(os.path.join(RAW, fn), nthreads)
        if parsed is None:
            print("warning: skipped unparsable log %s" % fn, file=sys.stderr)
            continue
        row = {"view": view, "threads": nthreads, "rep": rep}
        row.update(parsed)
        rows.append(row)
        key = (view, nthreads)
        if key not in best or row["thread_ms"] < best[key]["thread_ms"]:
            best[key] = row
    return rows, best


# ---- tiny SVG builder ----------------------------------------------------
class Svg:
    def __init__(self, width, height, label):
        self.width = width
        self.height = height
        self.parts = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
            'viewBox="0 0 %d %d" role="img" aria-label="%s">'
            % (width, height, width, height, html.escape(label)),
            '<rect width="%d" height="%d" fill="%s"/>'
            % (width, height, SURFACE),
        ]

    def add(self, raw):
        self.parts.append(raw)

    def line(self, x1, y1, x2, y2, stroke=AXIS, sw=1.0, dash=None,
             opacity=1.0):
        dash_attr = ' stroke-dasharray="%s"' % dash if dash else ""
        self.add(
            '<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f" stroke="%s" '
            'stroke-width="%.2f" opacity="%.2f"%s/>'
            % (x1, y1, x2, y2, stroke, sw, opacity, dash_attr))

    def path(self, d, fill="none", stroke="none", sw=1.0, title=None):
        inner = "<title>%s</title>" % html.escape(title) if title else ""
        self.add(
            '<path d="%s" fill="%s" stroke="%s" stroke-width="%.2f">%s</path>'
            % (d, fill, stroke, sw, inner))

    def circle(self, cx, cy, r, fill, stroke=SURFACE, sw=2.0, title=None):
        inner = "<title>%s</title>" % html.escape(title) if title else ""
        self.add(
            '<circle cx="%.2f" cy="%.2f" r="%.2f" fill="%s" stroke="%s" '
            'stroke-width="%.2f">%s</circle>'
            % (cx, cy, r, fill, stroke, sw, inner))

    def polyline(self, points, stroke, sw=2.0, dash=None):
        dash_attr = ' stroke-dasharray="%s"' % dash if dash else ""
        pts = " ".join("%.2f,%.2f" % (x, y) for x, y in points)
        self.add(
            '<polyline points="%s" fill="none" stroke="%s" '
            'stroke-width="%.2f" stroke-linejoin="round" '
            'stroke-linecap="round"%s/>' % (pts, stroke, sw, dash_attr))

    def text(self, x, y, value, size=11, fill=INK, anchor="start",
             weight="normal", rotate=None, tabular=False, opacity=1.0):
        transform = ""
        if rotate is not None:
            transform = ' transform="rotate(%.1f %.2f %.2f)"' % (
                rotate, x, y)
        tab = ' style="font-variant-numeric: tabular-nums"' if tabular else ""
        self.add(
            '<text x="%.2f" y="%.2f" font-family="%s" font-size="%.2f" '
            'fill="%s" font-weight="%s" text-anchor="%s" opacity="%.2f"%s%s>'
            '%s</text>'
            % (x, y, FONT, size, fill, weight, anchor, opacity, transform,
               tab, html.escape(str(value))))

    def save(self, path):
        self.parts.append("</svg>")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(self.parts))


def nice_step(value):
    """Smallest 'nice' step >= value (1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10)."""
    if value <= 0:
        return 1.0
    exponent = math.floor(math.log10(value))
    base = 10.0 ** exponent
    for mult in (1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10):
        if value <= mult * base:
            return mult * base
    return 10 * base


def rounded_top_bar(x, y_top, width, height, radius=3.0):
    if height <= 0 or width <= 0:
        return ""
    radius = min(radius, width / 2.0, height)
    bottom = y_top + height
    return (
        "M %.2f %.2f L %.2f %.2f Q %.2f %.2f %.2f %.2f "
        "L %.2f %.2f Q %.2f %.2f %.2f %.2f L %.2f %.2f Z"
        % (x, bottom,
           x, y_top + radius,
           x, y_top, x + radius, y_top,
           x + width - radius, y_top,
           x + width, y_top, x + width, y_top + radius,
           x + width, bottom))


# ---- figures -------------------------------------------------------------
MACHINE = ("Intel Core Ultra 9 285H · 6 P-cores + 8 E-cores + "
           "2 LP E-cores = 16 logical CPUs")
METHOD = "fastest of 5 runs per process, best of 3 processes"


def speedup_panel(svg, ox, oy, panel_w, panel_h, title, points,
                  y_top, first, x_ticks):
    x0, y0 = ox + 70, oy + 40
    pw, ph = panel_w - 70 - 24, panel_h - 40 - 60
    y_bottom = y0 + ph

    def sx(t):
        return x0 + (t - 1.0) / (24.0 - 1.0) * pw

    def sy(v):
        return y_bottom - v / y_top * ph

    svg.text(ox, oy + 22, title, size=15, weight="bold")

    # grid + y ticks
    for tick in range(0, int(y_top) + 1, 4):
        yy = sy(tick)
        svg.line(x0, yy, x0 + pw, yy, GRID, 1.0)
        svg.text(x0 - 8, yy + 4, tick, size=10, fill=MUTED,
                 anchor="end", tabular=True)

    # axes
    svg.line(x0, y0, x0, y_bottom, AXIS, 1.0)
    svg.line(x0, y_bottom, x0 + pw, y_bottom, AXIS, 1.0)

    # x ticks
    for t in x_ticks:
        svg.text(sx(t), y_bottom + 18, t, size=10, fill=MUTED,
                 anchor="middle", tabular=True)

    # reference lines at P-core and logical-CPU counts
    for ref, label in ((6, "6 P-cores"), (16, "16 logical CPUs")):
        xx = sx(ref)
        svg.line(xx, y0, xx, y_bottom, MUTED, 1.0, dash="4 5", opacity=0.7)
        svg.text(xx, y0 + 14, label, size=9, fill=MUTED, anchor="middle")

    # ideal y = x
    svg.line(sx(1), sy(1), sx(24), sy(24), MUTED, 1.5, dash="5 5")
    svg.text(sx(18) - 6, sy(18) - 8, "ideal linear (y = x)", size=10,
             fill=MUTED, anchor="end")

    # measured series
    coords = [(sx(t), sy(v)) for t, v in points]
    svg.polyline(coords, BLUE, 2.2)
    for (t, v), (cx, cy) in zip(points, coords):
        svg.circle(cx, cy, 4.5, BLUE,
                   title="%d threads: %.2fx" % (t, v))

    # selective direct label on the last point
    t_last, v_last = points[-1]
    cx, cy = coords[-1]
    svg.text(cx - 10, cy - 12, "%.2f×" % v_last, size=11,
             weight="bold", anchor="end")

    if first:
        svg.text(ox + 18, y0 + ph / 2.0, "Speedup vs. serial", size=11,
                 fill=INK2, anchor="middle", rotate=-90)
    svg.text(x0 + pw / 2.0, oy + panel_h - 12, "Number of threads",
             size=11, fill=INK2, anchor="middle")


def render_speedup(panels, path, panel_w, title, subtitle1, subtitle2):
    panel_h = 430
    gap = 36
    n = len(panels)
    width = 40 + n * panel_w + (n - 1) * gap + 40
    height = 100 + panel_h + 54

    svg = Svg(width, height, title)
    svg.text(40, 34, title, size=20, weight="bold")
    svg.text(40, 56, subtitle1, size=11, fill=INK2)
    svg.text(40, 74, subtitle2, size=10, fill=MUTED)

    x_ticks = sorted({t for p in panels for t, _ in p["points"]})
    for i, panel in enumerate(panels):
        speedup_panel(
            svg,
            40 + i * (panel_w + gap), 96,
            panel_w, panel_h,
            panel["title"], panel["points"],
            24, i == 0, x_ticks)

    svg.text(width / 2.0, height - 18,
             "Source: results/step3 — %s." % METHOD,
             size=10, fill=MUTED, anchor="middle")
    svg.save(path)


def render_busy(view, path, best, thread_counts):
    panels = [t for t in thread_counts if (view, t) in best]
    if not panels:
        return False

    panel_w, panel_h = 480, 250
    gap_x, gap_y = 28, 24
    cols = 2
    rows = int(math.ceil(len(panels) / float(cols)))
    width = 40 + cols * panel_w + (cols - 1) * gap_x + 40
    height = 104 + rows * panel_h + (rows - 1) * gap_y + 44

    title = "Per-thread busy time — contiguous blocks — View %d" % view
    svg = Svg(width, height, title)
    svg.text(40, 34, title, size=20, weight="bold")
    svg.text(40, 56,
             "Each bar is the time one thread spends computing its row band.",
             size=11, fill=INK2)
    svg.text(40, 74,
             "Wall time is bounded below by the tallest bar; shorter bars "
             "are idle capacity. " + METHOD.capitalize() + ".",
             size=10, fill=MUTED)

    for idx, nthreads in enumerate(panels):
        row = best[(view, nthreads)]
        ox = 40 + (idx % cols) * (panel_w + gap_x)
        oy = 92 + (idx // cols) * (panel_h + gap_y)

        busy = row["busy"]
        max_busy = row["max_busy"]
        mean_busy = row["mean_busy"]
        y_step = nice_step(max_busy * 1.1 / 4.0)
        y_top = y_step * math.ceil(max_busy * 1.1 / y_step)

        x0, y0 = ox + 56, oy + 50
        pw, ph = panel_w - 56 - 16, panel_h - 50 - 42
        y_bottom = y0 + ph

        def sy(v):
            return y_bottom - v / y_top * ph

        svg.text(ox, oy + 20, "T = %d" % nthreads, size=14, weight="bold")
        svg.text(ox, oy + 38,
                 "max %.1f ms · mean %.1f ms · max/mean %.2f"
                 % (max_busy, mean_busy, row["ratio"]),
                 size=10, fill=INK2)

        # y grid and labels
        tick = 0.0
        while tick <= y_top + 1e-9:
            yy = sy(tick)
            svg.line(x0, yy, x0 + pw, yy, GRID, 1.0)
            label = ("%d" % tick) if abs(tick - round(tick)) < 1e-9 \
                else ("%.1f" % tick)
            svg.text(x0 - 8, yy + 4, label, size=9, fill=MUTED,
                     anchor="end", tabular=True)
            tick += y_step

        svg.line(x0, y0, x0, y_bottom, AXIS, 1.0)
        svg.line(x0, y_bottom, x0 + pw, y_bottom, AXIS, 1.0)

        # bars
        slot = pw / float(nthreads)
        bar_w = min(slot - 2.0, 44.0)
        max_tid, max_value = max(busy, key=lambda r: r[2])[0], max_busy
        for tid, nrows, value in busy:
            cx = x0 + (tid + 0.5) * slot
            x = cx - bar_w / 2.0
            d = rounded_top_bar(x, sy(value), bar_w, y_bottom - sy(value))
            svg.path(d, fill=BLUE,
                     title="thread %d: %.2f ms (%d rows)"
                           % (tid, value, nrows))
            if nthreads > 12:
                svg.text(cx, y_bottom + 14, tid, size=8, fill=MUTED,
                         anchor="end", rotate=-60)
            else:
                svg.text(cx, y_bottom + 14, tid, size=9, fill=MUTED,
                         anchor="middle")

        # mean line
        ym = sy(mean_busy)
        svg.line(x0, ym, x0 + pw, ym, MUTED, 1.0, dash="4 4")
        svg.text(x0 + pw - 2, ym - 4, "mean %.1f" % mean_busy,
                 size=9, fill=MUTED, anchor="end")

        # selective direct label on the tallest bar
        cx_max = x0 + (max_tid + 0.5) * slot
        svg.text(cx_max, sy(max_value) - 6, "%.1f ms" % max_value,
                 size=9.5, weight="bold", anchor="middle")

        if idx % cols == 0:
            svg.text(ox + 16, y0 + ph / 2.0, "Busy time (ms)", size=10,
                     fill=INK2, anchor="middle", rotate=-90)

    svg.text(width / 2.0, height - 16,
             "Source: results/step3 — %s." % METHOD,
             size=10, fill=MUTED, anchor="middle")
    svg.save(path)
    return True


def render_ratio(best, path, thread_counts, views):
    width, height = 900, 540
    left, right, top, bottom = 78, 36, 112, 70
    pw, ph = width - left - right, height - top - bottom
    x0, y0 = left, top

    ratios = [best[(v, t)]["ratio"] for v in views for t in thread_counts
              if (v, t) in best]
    y_top = math.ceil(max(ratios) * 1.08 * 2.0) / 2.0
    if y_top <= 1.0:
        y_top = 1.5

    def sx(t):
        return x0 + (t - 1.0) / (24.0 - 1.0) * pw

    def sy(v):
        return y0 + ph - (v - 1.0) / (y_top - 1.0) * ph

    title = "Load imbalance of contiguous blocks"
    svg = Svg(width, height, title)
    svg.text(40, 34, title, size=20, weight="bold")
    svg.text(40, 56,
             "max busy time ÷ mean busy time per thread; "
             "1.0 means every thread finishes together.",
             size=11, fill=INK2)

    # legend
    lx = 40
    for i, view in enumerate(views):
        color = BLUE if i == 0 else ORANGE
        svg.line(lx, 84, lx + 26, 84, color, 2.2)
        svg.circle(lx + 13, 84, 4.0, color)
        svg.text(lx + 34, 88, "View %d" % view, size=11, fill=INK2)
        lx += 120

    # grid and y ticks
    tick = 1.0
    step = 0.5
    while tick <= y_top + 1e-9:
        yy = sy(tick)
        svg.line(x0, yy, x0 + pw, yy, GRID, 1.0)
        svg.text(x0 - 8, yy + 4, "%.1f" % tick, size=10, fill=MUTED,
                 anchor="end", tabular=True)
        tick += step

    svg.line(x0, y0, x0, y0 + ph, AXIS, 1.0)
    svg.line(x0, y0 + ph, x0 + pw, y0 + ph, AXIS, 1.0)

    for t in thread_counts:
        svg.text(sx(t), y0 + ph + 18, t, size=10, fill=MUTED,
                 anchor="middle", tabular=True)

    # perfect balance
    svg.line(x0, sy(1.0), x0 + pw, sy(1.0), MUTED, 1.4, dash="5 5")
    svg.text(x0 + pw - 4, sy(1.0) - 6, "perfect balance (1.0)",
             size=9.5, fill=MUTED, anchor="end")

    for i, view in enumerate(views):
        color = BLUE if i == 0 else ORANGE
        pts = [(t, best[(view, t)]["ratio"]) for t in thread_counts
               if (view, t) in best]
        coords = [(sx(t), sy(v)) for t, v in pts]
        svg.polyline(coords, color, 2.2)
        for (t, v), (cx, cy) in zip(pts, coords):
            svg.circle(cx, cy, 4.5, color,
                       title="View %d, %d threads: %.2f"
                             % (view, t, v))
        t_last, v_last = pts[-1]
        cx, cy = coords[-1]
        dy = -12 if i == 0 else 18
        svg.text(cx - 10, cy + dy, "View %d  %.2f×" % (view, v_last),
                 size=10.5, weight="bold", anchor="end")

    svg.text(x0 + pw / 2.0, height - 26, "Number of threads",
             size=11, fill=INK2, anchor="middle")
    svg.text(22, y0 + ph / 2.0, "Max / mean busy time", size=11,
             fill=INK2, anchor="middle", rotate=-90)
    svg.text(width / 2.0, height - 8,
             "Source: results/step3 — %s." % METHOD,
             size=10, fill=MUTED, anchor="middle")
    svg.save(path)


# ---- tables --------------------------------------------------------------
def write_tables(rows, best):
    fields = ["view", "threads", "rep", "serial_ms", "thread_ms", "speedup",
              "max_busy", "mean_busy", "ratio"]
    with open(os.path.join(RES, "summary_all.csv"), "w", newline="",
              encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in sorted(rows, key=lambda r: (r["view"], r["threads"],
                                               r["rep"])):
            writer.writerow(row)

    with open(os.path.join(RES, "summary_best.csv"), "w", newline="",
              encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for view in sorted({r["view"] for r in rows}):
            for nthreads in sorted({r["threads"] for r in rows}):
                if (view, nthreads) in best:
                    writer.writerow(best[(view, nthreads)])

    with open(os.path.join(RES, "thread_busy.csv"), "w", newline="",
              encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["view", "threads", "thread_id", "rows", "busy_ms"])
        for view in sorted({r["view"] for r in rows}):
            for nthreads in sorted({r["threads"] for r in rows}):
                if (view, nthreads) not in best:
                    continue
                for tid, nrows, busy in best[(view, nthreads)]["busy"]:
                    writer.writerow([view, nthreads, tid, nrows,
                                     "%.3f" % busy])


def write_report(rows, best):
    views = sorted({r["view"] for r in rows})
    threads = sorted({r["threads"] for r in rows})
    lines = []
    lines.append("# Program 1, step 3 - contiguous block decomposition\n")
    lines.append("Machine: Intel Core Ultra 9 285H, 16 cores / 16 logical "
                 "processors (6 P-cores + 8 E-cores + 2 LP E-cores), "
                 "63.5 GB RAM.\n")
    lines.append("Build: `g++ -m64 -O3 -std=c++11 -Wall` (MSYS2 UCRT64 "
                 "g++ 16.2.0).\n")
    lines.append("Data: `results/step3/raw/`. Each process runs the "
                 "benchmark 5 times and reports the minimum; the whole "
                 "process was repeated 3 times. Tables use the fastest "
                 "process run.\n")
    lines.append("\n## Speedup and thread balance\n")
    for view in views:
        lines.append("### View %d\n" % view)
        lines.append("| Threads | Serial (ms) | Threaded (ms) | Speedup | "
                     "Max busy (ms) | Mean busy (ms) | Max/Mean |")
        lines.append("|---:|---:|---:|---:|---:|---:|---:|")
        for t in threads:
            if (view, t) not in best:
                continue
            r = best[(view, t)]
            lines.append("| %d | %.3f | %.3f | %.2fx | %.3f | %.3f | %.2f |"
                         % (t, r["serial_ms"], r["thread_ms"], r["speedup"],
                            r["max_busy"], r["mean_busy"], r["ratio"]))
        lines.append("")
    gaps = [r["thread_ms"] - r["max_busy"] for r in best.values()]
    lines.append("`Threaded (ms)` is the measured wall time and includes "
                 "thread creation and join. It is at least `Max busy (ms)`; "
                 "in this data the gap is %.1f-%.1f ms.\n"
                 % (min(gaps), max(gaps)))

    for view in views:
        for t in (3,):
            if (view, t) not in best:
                continue
            r = best[(view, t)]
            lines.append("## Per-thread detail: View %d, T = %d\n"
                         % (view, t))
            lines.append("| Thread | Rows | Busy (ms) |")
            lines.append("|---:|---:|---:|")
            for tid, nrows, busy in r["busy"]:
                lines.append("| %d | %d | %.3f |" % (tid, nrows, busy))
            lines.append("\nMax/mean = %.2f, wall time = %.3f ms.\n"
                         % (r["ratio"], r["thread_ms"]))

    lines.append("## Figures\n")
    lines.append("### Speedup, both views\n")
    lines.append("![Speedup vs. threads, both views]"
                 "(charts/speedup_both_views.svg)\n")
    lines.append("### Per-thread busy time, View 1\n")
    lines.append("![Per-thread busy time, View 1]"
                 "(charts/thread_busy_view1.svg)\n")
    lines.append("### Per-thread busy time, View 2\n")
    lines.append("![Per-thread busy time, View 2]"
                 "(charts/thread_busy_view2.svg)\n")
    lines.append("### Load imbalance\n")
    lines.append("![Max/mean busy time vs. threads]"
                 "(charts/imbalance_vs_threads.svg)\n")
    lines.append("All charts are SVG files in `charts/`; individual view "
                 "speedup charts are `speedup_view1.svg` and "
                 "`speedup_view2.svg`.\n")

    with open(os.path.join(RES, "report.md"), "w", encoding="utf-8",
              newline="\n") as f:
        f.write("\n".join(lines))


# ---- main ----------------------------------------------------------------
def main():
    rows, best = collect()
    if not rows:
        sys.exit("no parsable logs under %s" % RAW)

    os.makedirs(CHARTS, exist_ok=True)
    write_tables(rows, best)
    write_report(rows, best)

    views = sorted({r["view"] for r in rows})
    threads = [1, 2, 3, 4, 5, 6, 7, 8, 16, 24]
    busy_threads = [3, 4, 5, 6, 7, 8, 16, 24]

    panels = []
    for view in views:
        pts = [(t, best[(view, t)]["speedup"]) for t in threads
               if (view, t) in best]
        if pts:
            panels.append({"title": "View %d" % view, "points": pts})

    machine_line = MACHINE
    for view in views:
        pts = [(t, best[(view, t)]["speedup"]) for t in threads
               if (view, t) in best]
        if not pts:
            continue
        render_speedup(
            [{"title": "View %d" % view, "points": pts}],
            os.path.join(CHARTS, "speedup_view%d.svg" % view),
            720,
            "Program 1 — speedup vs. threads (contiguous blocks)",
            "View %d · steps 1-3: each thread owns one contiguous "
            "band of rows" % view,
            machine_line + " · " + METHOD)

    if len(panels) > 1:
        render_speedup(
            panels,
            os.path.join(CHARTS, "speedup_both_views.svg"),
            430,
            "Program 1 — speedup vs. threads (contiguous blocks)",
            "Steps 1-3: each thread owns one contiguous band of rows",
            machine_line + " · " + METHOD)

    for view in views:
        render_busy(view,
                    os.path.join(CHARTS, "thread_busy_view%d.svg" % view),
                    best, busy_threads)

    if len(views) > 1:
        render_ratio(best,
                     os.path.join(CHARTS, "imbalance_vs_threads.svg"),
                     threads, views)

    print("wrote tables and report under %s" % RES)
    print("wrote charts under %s" % CHARTS)
    for view in views:
        for t in threads:
            if (view, t) in best:
                r = best[(view, t)]
                print("view %d  t=%2d  %6.3f ms  %5.2fx  "
                      "max/mean %.2f"
                      % (view, t, r["thread_ms"], r["speedup"], r["ratio"]))


if __name__ == "__main__":
    main()
