"""
Stub for JSearch (RapidAPI) — drop-in replacement for JobSpySource.
Uncomment and populate when you have a RapidAPI key.
"""
# import httpx
# from src.models.schemas import JobListing
# from src.sources.base import JobDataSource
#
# class JSearchSource(JobDataSource):
#     BASE_URL = "https://jsearch.p.rapidapi.com/search"
#
#     def __init__(self, api_key: str):
#         self._headers = {
#             "X-RapidAPI-Key": api_key,
#             "X-RapidAPI-Host": "jsearch.p.rapidapi.com",
#         }
#
#     def search(self, keywords, locations, hours_old, results_per_source,
#                job_types, remote_filter, min_salary) -> list[JobListing]:
#         results = []
#         for keyword in keywords:
#             for location in locations:
#                 resp = httpx.get(self.BASE_URL, headers=self._headers, params={
#                     "query": f"{keyword} in {location}",
#                     "date_posted": "today",
#                     "num_pages": 1,
#                 })
#                 resp.raise_for_status()
#                 for item in resp.json().get("data", []):
#                     results.append(JobListing(
#                         id=item["job_id"],
#                         title=item["job_title"],
#                         company=item["employer_name"],
#                         location=item.get("job_city", location),
#                         job_url=item["job_apply_link"],
#                         description=item.get("job_description", ""),
#                         source="jsearch",
#                         salary=None,
#                     ))
#         return results
