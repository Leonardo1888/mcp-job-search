"""
MCP Server 2 - Job Search
Searches job offers based on CV skills using the Adzuna API.
Docs: https://developer.adzuna.com/activedocs

Tools:
    search_jobs_by_skills  — primary search using top CV skills
    search_jobs_by_title   — fallback search using a synthesized job title
"""

import logging
import os
import httpx
from pathlib import Path
from mcp.server.fastmcp import FastMCP
import json
from dotenv import load_dotenv

#  Absolute paths 
ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    filename=LOG_DIR / "server2-adzuna.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

#  Config 
ADZUNA_APPLICATION_ID  = os.getenv("ADZUNA_APPLICATION_ID")
ADZUNA_APPLICATION_KEY = os.getenv("ADZUNA_APPLICATION_KEY")
ADZUNA_API_BASE        = "https://api.adzuna.com/v1/api"

mcp2 = FastMCP("job-matcher")


#  Adzuna API client 

class AdzunaClient:
    """
    Handles all HTTP calls to the Adzuna Jobs API.
    Always strips empty params before sending to avoid polluting the query.
    Docs: https://developer.adzuna.com/activedocs#/default/search
    """

    async def _get(self, country: str, params: dict) -> dict:
        """Base GET call to /jobs/{country}/search/1/. Merges auth + search params."""
        url = f"{ADZUNA_API_BASE}/jobs/{country}/search/1/"
        full_params = {
            "app_id":            ADZUNA_APPLICATION_ID,
            "app_key":           ADZUNA_APPLICATION_KEY,
            "results_per_page":  10,
            **params,
        }
        # Remove empty/None values — Adzuna treats empty strings as active filters
        full_params = {k: v for k, v in full_params.items() if v}

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, params=full_params)
            response.raise_for_status()
            return response.json()

    async def search_by_skills(self, what: str, what_or: str, country: str) -> dict:
        """Primary search: one mandatory skill + optional secondary skills."""
        return await self._get(country, {
            "what":    what,     # must appear in every result
            "what_or": what_or,  # at least one of these must appear
        })

    async def search_by_title(self, job_title: str, what_and: str, country: str) -> dict:
        """Fallback search: standard job title + optional reinforcing keyword."""
        return await self._get(country, {
            "what":     job_title,  # synthesized industry title
            "what_and": what_and,   # extra keyword that must also appear
        })


#  Helpers 

def _format(data: dict, source: str) -> str:
    """Normalizes Adzuna results into a clean, consistent JSON response."""
    jobs = data.get("results", [])
    logging.info(f"[{source}] Job offers found: {len(jobs)}")
    return json.dumps({
        "status":                 "success",
        "source":                 source,
        "total_job_offers_found": len(jobs),
        "jobOffers": [
            {
                "title":       job.get("title"),
                "company":     job.get("company", {}).get("display_name"),
                "location":    job.get("location", {}).get("display_name"),
                "description": job.get("description"),
                "url":         job.get("redirect_url"),
            }
            for job in jobs
        ],
    }, indent=2, ensure_ascii=False)


#  Tools 

@mcp2.tool()
async def search_jobs_by_skills(
    what: str,
    what_or: str,
    country: str = "it",
) -> str:
    """
    PRIMARY job search tool. Always call this FIRST, before search_jobs_by_title.
    Searches Adzuna using the candidate's most distinctive skills as keywords.

    How to build the query from a CV skill list:
    - `what`    -> pick the SINGLE most important/distinctive skill
                   (e.g. "Python", "React", "Machine Learning", "Kubernetes").
                   ONE keyword only — Adzuna requires this in every result.
                   Do NOT use generic terms like "programming" or "development".
    - `what_or` -> pick 2–4 complementary skills, space-separated
                   (e.g. "SQL PostgreSQL MongoDB").
                   At least one of these must appear in the result.
                   Do NOT paste the full CV skill list here.

    When to use this tool:
    - Always as the first job search step after extracting CV skills.

    When NOT to use this tool:
    - Do not retry with different skills if this returns 0 results.
      Instead, immediately call search_jobs_by_title as fallback.

    Args:
        what:    Single primary skill keyword, required in every result.
        what_or: 2–4 secondary skill keywords, space-separated.
        country: ISO 3166-1 alpha-2 country code (default: 'it' for Italy).
                 Examples: 'gb', 'us', 'de', 'fr', 'es'.

    Returns:
        JSON with total_job_offers_found and a list of jobOffers (title, company,
        location, description, url).
        If total_job_offers_found is 0, call search_jobs_by_title immediately.
    """
    try:
        data = await adzuna_client.search_by_skills(what, what_or, country)
        return _format(data, source="skills")
    except Exception as e:
        logging.error(f"search_jobs_by_skills failed: {e}")
        return json.dumps({"status": "error", "error": str(e)}, indent=2)


@mcp2.tool()
async def search_jobs_by_title(
    job_title: str,
    what_and: str = "",
    country: str = "it",
) -> str:
    """
    FALLBACK job search tool. Call this ONLY if search_jobs_by_skills returned 0 results.
    Searches Adzuna using a standard industry job title synthesized from the CV.

    How to build the query from a CV skill list:
    - `job_title` -> infer a standard industry job title that best fits the skill set.
                     Use common, well-known titles recruiters actually post:
                     "Full Stack Developer", "Data Scientist", "Frontend Engineer",
                     "Backend Developer", "DevOps Engineer", "Mobile Developer",
                     "Data Analyst", "Machine Learning Engineer", "Cloud Architect".
                     Avoid vague ("Developer") or overly specific ("React/Node Expert") titles.
    - `what_and`  -> optionally reinforce with ONE key skill that must appear
                     (e.g. "Python", "React"). Leave empty ("") when unsure —
                     adding a wrong keyword can reduce results to zero again.

    When to use this tool:
    - Only after search_jobs_by_skills has already returned 0 results.
    - Do NOT call this as the first search step.

    When NOT to use this tool:
    - Do not use this if search_jobs_by_skills already returned results.

    Args:
        job_title: Standard industry job title synthesized from the CV skills.
        what_and:  One additional keyword that must appear in every result (optional).
        country:   ISO 3166-1 alpha-2 country code (default: 'it' for Italy).
                   Examples: 'gb', 'us', 'de', 'fr', 'es'.

    Returns:
        JSON with total_job_offers_found and a list of jobOffers (title, company,
        location, description, url).
    """
    try:
        data = await adzuna_client.search_by_title(job_title, what_and, country)
        return _format(data, source="job_title")
    except Exception as e:
        logging.error(f"search_jobs_by_title failed: {e}")
        return json.dumps({"status": "error", "error": str(e)}, indent=2)


#  Entrypoint 

if __name__ == "__main__":
    adzuna_client = AdzunaClient()
    mcp2.run()