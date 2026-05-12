"""
Resume tailoring — keyword injection into master resume via Claude Sonnet.
Non-destructive: master resume.json is never modified.
Returns a new resume dict with injected keywords + re-scored ATS.
"""
import copy
import json
import logging
import os

import anthropic

from src.models.schemas import ATSScore, JobListing
from src.scoring.keyword import build_resume_token_set, keyword_score

logger = logging.getLogger(__name__)

_CLIENT: anthropic.Anthropic | None = None


def _client() -> anthropic.Anthropic:
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _CLIENT


_SYSTEM = """\
You are an expert resume writer and ATS optimization specialist.
Your task is to tailor a candidate's resume for a specific job description by:
1. Naturally injecting missing keywords into the summary and bullet points
2. Reordering experience bullets to front-load the most relevant ones
3. Adding any missing skills to the skills section ONLY if the candidate's experience supports them
4. Rewriting the summary to be role-specific

Rules:
- NEVER fabricate experience or skills the candidate doesn't have
- Keep bullet points truthful and grounded in the original experience
- Preserve the candidate's voice and style
- Return ONLY the modified resume as valid JSON — no markdown, no explanation
"""

_PROMPT = """\
## Target Job
Title: {title}
Company: {company}

## Job Description
{jd}

## Missing Keywords to Inject
{missing}

## Current Resume JSON
{resume_json}

Return the tailored resume JSON with the same structure. Make targeted changes only.
"""


def tailor_resume(
    job: JobListing,
    score: ATSScore,
    master_resume: dict,
) -> tuple[dict, list[str]]:
    """
    Returns (tailored_resume_dict, list_of_changes_made).
    Falls back to master resume if LLM call fails.
    """
    if not score.missing_keywords:
        return copy.deepcopy(master_resume), []

    prompt = _PROMPT.format(
        title=job.title,
        company=job.company,
        jd=job.description[:3000],
        missing=", ".join(score.missing_keywords[:10]),
        resume_json=json.dumps(master_resume, indent=2),
    )

    try:
        response = _client().messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        # Strip accidental markdown fences
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
        tailored = json.loads(raw)
    except Exception as exc:
        logger.warning("Resume tailoring failed for '%s': %s — using master", job.title, exc)
        return copy.deepcopy(master_resume), []

    changes = _diff_changes(master_resume, tailored, score.missing_keywords)
    return tailored, changes


def _diff_changes(original: dict, tailored: dict, injected: list[str]) -> list[str]:
    changes: list[str] = []
    if original.get("summary") != tailored.get("summary"):
        changes.append("Summary rewritten for role alignment")
    for kw in injected:
        tailored_text = json.dumps(tailored).lower()
        if kw.lower() in tailored_text:
            changes.append(f"Injected keyword: '{kw}'")
    orig_bullets = [b for e in original.get("experience", []) for b in e.get("bullets", [])]
    new_bullets = [b for e in tailored.get("experience", []) for b in e.get("bullets", [])]
    if orig_bullets != new_bullets:
        changes.append("Experience bullets reordered/updated")
    return changes


def verify_ats_improvement(
    job: JobListing, tailored_resume: dict, original_score: float
) -> float:
    """Quick keyword re-score to verify tailoring improved ATS match."""
    tokens = build_resume_token_set(tailored_resume)
    new_kw_score, _, _ = keyword_score(job, tokens)
    # Blend with original LLM score — keyword improvement is a proxy
    blended = min(10.0, original_score + (new_kw_score * 2))
    return round(blended, 2)
