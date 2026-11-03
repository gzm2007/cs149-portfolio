#!/usr/bin/env bash
#
# Sweep prog1 over thread counts / views and save every raw log.
#
# Usage:
#   ./scripts/run_sweep.sh [label] [threads] [views] [reps]
#
#   label    output folder name; use "block" now and "interleaved" after
#            you implement the strided/cyclic decomposition (default: block)
#   threads  space-separated list (default: 1 2 3 4 6 8 12 16 24)
#   views    space-separated list (default: 1 2)
#   reps     process-level repetitions; each process already takes the min
#            of 5 internal runs (default: 3)
#
# Must be run inside the MSYS2 UCRT64 shell.
#
set -euo pipefail

cd "$(dirname "$0")/.."

LABEL="${1:-block}"
THREADS="${2:-1 2 3 4 6 8 12 16 24}"
VIEWS="${3:-1 2}"
REPS="${4:-3}"

if ! command -v g++ >/dev/null 2>&1; then
    echo "error: g++ not found. Run this from the MSYS2 UCRT64 shell." >&2
    exit 1
fi

OUT="results/${LABEL}"
mkdir -p "${OUT}/raw"

# Keep a snapshot of the implementation so each chart is traceable.
cp mandelbrotThread.cpp "${OUT}/mandelbrotThread.cpp.snapshot"

{
    echo "label=${LABEL}"
    echo "threads=${THREADS}"
    echo "views=${VIEWS}"
    echo "reps=${REPS}"
} > "${OUT}/sweep.txt"

make -s

for v in ${VIEWS}; do
    for t in ${THREADS}; do
        for r in $(seq 1 "${REPS}"); do
            log="${OUT}/raw/t${t}_v${v}_r${r}.log"
            ./mandelbrot -t "${t}" -v "${v}" > "${log}" 2>&1
            printf '[%s] view=%s threads=%2s rep=%s  ' "${LABEL}" "${v}" "${t}" "${r}"
            grep -E '\[mandelbrot (serial|thread)\]:|speedup' "${log}" | tr '\n' ' '
            echo
        done
    done
done

echo
echo "raw logs: ${OUT}/raw"
echo "next:     python scripts/plot.py"
