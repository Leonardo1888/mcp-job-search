# Intelligent Job Search — MCP + A2A

An AI-powered pipeline for automated job search from a CV, developed as a Bachelor's thesis project in Computer Engineering at the University of Bergamo.

The architecture is built on two open and complementary protocols: Anthropic's [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) for communication between the LLM and individual tools, and the [Agent-to-Agent (A2A)](https://a2a-protocol.org/latest/) protocol for coordination between distinct specialised agents. The integration of both is the key architectural differentiator from existing job matching systems.

---

## Architecture

```
User (natural language)
        │
        ▼
  OpenWebUI (LLM: GPT-4o / any compatible model)
        │  OpenAPI
        ▼
     mcpo :8000
        │
        ├──► JobSearchAgent-A2A.py   ←── Orchestrator agent (A2A client)
        │           │
        │           ├──► Server1-LC.py        →  Lightcast API   (skill extraction, STDIO)
        │           ├──► Server2-A.py         →  Adzuna API      (job search, STDIO)
        │           ├──► Nominatim API        →  Geocoding       (public HTTP, no API key)
        │           └──► Server3-Maps.py      →  Google Maps API (map rendering, Streamable HTTP)
        │                  [remote on Render.com]
        │
        ├──► Server1-LC.py   (direct LLM access for standalone analysis)
        └──► Server2-A.py    (direct LLM access for standalone search)
```

### Full operational flow (`search_jobs_complete`)

1. The user sends a natural language request to the chat (e.g. *"analyse my CV and find jobs in Italy"*).
2. The LLM recognises the intent and invokes **a single tool**: `search_jobs_complete` on `JobSearchAgent-A2A`, passing the CV text.
3. `JobSearchAgent-A2A` opens an MCP session to **SKILL-EXTRACTOR** (STDIO) and calls `extract_skills_from_cv`.
4. The extracted skills are normalised and used to build the query; an MCP session is opened to **JOB-MATCHER** (STDIO) and `search_jobs_by_skills` is called.
5. Job offers are enriched with geographic coordinates via **Nominatim** geocoding (concurrent via `asyncio.gather`).
6. `JobSearchAgent-A2A` connects to the remote **JOB-MAP-RENDERER** server (Streamable HTTP) on Render.com and calls `render_jobs_map_by_coordinates`, obtaining a Google Maps Static URL.
7. The aggregated result — extracted skills, job list and map URL — is returned to the LLM, which synthesises and presents it in OpenWebUI (Markdown table + embedded map image).

By delegating all orchestration to `JobSearchAgent-A2A`, the LLM acts as an interpreter of the user's intent and a formatter of the final response — the two tasks at which modern language models excel — eliminating the risk of skipping steps or losing context in a multi-step pipeline.

### Protocols and communication

| Connection | Protocol | Notes |
|---|---|---|
| OpenWebUI → mcpo | OpenAPI REST | Port 8000 |
| mcpo → Server1, Server2, JobSearchAgent | MCP STDIO | Python subprocesses |
| mcpo → Server3 | MCP Streamable HTTP | Public endpoint on Render.com |
| JobSearchAgent → Server1, Server2 | MCP STDIO | Internal A2A pipeline calls |
| JobSearchAgent → Server3 | MCP Streamable HTTP | `mcp.client.streamable_http` |
| JobSearchAgent → Nominatim | HTTP REST | Free, no API key required |

---

## Project structure

```
mcp-job-search/
├── MCP-Servers/
│   ├── Server1-LC.py           # SKILL-EXTRACTOR  — Lightcast Skills API (local, STDIO)
│   ├── Server2-A.py            # JOB-MATCHER      — Adzuna Jobs API (local, STDIO)
│   └── JobSearchAgent-A2A.py   # A2A Agent        — full pipeline orchestrator
├── info/
│   ├── cv.txt                  # User CV (plain text input, fallback)
│   └── istruzioni.txt          # Custom system prompt for the LLM
├── logs/
│   ├── server1-lc.log          # SKILL-EXTRACTOR logs
│   ├── server2-adzuna.log      # JOB-MATCHER logs
│   └── job-search-agent-a2a.log # A2A agent logs
├── .env                        # API credentials (never commit)
├── .gitignore
├── a2a_agents.json             # Descriptive registry of A2A agents
├── config.json                 # mcpo configuration (local + remote servers)
├── docker-compose.yml          # OpenWebUI container
└── requirements.txt
```

The remote server `Server3-Maps.py` (JOB-MAP-RENDERER) is maintained in a separate repository and deployed on Render.com:
- **Repository**: [github.com/Leonardo1888/mcp-google-maps](https://github.com/Leonardo1888/mcp-google-maps)
- **Public endpoint**: `https://mcp-google-maps.onrender.com/mcp`

The `a2a_agents.json` file in the root is a descriptive registry of the system's agents (name, description, endpoint and communication protocol) and serves as operational documentation of the A2A architecture.

---

## Prerequisites

- Python 3.11+
- [uvx](https://docs.astral.sh/uv/) — `pip install uv`
- Docker + Docker Compose
- API credentials for Lightcast, Adzuna, Google Maps and OpenAI (see Configuration)

---

## Installation

```bash
# 1. Clone the repository
git clone https://github.com/Leonardo1888/mcp-job-search
cd mcp-job-search

# 2. Create and activate the virtual environment
python -m venv .venv
source .venv/bin/activate        # Linux/macOS
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
# Used for semantic skill extraction from the CV (OAuth2 Client Credentials)
LIGHTCAST_CLIENT_ID=your_client_id
LIGHTCAST_CLIENT_SECRET=your_client_secret

# Adzuna API — https://developer.adzuna.com/
# Used to search job offers aggregated from hundreds of sources
ADZUNA_APPLICATION_ID=your_app_id
ADZUNA_APPLICATION_KEY=your_app_key

# OpenAI API — https://platform.openai.com/
# Used by OpenWebUI to access GPT-4o (or any compatible model)
OPENAI_API_KEY=your_openai_key

# GOOGLE_MAPS_API_KEY — configured only on the remote Render.com server (mcp-google-maps)
# Not required locally
```

> **Note**: `GOOGLE_MAPS_API_KEY` is stored as an environment variable on the Render.com deployment server and should not be included in the local `.env` file.

### `config.json` — mcpo configuration

```json
{
  "mcpServers": {
    "skill-extractor": {
      "command": "python3",
      "args": ["MCP-Servers/Server1-LC.py"],
      "env": { "PYTHONPATH": "." }
    },
    "job-matcher": {
      "command": "python3",
      "args": ["MCP-Servers/Server2-A.py"],
      "env": { "PYTHONPATH": "." }
    },
    "job-search-agent": {
      "command": "python3",
      "args": ["MCP-Servers/JobSearchAgent-A2A.py"],
      "env": { "PYTHONPATH": "." }
    },
    "job-map-renderer": {
      "type": "streamable-http",
      "url": "https://mcp-google-maps.onrender.com/mcp"
    }
  }
}
```

---

## Running the stack

### 1. Activate the virtual environment

```bash
source .venv/bin/activate
```

### 2. Start OpenWebUI (Docker)

```bash
docker compose up -d

# Stop:
docker compose down

# View logs:
docker compose logs -f
```

### 3. Expose MCP servers via mcpo (port 8000)

```bash
uvx mcpo --port 8000 --config config.json
```

mcpo starts all local servers as subprocesses and exposes their tools as separate REST endpoints. The remote JOB-MAP-RENDERER is reached directly via Streamable HTTP.

| Server | mcpo endpoint | Swagger UI |
|---|---|---|
| SKILL-EXTRACTOR | `http://localhost:8000/skill-extractor` | `http://localhost:8000/skill-extractor/docs` |
| JOB-MATCHER | `http://localhost:8000/job-matcher` | `http://localhost:8000/job-matcher/docs` |
| JOB-SEARCH-AGENT (A2A) | `http://localhost:8000/job-search-agent` | `http://localhost:8000/job-search-agent/docs` |
| JOB-MAP-RENDERER | `https://mcp-google-maps.onrender.com/mcp` | *(remote)* |

### 4. Open OpenWebUI

Navigate to [http://localhost:3000](http://localhost:3000) in your browser.

---

## Registering tools in OpenWebUI

MCP servers must be registered in OpenWebUI as **External Tools** via the admin panel:

> OpenWebUI Admin Panel → Settings → External Tools → **+**

For each server:

| Field | Value |
|---|---|
| Type | OpenAPI |
| URL | `http://host.docker.internal:8000/<server-name>` |
| OpenAPI Spec | `openapi.json` |
| Auth | None |

Once registered, tools are visible to the LLM and invoked automatically when the user's request requires them.

---

## Available tools

### `JobSearchAgent-A2A` — Full pipeline (main entry point)

| Tool | Description |
|---|---|
| `search_jobs_complete` | Full A2A pipeline: skill extraction → job search → geocoding → map rendering |

This is the system's primary tool. The LLM invokes only this tool; `JobSearchAgent-A2A` autonomously orchestrates all internal steps.

**Parameters**:
- `cv_text` — full CV text as a string (primary input, preferred when visible in chat)
- `cv_filename` — `.txt` file name inside the `/info` folder (fallback)
- `country` — ISO 3166-1 alpha-2 country code (default: `it`). Examples: `gb`, `us`, `de`, `fr`
- `include_map` — enables map rendering (default: `true`)

**Output** (JSON):
- `skills_extracted` — list of skills found in the CV
- `jobs_found` — job offers with geographic coordinates (geocoded where missing)
- `map_url` — Google Maps Static image URL (embed with `![Job map](<url>)`)
- `map_jobs` — structured list `{number, title, company, location, url}` for each offer
- `summary` — full text recap with numbered list (the number corresponds to the map pin)

---

### `SKILL-EXTRACTOR` — Skill extraction (Server1-LC.py)

Interfaces with the **Lightcast Skills API**, which maintains a standardised database of over 33,000 skills classified by category. Authenticates via OAuth2 Client Credentials; the token is automatically refreshed on HTTP 401.

| Tool | Description |
|---|---|
| `extract_skills_from_cv` | Extracts skills from a CV via Lightcast. Returns ID, name, confidence score and category |

> The tools `get_skill_details`, `find_related_skills_for_cv` and `analyze_cv_complete` are present in the code but currently disabled (commented out). They can be re-enabled for standalone profile analysis scenarios.

**Parameters for `extract_skills_from_cv`**:
- `cv_text` — CV text as a plain string (preferred)
- `cv_filename` — `.txt` file in the `/info` folder (fallback)
- `confidence_threshold` — minimum confidence score (default: `0.6`; lower to `0.4` if too few skills are returned)

---

### `JOB-MATCHER` — Job search (Server2-A.py)

Interfaces with the **Adzuna Jobs API**, which aggregates offers from hundreds of job boards and company websites. Adzuna's official API guarantees stability and includes geographic coordinates in responses, which are essential for the map rendering step.

| Tool | Description |
|---|---|
| `search_jobs_by_skills` | Primary search: one mandatory skill (`what`) + complementary skills (`what_or`) |

The search strategy follows a two-level logic: the skill with the highest confidence becomes the mandatory parameter (`what`); complementary skills form an alternative set (`what_or`), at least one of which must appear in the listing.

> The `search_jobs_by_title` tool (search by synthesised job title) is present in the code but currently disabled. It can be re-enabled as a fallback when `search_jobs_by_skills` returns 0 results.

---

## Tech stack

| Component | Technology | Role |
|---|---|---|
| User interface | OpenWebUI | Chat frontend, local LLM hosting |
| Language model | GPT-4o (OpenAI API) or any compatible LLM | Natural language interpretation and response synthesis |
| MCP–HTTP bridge | mcpo | Converts MCP STDIO servers to OpenAPI REST endpoints |
| Orchestrator agent | `JobSearchAgent-A2A.py` (FastMCP) | A2A pipeline: coordinates all sub-agents |
| Skill extraction | `Server1-LC.py` (FastMCP, local) | Lightcast Skills API interface via OAuth2 |
| Job search | `Server2-A.py` (FastMCP, local) | Adzuna Jobs API interface |
| Map rendering | `Server3-Maps.py` (FastMCP, remote) | Google Maps Static API; hosted on Render.com |
| Geocoding | Nominatim (OpenStreetMap) | City name to coordinates conversion; no API key required |
| Container | Docker / Docker Compose | Local OpenWebUI deployment |

---

## Adding a new MCP server

The architecture is designed for easy extensibility. Adding a new specialised agent (e.g. LinkedIn search, CV review) requires only three steps:

1. Create `MCP-Servers/ServerN-XX.py` following the structure of the existing servers.

2. Add an entry to `config.json`:

```json
"my-new-server": {
  "command": "python3",
  "args": ["MCP-Servers/ServerN-XX.py"],
  "env": { "PYTHONPATH": "." }
}
```

3. Register the new endpoint in OpenWebUI:

```
Type: OpenAPI
URL:  http://host.docker.internal:8000/my-new-server
OpenAPI Spec: openapi.json
Auth: None
```

To integrate the new agent into the A2A pipeline, add its endpoint in `JobSearchAgent-A2A.py` and register it in `a2a_agents.json` — without modifying any other component of the system.

---

## Differences from existing systems

This system differentiates itself from the main existing MCP servers for job search (LinkedIn MCP Server, official Indeed MCP Server, JobSpy MCP Server) on three points:

- **Official APIs**: uses exclusively Lightcast and Adzuna via stable, authenticated APIs — no web scraping.
- **Semantic skill extraction**: the search starts from CV analysis, not from keywords manually entered by the user.
- **Hybrid MCP + A2A architecture**: combines local and remote servers via the A2A protocol, an approach that none of the existing systems adopts.

---

## Known limitations

- **No seniority filter**: the Adzuna API does not expose a dedicated parameter; keyword-based search returns offers at any experience level.
- **Remote-work listings**: offers that report only the company's country as their location are excluded from the map (not meaningfully geocodable) but remain visible in the text table.
- **Academic terminology**: for CVs with predominantly academic vocabulary, Lightcast may extract terms with confidence in the 0.60–0.70 range that do not match the nomenclature used in real job listings.
