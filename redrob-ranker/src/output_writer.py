"""
output_writer.py
-----------------
Writes the final submission CSV in the EXACT format required by
submission_spec.md / validate_submission.py:

  - header: candidate_id,rank,score,reasoning
  - exactly 100 data rows
  - rank 1-100, each used exactly once
  - score non-increasing as rank increases
  - ties broken by candidate_id ascending (validator checks this exactly)
  - UTF-8 encoding
"""

import csv


def write_submission_csv(ranked_results, output_path, top_n=100):
    """
    ranked_results: list of dicts, each with at least
        candidate_id, final_score, reasoning
      already sorted best-first (rank 1 = best) BEFORE calling this.

    Writes exactly top_n rows to output_path.
    """
    top_results = ranked_results[:top_n]

    if len(top_results) < top_n:
        raise ValueError(
            f"Need at least {top_n} candidates to produce a valid submission, "
            f"only have {len(top_results)}. Check your input data."
        )

    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["candidate_id", "rank", "score", "reasoning"])
        for rank, result in enumerate(top_results, start=1):
            writer.writerow([
                result["candidate_id"],
                rank,
                f"{result['final_score']:.4f}",
                result["reasoning"],
            ])

    print(f"Wrote {len(top_results)} rows to {output_path}")


def sort_with_deterministic_tiebreak(results):
    """
    Sorts results by final_score descending. Ties are broken by
    candidate_id ascending, exactly matching what validate_submission.py
    checks for ("Equal scores at ranks X and Y: tie-break requires
    candidate_id ascending").
    """
    return sorted(results, key=lambda r: (-r["final_score"], r["candidate_id"]))
