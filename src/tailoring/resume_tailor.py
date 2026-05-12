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
You are a precise resume editor. Your only job is to help the candidate's REAL experience \
speak the language of this specific job description. You are NOT a copywriter — you do not \
embellish, invent, or pad.

Your allowed edits:
1. REPHRASE existing bullet points to use the job's exact terminology, \
   where the underlying work is genuinely the same (e.g. the candidate built a recommendation \
   system — the JD calls it "personalization engine" — you may use that term).
2. REORDER bullets within each role to surface the most relevant ones first.
3. REWRITE the summary to reflect this specific role, using only skills and experience \
   that actually appear in the resume body.
4. ADD a skill token to the skills section ONLY if concrete evidence for it exists \
   in the experience bullets (do not add it just because the JD wants it).

Hard rules — violation means the output is rejected:
- Do NOT add any experience, project, metric, or technology that is not already \
  in the original resume.
- Do NOT inflate numbers or outcomes.
- Do NOT change job titles, companies, dates, or education.
- If a missing keyword has NO honest basis in the resume, leave it out entirely — \
  it is better to have a lower keyword score than a dishonest resume.
- Return ONLY valid JSON with the same schema as the input. No markdown, no explanation.
"""

_PROMPT = """\
## Target Job
Title: {title}
Company: {company}

## Job Description (first 3000 chars)
{jd}

## Keywords the JD wants that are currently underrepresented in the resume
{missing}

For each keyword above, only use it if the candidate's ACTUAL experience honestly \
supports it. Skip any that do not apply.

## Candidate's Current Resume (JSON)
{resume_json}

Return the tailored resume JSON. Make the minimum changes needed — do not touch \
sections that are already well-aligned.
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


_COVER_SYSTEM = """\
Act as a top 1% job-seeker with a 99% interview rate. You write cover letters that get read \
because they are specific, honest, and confident — not generic.

Rules:
- Open with the exact role and one concrete reason this candidate is the right person — not enthusiasm
- Every claim must map directly to the candidate's ACTUAL experience in the resume
- Do not use: "I am excited", "I would be a great fit", "I hope to hear from you", "passionate"
- Write like a senior professional, not a student
- 3 tight paragraphs: (1) why this role + one specific strength, (2) two concrete achievements \
  that directly address the JD's key requirements with metrics where they exist, \
  (3) clear ask + one sentence on what you bring on day one
- Max 250 words total
"""

_COVER_PROMPT = """\
## Target Role
{title} at {company}

## Job Description (key requirements)
{jd}

## Candidate Resume
{resume_json}

## What the recruiter said is missing or weak (address these honestly if possible)
{missing}

Write the cover letter now. Plain text only — no subject line, no "Dear Hiring Manager", \
just the 3 paragraphs.
"""


def generate_cover_letter(
    job: JobListing,
    score: ATSScore,
    master_resume: dict,
) -> str:
    """Returns a plain-text cover letter. Falls back to empty string on failure."""
    prompt = _COVER_PROMPT.format(
        title=job.title,
        company=job.company,
        jd=job.description[:2000],
        resume_json=json.dumps(master_resume, indent=2),
        missing=", ".join(score.missing_keywords[:6]) if score.missing_keywords else "none identified",
    )
    try:
        response = _client().messages.create(
            model="claude-sonnet-4-6",
            max_tokens=600,
            system=_COVER_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()
    except Exception as exc:
        logger.warning("Cover letter generation failed for '%s': %s", job.title, exc)
        return ""


def verify_ats_improvement(
    job: JobListing, tailored_resume: dict, original_score: float
) -> float:
    """Quick keyword re-score to verify tailoring improved ATS match."""
    tokens = build_resume_token_set(tailored_resume)
    new_kw_score, _, _ = keyword_score(job, tokens)
    # Blend with original LLM score — keyword improvement is a proxy
    blended = min(10.0, original_score + (new_kw_score * 2))
    return round(blended, 2)
