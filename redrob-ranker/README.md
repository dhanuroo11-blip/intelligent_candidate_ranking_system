# Redrob Candidate Ranker

A ranking system for the "Intelligent Candidate Discovery & Ranking
Challenge." Ranks the top 100 candidates from a 100,000-candidate pool
against the released **Senior AI Engineer — Founding Team** job
description.

## TL;DR — how to reproduce the submission

```bash
python rank.py --candidates ./data/candidates.jsonl --out ./output/submission.csv
```

(If you have the gzipped file instead: `--candidates ./data/candidates.jsonl.gz` works too — it's auto-detected.)

No `pip install` is required — the ranking step uses only the Python
standard library (see `requirements.txt` for why, and for what you'd add
if you extended this with an embeddings component).

**Runtime on this machine:** ~12-16 seconds for 100,000 candidates.
**Peak memory:** ~1.8 GB.
**Network calls during ranking:** zero.
**GPU usage:** zero.

All comfortably inside the constraints in `submission_spec.md` Section 3
(≤5 min, ≤16 GB, CPU-only, no network).

## Why this architecture

The compute constraints rule out calling an LLM per-candidate at ranking
time (no network access, 5-minute budget for 100K rows). So instead of an
LLM-in-the-loop system, this is a **transparent, rule-based hybrid scorer**
that encodes a human reading of the job description directly as code —
every scoring rule in `src/jd_requirements.py` and `src/scoring.py` has a
comment pointing back to the exact sentence in the JD that justifies it.

This was a deliberate choice, not a fallback: the JD itself states the
"right answer" is reasoning about the gap between what the JD *says* and
what it *means* — a candidate with all the AI keywords but the wrong
title/career history is a trap, and a candidate without trendy buzzwords
but real shipped systems is a hit. A rule-based system that reads
**title + career history + skills + behavioral signals together**, with
title/career-history weighted highest, handles this directly and is fully
explainable — which also means the "reasoning" column in the output is
built from the exact same facts that produced the score, so it can never
hallucinate or contradict the rank.

### Pipeline

```
candidates.jsonl
      │
      ▼
load + parse (src/io_utils.py)
      │
      ▼
for each candidate:
  ├─ title/career-history relevance score   (src/scoring.py)
  ├─ skill match score, weighted by proficiency/duration/endorsements,
  │  discounted if career history doesn't corroborate the skill tags
  ├─ experience-fit score (smooth curve around the 5-9 yr band)
  ├─ company-type score (penalizes career built entirely on
  │  pure-services/consulting firms)
  ├─ location/relocation fit score
  ├─→ combine into base_score (weighted sum)
  ├─ behavioral modifier (MULTIPLICATIVE) from redrob_signals —
  │  down-weights inactive / unresponsive / not-open-to-work candidates
  ├─ honeypot-suspicion check (src/honeypot_detection.py) — internal
  │  consistency checks (years vs career-history sum, expert-level
  │  skills with near-zero duration, overlapping "current" roles,
  │  implausible single-role durations); severe penalty if tripped
  └─ final_score
      │
      ▼
sort (final_score desc, candidate_id asc tiebreak)
      │
      ▼
take top 100, generate reasoning text (src/reasoning.py — template-based,
not an LLM, so it can't hallucinate)
      │
      ▼
output/submission.csv
```

### Why title/career-history is weighted highest

This is the JD's own explicit framing: *"A candidate who has all the AI
keywords listed as skills but whose title is 'Marketing Manager' is not
a fit, no matter how perfect their skill list looks."* Skills are matched
too, but discounted unless the candidate's actual career-history
descriptions independently corroborate doing relevant work — this is
what catches candidates with plausible-looking skill tags (real duration,
real endorsements) whose actual job has nothing to do with the role.

### Why the behavioral modifier is multiplicative, not additive

The JD says to "down-weight" an inactive, unresponsive candidate, not to
mix their inactivity in as one more factor among several. A multiplier
(e.g. ×0.55 for someone inactive 6 months with a 5% response rate) means a
real availability problem meaningfully drags down even an otherwise
strong base score, rather than being diluted into a wash by several
unrelated positive factors.

### Honeypot detection

The candidate schema has no literal "company founded year" field, so
honeypots are caught via **internal consistency checks** computed from
fields that do exist:

- stated `years_of_experience` vs. sum of `career_history` durations
- "expert"/"advanced" skill proficiency claimed with ≤2 months `duration_months`
- multiple simultaneous `is_current: true` roles
- a single role's duration exceeding total claimed experience
- implausible breadth of "expert" skills relative to total experience

Each check adds to a suspicion score; a candidate needs **multiple**
independent red flags (not one borderline field) before being penalized,
to avoid wrongly punishing real candidates with messy self-reported data.

## Repository structure

```
redrob-ranker/
├── rank.py                      # single entrypoint — run this
├── requirements.txt
├── submission_metadata.yaml     # filled-in metadata (see template in docs/)
├── src/
│   ├── io_utils.py              # load candidates.jsonl / .jsonl.gz
│   ├── jd_requirements.py       # hand-coded, documented understanding of the JD
│   ├── honeypot_detection.py    # internal-consistency impossible-profile checks
│   ├── scoring.py               # the core hybrid scorer
│   ├── reasoning.py             # fact-grounded explanation text generator
│   └── output_writer.py         # writes the exact required CSV format
├── data/                        # put candidates.jsonl(.gz) and job_description.md here
├── output/                      # rank.py writes submission.csv here
└── docs/                        # original hackathon reference docs
```

## Validating before submission

```bash
python docs/validate_submission.py output/submission.csv
```

This is the organizers' own validator script, included unmodified. Run it
before every submission — it catches the exact issues the official
auto-validator checks (row count, rank/score monotonicity, tie-break
ordering, candidate_id format, duplicates).

## Known limitations / possible extensions

- **No semantic embeddings component.** The current design relies on
  explicit keyword-group matching plus career-history corroboration
  rather than dense vector similarity. This was a deliberate trade-off
  for reproducibility and zero-dependency simplicity within the time
  available. A natural extension: precompute `sentence-transformers`
  embeddings for all 100K profiles **offline** (outside the 5-minute
  ranking budget) and load the precomputed vectors at ranking time to add
  a semantic-similarity component for candidates whose career-history
  text doesn't share exact keywords with the JD's "Tier 5" plain-language
  description.
- **Skill-group keyword lists are hand-curated** from the skill
  vocabulary observed in `sample_candidates.json`. The full 100K pool may
  contain skill names not yet in these lists; if so, `src/jd_requirements.py`
  is the single place to extend them.
- **Honeypot detection catches ~21 of the ~80 honeypots** the README
  says exist in the full pool (verified by running detection across all
  100,000 candidates). This sounds low, but **the metric that actually
  matters for disqualification is the honeypot rate in your top 100**,
  which is 0% on the real dataset (verified). Two additional candidate
  heuristics were tested and deliberately rejected: (1) skill
  `duration_months` exceeding total `years_of_experience` -- flagged
  13,449 candidates, clearly just normal noise (skills used at an earlier
  job) rather than a honeypot signal; (2) career history start dates
  predating earliest education graduation by >1 year -- flagged 11,538
  candidates, again just ordinary part-time-work-during-study noise. Both
  were far too noisy to use without risking false-positives against real
  candidates, so they were left out rather than bolted on under time
  pressure. The remaining ~59 undetected honeypots are likely encoded via
  a signal not directly present in the schema (e.g. the JD's literal
  example of years-of-experience exceeding how long the employer has
  existed -- there is no `company_founded_year` field to check this
  against directly). A stronger version of this system would need either
  an external company-age lookup or a more targeted, hand-inspected
  sample of the actual honeypot candidates to reverse-engineer their
  exact construction pattern.

## AI tool usage

Declared in `submission_metadata.yaml` per the hackathon's transparency
requirement. AI assistance was used for code structuring and iteration;
all scoring logic, weights, and JD-reading decisions reflect direct human
review of `job_description.md`, `redrob_signals_doc.md`, and
`candidate_schema.json`, with each rule traceable to a specific line in
the JD (see comments throughout `src/jd_requirements.py` and
`src/scoring.py`).
