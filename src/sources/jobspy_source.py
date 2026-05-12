import hashlib
import logging
from datetime import datetime, timezone

import pandas as pd
from jobspy import scrape_jobs

from src.models.schemas import JobListing
from src.sources.base import JobDataSource

logger = logging.getLogger(__name__)

# jobspy remote filter mapping
_REMOTE_MAP = {
    "remote": True,
    "onsite": False,
    "hybrid": None,   # jobspy has no hybrid filter — include all, LLM stage handles it
}


def _make_id(title: str, company: str, url: str) -> str:
    raw = f"{title}|{company}|{url}"
    return hashlib.md5(raw.encode()).hexdigest()[:12]


def _parse_salary(row: pd.Series) -> str | None:
    min_s = row.get("min_amount")
    max_s = row.get("max_amount")
    currency = row.get("currency", "USD") or "USD"
    interval = row.get("interval", "yearly") or "yearly"
    if pd.notna(min_s) and pd.notna(max_s):
        return f"{currency} {int(min_s):,}–{int(max_s):,} / {interval}"
    if pd.notna(min_s):
        return f"{currency} {int(min_s):,}+ / {interval}"
    return None


class JobSpySource(JobDataSource):
    SITES = ["linkedin", "indeed", "glassdoor"]

    def search(
        self,
        keywords: list[str],
        locations: list[str],
        hours_old: int,
        results_per_source: int,
        job_types: list[str],
        remote_filter: str | None,
        min_salary: int | None,
    ) -> list[JobListing]:
        seen_ids: set[str] = set()
        results: list[JobListing] = []

        is_remote = _REMOTE_MAP.get(remote_filter) if remote_filter else None

        for keyword in keywords:
            for location in locations:
                try:
                    df = scrape_jobs(
                        site_name=self.SITES,
                        search_term=keyword,
                        location=location,
                        results_wanted=results_per_source,
                        hours_old=hours_old,
                        job_type=job_types[0] if job_types else None,
                        is_remote=is_remote,
                        linkedin_fetch_description=True,
                        verbose=0,
                    )
                except Exception as exc:
                    logger.warning("jobspy scrape failed for '%s'/'%s': %s", keyword, location, exc)
                    continue

                if df is None or df.empty:
                    continue

                for _, row in df.iterrows():
                    url = str(row.get("job_url", "")) or ""
                    title = str(row.get("title", "")) or ""
                    company = str(row.get("company", "")) or ""
                    description = str(row.get("description", "")) or ""

                    if not url or not description:
                        continue

                    job_id = _make_id(title, company, url)
                    if job_id in seen_ids:
                        continue
                    seen_ids.add(job_id)

                    posted_raw = row.get("date_posted")
                    posted_at: datetime | None = None
                    if pd.notna(posted_raw):
                        try:
                            posted_at = pd.Timestamp(posted_raw).to_pydatetime()
                            if posted_at.tzinfo is None:
                                posted_at = posted_at.replace(tzinfo=timezone.utc)
                        except Exception:
                            pass

                    salary = _parse_salary(row)
                    if min_salary and salary is None:
                        pass  # keep — salary may be in description; LLM stage will check

                    results.append(
                        JobListing(
                            id=job_id,
                            title=title,
                            company=company,
                            location=str(row.get("location", location)),
                            job_url=url,
                            description=description,
                            source=str(row.get("site", "unknown")),
                            salary=salary,
                            posted_at=posted_at,
                            applicant_count=None,  # jobspy doesn't expose this
                            easy_apply=bool(row.get("is_easy_apply")) if pd.notna(row.get("is_easy_apply")) else None,
                            is_remote=bool(row.get("is_remote")) if pd.notna(row.get("is_remote")) else None,
                        )
                    )

        logger.info("JobSpySource fetched %d unique jobs", len(results))
        return results
