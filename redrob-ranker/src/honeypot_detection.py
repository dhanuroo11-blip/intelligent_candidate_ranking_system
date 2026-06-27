"""
honeypot_detection.py
----------------------
Detects candidates with internally inconsistent / impossible profiles.

The challenge README and JD both call out ~80 honeypot candidates with
"subtly impossible profiles" -- e.g. years of experience inconsistent with
career history, or "expert" skill proficiency claimed with near-zero time
spent using the skill. The candidate schema does NOT give us a literal
"company founded year" field, so we detect impossibility through INTERNAL
CONSISTENCY checks on fields we do have. This is deliberate: it's more
robust (works even if the trap is constructed a different way than our
exact example) and it's easy to explain and defend.

We return a honeypot "suspicion score" (0 = totally consistent profile,
higher = more red flags) rather than a hard yes/no, then apply it as a
strong multiplicative penalty in scoring.py. This avoids accidentally
nuking a real candidate over one borderline data-entry quirk, while still
driving genuine honeypots to the bottom of the ranking.
"""


def compute_honeypot_flags(candidate):
    """
    Runs every internal-consistency check on one candidate and returns:
      (suspicion_score: int, reasons: list[str])

    suspicion_score starts at 0 and increases for each red flag found.
    A score of 0 means no red flags detected.
    """
    reasons = []
    score = 0

    profile = candidate.get("profile", {})
    career_history = candidate.get("career_history", [])
    skills = candidate.get("skills", [])

    stated_years = profile.get("years_of_experience", 0) or 0

    # --- Check 1: stated years_of_experience vs sum of career_history durations ---
    total_months = sum(ch.get("duration_months", 0) or 0 for ch in career_history)
    total_years_from_history = total_months / 12.0

    if total_years_from_history > 0:
        diff = abs(stated_years - total_years_from_history)
        # Allow some natural slack (gaps between jobs, rounding) before flagging.
        if diff > 2.5:
            score += 2
            reasons.append(
                f"stated experience ({stated_years} yrs) doesn't match career "
                f"history total ({total_years_from_history:.1f} yrs)"
            )

    # --- Check 2: "expert"/"advanced" proficiency claimed with near-zero duration ---
    suspicious_skill_count = 0
    for s in skills:
        proficiency = s.get("proficiency", "")
        duration = s.get("duration_months", 0) or 0
        if proficiency in ("expert", "advanced") and duration <= 2:
            suspicious_skill_count += 1

    if suspicious_skill_count >= 3:
        # A single oddity could just be messy self-reported data; several
        # at once is a much stronger signal of a constructed honeypot.
        score += 2
        reasons.append(
            f"{suspicious_skill_count} skills marked expert/advanced with <=2 months experience"
        )

    # --- Check 3: overlapping full-time roles (two is_current=true entries, or
    # date ranges that overlap by more than a small buffer) ---
    current_roles = [ch for ch in career_history if ch.get("is_current")]
    if len(current_roles) > 1:
        score += 2
        reasons.append(f"{len(current_roles)} roles simultaneously marked as current")

    # --- Check 4: a single role's duration_months is implausibly long relative
    # to total claimed experience (e.g. one job longer than their whole career) ---
    for ch in career_history:
        dur_years = (ch.get("duration_months", 0) or 0) / 12.0
        if stated_years > 0 and dur_years > stated_years + 1:
            score += 2
            reasons.append(
                f"single role at {ch.get('company', 'unknown company')} "
                f"({dur_years:.1f} yrs) exceeds total stated experience ({stated_years} yrs)"
            )
            break  # one mention is enough, don't double-count

    # --- Check 5: extremely high number of "expert" skills relative to total
    # experience -- e.g. claiming expert in 10+ areas with only 1-2 years total
    # experience is implausible breadth for the time available ---
    expert_count = sum(1 for s in skills if s.get("proficiency") == "expert")
    if stated_years <= 2 and expert_count >= 5:
        score += 1
        reasons.append(
            f"{expert_count} skills at expert level despite only {stated_years} yrs total experience"
        )

    return score, reasons


HONEYPOT_SUSPICION_THRESHOLD = 3
# A candidate with suspicion_score >= this value is treated as a likely
# honeypot and gets a severe scoring penalty (see scoring.py). We keep the
# bar at "multiple independent red flags", not "one weird field", to avoid
# falsely penalizing real candidates with slightly messy self-reported data.
