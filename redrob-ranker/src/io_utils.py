"""
io_utils.py
-----------
Handles all file reading: the candidate pool (.jsonl or .jsonl.gz) and the
job description (plain text/markdown).

Kept separate from scoring logic so the rest of the codebase doesn't care
whether the input was gzipped or not.
"""

import gzip
import json
from pathlib import Path


def load_candidates(path):
    """
    Loads candidates from a .jsonl or .jsonl.gz file.
    Returns a list of dicts, one per candidate, in file order.

    Each line in the file is one JSON object (a full candidate record
    matching candidate_schema.json).
    """
    path = Path(path)
    candidates = []

    opener = gzip.open if path.suffix == ".gz" else open
    mode = "rt"  # text mode, works for both gzip.open and open

    with opener(path, mode, encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                candidates.append(json.loads(line))
            except json.JSONDecodeError as e:
                # Don't silently skip — a malformed line could be a real
                # data issue worth knowing about, but also don't crash the
                # whole 100k-row run over one bad line.
                print(f"WARNING: could not parse line {line_num} in {path}: {e}")

    return candidates


def load_job_description(path):
    """Reads the job description text file (markdown or plain text) as a string."""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()
