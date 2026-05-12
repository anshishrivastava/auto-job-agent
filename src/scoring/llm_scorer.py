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
Act as a recruiter hiring for the role described below. Your job is to decide — honestly and \
specifically — whether you would move this candidate to an interview.

You are experienced, direct, and do not use filler language. You evaluate based on:
- Actual experience depth vs. what the role requires
- Seniority signal (titles, scope, team size, impact)
- Skill overlap with the specific tech stack and domain
- Red flags (job-hopping, gaps, inflated language, mismatch)

Return ONLY valid JSON — no markdown, no text outside the JSON object.
"""

_PROMPT_TEMPLATE = """\
## Job Description
{jd}

## Candidate Resume
{resume}

## Your Task
You are the recruiter for this exact role. Assess whether you would invite this candidate to \
an interview. Be specific — reference actual lines from the resume and JD.

Return exactly this JSON:
{{
  "would_interview": <true|false>,
  "interview_verdict": "<Yes | Likely | Unlikely | No>",
  "interview_probability": <integer 0-100, your estimated % chance this candidate gets an interview>,
  "overall_score": <float 0-10>,
  "keyword_match_score": <float 0-10>,
  "experience_relevance_score": <float 0-10>,
  "seniority_match_score": <float 0-10>,
  "missing_keywords": [<up to 6 specific skills/terms the JD needs that the resume lacks>],
  "present_keywords": [<up to 6 strong matches between JD requirements and resume>],
  "seniority_match": <true|false>,
  "visa_sponsorship_mentioned": <true|false|null>,
  "reasoning": "<3-4 sentences: what makes this candidate strong or weak for THIS role, \
citing specific evidence from both the JD and resume. If no, explain exactly what is missing \
and what would change your decision.>"
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
        interview_verdict=data.get("interview_verdict", "Unknown"),
        interview_probability=int(data.get("interview_probability", 0)),
    )
