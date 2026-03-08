"""
A2A Job Search Agent
Chiama i server MCP direttamente via STDIO, usando il corretto Python SDK MCP.

Questo server:
- È un MCP server registrato in config.json
- Espone UN tool: search_jobs_complete
- Chiama DIRETTAMENTE i server MCP locali via STDIO:
   - skill-extractor (Server1-LC.py), il server che cerca le skill tramite le LightCast API
   - job-matcher (Server2-A.py), il server che cerca le offerte di lavoro tramite Adzuna API
- Chiama il server remoto su Render (job-map-renderer), il server che utilizza le Google Maps API per mostrare una mappa
"""

import os
import json
import logging
import httpx
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime

from mcp.server.fastmcp import FastMCP

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

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

# creazione del server MCP per A2A
a2a_server = FastMCP("job-search-agent")

logger.info("=== Job Search Agent (A2A) Server Initialized ===")

# ============ CONFIGURAZIONE ============

# Percorsi ai server MCP locali
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

logger.info(f"Configured:")
logger.info(f"  - Skill Extractor: python3 {ROOT / 'MCP-Servers' / 'Server1-LC.py'}")
logger.info(f"  - Job Matcher: python3 {ROOT / 'MCP-Servers' / 'Server2-A.py'}")
logger.info(f"  - Job Map Renderer: {JOB_MAP_RENDERER_URL}")

# ============ MCP CLIENT VIA STDIO ============

async def call_skill_extractor_tool(cv_text: str = "", cv_filename: str = "") -> Dict[str, Any]:
    """
    Chiama extract_skills_from_cv tramite STDIO usando il pattern corretto Python SDK.
    
    Pattern corretto:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(...)
    """
    logger.info("A2A: Calling skill-extractor via STDIO")

    try:
        async with stdio_client(SKILL_EXTRACTOR_PARAMS) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                result = await session.call_tool(
                    "extract_skills_from_cv",
                    arguments={
                        "cv_text": cv_text if cv_text else "",
                        "cv_filename": cv_filename if cv_filename else "cv.txt",
                        "confidence_threshold": 0.6,
                    },
                )

                # Il risultato è una lista di content block; il primo è TextContent
                raw_text = result.content[0].text
                try:
                    parsed = json.loads(raw_text)
                except json.JSONDecodeError:
                    parsed = {"status": "error", "error": f"Invalid JSON from skill-extractor: {raw_text}"}

                skills = parsed.get("skills", [])
                logger.info(f"A2A: Extracted {len(skills)} skills")
                return parsed

    except Exception as e:
        logger.error(f"A2A: Error calling skill-extractor: {str(e)}")
        return {
            "status": "error",
            "error": f"Failed to extract skills: {str(e)}",
        }


async def call_job_matcher_tool(what: str, what_or: str, country: str = "it") -> Dict[str, Any]:
    """
    Chiama search_jobs_by_skills tramite STDIO usando il pattern corretto Python SDK.
    """
    logger.info(f"A2A: Calling job-matcher via STDIO (what={what})")

    try:
        async with stdio_client(JOB_MATCHER_PARAMS) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                result = await session.call_tool(
                    "search_jobs_by_skills",
                    arguments={
                        "what": what,
                        "what_or": what_or,
                        "country": country,
                    },
                )

                raw_text = result.content[0].text
                try:
                    parsed = json.loads(raw_text)
                except json.JSONDecodeError:
                    parsed = {"status": "error", "error": f"Invalid JSON from job-matcher: {raw_text}"}

                jobs = parsed.get("jobOffers", [])
                logger.info(f"A2A: Found {len(jobs)} job offers")
                return parsed

    except Exception as e:
        logger.error(f"A2A: Error calling job-matcher: {str(e)}")
        return {
            "status": "error",
            "error": f"Failed to search jobs: {str(e)}",
        }


async def call_map_renderer_tool(locations: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Chiama il server remoto di mappa su Render tramite HTTP (invariato).
    """
    if not locations:
        logger.info("A2A: No locations for map")
        return {"status": "success", "message": "No locations"}

    logger.info(f"A2A: Calling job-map-renderer (locations={len(locations)})")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            payload = {"locations": locations}

            try:
                url = f"{JOB_MAP_RENDERER_URL}/render_map"
                logger.info(f"A2A: POST {url}")
                response = await client.post(url, json=payload)
                response.raise_for_status()
                result = response.json()
                logger.info("A2A: Map rendered successfully")
                return result
            except Exception:
                logger.warning("A2A: Trying fallback map endpoint")
                response = await client.post(JOB_MAP_RENDERER_URL, json=payload)
                response.raise_for_status()
                result = response.json()
                logger.info("A2A: Map rendered successfully (fallback)")
                return result

    except Exception as e:
        logger.warning(f"A2A: Error calling map-renderer: {str(e)}")
        return {
            "status": "error",
            "error": f"Map rendering failed: {str(e)}",
        }


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
    Chiama i server MCP locali via STDIO (pattern corretto Python SDK).
    
    Args:
        cv_text:     Full CV text as a plain string (preferred).
        cv_filename: Name of the CV file inside /info (fallback, default: "cv.txt").
        country:     ISO 3166-1 alpha-2 country code (default: 'it' for Italy).
        include_map: Whether to render a map with job locations (default: True).
    
    Returns:
        JSON with skills_extracted, jobs_found, map_url, and summary.
    """
    logger.info("=" * 80)
    logger.info("A2A: STARTING search_jobs_complete")
    logger.info("=" * 80)

    result = {
        "status": "success",
        "skills_extracted": [],
        "jobs_found": [],
        "map_url": None,
        "map_data": None,
        "summary": "",
        "timestamp": datetime.now().isoformat(),
    }

    try:
        # ====== STEP 1: EXTRACT SKILLS ======
        logger.info("A2A: STEP 1 - Extracting skills from CV")

        skills_response = await call_skill_extractor_tool(cv_text, cv_filename)

        if skills_response.get("status") != "success":
            error_msg = skills_response.get("error", "Unknown error in skill extraction")
            logger.error(f"A2A: Skill extraction failed: {error_msg}")
            result["status"] = "error"
            result["summary"] = f"Failed to extract skills: {error_msg}"
            return json.dumps(result, indent=2, ensure_ascii=False)

        skills = skills_response.get("skills", [])
        result["skills_extracted"] = skills
        logger.info(f"A2A: Successfully extracted {len(skills)} skills")

        if not skills:
            result["summary"] = "No skills found in CV. Cannot search for jobs."
            logger.warning("A2A: No skills found in CV")
            return json.dumps(result, indent=2, ensure_ascii=False)

        # ====== STEP 2: SELECT PRIMARY AND SECONDARY SKILLS ======
        logger.info("A2A: STEP 2 - Selecting primary and secondary skills")

        primary_skill = skills[0]["name"]
        secondary_skills = " ".join([s["name"] for s in skills[1:4] if "name" in s])

        logger.info(f"A2A: Primary skill: {primary_skill}")
        logger.info(f"A2A: Secondary skills: {secondary_skills}")

        # ====== STEP 3: SEARCH JOBS ======
        logger.info("A2A: STEP 3 - Searching jobs by skills")

        jobs_response = await call_job_matcher_tool(primary_skill, secondary_skills, country)

        if jobs_response.get("status") != "success":
            logger.warning(f"A2A: Job search returned error: {jobs_response.get('error')}")
            jobs = []
        else:
            jobs = jobs_response.get("jobOffers", [])

        result["jobs_found"] = jobs
        logger.info(f"A2A: Found {len(jobs)} job offers")

        # ====== STEP 4: RENDER MAP ======
        if include_map and jobs:
            logger.info("A2A: STEP 4 - Rendering map")

            locations_for_map = [
                {
                    "title": job.get("title"),
                    "company": job.get("company"),
                    "location": job.get("location"),
                    "latitude": job.get("latitude"),
                    "longitude": job.get("longitude"),
                    "url": job.get("url"),
                }
                for job in jobs
                if job.get("latitude") is not None and job.get("longitude") is not None
            ]

            if locations_for_map:
                logger.info(f"A2A: Preparing {len(locations_for_map)} locations for map")
                map_response = await call_map_renderer_tool(locations_for_map)

                if map_response.get("status") == "success":
                    result["map_url"] = map_response.get("map_url")
                    result["map_data"] = map_response
                    logger.info("A2A: Map rendered successfully")
                else:
                    logger.warning(f"A2A: Map rendering failed: {map_response.get('error')}")
            else:
                logger.info("A2A: No jobs with coordinates for map")

        # ====== STEP 5: SYNTHESIZE RESPONSE ======
        logger.info("A2A: STEP 5 - Synthesizing response")

        summary_parts = [
            f"Ho estratto {len(skills)} competenze dal CV.",
            f"Ho trovato {len(jobs)} offerte di lavoro pertinenti.",
        ]

        if result["map_url"]:
            summary_parts.append("Ho generato una mappa con le offerte geografiche.")

        result["summary"] = " ".join(summary_parts)
        result["status"] = "success"

        logger.info("A2A: Task completed successfully")
        logger.info("=" * 80)

        return json.dumps(result, indent=2, ensure_ascii=False)

    except Exception as e:
        logger.error(f"A2A: Exception in search_jobs_complete: {str(e)}")
        result["status"] = "error"
        result["summary"] = f"Exception: {str(e)}"
        logger.info("=" * 80)
        return json.dumps(result, indent=2, ensure_ascii=False)


# ============ MAIN ============

if __name__ == "__main__":
    logger.info("Starting Job Search Agent (A2A) Server")
    logger.info("This server will be run by mcpo as a subprocess")
    logger.info("Exposed tool: search_jobs_complete")
    a2a_server.run()