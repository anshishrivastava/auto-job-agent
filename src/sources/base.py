from abc import ABC, abstractmethod
from src.models.schemas import JobListing


class JobDataSource(ABC):
    """
    Swap implementations without touching the pipeline.
    Current: JobSpySource (scraping)
    Future:  JSearchSource (RapidAPI), ApifySource, etc.
    """

    @abstractmethod
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
        ...
