"""
Stage 1 — fast keyword pre-filter (~10ms/job, free).
Extracts required/preferred skills from the JD and checks % present in resume text.
"""
import re
import string
from src.models.schemas import JobListing


def _tokenize(text: str) -> set[str]:
    text = text.lower()
    text = re.sub(r"[^\w\s\+\#]", " ", text)
    return set(text.split())


def _normalize(phrase: str) -> str:
    return phrase.lower().strip(string.punctuation)


_ALIASES: dict[str, list[str]] = {
    "machine learning": ["ml", "machine learning"],
    "large language model": ["llm", "large language model", "large language models"],
    "retrieval augmented generation": ["rag", "retrieval augmented generation", "retrieval-augmented"],
    "natural language processing": ["nlp", "natural language processing"],
    "kubernetes": ["k8s", "kubernetes"],
    "continuous integration": ["ci/cd", "cicd", "continuous integration"],
    "amazon web services": ["aws", "amazon web services"],
    "google cloud": ["gcp", "google cloud platform", "google cloud"],
    "pytorch": ["pytorch", "torch"],
    "tensorflow": ["tensorflow", "tf"],
}


def _expand_aliases(tokens: set[str]) -> set[str]:
    expanded = set(tokens)
    for canonical, variants in _ALIASES.items():
        if any(v in tokens for v in variants):
            expanded.update(variants)
            expanded.add(canonical)
    return expanded


def build_resume_token_set(resume: dict) -> set[str]:
    parts: list[str] = []
    parts.append(resume.get("summary", ""))
    for exp in resume.get("experience", []):
        parts.append(exp.get("title", ""))
        parts.extend(exp.get("bullets", []))
        parts.extend(exp.get("skills_used", []))
    for skill_group in resume.get("skills", {}).values():
        parts.extend(skill_group)
    return _expand_aliases(_tokenize(" ".join(parts)))


def keyword_score(job: JobListing, resume_tokens: set[str]) -> tuple[float, list[str], list[str]]:
    """Returns (score 0–1, missing_keywords, present_keywords)."""
    jd_tokens = _expand_aliases(_tokenize(job.description))

    words = job.description.lower().split()
    skill_candidates: list[str] = list(jd_tokens)
    for n in (2, 3):
        for i in range(len(words) - n + 1):
            phrase = " ".join(words[i: i + n])
            if any(phrase in s for alias_list in _ALIASES.values() for s in alias_list):
                skill_candidates.append(phrase)

    if not skill_candidates:
        return 0.5, [], []

    present = [kw for kw in skill_candidates if kw in resume_tokens]
    missing = [kw for kw in skill_candidates if kw not in resume_tokens]
    score = len(present) / len(skill_candidates)
    return round(score, 3), missing[:20], present[:20]
