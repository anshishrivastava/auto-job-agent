"""
Tiered ATS scoring pipeline.

Stage 1  keyword match      — drop jobs with score < KEYWORD_MIN  (~10ms, free)
Stage 2  embedding similarity — drop bottom half of survivors       (~150ms, free)
Stage 3  LLM holistic score  — score survivors 0-10, keep > threshold (~3s, ~$0.003)
"""
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.models.schemas import ATSScore, JobListing
from src.scoring.embedding import embedding_score
from src.scoring.keyword import build_resume_token_set, keyword_score
from src.scoring.llm_scorer import llm_score

logger = logging.getLogger(__name__)

KEYWORD_MIN = 0.25      # Stage 1 cutoff (25% keyword overlap)
EMBEDDING_KEEP = 0.5    # Stage 2: keep top 50% by embedding score
LLM_WORKERS = 4         # parallel LLM calls


def run_scoring_pipeline(
    jobs: list[JobListing],
    resume: dict,
    ats_threshold: float,
    near_miss_min: float,
) -> tuple[list[tuple[JobListing, ATSScore]], list[tuple[JobListing, ATSScore]]]:
    """
    Returns:
        above_threshold: jobs scoring >= ats_threshold  → Telegram
        near_misses:     jobs scoring in [near_miss_min, ats_threshold) → Email
    """
    resume_tokens = build_resume_token_set(resume)

    # ── Stage 1: keyword pre-filter ──────────────────────────────────────────
    stage1: list[tuple[JobListing, float, list[str], list[str]]] = []
    for job in jobs:
        score, missing, present = keyword_score(job, resume_tokens)
        if score >= KEYWORD_MIN:
            stage1.append((job, score, missing, present))

    logger.info("Stage 1 (keyword): %d/%d jobs passed", len(stage1), len(jobs))

    # ── Stage 2: embedding similarity ────────────────────────────────────────
    scored: list[tuple[JobListing, float, float, list[str], list[str]]] = []
    for job, kw_score, missing, present in stage1:
        emb = embedding_score(job, resume)
        scored.append((job, kw_score, emb, missing, present))

    scored.sort(key=lambda x: x[2], reverse=True)
    keep_n = max(1, int(len(scored) * EMBEDDING_KEEP))
    stage2 = scored[:keep_n]
    logger.info("Stage 2 (embedding): %d/%d jobs kept", len(stage2), len(scored))

    # ── Stage 3: LLM holistic scoring (parallel) ─────────────────────────────
    above_threshold: list[tuple[JobListing, ATSScore]] = []
    near_misses: list[tuple[JobListing, ATSScore]] = []

    def _score_one(item):
        job, kw_s, emb_s, missing, present = item
        ats = llm_score(job, resume, missing, present)
        ats.keyword_score = kw_s
        ats.embedding_score = emb_s
        return job, ats

    with ThreadPoolExecutor(max_workers=LLM_WORKERS) as pool:
        futures = {pool.submit(_score_one, item): item for item in stage2}
        for future in as_completed(futures):
            try:
                job, ats = future.result()
                if ats.overall_score >= ats_threshold:
                    above_threshold.append((job, ats))
                elif ats.overall_score >= near_miss_min:
                    near_misses.append((job, ats))
            except Exception as exc:
                logger.warning("LLM stage failed for a job: %s", exc)

    above_threshold.sort(key=lambda x: x[1].overall_score, reverse=True)
    near_misses.sort(key=lambda x: x[1].overall_score, reverse=True)

    logger.info(
        "Stage 3 (LLM): %d above threshold (%.1f), %d near-misses",
        len(above_threshold), ats_threshold, len(near_misses),
    )
    return above_threshold, near_misses
