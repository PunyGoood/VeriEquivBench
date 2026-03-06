"""
test.py — Score claude-sonnet-4 Dafny outputs using run_verifier.py.

Loads rollout_3/dafny_code_final.dfy from every code_* subfolder in
metrics/claude-sonnet-4 copy, then calls the scoring functions from run_verifier.
"""

import os
import sys

METRICS_DIR = os.path.dirname(os.path.abspath(__file__))
if METRICS_DIR not in sys.path:
    sys.path.insert(0, METRICS_DIR)

from run_verifier import (
    process_data,
    gt_score,
    subset_reward,
)
import run_verifier

DATA_DIR = os.path.join(METRICS_DIR, "claude-sonnet-4 copy")
LOG_DIR = os.path.join(METRICS_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

# Patch output_dir used by run_verifier functions
run_verifier.output_dir = LOG_DIR


if __name__ == "__main__":
    print(f"Data directory : {DATA_DIR}")
    print(f"Log directory  : {LOG_DIR}")
    print(f"Loading rollout_3/dafny_code_final.dfy from every code_* folder …\n")

    data_list = process_data(DATA_DIR)
    # Use only rollout_3 as specified
    data_list = [d for d in data_list if d["rollout"] == "rollout_3"]

    if not data_list:
        print("ERROR: no data found.")
        sys.exit(1)

    print(f"Loaded {len(data_list)} samples.\n")
    print("=" * 60)

    # GT spec-to-code equivalence
    print("\n>>> GT spec check")
    gt_score(data_list, log_dir=LOG_DIR)

    print("\n" + "=" * 60)
    print("Done.")
