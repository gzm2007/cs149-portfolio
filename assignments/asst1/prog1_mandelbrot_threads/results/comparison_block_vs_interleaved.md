# Program 1 — contiguous blocks vs. interleaved rows

Machine: Intel Core Ultra 9 285H, 16 cores / 16 logical processors
(6 P-cores + 8 E-cores + 2 LP E-cores), 63.5 GB RAM.

Build: `g++ -m64 -O3 -std=c++11 -Wall` (MSYS2 UCRT64 g++ 16.2.0).

Data: `results/step3/` (contiguous blocks) and
`results/interleaved/` (interleaved rows). Each process runs the benchmark
5 times and reports the minimum; every configuration was repeated 3 times.
The tables use the fastest process run.

The original step-3 sweep covered T = 1, 2, 3, 4, 8, 16, 24. The missing
T = 5, 6, 7 points were added on 2026-11-01: the block points were re-run
from a saved copy of the block implementation, and the interleaved points
were run with the final implementation.

## View 1

| Threads | Block speedup | Block wall (ms) | Block max/mean | Interleaved speedup | Interleaved wall (ms) | Interleaved max/mean | Wall reduction |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 1.01x | 218.603 | 1.00 | 1.00x | 222.557 | 1.00 | -1.8% |
| 2 | 2.00x | 109.882 | 1.00 | 2.00x | 110.614 | 1.00 | -0.7% |
| 3 | 1.67x | 132.006 | 1.82 | 3.05x | 72.757 | 1.00 | 44.9% |
| 4 | 2.52x | 88.289 | 1.62 | 4.05x | 55.014 | 1.00 | 37.7% |
| 5 | 2.56x | 87.662 | 1.98 | 4.98x | 44.834 | 1.01 | 48.9% |
| 6 | 3.35x | 66.292 | 1.81 | 5.85x | 38.563 | 1.02 | 41.8% |
| 7 | 3.53x | 63.637 | 1.99 | 6.63x | 33.588 | 1.02 | 47.2% |
| 8 | 4.05x | 53.848 | 1.91 | 7.61x | 29.455 | 1.01 | 45.3% |
| 16 | 7.10x | 31.069 | 1.98 | 8.02x | 27.700 | 1.26 | 10.8% |
| 24 | 8.95x | 25.083 | 1.93 | 9.94x | 22.362 | 1.26 | 10.8% |

## View 2

| Threads | Block speedup | Block wall (ms) | Block max/mean | Interleaved speedup | Interleaved wall (ms) | Interleaved max/mean | Wall reduction |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 1.00x | 125.568 | 1.00 | 1.00x | 127.317 | 1.00 | -1.4% |
| 2 | 1.72x | 73.445 | 1.19 | 2.02x | 62.876 | 1.00 | 14.4% |
| 3 | 2.22x | 56.914 | 1.35 | 2.98x | 42.192 | 1.01 | 25.9% |
| 4 | 2.62x | 48.424 | 1.55 | 4.00x | 31.609 | 1.00 | 34.7% |
| 5 | 2.97x | 42.537 | 1.69 | 5.02x | 26.007 | 1.01 | 38.9% |
| 6 | 3.43x | 37.531 | 1.78 | 5.94x | 21.812 | 1.02 | 41.9% |
| 7 | 3.74x | 33.951 | 1.76 | 6.42x | 19.709 | 1.02 | 41.9% |
| 8 | 4.19x | 30.301 | 1.83 | 7.20x | 17.738 | 1.03 | 41.5% |
| 16 | 6.90x | 18.269 | 1.86 | 8.52x | 14.947 | 1.14 | 18.2% |
| 24 | 9.80x | 12.970 | 1.97 | 8.97x | 13.992 | 1.28 | -7.9% |

## Findings

**Step 2 — the block decomposition does not scale linearly.**

With contiguous row bands, a thread's work depends on which part of the
image it owns. View 1 is especially uneven: the middle rows iterate far
more times than the top and bottom rows. The complete 1–8 curve shows the
sawtooth this produces:

- T = 3: **1.67x** (max/mean 1.82) — the three-way split gives the middle
  thread a much more expensive band.
- T = 5: **2.56x** (max/mean 1.98) — almost no gain over T = 4 (2.52x).
- T = 6: **3.35x**; T = 7: **3.53x** (max/mean 1.99) — still well below
  linear speedup.
- T = 8: **4.05x** (max/mean 1.91) — the imbalance persists at every
  thread count.

View 2 is flatter (the three-thread anomaly is much smaller: 2.22x,
max/mean 1.35), but it still shows the same trend as T grows.

**Step 3 — per-thread timing explains the curve.**

The Max/Mean busy-time ratio stays near 1.8–2.0 for most block
configurations, meaning the slowest thread does about twice the average
work. Since wall time is bounded below by the slowest thread, the extra
threads idle while one thread finishes its expensive band. The per-thread
detail and `thread_busy_*.svg` charts in `results/step3/report.md` show
this directly (e.g. view 1, T = 3: 43.0, 131.7, 42.5 ms).

**Step 4 — the interleaved policy fixes the imbalance.**

Thread `t` computes rows `t, t+T, t+2T, ...`. Every thread therefore owns
the same number of rows and, more importantly, the same mix of cheap and
expensive rows. The policy needs no synchronization and is valid for every
thread count.

The per-thread busy times confirm this directly:

- View 1, T = 3: Max/Mean falls from **1.82** (blocks) to **1.00**
  (interleaved); speedup rises from **1.67x** to **3.05x**.
- View 1, T = 5/6/7: **4.98x / 5.85x / 6.63x**, Max/Mean 1.01–1.02.
- View 1, T = 8: Max/Mean falls from **1.91** to **1.01**; speedup rises
  from **4.05x** to **7.61x**.
- View 2, T = 8: Max/Mean falls from **1.83** to **1.03**; speedup rises
  from **4.19x** to **7.20x**.

**The 8-thread target is met on both views: 7.61x (view 1) and 7.20x
(view 2).** The remaining gap to 8x is thread creation/join and other
fixed overhead, not load imbalance.

**Step 5 — 16 threads is only modestly faster than 8.**

| View | 8 threads | 16 threads | Wall-time change |
|---|---:|---:|---:|
| 1 | 7.61x / 29.455 ms | 8.02x / 27.700 ms | -6.0% |
| 2 | 7.20x / 17.738 ms | 8.52x / 14.947 ms | -15.7% |

Sixteen threads do help, but not by anything close to 2x. Reasons:

1. The machine has 16 logical CPUs, so 8 threads already occupy half of
   them. Doubling the threads cannot double throughput.
2. The cores are heterogeneous: 6 P-cores, 8 E-cores, and 2 LP E-cores.
   The extra 8 threads mostly land on slower cores, so their marginal
   contribution is small.
3. At T = 16 the Max/Mean busy ratio rises to 1.26 (view 1) and 1.14
   (view 2). This is *not* a work-decomposition problem — all threads own
   exactly 75 rows. It reflects unequal core speeds and OS scheduling.
4. The gap between wall time and max busy time also grows, because thread
   creation/join and wake-up delays become significant when the run is
   only ~15-28 ms long.

At 24 threads the workload is oversubscribed (24 workers on 16 logical
CPUs). View 1 still improves to 9.94x, while view 2 comes out slightly
below its block result (8.97x vs 9.80x); at this thread count scheduling
noise dominates the remaining differences.

## Files

- `results/step3/report.md` — block tables, per-thread detail, charts
  (now including T = 5, 6, 7).
- `results/interleaved/report.md` — interleaved tables, per-thread detail,
  charts (now including T = 5, 6, 7).
- `results/step3/summary_all.csv`, `summary_best.csv`, `thread_busy.csv`.
- `results/interleaved/summary_all.csv`, `summary_best.csv`,
  `thread_busy.csv`.
- `results/step3/charts/*.svg` and `results/interleaved/charts/*.svg` —
  speedup, per-thread busy time, and imbalance charts.
