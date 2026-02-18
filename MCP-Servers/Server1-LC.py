"""
MCP Server 1 - CV Profile Analysis & Skill Extraction
Extracts and analyzes skills from a CV using the Lightcast API.
Docs: https://docs.lightcast.io/lightcast-api/reference/api-introduction

Tools:
    extract_skills_from_cv      — extract skills from a CV file
    get_skill_details           — get full details for specific skill IDs
    find_related_skills_for_cv  — extract skills + find related ones
    analyze_cv_complete         — full pipeline: skills + details + related
"""

import httpx, os, json, logging
from mcp.server.fastmcp import FastMCP
from pathlib import Path
from typing import Dict, Any, List
from dotenv import load_dotenv

#  Absolute paths 
ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    filename=LOG_DIR / "server1-lc.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

#  Config 
LIGHTCAST_API_BASE = "https://api.lightcast.io"
LIGHTCAST_AUTH_URL = "https://auth.emsicloud.com/connect/token"
CLIENT_ID     = os.getenv("LIGHTCAST_CLIENT_ID")
CLIENT_SECRET = os.getenv("LIGHTCAST_CLIENT_SECRET")

mcp1 = FastMCP("skill-extractor")


#  Lightcast API client 

class LightcastClient:
    """
    Handles OAuth2 authentication and all calls to the Lightcast Skills API.
    Token is cached in memory and auto-refreshed on 401.
    Docs: https://docs.lightcast.io/lightcast-api/docs/authentication-guide
    """

    def __init__(self):
        self.access_token = None

    async def _auth(self) -> str:
        """Fetches a new OAuth2 Bearer token from Lightcast."""
        logging.info("Requesting new Lightcast access token")
        async with httpx.AsyncClient() as client:
            r = await client.post(
                LIGHTCAST_AUTH_URL,
                data={
                    "client_id":     CLIENT_ID,
                    "client_secret": CLIENT_SECRET,
                    "grant_type":    "client_credentials",
                    "scope":         "emsi_open",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            r.raise_for_status()
            self.access_token = r.json()["access_token"]
            logging.info("Access token obtained successfully")
            return self.access_token

    def _headers(self) -> dict:
        return {
            "accept":        "application/json",
            "content-type":  "application/json",
            "authorization": f"Bearer {self.access_token}",
        }

    async def extract_skills(self, text: str, confidence_threshold: float = 0.6) -> Dict[str, Any]:
        """
        Calls /skills/versions/latest/extract.
        Auto-retries once on 401 (expired token).
        """
        if not self.access_token:
            await self._auth()

        url = f"{LIGHTCAST_API_BASE}/skills/versions/latest/extract"
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.post(
                    url,
                    json={"text": text, "confidenceThreshold": confidence_threshold},
                    headers=self._headers(),
                )
                r.raise_for_status()
                return r.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                await self._auth()
                return await self.extract_skills(text, confidence_threshold)
            raise

    async def get_skills_details(self, skill_ids: List[str]) -> Dict[str, Any]:
        """Calls /skills/versions/latest/skills with a list of IDs."""
        if not self.access_token:
            await self._auth()
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                f"{LIGHTCAST_API_BASE}/skills/versions/latest/skills",
                json={"ids": skill_ids},
                headers=self._headers(),
            )
            r.raise_for_status()
            return r.json()

    async def find_related_skills(self, skill_ids: List[str], limit: int = 10) -> Dict[str, Any]:
        """Calls /skills/versions/latest/related for a list of skill IDs."""
        if not self.access_token:
            await self._auth()
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                f"{LIGHTCAST_API_BASE}/skills/versions/latest/related",
                json={"ids": skill_ids, "limit": limit},
                headers=self._headers(),
            )
            r.raise_for_status()
            return r.json()


#  Helpers 

def read_cv_file(filename: str) -> str:
    """Reads a CV file from the /info directory. Raises FileNotFoundError if missing."""
    path = ROOT / "info" / filename
    if not path.exists():
        raise FileNotFoundError(f"CV file '{filename}' not found in /info/")
    return path.read_text(encoding="utf-8")

def _fmt_skill(skill: dict) -> dict:
    """Normalizes a raw Lightcast skill object into a clean dict."""
    return {
        "id":         skill["skill"]["id"],
        "name":       skill["skill"]["name"],
        "confidence": skill["confidence"],
        "type":       skill["skill"].get("type", {}).get("name", "Unknown"),
    }


#  Tools 

@mcp1.tool()
async def extract_skills_from_cv(
    cv_filename: str,
    confidence_threshold: float = 0.6,
) -> str:
    """
    Extract professional skills from a CV file using the Lightcast Skills API.

    Use this as the FIRST step in any CV analysis workflow.
    The extracted skill names and IDs can then be passed to other tools
    (get_skill_details, find_related_skills_for_cv, search_jobs_by_skills).

    Args:
        cv_filename:          Name of the CV text file inside the /info folder
                              (e.g. "cv.txt"). The file must already exist there.
        confidence_threshold: Minimum confidence score to include a skill (0.0–1.0).
                              Default 0.6 filters out weak/ambiguous matches.
                              Lower to 0.4 if too few skills are returned.

    Returns:
        JSON with:
          - total_skills_found (int)
          - skills: list of {id, name, confidence, type}
        On error: {status: "error", error: "<message>"}
    """
    try:
        cv_text = read_cv_file(cv_filename)
        logging.info(f"CV loaded: {cv_filename}")

        raw = await lightcast_client.extract_skills(cv_text, confidence_threshold)
        skills = raw.get("data", [])
        logging.info(f"Skills extracted: {len(skills)} (threshold={confidence_threshold})")

        return json.dumps({
            "status":             "success",
            "cv_filename":        cv_filename,
            "total_skills_found": len(skills),
            "skills":             [_fmt_skill(s) for s in skills],
        }, indent=2, ensure_ascii=False)

    except FileNotFoundError as e:
        return json.dumps({"status": "error", "error": str(e)}, indent=2)
    except Exception as e:
        logging.error(f"extract_skills_from_cv failed: {e}")
        return json.dumps({"status": "error", "error": str(e)}, indent=2)


@mcp1.tool()
async def get_skill_details(skill_ids: List[str]) -> str:
    """
    Fetch full Lightcast metadata for one or more skills by their IDs.

    Use this AFTER extract_skills_from_cv when you need richer information
    about specific skills (category, subcategory, description, tags).
    Do NOT use this to search skills by name — it requires exact Lightcast IDs.

    Args:
        skill_ids: List of Lightcast skill IDs obtained from extract_skills_from_cv.
                   Example: ["KS125LS6K7RY98Y6Y6LY", "KS440KJ6BKJNLY7KQMV9"]
                   Pass only IDs you actually received — invalid IDs cause errors.

    Returns:
        JSON with:
          - skills: list of full Lightcast skill objects
        On error: {status: "error", error: "<message>"}
    """
    try:
        data = await lightcast_client.get_skills_details(skill_ids)
        return json.dumps({
            "status": "success",
            "skills": data.get("data", []),
        }, indent=2, ensure_ascii=False)
    except Exception as e:
        logging.error(f"get_skill_details failed: {e}")
        return json.dumps({"status": "error", "error": str(e)}, indent=2)


@mcp1.tool()
async def find_related_skills_for_cv(
    cv_filename: str,
    limit_per_skill: int = 5,
) -> str:
    """
    Extract skills from a CV and return related/adjacent skills for each one.

    Use this to EXPAND a candidate's skill profile — useful for suggesting
    skills the candidate could develop, or for broadening a job search.
    This tool runs extract_skills_from_cv internally; no need to call it first.

    Args:
        cv_filename:     Name of the CV text file inside /info (e.g. "cv.txt").
        limit_per_skill: Max number of related skills to return per extracted skill.
                         Default 5. Increase to 10 for a broader suggestion list.

    Returns:
        JSON with:
          - extracted_skills_count (int)
          - extracted_skills: list of {id, name, confidence}
          - related_skills: Lightcast related skills data
        On error: {status: "error", error: "<message>"}
    """
    try:
        cv_text = read_cv_file(cv_filename)
        raw = await lightcast_client.extract_skills(cv_text, 0.6)
        skills = raw.get("data", [])

        if not skills:
            return json.dumps({"status": "success", "message": "No skills found in CV."}, indent=2)

        ids = [s["skill"]["id"] for s in skills]
        related = await lightcast_client.find_related_skills(ids, limit_per_skill)

        return json.dumps({
            "status":                 "success",
            "extracted_skills_count": len(skills),
            "extracted_skills":       [{"id": s["skill"]["id"], "name": s["skill"]["name"], "confidence": s["confidence"]} for s in skills],
            "related_skills":         related.get("data", []),
        }, indent=2, ensure_ascii=False)

    except Exception as e:
        logging.error(f"find_related_skills_for_cv failed: {e}")
        return json.dumps({"status": "error", "error": str(e)}, indent=2)


@mcp1.tool()
async def analyze_cv_complete(cv_filename: str = "cv.txt") -> str:
    """
    Run the full CV analysis pipeline in a single call.

    Combines extract_skills_from_cv + get_skill_details + find_related_skills_for_cv.
    Use this when you need a comprehensive skill profile in one step,
    for example before presenting results to the user or feeding into job search.

    Prefer this over calling the three tools individually to reduce round-trips.
    Do NOT use this just to extract skills — use extract_skills_from_cv instead.

    Args:
        cv_filename: Name of the CV text file inside /info (default: "cv.txt").

    Returns:
        JSON with:
          - analysis.total_skills_extracted (int)
          - analysis.extracted_skills: list of {id, name, confidence, type}
          - analysis.skills_details: full Lightcast metadata for each skill
          - analysis.related_skills: adjacent skills for the full profile
        On error: {status: "error", error: "<message>"}
    """
    try:
        cv_text = read_cv_file(cv_filename)
        raw = await lightcast_client.extract_skills(cv_text, 0.6)
        skills = raw.get("data", [])

        if not skills:
            return json.dumps({"status": "success", "message": "No skills found in CV."}, indent=2)

        ids = [s["skill"]["id"] for s in skills]
        details = await lightcast_client.get_skills_details(ids)
        related  = await lightcast_client.find_related_skills(ids, 5)

        logging.info(f"analyze_cv_complete: {len(skills)} skills from '{cv_filename}'")

        return json.dumps({
            "status":      "success",
            "cv_filename": cv_filename,
            "analysis": {
                "total_skills_extracted": len(skills),
                "extracted_skills":       [_fmt_skill(s) for s in skills],
                "skills_details":         details.get("data", []),
                "related_skills":         related.get("data", []),
            },
        }, indent=2, ensure_ascii=False)

    except Exception as e:
        logging.error(f"analyze_cv_complete failed: {e}")
        return json.dumps({"status": "error", "error": str(e)}, indent=2)


#  Entrypoint 

if __name__ == "__main__":
    lightcast_client = LightcastClient()
    mcp1.run()