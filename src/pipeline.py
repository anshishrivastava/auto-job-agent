"""
Main orchestrator — runs the full daily pipeline end-to-end.
"""
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml

from src.models.schemas import RunResult, TailoredApplication
from src.notifications.email_sender import send_near_miss_digest
from src.notifications.telegram_bot import send_digest, send_error_alert
from src.scoring.pipeline import run_scoring_pipeline
from src.sources.jobspy_source import JobSpySource
from src.storage.database import init_db, save_jobs, save_run
from src.tailoring.pdf_generator import generate_pdf
from src.tailoring.referral import generate_referral_messages
from src.tailoring.resume_tailor import generate_cover_letter, tailor_resume, verify_ats_improvement

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "config.yaml"
RESUME_PATH = Path(__file__).resolve().parents[2] / "config" / "resume.json"


def _load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)["preferences"]


def _load_resume() -> dict:
    with open(RESUME_PATH) as f:
        return json.load(f)


def run_pipeline(dry_run: bool = False) -> RunResult:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
    run_date = datetime.now(timezone.utc).strftime("%b %d, %Y")

    logger.info("═" * 50)
    logger.info("Job Agent run started: %s", run_id)

    init_db()
    cfg = _load_config()
    master_resume = _load_resume()

    # ── 1. Fetch jobs ──────────────────────────────────────────────────────
    source = JobSpySource()
    jobs = source.search(
        keywords=cfg["job_keywords"],
        locations=cfg["locations"],
        hours_old=cfg["hours_old"],
        results_per_source=cfg["results_per_source"],
        job_types=cfg["job_types"],
        remote_filter=cfg.get("remote_filter"),
        min_salary=cfg.get("min_salary"),
    )
    logger.info("Fetched %d jobs total", len(jobs))

    if not jobs:
        logger.warning("No jobs found — check network or scraper.")
        send_error_alert("No jobs fetched in today's run. Check scraper.")
        return RunResult(run_id=run_id, run_at=datetime.now(timezone.utc),
                         total_fetched=0, passed_keyword_filter=0,
                         passed_embedding_filter=0, passed_ats_threshold=0, near_misses=0)

    # ── 2. Score jobs ──────────────────────────────────────────────────────
    above_threshold, near_misses = run_scoring_pipeline(
        jobs=jobs,
        resume=master_resume,
        ats_threshold=cfg["ats_threshold"],
        near_miss_min=cfg["near_miss_min"],
    )

    # Respect top_k
    top_k = cfg.get("top_k", 8)
    above_threshold = above_threshold[:top_k]

    # ── 3. Tailor resumes + generate PDFs ─────────────────────────────────
    applications: list[TailoredApplication] = []

    for job, score in above_threshold:
        if dry_run:
            logger.info("[DRY RUN] Would tailor resume for: %s @ %s", job.title, job.company)
            continue

        tailored_resume, changes = tailor_resume(job, score, master_resume)
        pdf_path = generate_pdf(tailored_resume, job.title, job.company, job.id)
        final_score = verify_ats_improvement(job, tailored_resume, score.overall_score)
        cover_letter = generate_cover_letter(job, score, tailored_resume)
        referral = generate_referral_messages(job, tailored_resume, score.present_keywords)

        applications.append(TailoredApplication(
            job=job,
            score=score,
            tailored_resume_path=pdf_path,
            changes_made=changes,
            referral_messages=referral,
            final_ats_score=final_score,
            cover_letter=cover_letter,
        ))

    # ── 4. Save to DB ──────────────────────────────────────────────────────
    if not dry_run:
        save_run(run_id, {
            "run_at": datetime.now(timezone.utc),
            "total_fetched": len(jobs),
            "passed_keyword": len(above_threshold) + len(near_misses),
            "passed_embedding": len(above_threshold) + len(near_misses),
            "passed_threshold": len(above_threshold),
            "near_misses": len(near_misses),
        })
        save_jobs(run_id, above_threshold, near_misses, applications)

    # ── 5. Send notifications ──────────────────────────────────────────────
    run_stats = {
        "date": run_date,
        "total_fetched": len(jobs),
        "near_misses": len(near_misses),
        "threshold": cfg["ats_threshold"],
    }

    if not dry_run:
        send_digest(applications, run_stats)
        send_near_miss_digest(near_misses, run_date, cfg["ats_threshold"])

    result = RunResult(
        run_id=run_id,
        run_at=datetime.now(timezone.utc),
        total_fetched=len(jobs),
        passed_keyword_filter=len(above_threshold) + len(near_misses),
        passed_embedding_filter=len(above_threshold) + len(near_misses),
        passed_ats_threshold=len(above_threshold),
        near_misses=len(near_misses),
        applications=applications,
        near_miss_jobs=near_misses,
    )

    logger.info(
        "Run complete: %d fetched → %d above threshold → %d near-misses",
        len(jobs), len(above_threshold), len(near_misses),
    )
    logger.info("═" * 50)
    return result
