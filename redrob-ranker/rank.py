#!/usr/bin/env python3
"""
rank.py
-------
THE single entrypoint script. Per submission_spec.md Section 10.3, this
must be runnable as one command that produces the submission CSV from the
candidates file:

    python rank.py --candidates ./data/candidates.jsonl --out ./output/submission.csv

Runs entirely offline, CPU-only, no GPU, no network calls -- compliant
with the 5-minute / 16GB / CPU-only / no-network compute constraints in
submission_spec.md Section 3.
"""

import argparse
import time
from pathlib import Path

from src.io_utils import load_candidates
from src.scoring import score_candidate
from src.reasoning import build_reasoning
from src.output_writer import write_submission_csv, sort_with_deterministic_tiebreak


def main():
    parser = argparse.ArgumentParser(description="Rank Redrob candidates against the Senior AI Engineer JD.")
    parser.add_argument("--candidates", required=True, help="Path to candidates.jsonl or candidates.jsonl.gz")
    parser.add_argument("--out", required=True, help="Path to write the output submission CSV")
    parser.add_argument("--top-n", type=int, default=100, help="Number of top candidates to include (default 100)")
    args = parser.parse_args()

    start_time = time.time()

    print(f"Loading candidates from {args.candidates} ...")
    candidates = load_candidates(args.candidates)
    print(f"Loaded {len(candidates)} candidates in {time.time() - start_time:.1f}s")

    print("Scoring all candidates ...")
    results = []
    for candidate in candidates:
        score_result = score_candidate(candidate)
        score_result["reasoning"] = build_reasoning(candidate, score_result)
        results.append(score_result)
    print(f"Scored {len(results)} candidates in {time.time() - start_time:.1f}s total")

    print("Sorting and selecting top candidates ...")
    ranked = sort_with_deterministic_tiebreak(results)

    # Surface a quick sanity signal in the console: how many of our top 100
    # tripped the honeypot suspicion flag. Per submission_spec.md Section 7,
    # a rate above 10% would be a disqualifying problem -- worth seeing
    # immediately, not discovering after submission.
    top_n_preview = ranked[: args.top_n]
    honeypot_count = sum(1 for r in top_n_preview if r["is_honeypot_suspect"])
    print(f"Honeypot-suspect candidates in top {args.top_n}: {honeypot_count} "
          f"({honeypot_count / args.top_n:.1%})")

    output_path = Path(args.out)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_submission_csv(ranked, output_path, top_n=args.top_n)

    elapsed = time.time() - start_time
    print(f"\nDone in {elapsed:.1f} seconds.")
    if elapsed > 300:
        print("WARNING: exceeded the 5-minute compute budget specified in submission_spec.md Section 3.")


if __name__ == "__main__":
    main()
