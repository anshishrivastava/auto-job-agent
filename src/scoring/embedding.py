"""
Stage 2 — semantic similarity via sentence-transformers (~150ms/job, free/local).
Runs only on jobs that passed the keyword pre-filter.
"""
import logging
from functools import lru_cache

import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

from src.models.schemas import JobListing

logger = logging.getLogger(__name__)
MODEL_NAME = "all-MiniLM-L6-v2"


@lru_cache(maxsize=1)
def _model() -> SentenceTransformer:
    logger.info("Loading embedding model '%s'…", MODEL_NAME)
    return SentenceTransformer(MODEL_NAME)


def _resume_text(resume: dict) -> str:
    parts: list[str] = [resume.get("summary", "")]
    for exp in resume.get("experience", []):
        parts.append(exp.get("title", ""))
        parts.extend(exp.get("bullets", []))
        parts.extend(exp.get("skills_used", []))
    for group in resume.get("skills", {}).values():
        parts.extend(group)
    return " ".join(parts)


def embedding_score(job: JobListing, resume: dict) -> float:
    """Returns cosine similarity (0–1) between resume and job description."""
    model = _model()
    resume_text = _resume_text(resume)
    jd_text = job.title + " " + job.description[:2000]  # cap tokens
    vecs = model.encode([resume_text, jd_text], show_progress_bar=False)
    score = float(cosine_similarity([vecs[0]], [vecs[1]])[0][0])
    return round(max(0.0, min(1.0, score)), 4)
