from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class JobListing:
    id: str
    title: str
    company: str
    location: str
    job_url: str
    description: str
    source: str                          # "linkedin" | "indeed" | "glassdoor" etc.
    salary: Optional[str] = None
    posted_at: Optional[datetime] = None
    applicant_count: Optional[int] = None
    easy_apply: Optional[bool] = None
    is_remote: Optional[bool] = None


@dataclass
class ATSScore:
    keyword_score: float                 # 0–1, Stage 1
    embedding_score: float               # 0–1, Stage 2
    llm_score: float                     # 0–10, Stage 3
    overall_score: float                 # 0–10, weighted final
    missing_keywords: list[str] = field(default_factory=list)
    present_keywords: list[str] = field(default_factory=list)
    reasoning: str = ""
    seniority_match: bool = True
    visa_sponsorship: Optional[bool] = None


@dataclass
class ReferralMessages:
    connection_request: str              # ≤300 chars for LinkedIn
    inmail: str
    cold_email_subject: str
    cold_email_body: str


@dataclass
class TailoredApplication:
    job: JobListing
    score: ATSScore
    tailored_resume_path: str
    changes_made: list[str]
    referral_messages: ReferralMessages
    final_ats_score: float               # re-scored after tailoring


@dataclass
class RunResult:
    run_id: str
    run_at: datetime
    total_fetched: int
    passed_keyword_filter: int
    passed_embedding_filter: int
    passed_ats_threshold: int            # → Telegram
    near_misses: int                     # → Email
    applications: list[TailoredApplication] = field(default_factory=list)
    near_miss_jobs: list[tuple[JobListing, ATSScore]] = field(default_factory=list)
