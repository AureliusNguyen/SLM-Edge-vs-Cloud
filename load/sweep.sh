#!/usr/bin/env bash
# Run one policy over every rate, then redraw the plot. Needs the gateway running.
#
#   load/sweep.sh                          # task-rule, Poisson arrivals, uniform task mix
#   load/sweep.sh always-cloud
#   load/sweep.sh always-local
#   load/sweep.sh task-rule bursty
#   load/sweep.sh task-rule poisson zipf
set -euo pipefail
cd "$(dirname "$0")/.."

POLICY=${1:-task-rule}
ARRIVALS=${2:-poisson}
MIX=${3:-uniform}

python3 load/trace.py "$ARRIVALS" "$MIX"
for trace in load/traces/"$ARRIVALS-$MIX"-r*-s1.json; do
  python3 load/run.py "$trace" "$POLICY"
done
python3 load/plot.py
