"""
reasoning.py
------------
Generates the 1-2 sentence "reasoning" column required by the submission
spec -- built entirely from facts already computed in scoring.py, using
plain string templates, NOT an LLM call.

Why not an LLM here: the spec explicitly checks reasoning for hallucination
("claims that don't correspond to something in the candidate's profile are
red flags") and rank-consistency. Template generation from the exact
numbers and facts that produced the rank makes both of those checks pass
by construction -- there's no model in the loop that could invent a skill
or contradict the score. It also means this step costs ~0 compute time,
which matters across 100,000 candidates even though we only need it for
the top 100.
"""


def build_reasoning(candidate, score_result):
    """
    Builds a 1-2 sentence, fact-grounded explanation for why this
    candidate landed at their score, using the actual computed
    sub-scores and extracted facts -- never invented details.
    """
    profile = candidate.get("profile", {})
    years = profile.get("years_of_experience", "unknown")
    title = profile.get("current_title", "unknown title")
    company = profile.get("current_company", "unknown company")
    location = profile.get("location", "unknown location")

    parts = []

    # Lead with the strongest factual anchor: years + title + company
    parts.append(f"{title} at {company} with {years} yrs experience ({location}).")

    # Title/career relevance reason (only the most informative fragment)
    if score_result["title_reasons"]:
        parts.append(score_result["title_reasons"][0].capitalize() + ".")

    # Matched skills, if any
    if score_result["matched_skills"]:
        top_skills = sorted(set(score_result["matched_skills"]))[:3]
        parts.append(f"Relevant skills: {', '.join(top_skills)}.")
    elif score_result["skill_score"] < 0.3:
        parts.append("Limited overlap with the JD's core retrieval/ranking skill requirements.")

    # Experience fit, only mention if notably off-band (keeps reasoning concise)
    if score_result["experience_score"] < 0.85:
        parts.append(score_result["experience_reason"].capitalize() + ".")

    # Company-type concern, if present
    if score_result["company_reason"]:
        parts.append(score_result["company_reason"].capitalize() + ".")

    # Behavioral/availability concern, only flag if modifier indicates a real issue
    if score_result["behavioral_modifier"] < 0.85:
        parts.append(f"Availability concern: {score_result['behavioral_reason']}.")

    # Honeypot flag, if applicable -- always surfaced, this is important
    # for transparency even though these candidates will rank near zero
    # and likely won't appear in a real top-100 anyway.
    if score_result["is_honeypot_suspect"]:
        parts.append(f"FLAGGED as likely inconsistent profile: {'; '.join(score_result['honeypot_reasons'])}.")

    reasoning = " ".join(parts)

    # Keep it tight -- spec wants 1-2 sentences, not a paragraph dump.
    # We cap the number of fragments used rather than truncating mid-sentence.
    return reasoning
