# CV Skill Extractor & Job Matcher — MCP Server

An AI-powered pipeline that extracts skills from a CV and finds matching job offers, built on the [Model Context Protocol (MCP)](https://modelcontextprotocol.io/). Integrates with OpenWebUI + LLM via [mcpo](https://github.com/open-webui/mcpo).

---

## Architecture

```
OpenWebUI (LLM)
      │
      │  OpenAPI
      ▼
   mcpo :8000
      │
      ├──► Server1-LC.py  →  Lightcast API  (skill extraction)
      └──► Server2-A.py   →  Adzuna API     (job search)
      └──► ... (other servers)
```

- **Server1-LC.py**: extracts and analyzes skills from a CV using the [Lightcast Skills API](https://docs.lightcast.io/lightcast-api/reference/api-introduction)
- **Server2-A.py**: searches job offers using the [Adzuna Jobs API](https://developer.adzuna.com/activedocs)
- **mcpo**: bridges MCP (STDIO) servers to a REST/OpenAPI endpoint that OpenWebUI can consume

---

## Project Structure

```
MCP-SERVER/
├── .venv/                  # Python virtual environment
├── info/
│   ├── cv.txt              # CV to analyze
│   └── istruzioni.txt      # custom LLM instructions
├── logs/
│   ├── server1-lc.log      # Lightcast server logs
│   └── server2-adzuna.log  # Adzuna server logs
├── MCP-Servers/
│   ├── Server1-LC.py       # MCP Server 1 — skill extraction
│   └── Server2-A.py        # MCP Server 2 — job search
│   └── client.py           # Used to test API's without having to use the LLM
│   └── ... (other servers)
├── .env                    # API keys (never commit this)
├── .gitignore
├── config.json             # mcpo multi-server config
├── docker-compose.yml      # OpenWebUI container
└── requirements.txt
```

---

## Prerequisites

- Python 3.11+
- [uvx](https://docs.astral.sh/uv/) (`pip install uv`)
- Docker + Docker Compose
- API keys for Lightcast and Adzuna (see `.env` setup below)

---

## Installation

```bash
# 1. Clone the repo
    git clone https://github.com/Leonardo1888/mcp-job-search
cd MCP-SERVER

# 2. Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate        # Linux/Mac
# .venv\Scripts\activate         # Windows

# 3. Install dependencies
pip install -r requirements.txt
```

---

## Configuration

### `.env` file

Create a `.env` file in the project root:

```env
# Lightcast API — https://lightcast.io/
LIGHTCAST_CLIENT_ID=your_client_id
LIGHTCAST_CLIENT_SECRET=your_client_secret

# Adzuna API — https://developer.adzuna.com/
ADZUNA_APPLICATION_ID=your_app_id
ADZUNA_APPLICATION_KEY=your_app_key
```

### `config.json` — mcpo server routing

```json
{
  "mcpServers": {
    "skill-extractor": {
      "command": "python3",
      "args": ["MCP-Servers/Server1-LC.py"]
    },
    "job-matcher": {
      "command": "python3",
      "args": ["MCP-Servers/Server2-A.py"]
    }
  }
}
```

---

## Running the Stack

### 1. Activate the virtual environment

```bash
source .venv/bin/activate
```

### 2. Start OpenWebUI (Docker)

```bash
# Configure the container if needed
nano docker-compose.yml

# Start
docker compose up -d

# Stop
docker compose down

# View Docker logs
docker compose logs -f
```

### 3. Expose MCP servers via mcpo (port 8000)

```bash
uvx mcpo --port 8000 --config config.json
```

This exposes two OpenAPI endpoints:

| Server | Endpoint | Swagger UI |
|---|---|---|
| Skill Extractor | `http://localhost:8000/skill-extractor` | `http://localhost:8000/skill-extractor/docs` |
| Job Matcher | `http://localhost:8000/job-matcher` | `http://localhost:8000/job-matcher/docs` |

---


## Available Tools

### Server 1 — Skill Extractor (`skill-extractor`)

| Tool | Description |
|---|---|
| `extract_skills_from_cv` | Extract skills from a CV file using Lightcast |
| `get_skill_details` | Get full Lightcast metadata for specific skill IDs |
| `find_related_skills_for_cv` | Extract skills and find adjacent/related skills |
| `analyze_cv_complete` | Full pipeline: extract + details + related in one call |

### Server 2 — Job Matcher (`job-matcher`)

| Tool | Description |
|---|---|
| `search_jobs_by_skills` | Primary search using top CV skills (call this first) |
| `search_jobs_by_title` | Fallback search using a synthesized job title |

**Job search flow:**
1. `search_jobs_by_skills` is always called first with the most distinctive skill
2. If it returns 0 results → `search_jobs_by_title` is called automatically with a synthesized job title (e.g. "Full Stack Developer")

---

## Adding a New MCP Server

1. Create `MCP-Servers/ServerN-XX.py` following the same structure as the existing servers
2. Add one entry to `config.json`:

```json
"my-new-server": {
  "command": "python3",
  "args": ["MCP-Servers/ServerN-XX.py"]
}
```

3. Add a new connection in OpenWebUI pointing to `http://host.docker.internal:8000/my-new-server` <br>
Go to: OpenWebUI Admin Panel > Settings > External Tools and click on +. <br>
The configuration must be: <br>
```
* Type: OpenAPI
* URL: http://host.docker.internal:8000/mcp-new-server-name
* OpenAPI Spec: openapi.json
* Auth: None
```

---
