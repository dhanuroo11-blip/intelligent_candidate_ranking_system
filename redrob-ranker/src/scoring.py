"""
scoring.py
----------
The core hybrid ranking engine. Computes a final 0-1 score for each
candidate against the Redrob "Senior AI Engineer" job description.

DESIGN PHILOSOPHY (worth restating, since this is what we'd defend in an
interview): the JD explicitly warns that the "right answer" is NOT keyword
matching -- a candidate with all the AI buzzwords but a Marketing Manager
title is not a fit, while a candidate without the trendy keywords but a
real shipped recommendation system IS a fit. So our scoring weighs:

  1. TITLE / CAREER HISTORY relevance (highest weight) -- this is the
     anchor signal a naive keyword system gets wrong, and the JD spends
     the most words on exactly this trap.
  2. SKILL MATCH -- weighted by proficiency + duration + endorsements,
     not just presence/absence, so a skill listed with 0 months and no
     endorsements counts for much less than one used for years. Also
     cross-checked against career history: skill tags only get full
     credit if the candidate's actual job descriptions corroborate
     having done relevant work (catches plausible-looking AI skill tags
     on an otherwise unrelated career).
  3. EXPERIENCE FIT -- a smooth curve around the 5-9 yr band, not a hard
     cutoff (JD explicitly says this is a range, not a requirement).
  4. COMPANY-TYPE fit -- penalizes pure-services-only careers, per JD.
  5. LOCATION fit -- Pune/Noida preferred, broader India acceptable,
     outside India needs willing_to_relocate=true (no visa sponsorship).

A natural extension (not implemented here, see README "Possible
extensions") would add a 6th component: embeddings-based semantic
similarity between the JD's "ideal candidate" narrative and each
candidate's free-text summary, precomputed OFFLINE so it doesn't count
against the 5-minute ranking-time budget. This would help catch
"Tier 5" candidates whose career-history wording doesn't share exact
keywords with the JD but describes equivalent work.

These combine into a base_score (0-1), which is then MULTIPLIED by a
behavioral-activity modifier (engagement, availability) -- per the JD's
explicit instruction to "down-weight" inactive candidates rather than
let one strong skill signal cancel out total unavailability.

Honeypot-suspicious candidates get a severe separate penalty applied last.
"""

from src import jd_requirements as req
from src.honeypot_detection import compute_honeypot_flags, HONEYPOT_SUSPICION_THRESHOLD


def _text_contains_any(text, keywords):
    """Case-insensitive substring check against a list of keywords."""
    text_lower = text.lower()
    return [kw for kw in keywords if kw.lower() in text_lower]


def score_title_relevance(candidate):
    """
    Scores how relevant the candidate's CURRENT TITLE and CAREER HISTORY
    (not just their skills tag list) are to an applied AI/ML systems role.

    Returns (score 0-1, list of reason fragments for the explanation text).
    """
    profile = candidate.get("profile", {})
    title = (profile.get("current_title") or "").lower()
    career_history = candidate.get("career_history", [])

    reasons = []
    score = 0.0

    # Strong direct signal: current title matches a real applied ML/AI role
    if any(kw in title for kw in req.STRONG_TITLE_KEYWORDS):
        score += 0.6
        reasons.append(f"current title '{profile.get('current_title')}' is a direct applied-ML/AI role")
    # Explicit disqualifying titles -- per JD, these are not a fit regardless
    # of any AI skill tags listed (the keyword-stuffing trap).
    elif any(kw in title for kw in req.DISQUALIFYING_TITLE_KEYWORDS):
        score -= 0.3
        reasons.append(f"current title '{profile.get('current_title')}' is unrelated to an AI/ML systems role")
    else:
        # Adjacent technical title (e.g. Backend Engineer, Data Engineer) --
        # plausible path into the role per JD's "Tier 5" plain-language case,
        # so we don't penalize, but we don't reward as much as a direct title.
        score += 0.2
        reasons.append(f"current title '{profile.get('current_title')}' is technical but not a direct AI/ML title")

    # Look at career history DESCRIPTIONS (not just skill tags) for evidence
    # of having actually shipped retrieval/ranking/recommendation systems.
    # This is the JD's explicit "Tier 5" signal: someone whose career history
    # shows they built a recommendation system at a product company is a fit
    # even without buzzwords in their skills list.
    shipped_relevant_system = False
    history_text = " ".join(
        (ch.get("description") or "") + " " + (ch.get("title") or "")
        for ch in career_history
    ).lower()

    shipping_signals = [
        "recommendation system", "ranking", "retrieval", "search relevance",
        "embeddings", "vector search", "real-time", "production", "scale",
        "machine learning model", "ml model", "recommend",
    ]
    matched_signals = _text_contains_any(history_text, shipping_signals)
    if len(matched_signals) >= 2:
        shipped_relevant_system = True
        score += 0.25
        reasons.append("career history describes shipping a relevant production system")

    score = max(0.0, min(1.0, score))
    return score, reasons, shipped_relevant_system


def score_skill_match(candidate, shipped_relevant_system):
    """
    Scores how well the candidate's actual SKILLS match the JD's must-have
    skill groups, weighted by proficiency level, duration_months, and
    endorsements -- so a skill claimed with 0 months/0 endorsements counts
    for much less than the same skill used for years with real endorsement.

    Returns (score 0-1, matched_skill_names: list, reasons: list).
    """
    skills = candidate.get("skills", [])
    proficiency_weight = {"beginner": 0.3, "intermediate": 0.55, "advanced": 0.8, "expert": 1.0}

    # Build a quick lookup: skill name (lowercase) -> skill record
    skill_lookup = {s.get("name", "").lower(): s for s in skills}

    group_scores = []
    matched_names = []

    for group_name, keywords in req.MUST_HAVE_SKILL_GROUPS.items():
        best_for_group = 0.0
        best_skill_name = None
        for kw in keywords:
            if kw in skill_lookup:
                s = skill_lookup[kw]
                prof = proficiency_weight.get(s.get("proficiency", "beginner"), 0.3)
                duration_months = s.get("duration_months", 0) or 0
                endorsements = s.get("endorsements", 0) or 0

                # Trust multiplier: a skill used for a long time and
                # endorsed by others is more believable than a bare tag.
                # Capped so a single skill can't dominate the whole group.
                duration_factor = min(1.0, duration_months / 24.0)  # full credit at 2+ yrs
                endorsement_factor = min(1.0, endorsements / 20.0)   # full credit at 20+ endorsements
                trust_multiplier = 0.5 + 0.3 * duration_factor + 0.2 * endorsement_factor

                effective = prof * trust_multiplier
                if effective > best_for_group:
                    best_for_group = effective
                    best_skill_name = s.get("name")

        group_scores.append(best_for_group)
        if best_skill_name:
            matched_names.append(best_skill_name)

    overall = sum(group_scores) / len(group_scores) if group_scores else 0.0

    # CROSS-CHECK against career history: the JD explicitly warns that a
    # candidate can list plausible-looking AI skill tags (with real
    # duration/endorsements) while their actual career history shows a
    # different, unrelated job. Skills alone can't fully distinguish
    # "used this at work" from "did a side project / self-study" -- so
    # we only give FULL credit for skill matches when career history
    # independently corroborates relevant work. Otherwise we discount,
    # rather than zero out, since side-project/self-taught skill growth
    # is real and shouldn't be punished to zero.
    if not shipped_relevant_system and overall > 0:
        overall *= 0.6

    reasons = []
    if matched_names:
        reasons.append("matched skills: " + ", ".join(sorted(set(matched_names))))
    missing_groups = [g for g, s in zip(req.MUST_HAVE_SKILL_GROUPS.keys(), group_scores) if s < 0.3]
    if missing_groups:
        reasons.append("weak/missing on: " + ", ".join(missing_groups))
    if not shipped_relevant_system and matched_names:
        reasons.append("skill tags not corroborated by career history descriptions")

    return overall, matched_names, reasons


def score_experience_fit(candidate):
    """
    Scores fit against the 5-9 year band as a SMOOTH curve, not a hard
    cutoff -- per JD: "a range, not a requirement... we'll seriously
    consider candidates outside the band if other signals are strong."

    Full score (1.0) inside the 5-9 band. Score decays gradually outside
    it, never dropping to zero, so a strong 4-year or 11-year candidate
    isn't automatically destroyed by this one factor.
    """
    years = candidate.get("profile", {}).get("years_of_experience", 0) or 0

    if req.EXPERIENCE_MIN_YEARS <= years <= req.EXPERIENCE_MAX_YEARS:
        return 1.0, f"{years} yrs experience is within the target 5-9 yr band"
    elif years < req.EXPERIENCE_MIN_YEARS:
        gap = req.EXPERIENCE_MIN_YEARS - years
        score = max(0.2, 1.0 - gap * 0.18)
        return score, f"{years} yrs experience is below the 5-9 yr band"
    else:
        gap = years - req.EXPERIENCE_MAX_YEARS
        score = max(0.3, 1.0 - gap * 0.12)
        return score, f"{years} yrs experience is above the 5-9 yr band"


def score_company_fit(candidate):
    """
    Penalizes a career built ENTIRELY on pure-services/IT-services
    companies, per JD. Does NOT penalize someone currently at one of these
    companies if their earlier career_history shows a product company.

    Returns (score 0-1, reason string or None).
    """
    career_history = candidate.get("career_history", [])
    if not career_history:
        return 0.6, None  # no data either way, neutral-ish

    def is_services(ch):
        company = (ch.get("company") or "").lower()
        industry = (ch.get("industry") or "").lower()
        return (
            any(sc in company for sc in req.PURE_SERVICES_COMPANIES)
            or industry in req.SERVICES_INDUSTRY_NAMES
        )

    all_services = all(is_services(ch) for ch in career_history)
    if all_services:
        return 0.4, "entire career history is at IT-services/consulting firms, no product-company experience"
    return 1.0, None


def score_location_fit(candidate):
    """
    Scores location/relocation fit. Pune/Noida = full score. Other listed
    Indian cities = strong score. Elsewhere in India = decent score
    (JD says flexible). Outside India = needs willing_to_relocate.
    """
    profile = candidate.get("profile", {})
    signals = candidate.get("redrob_signals", {})
    location = (profile.get("location") or "").lower()
    country = (profile.get("country") or "").lower()
    willing_to_relocate = signals.get("willing_to_relocate", False)

    if any(loc in location for loc in req.PREFERRED_LOCATIONS):
        return 1.0, f"based in {profile.get('location')}, a preferred location"
    if any(loc in location for loc in req.ACCEPTABLE_LOCATIONS):
        return 0.85, f"based in {profile.get('location')}, an accepted India location"
    if country == req.COUNTRY_REQUIRED:
        return 0.65, f"based in India ({profile.get('location')}) but outside preferred cities"
    # Outside India
    if willing_to_relocate:
        return 0.45, f"outside India ({profile.get('location')}) but willing to relocate"
    return 0.15, f"outside India ({profile.get('location')}), not willing to relocate, and Redrob does not sponsor visas"


def score_behavioral_modifier(candidate):
    """
    Computes a MULTIPLICATIVE modifier (not an additive score) from the
    redrob_signals platform-activity fields, per the JD's explicit
    instruction: "a perfect-on-paper candidate who hasn't logged in for
    6 months and has a 5% recruiter response rate is, for hiring purposes,
    not actually available. Down-weight them appropriately."

    Returns (modifier in roughly [0.3, 1.1], reason string).
    """
    signals = candidate.get("redrob_signals", {})

    open_to_work = signals.get("open_to_work_flag", False)
    response_rate = signals.get("recruiter_response_rate", 0) or 0
    last_active = signals.get("last_active_date", "")

    modifier = 1.0
    reasons = []

    # Open to work is a strong positive signal
    if open_to_work:
        modifier += 0.05
    else:
        modifier -= 0.15
        reasons.append("not marked open to work")

    # Recruiter response rate -- directly stated as a key signal in the JD's
    # own example ("5% recruiter response rate... not actually available")
    if response_rate < 0.15:
        modifier -= 0.25
        reasons.append(f"very low recruiter response rate ({response_rate:.0%})")
    elif response_rate < 0.4:
        modifier -= 0.10
        reasons.append(f"below-average recruiter response rate ({response_rate:.0%})")
    elif response_rate >= 0.6:
        modifier += 0.05
        reasons.append(f"strong recruiter response rate ({response_rate:.0%})")

    # Recency of activity (simple string comparison works since dates are
    # ISO format YYYY-MM-DD and we just need a coarse recency bucket)
    # We treat "recent" as the most important fast-decaying signal.
    if last_active:
        try:
            from datetime import date
            last_active_date = date.fromisoformat(last_active)
            today = date.today()
            days_inactive = (today - last_active_date).days
            if days_inactive > 180:
                modifier -= 0.30
                reasons.append(f"inactive for {days_inactive} days")
            elif days_inactive > 90:
                modifier -= 0.15
                reasons.append(f"inactive for {days_inactive} days")
            elif days_inactive <= 14:
                modifier += 0.05
        except (ValueError, TypeError):
            pass  # unparseable date, skip this sub-check rather than crash

    modifier = max(0.3, min(1.1, modifier))
    reason_text = "; ".join(reasons) if reasons else "good platform engagement"
    return modifier, reason_text


def score_candidate(candidate):
    """
    Combines every component into one final score for a single candidate.

    Returns a dict with the final score plus every component, so the
    reasoning generator (reasoning.py) can build an honest, fact-grounded
    explanation from the SAME numbers that produced the rank -- this is
    what guarantees the reasoning text can never contradict the score.
    """
    title_score, title_reasons, shipped_relevant_system = score_title_relevance(candidate)
    skill_score, matched_skills, skill_reasons = score_skill_match(candidate, shipped_relevant_system)
    experience_score, experience_reason = score_experience_fit(candidate)
    company_score, company_reason = score_company_fit(candidate)
    location_score, location_reason = score_location_fit(candidate)

    # Weights reflect the JD's own emphasis: title/career-history relevance
    # is weighted highest because that's explicitly the trap the JD warns
    # about ("keyword-stuffed but wrong title is not a fit").
    base_score = (
        title_score * 0.35 +
        skill_score * 0.30 +
        experience_score * 0.15 +
        company_score * 0.10 +
        location_score * 0.10
    )

    behavioral_modifier, behavioral_reason = score_behavioral_modifier(candidate)
    score_after_behavior = base_score * behavioral_modifier

    honeypot_suspicion, honeypot_reasons = compute_honeypot_flags(candidate)
    is_honeypot_suspect = honeypot_suspicion >= HONEYPOT_SUSPICION_THRESHOLD
    if is_honeypot_suspect:
        final_score = score_after_behavior * 0.05  # severe penalty, not literal zero
    else:
        final_score = score_after_behavior

    final_score = max(0.0, min(1.0, final_score))

    return {
        "candidate_id": candidate.get("candidate_id"),
        "final_score": final_score,
        "title_score": title_score,
        "skill_score": skill_score,
        "experience_score": experience_score,
        "company_score": company_score,
        "location_score": location_score,
        "behavioral_modifier": behavioral_modifier,
        "is_honeypot_suspect": is_honeypot_suspect,
        "honeypot_reasons": honeypot_reasons,
        "matched_skills": matched_skills,
        "title_reasons": title_reasons,
        "skill_reasons": skill_reasons,
        "experience_reason": experience_reason,
        "company_reason": company_reason,
        "location_reason": location_reason,
        "behavioral_reason": behavioral_reason,
    }
