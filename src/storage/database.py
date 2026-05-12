"""
SQLite storage via SQLAlchemy.
Tracks runs, scored jobs, applications, skipped jobs (feedback loop).
"""
import json
import logging
import os
from datetime import datetime
from pathlib import Path

from sqlalchemy import (Boolean, Column, DateTime, Float, Integer, String,
                        Text, create_engine)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from src.models.schemas import ATSScore, JobListing, TailoredApplication

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).resolve().parents[2] / "output" / "jobs.db"


class Base(DeclarativeBase):
    pass


class RunRecord(Base):
    __tablename__ = "runs"
    id = Column(String, primary_key=True)
    run_at = Column(DateTime, default=datetime.utcnow)
    total_fetched = Column(Integer)
    passed_keyword = Column(Integer)
    passed_embedding = Column(Integer)
    passed_threshold = Column(Integer)
    near_misses = Column(Integer)


class JobRecord(Base):
    __tablename__ = "jobs"
    id = Column(String, primary_key=True)
    run_id = Column(String)
    title = Column(String)
    company = Column(String)
    location = Column(String)
    salary = Column(String)
    job_url = Column(String)
    source = Column(String)
    posted_at = Column(DateTime)
    overall_score = Column(Float)
    keyword_score = Column(Float)
    embedding_score = Column(Float)
    llm_score = Column(Float)
    missing_keywords = Column(Text)    # JSON list
    reasoning = Column(Text)
    seniority_match = Column(Boolean)
    visa_sponsorship = Column(Boolean)
    resume_pdf_path = Column(String)
    category = Column(String)          # "above_threshold" | "near_miss" | "filtered"
    skipped = Column(Boolean, default=False)
    force_include = Column(Boolean, default=False)


_engine = None
_SessionLocal = None


def init_db():
    global _engine, _SessionLocal
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    _engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)
    Base.metadata.create_all(_engine)
    _SessionLocal = sessionmaker(bind=_engine)
    logger.info("Database ready at %s", DB_PATH)


def get_session() -> Session:
    if _SessionLocal is None:
        init_db()
    return _SessionLocal()


def save_run(run_id: str, stats: dict):
    with get_session() as session:
        session.add(RunRecord(id=run_id, **stats))
        session.commit()


def save_jobs(
    run_id: str,
    above: list[tuple[JobListing, ATSScore]],
    near_misses: list[tuple[JobListing, ATSScore]],
    applications: list[TailoredApplication],
):
    pdf_map = {app.job.id: app.tailored_resume_path for app in applications}

    with get_session() as session:
        for job, score in above + near_misses:
            cat = "above_threshold" if (job, score) in above else "near_miss"
            session.merge(JobRecord(
                id=job.id,
                run_id=run_id,
                title=job.title,
                company=job.company,
                location=job.location,
                salary=job.salary,
                job_url=job.job_url,
                source=job.source,
                posted_at=job.posted_at,
                overall_score=score.overall_score,
                keyword_score=score.keyword_score,
                embedding_score=score.embedding_score,
                llm_score=score.llm_score,
                missing_keywords=json.dumps(score.missing_keywords),
                reasoning=score.reasoning,
                seniority_match=score.seniority_match,
                visa_sponsorship=score.visa_sponsorship,
                resume_pdf_path=pdf_map.get(job.id),
                category=cat,
            ))
        session.commit()


def mark_skipped(job_id: str):
    with get_session() as session:
        rec = session.get(JobRecord, job_id)
        if rec:
            rec.skipped = True
            session.commit()


def mark_force_include(job_id: str):
    with get_session() as session:
        rec = session.get(JobRecord, job_id)
        if rec:
            rec.force_include = True
            session.commit()
