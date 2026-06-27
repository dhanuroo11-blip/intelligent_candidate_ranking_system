"""
jd_requirements.py
-------------------
This module is the "understand the role" half of the system.

IMPORTANT DESIGN DECISION: we do NOT call an LLM at ranking time to parse
the JD (that's disallowed by the compute constraints -- no network, no GPU,
5 min budget for 100K candidates). Instead, we read the JD ourselves, once,
as humans, and encode our understanding as explicit, documented Python
structures below.

This is actually a *better* fit for a 100K-candidate, no-network ranking
system: parsing logic is fixed and instant, fully inspectable, and there
is nothing to hallucinate. Every rule below has a comment pointing at the
exact part of job_description.md that justifies it, so this is easy to
defend in a design review or interview.

If the job description changes, a human updates this file. That's a
reasonable trade-off for a single, well-understood role (this isn't a
general-purpose multi-JD parser; that's a different system).
"""

# ----------------------------------------------------------------------
# CORE ROLE FACTS
# Source: job_description.md, header block
# ----------------------------------------------------------------------
ROLE_TITLE = "Senior AI Engineer -- Founding Team"
EXPERIENCE_MIN_YEARS = 5
EXPERIENCE_MAX_YEARS = 9
# JD: "5-9 years... a range, not a requirement... we'll seriously consider
# candidates outside the band if other signals are strong." -> soft band,
# NOT a hard cutoff. We implement this as a smooth scoring curve, not a
# pass/fail filter, in scoring.py.

# ----------------------------------------------------------------------
# MUST-HAVE SKILL AREAS
# Source: JD section "Things you absolutely need"
# Each entry is a *concept*, matched against multiple possible skill-name
# spellings/synonyms seen in the dataset's skill vocabulary, because the
# JD explicitly says "we don't care which model/tech, we care about the
# operational experience" -- so we match broadly within a concept.
# ----------------------------------------------------------------------
MUST_HAVE_SKILL_GROUPS = {
    "embeddings_retrieval": [
        "embeddings", "sentence transformers", "sentence-transformers",
        "vector search", "information retrieval", "bm25", "haystack",
        "recommendation systems", "semantic search",
    ],
    "vector_db_or_hybrid_search": [
        "pinecone", "weaviate", "qdrant", "milvus", "opensearch",
        "elasticsearch", "faiss", "vector search",
    ],
    "python": [
        "python",
    ],
    "ranking_evaluation": [
        "ndcg", "mrr", "map", "a/b test", "learning to rank",
        "recommendation systems", "information retrieval",
    ],
}

# ----------------------------------------------------------------------
# NICE-TO-HAVE SKILLS (boost score, never penalize for absence)
# Source: JD section "Things we'd like you to have but won't reject you for"
# ----------------------------------------------------------------------
NICE_TO_HAVE_SKILLS = [
    "lora", "qlora", "peft", "fine-tuning llms", "xgboost",
    "kubernetes", "docker", "mlops", "mlflow",
]

# ----------------------------------------------------------------------
# CORE "AI ENGINEER" SIGNAL SKILLS (used for keyword-stuffing detection)
# These are the skills a *real* AI/ML systems engineer would plausibly
# have, but which are also exactly the skills the JD warns are stuffed
# into irrelevant profiles (HR Manager with 9 AI skills, etc). We use
# this list together with TITLE and CAREER HISTORY checks -- never
# skills alone -- specifically because the JD calls this out as a trap.
# ----------------------------------------------------------------------
AI_CORE_SKILLS = [
    "nlp", "machine learning", "deep learning", "embeddings",
    "fine-tuning llms", "lora", "peft", "prompt engineering",
    "vector search", "recommendation systems", "information retrieval",
    "bm25", "faiss", "pinecone", "weaviate", "qdrant", "milvus",
    "elasticsearch", "opensearch", "haystack", "sentence transformers",
    "hugging face transformers", "langchain", "mlops", "mlflow",
    "reinforcement learning", "computer vision", "speech recognition",
    "tts", "gans", "cnn", "object detection", "image classification",
]

# ----------------------------------------------------------------------
# TITLES that strongly indicate a genuine applied-ML/AI systems role
# Source: JD throughout -- "own the intelligence layer", "ranking,
# retrieval, matching systems"
# ----------------------------------------------------------------------
STRONG_TITLE_KEYWORDS = [
    "machine learning engineer", "ml engineer", "ai engineer",
    "applied scientist", "research engineer", "recommendation systems",
    "search engineer", "search relevance", "ranking engineer",
    "nlp engineer", "data scientist",
]

# Titles that are explicitly NOT a fit per the JD, regardless of skills listed
# Source: "people whose primary expertise is computer vision, speech, or
# robotics without significant NLP/IR exposure", and general non-technical
# roles that would never legitimately hold this title
DISQUALIFYING_TITLE_KEYWORDS = [
    "hr manager", "human resources", "marketing manager", "accountant",
    "customer support", "sales", "operations manager", "graphic designer",
    "content writer", "civil engineer", "mechanical engineer", "business analyst",
]

# ----------------------------------------------------------------------
# COMPANY / EMPLOYER TYPE PENALTIES
# Source: JD "People who have only worked at consulting firms (TCS,
# Infosys, Wipro, Accenture, Cognizant, Capgemini, etc.) in their entire
# career... If you're currently at one of these companies but have prior
# product-company experience, that's fine."
# ----------------------------------------------------------------------
PURE_SERVICES_COMPANIES = [
    "tcs", "infosys", "wipro", "accenture", "cognizant", "capgemini",
    "mindtree", "hcl", "tech mahindra",
]
SERVICES_INDUSTRY_NAMES = ["it services"]
# Note: being AT one of these now is fine if career_history shows a prior
# product company -- see scoring.py for how this is actually applied
# (penalty only if EVERY job in career_history is services/IT-services).

# ----------------------------------------------------------------------
# LOCATION FIT
# Source: JD "Location: Pune/Noida-preferred but flexible... Candidates
# in Hyderabad, Pune, Mumbai, Delhi NCR welcome to apply. Outside India:
# case-by-case, but we don't sponsor work visas."
# ----------------------------------------------------------------------
PREFERRED_LOCATIONS = ["pune", "noida"]
ACCEPTABLE_LOCATIONS = ["hyderabad", "pune", "mumbai", "delhi", "ncr", "gurugram", "gurgaon", "noida"]
COUNTRY_REQUIRED = "india"
# JD: "we don't sponsor work visas" -> candidates outside India are a real
# concern unless willing_to_relocate is true.

# ----------------------------------------------------------------------
# DISQUALIFIER CHECKS (soft penalties, not hard excludes -- the JD itself
# uses words like "will probably not move forward", not "automatically
# rejected", so we implement these as large penalties rather than filters
# that remove candidates outright. This also protects us from accidentally
# filtering out a borderline-good match due to one weak signal.)
# ----------------------------------------------------------------------

# JD: "If you've spent your career in pure research environments...
# without any production deployment -- we will not move forward."
RESEARCH_ONLY_INDUSTRY_HINTS = ["research", "academia", "academic"]

# JD: "If your AI experience consists primarily of recent (under 12
# months) projects using LangChain to call OpenAI... unless you can
# demonstrate substantial pre-LLM-era ML production experience."
RECENT_LLM_ONLY_SKILL_HINTS = ["langchain", "prompt engineering", "fine-tuning llms"]
PRE_LLM_ML_SKILL_HINTS = [
    "machine learning", "statistical modeling", "feature engineering",
    "recommendation systems", "information retrieval", "deep learning",
    "computer vision", "nlp", "data science",
]
