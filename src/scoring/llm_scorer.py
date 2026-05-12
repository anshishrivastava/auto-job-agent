"""
Stage 3 — LLM holistic scoring via Claude Haiku (~3s/job, ~$0.003/job).
Runs only on top candidates that passed stages 1 & 2.
Returns a 0–10 score with breakdown, missing keywords, visa signal, and reasoning.
"""
import json
import logging
import os

import anthropic

from src.models.schemas import ATSScore, JobListing

logger = logging.getLogger(__name__)

_CLIENT: anthropic.Anthropic | None = None


def _client() -> anthropic.Anthropic:
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _CLIENT


_SYSTEM = """\
You are an expert ATS (Applicant Tracking System) evaluator and career coach.
Given a job description and a candidate's resume, score the match and return ONLY valid JSON.
No markdown, no explanation outside the JSON object.
"""

_PROMPT_TEMPLATE = """\
## Job Description
{jd}

## Candidate Resume (plain text)
{resume}

## Task
Score this candidate for this specific role. Return exactly this JSON schema:
{{
  "overall_score": <float 0-10>,
  "keyword_match_score": <float 0-10>,
  "skills_fit_score": <float 0-10>,
  "experience_relevance_score": <float 0-10>,
  "seniority_match_score": <float 0-10>,
  "missing_keywords": [<top 5 keywords in JD not in resume>],
  "present_keywords": [<top 5 strong keyword matches>],
  "seniority_match": <true|false>,
  "visa_sponsorship_mentioned": <true|false|null>,
  "reasoning": "<2-3 sentence explanation of the score>"
}}
"""


def _resume_to_text(resume: dict) -> str:
    lines: list[str] = []
    p = resume.get("personal", {})
    lines.append(f"{p.get('name', '')} | {p.get('location', '')} | {p.get('email', '')}")
    lines.append(resume.get("summary", ""))
    for exp in resume.get("experience", []):
        lines.append(f"\n{exp['title']} @ {exp['company']} ({exp['duration']})")
        for b in exp.get("bullets", []):
            lines.append(f"  - {b}")
        lines.append(f"  Skills: {', '.join(exp.get('skills_used', []))}")
    lines.append("\nSkills:")
    for group, items in resume.get("skills", {}).items():
        lines.append(f"  {group}: {', '.join(items)}")
    return "\n".join(lines)


def llm_score(
    job: JobListing,
    resume: dict,
    stage1_missing: list[str],
    stage1_present: list[str],
) -> ATSScore:
    resume_text = _resume_to_text(resume)
    jd_text = f"Title: {job.title}\nCompany: {job.company}\n\n{job.description[:3000]}"

    prompt = _PROMPT_TEMPLATE.format(jd=jd_text, resume=resume_text)

    try:
        response = _client().messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            system=_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        data = json.loads(raw)
    except Exception as exc:
        logger.warning("LLM scoring failed for '%s': %s — using fallback", job.title, exc)
        return ATSScore(
            keyword_score=0.0,
            embedding_score=0.0,
            llm_score=5.0,
            overall_score=5.0,
            missing_keywords=stage1_missing,
            present_keywords=stage1_present,
            reasoning="LLM scoring unavailable.",
        )

    overall = float(data.get("overall_score", 5.0))
    return ATSScore(
        keyword_score=float(data.get("keyword_match_score", 5.0)) / 10,
        embedding_score=0.0,   # filled by pipeline after this call
        llm_score=overall,
        overall_score=overall,
        missing_keywords=data.get("missing_keywords", stage1_missing)[:8],
        present_keywords=data.get("present_keywords", stage1_present)[:8],
        reasoning=data.get("reasoning", ""),
        seniority_match=bool(data.get("seniority_match", True)),
        visa_sponsorship=data.get("visa_sponsorship_mentioned"),
    )
