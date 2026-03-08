"""
A2A Job Search Agent
Orchestrates the full job search pipeline via A2A protocol.

Pipeline:
  1. Extract skills from CV  →  Server1-LC.py  (STDIO)
  2. Search jobs by skills   →  Server2-A.py   (STDIO)
  3. Geocode missing coords  →  Nominatim API  (HTTP, free)
  4. Render map              →  Server3-Maps.py (streamable-http MCP)
"""

import os
import re
import json
import logging
import httpx
import asyncio
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime

from mcp.server.fastmcp import FastMCP
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client
from dotenv import load_dotenv

# ============ SETUP ============

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    filename=LOG_DIR / "job-search-agent-a2a.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

a2a_server = FastMCP("job-search-agent")
logger.info("=== Job Search Agent (A2A) Server Initialized ===")

# ============ CONFIGURAZIONE ============

SKILL_EXTRACTOR_PARAMS = StdioServerParameters(
    command="python3",
    args=[str(ROOT / "MCP-Servers" / "Server1-LC.py")],
    env={"PYTHONPATH": str(ROOT)},
)

JOB_MATCHER_PARAMS = StdioServerParameters(
    command="python3",
    args=[str(ROOT / "MCP-Servers" / "Server2-A.py")],
    env={"PYTHONPATH": str(ROOT)},
)

JOB_MAP_RENDERER_URL = "https://mcp-google-maps.onrender.com/mcp"

logger.info(f"  - Skill Extractor: {SKILL_EXTRACTOR_PARAMS.args}")
logger.info(f"  - Job Matcher: {JOB_MATCHER_PARAMS.args}")
logger.info(f"  - Job Map Renderer: {JOB_MAP_RENDERER_URL}")


# ============ MCP CLIENT HELPERS ============

async def call_skill_extractor_tool(cv_text: str = "", cv_filename: str = "") -> Dict[str, Any]:
    """Calls extract_skills_from_cv on Server1-LC.py via STDIO."""
    logger.info("A2A: Calling skill-extractor via STDIO")
    try:
        async with stdio_client(SKILL_EXTRACTOR_PARAMS) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "extract_skills_from_cv",
                    arguments={
                        "cv_text": cv_text or "",
                        "cv_filename": cv_filename or "cv.txt",
                        "confidence_threshold": 0.6,
                    },
                )
                raw = result.content[0].text
                try:
                    parsed = json.loads(raw)
                except json.JSONDecodeError:
                    parsed = {"status": "error", "error": f"Invalid JSON: {raw}"}
                logger.info(f"A2A: Extracted {len(parsed.get('skills', []))} skills")
                return parsed
    except Exception as e:
        logger.error(f"A2A: skill-extractor error: {e}")
        return {"status": "error", "error": str(e)}


async def call_job_matcher_tool(what: str, what_or: str, country: str = "it") -> Dict[str, Any]:
    """Calls search_jobs_by_skills on Server2-A.py via STDIO."""
    logger.info(f"A2A: Calling job-matcher via STDIO (what={what}, what_or={what_or})")
    try:
        async with stdio_client(JOB_MATCHER_PARAMS) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "search_jobs_by_skills",
                    arguments={"what": what, "what_or": what_or, "country": country},
                )
                raw = result.content[0].text
                try:
                    parsed = json.loads(raw)
                except json.JSONDecodeError:
                    parsed = {"status": "error", "error": f"Invalid JSON: {raw}"}
                logger.info(f"A2A: Found {len(parsed.get('jobOffers', []))} jobs")
                return parsed
    except Exception as e:
        logger.error(f"A2A: job-matcher error: {e}")
        return {"status": "error", "error": str(e)}


async def call_map_renderer_tool(jobs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Calls render_jobs_map_by_coordinates on Server3-Maps.py via streamable-http MCP.
    Server3 is an MCP server, NOT a REST API — must use streamablehttp_client.
    """
    if not jobs:
        return {"status": "error", "error": "No jobs provided"}

    logger.info(f"A2A: Calling map renderer via streamable-http ({len(jobs)} jobs)")
    try:
        async with streamablehttp_client(JOB_MAP_RENDERER_URL) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "render_jobs_map_by_coordinates",
                    arguments={"jobs": jobs},
                )
                raw = result.content[0].text
                try:
                    parsed = json.loads(raw)
                except json.JSONDecodeError:
                    parsed = {"status": "error", "error": f"Invalid JSON: {raw}"}
                logger.info(f"A2A: map_url={parsed.get('map_url', 'none')[:80] if parsed.get('map_url') else 'none'}")
                return parsed
    except Exception as e:
        logger.error(f"A2A: map-renderer error: {e}")
        return {"status": "error", "error": str(e)}


# ============ GEOCODING ============

async def geocode_location(location_str: str) -> Dict[str, float]:
    """
    Geocodes a location string using Nominatim (OpenStreetMap). Free, no API key.
    Returns {"latitude": float, "longitude": float} or {} on failure/skip.

    Handles Italian patterns:
      "Torino, Provincia di Torino"           -> "Torino, Italia"
      "Provincia di Napoli, Campania"         -> "Napoli, Italia"
      "Provincia di Modena, Emilia-Romagna"   -> "Modena, Italia"
    Skips generic "Italia" / "Italy" — not geocodable to a meaningful point.
    """
    if not location_str:
        return {}

    normalized = location_str.strip().lower()
    if normalized in ("italia", "italy", ""):
        logger.info(f"A2A: Skipping generic location '{location_str}'")
        return {}

    clean = location_str.strip()
    match = re.match(r"[Pp]rovincia\s+di\s+([^,]+)", clean)
    if match:
        city = match.group(1).strip()
    else:
        city = clean.split(",")[0].strip()
        city = re.sub(r"^[Pp]rovincia\s+di\s+", "", city).strip()

    query = f"{city}, Italia"
    logger.info(f"A2A: Geocoding '{location_str}' -> '{query}'")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": query, "format": "json", "limit": 1, "countrycodes": "it"},
                headers={"User-Agent": "JobSearchAgent-A2A/1.0"},
            )
            response.raise_for_status()
            results = response.json()
            if results:
                lat = float(results[0]["lat"])
                lon = float(results[0]["lon"])
                logger.info(f"A2A: Geocoded '{query}' -> ({lat}, {lon})")
                return {"latitude": lat, "longitude": lon}
            logger.warning(f"A2A: No geocoding result for '{query}'")
            return {}
    except Exception as e:
        logger.warning(f"A2A: Geocoding error for '{query}': {e}")
        return {}


async def enrich_jobs_with_coordinates(jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Geocodes jobs missing lat/lon concurrently via Nominatim.
    Jobs that already have coordinates are left unchanged.
    """
    to_geocode = [
        (i, job) for i, job in enumerate(jobs)
        if job.get("latitude") is None or job.get("longitude") is None
    ]

    if not to_geocode:
        logger.info("A2A: All jobs already have coordinates")
        return jobs

    tasks = [geocode_location(job.get("location", "")) for _, job in to_geocode]
    results = await asyncio.gather(*tasks)

    enriched = list(jobs)
    geocoded = 0
    for (i, _), coords in zip(to_geocode, results):
        if coords:
            enriched[i] = {**enriched[i], **coords}
            geocoded += 1

    already = len(jobs) - len(to_geocode)
    logger.info(
        f"A2A: Geocoding done — {already} had coords, {geocoded} geocoded, "
        f"{len(to_geocode) - geocoded} skipped"
    )
    return enriched


# ============ SKILL CLEANING ============

def clean_skill_name(name: str) -> str:
    """
    Strips Lightcast's verbose parenthetical suffixes.
    "React.js (Javascript Library)" -> "React.js"
    "Python (Programming Language)" -> "Python"
    """
    return re.sub(r"\s*\(.*?\)", "", name).strip()


# ============ A2A MAIN TOOL ============

@a2a_server.tool()
async def search_jobs_complete(
    cv_text: str = "",
    cv_filename: str = "cv.txt",
    country: str = "it",
    include_map: bool = True,
) -> str:
    """
    Complete Job Search Tool via A2A Protocol.
    Extracts skills from a CV, finds matching job offers, geocodes locations,
    and renders all results on a Google Maps image.

    ── HOW TO PASS THE CV ──────────────────────────────────────────────────────
    Always pass the full ORIGINAL CV text in `cv_text` when visible in the chat.

    CORRECT:
        search_jobs_complete(
            cv_text="Curriculum Vitae\nNome: Mario Rossi\nCompetenze: React, Python...",
            country="it"
        )

    WRONG — never pass skill lists, summaries, or your own previous output:
        search_jobs_complete(cv_text="1. React.js\n2. Python...")     ← NO
        search_jobs_complete(cv_text="Ho trovato 10 offerte...")      ← NO
        search_jobs_complete(cv_text="", cv_filename="cv.txt")        ← only if CV truly unavailable

    `cv_filename` is a last-resort fallback when no CV text is available at all.
    ────────────────────────────────────────────────────────────────────────────

    ── HOW TO DISPLAY THE RESULTS ──────────────────────────────────────────────
    After receiving the response:
    1. If map_url is present, show the map image: ![Mappa offerte](<map_url>)
    2. Show ALL jobs in map_jobs as a numbered Markdown table:
       | # | Titolo | Azienda | Città |
       Use the "number" field as row label. Make titles clickable links if url present.
    3. Never truncate — show every single job in the list.
    ────────────────────────────────────────────────────────────────────────────

    Args:
        cv_text:     Full original CV text. PRIMARY input.
        cv_filename: .txt file in /info folder. Fallback only. Default: "cv.txt".
        country:     ISO 3166-1 alpha-2 code. Default: "it". Examples: "gb","us","de".
        include_map: Render a map with job locations. Default: True.

    Returns:
        JSON with:
          - skills_extracted: list of skills found in the CV
          - jobs_found: all job offers with coordinates (geocoded where missing)
          - map_url: Google Static Maps URL — embed as ![Mappa offerte](<map_url>)
          - map_jobs: [{number, title, company, location, url}] — one entry per map marker
          - summary: full recap with complete numbered job list (never truncate this)
    """
    logger.info("=" * 80)
    logger.info("A2A: STARTING search_jobs_complete")
    logger.info("=" * 80)

    result = {
        "status": "success",
        "skills_extracted": [],
        "jobs_found": [],
        "map_url": None,
        "map_jobs": [],
        "summary": "",
        "timestamp": datetime.now().isoformat(),
    }

    try:
        # ── STEP 1: EXTRACT SKILLS ────────────────────────────────────────────
        logger.info("A2A: STEP 1 - Extracting skills")

        skills_response = await call_skill_extractor_tool(cv_text, cv_filename)

        if skills_response.get("status") != "success":
            err = skills_response.get("error", "Unknown error")
            logger.error(f"A2A: Skill extraction failed: {err}")
            result["status"] = "error"
            result["summary"] = f"Errore estrazione competenze: {err}"
            return json.dumps(result, indent=2, ensure_ascii=False)

        skills = skills_response.get("skills", [])
        result["skills_extracted"] = skills
        logger.info(f"A2A: {len(skills)} skills extracted")

        if not skills:
            result["summary"] = "Nessuna competenza trovata nel CV. Impossibile cercare lavori."
            return json.dumps(result, indent=2, ensure_ascii=False)

        # ── STEP 2: BUILD SEARCH QUERY ────────────────────────────────────────
        logger.info("A2A: STEP 2 - Building query")

        primary_skill = clean_skill_name(skills[0]["name"])
        secondary_skills = " ".join(
            clean_skill_name(s["name"]) for s in skills[1:4] if "name" in s
        )
        logger.info(f"A2A: what='{primary_skill}' what_or='{secondary_skills}'")

        # ── STEP 3: SEARCH JOBS ───────────────────────────────────────────────
        logger.info("A2A: STEP 3 - Searching jobs")

        jobs_response = await call_job_matcher_tool(primary_skill, secondary_skills, country)

        if jobs_response.get("status") != "success":
            logger.warning(f"A2A: Job search error: {jobs_response.get('error')}")
            jobs = []
        else:
            jobs = jobs_response.get("jobOffers", [])

        logger.info(f"A2A: {len(jobs)} jobs found")

        # ── STEP 4: GEOCODE + RENDER MAP ──────────────────────────────────────
        if include_map and jobs:
            logger.info("A2A: STEP 4 - Geocoding + rendering map")
            jobs = await enrich_jobs_with_coordinates(jobs)

            map_response = await call_map_renderer_tool(jobs)
            if map_response.get("map_url"):
                result["map_url"] = map_response["map_url"]
                result["map_jobs"] = map_response.get("jobs", [])
                logger.info(
                    f"A2A: Map OK — by_coords={map_response.get('by_coordinates',0)} "
                    f"by_city={map_response.get('by_location',0)} "
                    f"skipped={map_response.get('skipped',0)}"
                )
            else:
                logger.warning(f"A2A: Map failed: {map_response.get('error')}")

        result["jobs_found"] = jobs

        # ── STEP 5: BUILD SUMMARY ─────────────────────────────────────────────
        logger.info("A2A: STEP 5 - Building summary")

        jobs_with_coords = sum(1 for j in jobs if j.get("latitude") and j.get("longitude"))
        lines = [
            f"Competenze estratte: {len(skills)}",
            f"Offerte trovate: {len(jobs)} — mostrare TUTTE",
            f"Offerte con coordinate mappa: {jobs_with_coords}",
        ]

        if result["map_url"]:
            lines.append(f"MAPPA → mostra con: ![Mappa offerte]({result['map_url']})")

        lines.append("")
        lines.append("LISTA COMPLETA — mostrare tutte le seguenti offerte senza troncare:")
        for i, job in enumerate(jobs, 1):
            loc = job.get("location") or "N/D"
            url = job.get("url") or ""
            title = job.get("title") or "N/D"
            company = job.get("company") or "N/D"
            lines.append(f"{i}. [{title}]({url}) | {company} | {loc}")

        result["summary"] = "\n".join(lines)
        result["status"] = "success"

        logger.info("A2A: Pipeline completed successfully")
        logger.info("=" * 80)
        return json.dumps(result, indent=2, ensure_ascii=False)

    except Exception as e:
        logger.error(f"A2A: Unhandled exception: {e}")
        result["status"] = "error"
        result["summary"] = f"Eccezione: {str(e)}"
        logger.info("=" * 80)
        return json.dumps(result, indent=2, ensure_ascii=False)


# ============ MAIN ============

if __name__ == "__main__":
    logger.info("Starting Job Search Agent (A2A) Server")
    a2a_server.run()