"""
Generates three referral message variants per job using Claude Haiku.
"""
import json
import logging
import os
from dataclasses import asdict

import anthropic

from src.models.schemas import JobListing, ReferralMessages

logger = logging.getLogger(__name__)

_CLIENT: anthropic.Anthropic | None = None


def _client() -> anthropic.Anthropic:
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _CLIENT


_SYSTEM = """\
You are a professional career coach writing outreach messages for a job applicant.
Write concise, authentic messages that highlight specific alignment between the candidate and role.
Avoid generic phrases like "I am excited" or "I would be a great fit".
Return ONLY valid JSON, no markdown.
"""

_PROMPT = """\
## Candidate
Name: {name}
Current Role: {current_role}
Top strengths relevant to this job: {strengths}

## Target Job
Title: {title}
Company: {company}
Key requirements: {requirements}

Generate three outreach messages and return this exact JSON:
{{
  "connection_request": "<LinkedIn connection request, max 280 chars, first-person, specific>",
  "inmail": "<LinkedIn InMail, 3-4 sentences, reference specific JD requirements and candidate achievements>",
  "cold_email_subject": "<email subject line, under 60 chars>",
  "cold_email_body": "<3 short paragraphs: hook referencing the role, 2 specific achievements relevant to JD, clear ask>"
}}
"""


def generate_referral_messages(
    job: JobListing,
    resume: dict,
    present_keywords: list[str],
) -> ReferralMessages:
    personal = resume.get("personal", {})
    name = personal.get("name", "The candidate")
    current_exp = resume.get("experience", [{}])[0]
    current_role = f"{current_exp.get('title', '')} at {current_exp.get('company', '')}"
    strengths = ", ".join(present_keywords[:6]) if present_keywords else "ML engineering, GenAI, AWS"
    requirements = " ".join(job.description.split()[:80])  # first ~80 words of JD

    prompt = _PROMPT.format(
        name=name,
        current_role=current_role,
        strengths=strengths,
        title=job.title,
        company=job.company,
        requirements=requirements,
    )

    try:
        response = _client().messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=600,
            system=_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
        data = json.loads(raw)
        return ReferralMessages(
            connection_request=data.get("connection_request", "")[:300],
            inmail=data.get("inmail", ""),
            cold_email_subject=data.get("cold_email_subject", f"Re: {job.title} at {job.company}"),
            cold_email_body=data.get("cold_email_body", ""),
        )
    except Exception as exc:
        logger.warning("Referral generation failed for '%s': %s", job.title, exc)
        return ReferralMessages(
            connection_request=f"Hi, I'm applying for the {job.title} role at {job.company} and would love to connect.",
            inmail=f"I'm interested in the {job.title} position at {job.company}.",
            cold_email_subject=f"Interest in {job.title} — {job.company}",
            cold_email_body="",
        )
