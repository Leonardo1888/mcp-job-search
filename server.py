"""
MCP Server 1 - Analisi del Profilo ed Estrazione Dati
Estrae competenze da un CV usando l'API Lightcast Skills
Tools:
    extract_skills_from_cv
    get_skill_details
    find_related_skills_for_cv
    analyze_cv_complete
"""

from mcp.server.fastmcp import FastMCP
import httpx
import os
from pathlib import Path
from typing import Dict, Any, List
import json
import logging
from dotenv import load_dotenv

load_dotenv()

# logging, visto che il server è asincrono, è meglio usare logging invece di print per evitare confusione nei messaggi
logging.basicConfig(
    filename='server.log',
    level=logging.INFO,
    format='%(asctime)s - %(message)s'
)

# Inizializza FastMCP
mcp = FastMCP("skill-extractor")

# Configurazione API Lightcast
LIGHTCAST_API_BASE = "https://api.lightcast.io"
LIGHTCAST_AUTH_URL = "https://auth.emsicloud.com/connect/token"

# Credenziali
CLIENT_ID = os.getenv("LIGHTCAST_CLIENT_ID")  
CLIENT_SECRET = os.getenv("LIGHTCAST_CLIENT_SECRET")  


class LightcastClient:
    """Client per interagire con le API Lightcast. Docs: https://docs.lightcast.io/lightcast-api/docs/authentication-guide"""
    
    def __init__(self):
        self.access_token = None
        self.token_expires_at = None
    
    async def get_access_token(self) -> str:
        """Ottiene un access token OAuth2 da Lightcast"""
        logging.info("Richiesta access token a Lightcast")       
         
        async with httpx.AsyncClient() as client:
            response = await client.post(
                LIGHTCAST_AUTH_URL,
                data={
                    "client_id": CLIENT_ID,
                    "client_secret": CLIENT_SECRET,
                    "grant_type": "client_credentials",
                    "scope": "emsi_open"
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            response.raise_for_status()
            data = response.json()
            self.access_token = data["access_token"]
            logging.info(f"Access token ottenuto con successo: {self.access_token}")
            return self.access_token
    
    async def extract_skills(
        self, 
        text: str, 
        confidence_threshold: float = 0.5
    ) -> Dict[str, Any]:
        """
        Estrae competenze da un testo usando Lightcast Skills API
        Docs: https://docs.lightcast.io/lightcast-api/reference/skills_post_extract_skills-1
        Args:
            text: Testo del documento/CV
            confidence_threshold: Soglia di confidenza (0.0 - 1.0)
        
        Returns:
            Risposta API con lista di competenze estratte
        """
        
        # Ottieni token se non disponibile
        if not self.access_token:
            await self.get_access_token()
        
        url = f"{LIGHTCAST_API_BASE}/skills/versions/latest/extract"
        
        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "authorization": f"Bearer {self.access_token}"
        }
        
        payload = {
            "text": text,
            "confidenceThreshold": confidence_threshold
        }
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                return response.json()
        
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                # Token scaduto, rigenera
                await self.get_access_token()
                return await self.extract_skills(text, confidence_threshold)
            raise
    
    async def get_skills_details(self, skill_ids: List[str]) -> Dict[str, Any]:
        """
        Ottiene dettagli completi per una lista di skill IDs
        Docs: https://docs.lightcast.io/lightcast-api/reference/skills_get_all_skills-1
        
        Args:
            skill_ids: Lista di ID competenze
        
        Returns:
            Dettagli delle competenze
        """
        
        if not self.access_token:
            await self.get_access_token()
        
        url = f"{LIGHTCAST_API_BASE}/skills/versions/latest/skills"
        
        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "authorization": f"Bearer {self.access_token}"
        }
        
        payload = {
            "ids": skill_ids
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            return response.json()
    
    async def find_related_skills(
        self, 
        skill_ids: List[str], 
        limit: int = 10
    ) -> Dict[str, Any]:
        """
        Trova competenze correlate a quelle fornite
        docs: https://docs.lightcast.io/lightcast-api/reference/skills_post_find_related_skills-1
        Args:
            skill_ids: Lista di ID competenze
            limit: Numero massimo di skill correlate per skill
        
        Returns:
            Competenze correlate
        """
        
        if not self.access_token:
            await self.get_access_token()
        
        url = f"{LIGHTCAST_API_BASE}/skills/versions/latest/related"
        
        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "authorization": f"Bearer {self.access_token}"
        }
        
        payload = {
            "ids": skill_ids,
            "limit": limit
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            return response.json()


# Inizializza il client
lightcast_client = LightcastClient()


def read_cv_file(filename: str) -> str:
    """Legge il contenuto del file CV"""
    
    file_path = Path(__file__).parent / filename
    
    if not file_path.exists():
        raise FileNotFoundError(f"File {filename} non trovato nella directory corrente")
    
    with open(file_path, 'r', encoding='utf-8') as f:
        return f.read()


@mcp.tool()
async def extract_skills_from_cv(
    cv_filename: str,
    confidence_threshold: float = 0.6
) -> str:
    """
    Estrae competenze dal file CV usando Lightcast API
    
    Args:
        cv_filename: Nome del file CV (default: cv.txt)
        confidence_threshold: Soglia di confidenza minima (0.0 - 1.0, default: 0.6)
    
    Returns:
        JSON con competenze estratte e relativi dettagli
    """
    
    try:
        # Leggi il CV
        cv_text = read_cv_file(cv_filename)
        logging.info(f"CV letto con successo: {cv_filename}")
        
        # Estrai competenze
        skills_data = await lightcast_client.extract_skills(
            text=cv_text,
            confidence_threshold=confidence_threshold
        )
        
        # Formatta risultato
        extracted_skills = skills_data.get("data", [])
        logging.info(f"Competenze estratte correttamente. Sono: {len(extracted_skills)} skills.")
        
        result = {
            "status": "success",
            "cv_filename": cv_filename,
            "total_skills_found": len(extracted_skills),
            "skills": [
                {
                    "id": skill["skill"]["id"],
                    "name": skill["skill"]["name"],
                    "confidence": skill["confidence"],
                    "type": skill["skill"].get("type", {}).get("name", "Unknown")
                }
                for skill in extracted_skills
            ]
        }
        
        return json.dumps(result, indent=2, ensure_ascii=False)
    
    except FileNotFoundError as e:
        return json.dumps({
            "status": "error",
            "error": str(e)
        }, indent=2)
    
    except Exception as e:
        return json.dumps({
            "status": "error",
            "error": f"Errore nell'estrazione delle competenze: {str(e)}"
        }, indent=2)


@mcp.tool()
async def get_skill_details(skill_ids: List[str]) -> str:
    """
    Ottiene dettagli completi per una lista di competenze
    
    Args:
        skill_ids: Lista di ID competenze (es. ["KS125LS6K7RY98Y6Y6LY"])
    
    Returns:
        JSON con dettagli delle competenze
    """
    
    try:
        details = await lightcast_client.get_skills_details(skill_ids)
        
        result = {
            "status": "success",
            "skills": details.get("data", [])
        }
        
        return json.dumps(result, indent=2, ensure_ascii=False)
    
    except Exception as e:
        return json.dumps({
            "status": "error",
            "error": f"Errore nel recupero dettagli: {str(e)}"
        }, indent=2)


@mcp.tool()
async def find_related_skills_for_cv(
    cv_filename,
    limit_per_skill: int = 5
) -> str:
    """
    Estrae competenze dal CV e trova competenze correlate
    
    Args:
        cv_filename: Nome del file CV (default: cv.txt)
        limit_per_skill: Numero massimo di skill correlate per ogni skill trovata
    
    Returns:
        JSON con competenze estratte e loro correlate
    """
    
    try:
        # Leggi CV
        cv_text = read_cv_file(cv_filename)
        
        # Estrai competenze
        skills_data = await lightcast_client.extract_skills(cv_text, 0.6)
        extracted_skills = skills_data.get("data", [])
        
        if not extracted_skills:
            return json.dumps({
                "status": "success",
                "message": "Nessuna competenza trovata nel CV"
            }, indent=2)
        
        # Ottieni IDs delle skill estratte
        skill_ids = [skill["skill"]["id"] for skill in extracted_skills]
        
        # Trova competenze correlate
        related_data = await lightcast_client.find_related_skills(
            skill_ids, 
            limit_per_skill
        )
        
        result = {
            "status": "success",
            "extracted_skills_count": len(extracted_skills),
            "extracted_skills": [
                {
                    "id": skill["skill"]["id"],
                    "name": skill["skill"]["name"],
                    "confidence": skill["confidence"]
                }
                for skill in extracted_skills
            ],
            "related_skills": related_data.get("data", [])
        }
        
        return json.dumps(result, indent=2, ensure_ascii=False)
    
    except Exception as e:
        return json.dumps({
            "status": "error",
            "error": f"Errore nella ricerca competenze correlate: {str(e)}"
        }, indent=2)


@mcp.tool()
async def analyze_cv_complete(
    cv_filename: str = "cv.txt"
) -> str:
    """
    Analisi completa del CV: estrae competenze, dettagli e correlate
    
    Args:
        cv_filename: Nome del file CV (default: cv.txt)
    
    Returns:
        JSON con analisi completa del profilo
    """
    
    try:
        # Leggi CV
        cv_text = read_cv_file(cv_filename)
        
        # Estrai competenze
        skills_data = await lightcast_client.extract_skills(cv_text, 0.6)
        extracted_skills = skills_data.get("data", [])
        
        if not extracted_skills:
            return json.dumps({
                "status": "success",
                "message": "Nessuna competenza trovata nel CV"
            }, indent=2)
        
        # Ottieni IDs
        skill_ids = [skill["skill"]["id"] for skill in extracted_skills]
        
        # Ottieni dettagli
        details_data = await lightcast_client.get_skills_details(skill_ids)
        
        # Trova correlate
        related_data = await lightcast_client.find_related_skills(skill_ids, 5)
        
        result = {
            "status": "success",
            "cv_filename": cv_filename,
            "analysis": {
                "total_skills_extracted": len(extracted_skills),
                "extracted_skills": [
                    {
                        "id": skill["skill"]["id"],
                        "name": skill["skill"]["name"],
                        "confidence": skill["confidence"],
                        "type": skill["skill"].get("type", {}).get("name", "Unknown")
                    }
                    for skill in extracted_skills
                ],
                "skills_details": details_data.get("data", []),
                "related_skills": related_data.get("data", [])
            }
        }
        
        return json.dumps(result, indent=2, ensure_ascii=False)
    
    except Exception as e:
        return json.dumps({
            "status": "error",
            "error": f"Errore nell'analisi completa: {str(e)}"
        }, indent=2)


if __name__ == "__main__":
    mcp.run()