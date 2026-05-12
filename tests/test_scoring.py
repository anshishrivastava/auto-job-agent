"""Unit tests for keyword and embedding scoring."""
from src.models.schemas import JobListing
from src.scoring.keyword import build_resume_token_set, keyword_score

SAMPLE_RESUME = {
    "summary": "Senior ML Engineer specializing in RAG, LLM agents, and AWS infrastructure.",
    "experience": [
        {
            "title": "Senior ML Engineer",
            "company": "AWS GAIIC",
            "duration": "2025-Present",
            "bullets": ["Built RAG pipelines on AWS Bedrock", "Deployed LLM agents using SageMaker"],
            "skills_used": ["Python", "AWS Bedrock", "RAG", "LLM"],
        }
    ],
    "skills": {
        "languages": ["Python", "Scala"],
        "cloud": ["AWS", "GCP"],
    },
}

SAMPLE_JD = JobListing(
    id="test1",
    title="Senior ML Engineer",
    company="OpenAI",
    location="Remote",
    job_url="https://example.com",
    description="Looking for an ML engineer with experience in RAG systems, LLM agents, Python, and AWS. Experience with SageMaker preferred.",
    source="test",
)


def test_resume_token_set_includes_key_skills():
    tokens = build_resume_token_set(SAMPLE_RESUME)
    assert "python" in tokens
    assert "rag" in tokens


def test_keyword_score_returns_valid_range():
    tokens = build_resume_token_set(SAMPLE_RESUME)
    score, missing, present = keyword_score(SAMPLE_JD, tokens)
    assert 0.0 <= score <= 1.0
    assert isinstance(missing, list)
    assert isinstance(present, list)


def test_keyword_score_high_for_matching_resume():
    tokens = build_resume_token_set(SAMPLE_RESUME)
    score, _, _ = keyword_score(SAMPLE_JD, tokens)
    assert score >= 0.3, f"Expected score >= 0.3, got {score}"


def test_keyword_score_low_for_mismatched_jd():
    mismatch_jd = JobListing(
        id="test2", title="iOS Developer", company="Apple", location="Cupertino",
        job_url="https://example.com",
        description="Swift, Objective-C, UIKit, SwiftUI, Xcode, Core Data, iOS SDK",
        source="test",
    )
    tokens = build_resume_token_set(SAMPLE_RESUME)
    score, _, _ = keyword_score(mismatch_jd, tokens)
    assert score < 0.4, f"Expected score < 0.4 for iOS JD, got {score}"
