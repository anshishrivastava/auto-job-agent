"""
Generates three referral message variants per job using Claude Haiku.
"""
import json
import logging
import os
from dataclasses import asdict

import anthropic

from src.models.schemas import JobListing, RecruiterTarget, ReferralMessages

logger = logging.getLogger(__name__)

_CLIENT: anthropic.Anthropic | None = None


def _client() -> anthropic.Anthropic:
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _CLIENT


_SYSTEM = """\
Act as a networking strategist who helps job seekers get interviews through direct outreach — \
not just applications. You identify the right people to contact at a company and craft messages \
that are specific, confident, and human — never generic or sycophantic.

Rules:
- Never write "I am excited" / "I would be a great fit" / "I hope this finds you well"
- Every message must reference something specific from the candidate's background AND the role
- Connection requests must be under 280 characters
- Return ONLY valid JSON, no markdown
"""

_PROMPT = """\
## Candidate
Name: {name}
Current Role: {current_role}
Strongest relevant experience: {strengths}

## Target Job
Title: {title}
Company: {company}
Key requirements (first 120 words of JD): {requirements}

## Your Task
Identify 3 people the candidate should reach out to on LinkedIn to maximise interview chances. \
Choose roles like: the hiring manager for this team, a technical recruiter at {company}, \
and a senior engineer or team lead in the relevant org.

For each person, provide a LinkedIn search tip to find them, plus a connection message and InMail.

Also generate a cold email for when LinkedIn fails.

Return exactly this JSON:
{{
  "recruiter_targets": [
    {{
      "role": "<job title to search for on LinkedIn, e.g. 'Engineering Manager, ML Platform'>",
      "search_tip": "<how to find this person, e.g. 'Search LinkedIn: {company} + ML Manager'>",
      "connection_message": "<max 280 chars, first-person, reference one specific JD requirement \
and one specific candidate achievement>",
      "inmail": "<3-4 sentences: open with the specific role + why you're reaching out, \
cite one concrete achievement that maps to their team's work, end with a specific ask>"
    }},
    {{
      "role": "<second target>",
      "search_tip": "<search tip>",
      "connection_message": "<max 280 chars>",
      "inmail": "<3-4 sentences>"
    }},
    {{
      "role": "<third target>",
      "search_tip": "<search tip>",
      "connection_message": "<max 280 chars>",
      "inmail": "<3-4 sentences>"
    }}
  ],
  "connection_request": "<fallback LinkedIn connection request, max 280 chars>",
  "inmail": "<fallback InMail, 3-4 sentences>",
  "cold_email_subject": "<subject, under 60 chars, specific — not 'Following up'>",
  "cold_email_body": "<3 short paragraphs: hook with specific role context, \
2 achievements that directly map to JD requirements, clear ask with one easy next step>"
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
            max_tokens=1200,
            system=_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
        data = json.loads(raw)

        targets = [
            RecruiterTarget(
                role=t.get("role", ""),
                search_tip=t.get("search_tip", ""),
                connection_message=t.get("connection_message", "")[:300],
                inmail=t.get("inmail", ""),
            )
            for t in data.get("recruiter_targets", [])
        ]

        return ReferralMessages(
            connection_request=data.get("connection_request", "")[:300],
            inmail=data.get("inmail", ""),
            cold_email_subject=data.get("cold_email_subject", f"Re: {job.title} at {job.company}"),
            cold_email_body=data.get("cold_email_body", ""),
            recruiter_targets=targets,
        )
    except Exception as exc:
        logger.warning("Referral generation failed for '%s': %s", job.title, exc)
        return ReferralMessages(
            connection_request=f"Hi, I'm applying for the {job.title} role at {job.company} and would love to connect.",
            inmail=f"I'm interested in the {job.title} position at {job.company}.",
            cold_email_subject=f"Interest in {job.title} — {job.company}",
            cold_email_body="",
        )
