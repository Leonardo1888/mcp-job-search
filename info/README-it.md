# Ricerca del Lavoro Intelligente — MCP + A2A

Sistema AI-powered per la ricerca automatizzata di offerte di lavoro a partire da un CV, sviluppato come progetto di tesi triennale in Ingegneria Informatica presso l'Università degli Studi di Bergamo.

L'architettura si basa su due protocolli aperti e complementari: il [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) di Anthropic per la comunicazione tra l'LLM e i singoli strumenti, e il protocollo [Agent-to-Agent (A2A)](https://a2a-protocol.org/latest/) per il coordinamento tra agenti specializzati distinti. L'integrazione di entrambi è l'elemento architetturale distintivo rispetto ai sistemi di job matching esistenti.

---

## Architettura

```
Utente (linguaggio naturale)
        │
        ▼
  OpenWebUI (LLM: GPT-4o / qualsiasi modello compatibile)
        │  OpenAPI
        ▼
     mcpo :8000
        │
        ├──► JobSearchAgent-A2A.py   ←── Agente orchestratore (A2A client)
        │           │
        │           ├──► Server1-LC.py        →  Lightcast API   (estrazione skill, STDIO)
        │           ├──► Server2-A.py         →  Adzuna API      (ricerca offerte, STDIO)
        │           ├──► Nominatim API        →  Geocoding       (HTTP pubblico, no API key)
        │           └──► Server3-Maps.py      →  Google Maps API (rendering mappa, Streamable HTTP)
        │                  [remoto su Render.com]
        │
        ├──► Server1-LC.py   (accesso diretto dall'LLM per analisi standalone)
        └──► Server2-A.py    (accesso diretto dall'LLM per ricerca standalone)
```

### Flusso operativo completo (`search_jobs_complete`)

1. L'utente invia alla chat una richiesta in linguaggio naturale (es. *"analizza il mio CV e cercami lavori in Italia"*).
2. L'LLM riconosce l'intenzione e invoca **un solo tool**: `search_jobs_complete` del `JobSearchAgent-A2A`, passando il testo del CV.
3. Il `JobSearchAgent-A2A` apre una sessione MCP verso **SKILL-EXTRACTOR** (STDIO) e chiama `extract_skills_from_cv`.
4. Le competenze estratte vengono normalizzate e usate per costruire la query; si apre una sessione MCP verso **JOB-MATCHER** (STDIO) e si chiama `search_jobs_by_skills`.
5. Le offerte vengono arricchite con coordinate geografiche tramite geocoding **Nominatim** (concorrente via `asyncio.gather`).
6. Il `JobSearchAgent-A2A` si connette al server remoto **JOB-MAP-RENDERER** (Streamable HTTP) su Render.com e chiama `render_jobs_map_by_coordinates`, ottenendo un URL Google Maps Static.
7. Il risultato aggregato — skill estratte, lista offerte e URL della mappa — viene restituito all'LLM, che lo sintetizza e lo presenta in OpenWebUI (tabella Markdown + immagine mappa embedded).

Delegando tutta l'orchestrazione al `JobSearchAgent-A2A`, l'LLM opera come interprete dell'intenzione dell'utente e come formattatore della risposta finale — i due compiti in cui i modelli linguistici moderni eccellono — eliminando il rischio che salti passi o perda il contesto della pipeline multi-step.

### Protocolli e comunicazione

| Connessione | Protocollo | Note |
|---|---|---|
| OpenWebUI → mcpo | OpenAPI REST | Porta 8000 |
| mcpo → Server1, Server2, JobSearchAgent | MCP STDIO | Sottoprocessi Python |
| mcpo → Server3 | MCP Streamable HTTP | Endpoint pubblico su Render.com |
| JobSearchAgent → Server1, Server2 | MCP STDIO | Chiamate interne della pipeline A2A |
| JobSearchAgent → Server3 | MCP Streamable HTTP | `mcp.client.streamable_http` |
| JobSearchAgent → Nominatim | HTTP REST | Gratuito, nessuna API key richiesta |

---

## Struttura del progetto

```
mcp-job-search/
├── MCP-Servers/
│   ├── Server1-LC.py           # SKILL-EXTRACTOR  — Lightcast Skills API (locale, STDIO)
│   ├── Server2-A.py            # JOB-MATCHER      — Adzuna Jobs API (locale, STDIO)
│   └── JobSearchAgent-A2A.py   # Agente A2A       — orchestratore pipeline completa
├── info/
│   ├── cv.txt                  # CV dell'utente (input testuale, fallback)
│   └── istruzioni.txt          # System prompt personalizzato per l'LLM
├── logs/
│   ├── server1-lc.log          # Log SKILL-EXTRACTOR
│   ├── server2-adzuna.log      # Log JOB-MATCHER
│   └── job-search-agent-a2a.log # Log dell'agente A2A
├── .env                        # Credenziali API (non committare mai)
├── .gitignore
├── a2a_agents.json             # Registro descrittivo degli agenti A2A
├── config.json                 # Configurazione mcpo (server locali + remoti)
├── docker-compose.yml          # Container OpenWebUI
└── requirements.txt
```

Il server remoto `Server3-Maps.py` (JOB-MAP-RENDERER) è mantenuto in un repository separato e deployato su Render.com:
- **Repository**: [github.com/Leonardo1888/mcp-google-maps](https://github.com/Leonardo1888/mcp-google-maps)
- **Endpoint pubblico**: `https://mcp-google-maps.onrender.com/mcp`

Il file `a2a_agents.json` nella root costituisce un registro descrittivo degli agenti del sistema (nome, descrizione, endpoint e protocollo di comunicazione) ed è utile come documentazione operativa dell'architettura A2A.

---

## Prerequisiti

- Python 3.11+
- [uvx](https://docs.astral.sh/uv/) — `pip install uv`
- Docker + Docker Compose
- Credenziali API per Lightcast, Adzuna, Google Maps e OpenAI (vedi sezione Configurazione)

---

## Installazione

```bash
# 1. Clona il repository
git clone https://github.com/Leonardo1888/mcp-job-search
cd mcp-job-search

# 2. Crea e attiva il virtual environment
python -m venv .venv
source .venv/bin/activate        # Linux/macOS
# .venv\Scripts\activate         # Windows

# 3. Installa le dipendenze
pip install -r requirements.txt
```

---

## Configurazione

### File `.env`

Crea un file `.env` nella root del progetto:

```env
# Lightcast API — https://lightcast.io/
# Utilizzata per l'estrazione semantica delle competenze dal CV (OAuth2 Client Credentials)
LIGHTCAST_CLIENT_ID=your_client_id
LIGHTCAST_CLIENT_SECRET=your_client_secret

# Adzuna API — https://developer.adzuna.com/
# Utilizzata per la ricerca di offerte di lavoro aggregate da centinaia di fonti
ADZUNA_APPLICATION_ID=your_app_id
ADZUNA_APPLICATION_KEY=your_app_key

# OpenAI API — https://platform.openai.com/
# Utilizzata da OpenWebUI per accedere a GPT-4o (o qualsiasi modello compatibile)
OPENAI_API_KEY=your_openai_key

# GOOGLE_MAPS_API_KEY — configurata solo sul server remoto Render.com (mcp-google-maps)
# Non è necessaria in locale
```

> **Nota**: la `GOOGLE_MAPS_API_KEY` è memorizzata come variabile d'ambiente sul server di deploy Render.com e non va inclusa nel `.env` locale.

### File `config.json` — configurazione mcpo

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

## Avvio del sistema

### 1. Attiva il virtual environment

```bash
source .venv/bin/activate
```

### 2. Avvia OpenWebUI (Docker)

```bash
docker compose up -d

# Per fermare:
docker compose down

# Per visualizzare i log:
docker compose logs -f
```

### 3. Avvia i server MCP tramite mcpo (porta 8000)

```bash
uvx mcpo --port 8000 --config config.json
```

mcpo avvia come sottoprocessi tutti i server locali ed espone i loro tool come endpoint REST separati. Il server remoto JOB-MAP-RENDERER viene raggiunto direttamente tramite Streamable HTTP.

| Server | Endpoint mcpo | Swagger UI |
|---|---|---|
| SKILL-EXTRACTOR | `http://localhost:8000/skill-extractor` | `http://localhost:8000/skill-extractor/docs` |
| JOB-MATCHER | `http://localhost:8000/job-matcher` | `http://localhost:8000/job-matcher/docs` |
| JOB-SEARCH-AGENT (A2A) | `http://localhost:8000/job-search-agent` | `http://localhost:8000/job-search-agent/docs` |
| JOB-MAP-RENDERER | `https://mcp-google-maps.onrender.com/mcp` | *(remoto)* |

### 4. Accedi a OpenWebUI

Apri [http://localhost:3000](http://localhost:3000) nel browser.

---

## Registrazione dei tool in OpenWebUI

I server MCP devono essere registrati in OpenWebUI come **External Tools** tramite il pannello di amministrazione:

> OpenWebUI Admin Panel → Settings → External Tools → **+**

Per ciascun server:

| Campo | Valore |
|---|---|
| Type | OpenAPI |
| URL | `http://host.docker.internal:8000/<nome-server>` |
| OpenAPI Spec | `openapi.json` |
| Auth | None |

Dopo la registrazione, i tool sono visibili all'LLM e vengono invocati automaticamente quando la richiesta dell'utente lo richiede.

---

## Tool disponibili

### `JobSearchAgent-A2A` — Pipeline completa (punto di ingresso principale)

| Tool | Descrizione |
|---|---|
| `search_jobs_complete` | Pipeline A2A completa: estrazione skill → ricerca offerte → geocoding → rendering mappa |

Questo è il tool principale del sistema. L'LLM invoca solo questo tool; è il `JobSearchAgent-A2A` a orchestrare autonomamente tutti i passi interni.

**Parametri**:
- `cv_text` — testo integrale del CV (input primario, preferito quando visibile in chat)
- `cv_filename` — nome del file `.txt` nella cartella `/info` (fallback)
- `country` — codice ISO paese (default: `it`). Esempi: `gb`, `us`, `de`, `fr`
- `include_map` — abilita il rendering della mappa (default: `true`)

**Output** (JSON):
- `skills_extracted` — lista delle skill estratte dal CV
- `jobs_found` — offerte di lavoro con coordinate geografiche (geocodificate dove mancanti)
- `map_url` — URL immagine Google Maps Static (embed con `![Mappa offerte](<url>)`)
- `map_jobs` — lista strutturata `{number, title, company, location, url}` per ogni offerta
- `summary` — riepilogo testuale completo con lista numerata (il numero corrisponde al pin sulla mappa)

---

### `SKILL-EXTRACTOR` — Estrazione competenze (Server1-LC.py)

Interfaccia con la **Lightcast Skills API**, che mantiene un database standardizzato di oltre 33.000 competenze classificate per categoria. Si autentica tramite OAuth2 Client Credentials e il token viene rinnovato automaticamente alla ricezione di un errore HTTP 401.

| Tool | Descrizione |
|---|---|
| `extract_skills_from_cv` | Estrae skill da un CV tramite Lightcast. Restituisce ID, nome, confidenza e categoria |

> I tool `get_skill_details`, `find_related_skills_for_cv` e `analyze_cv_complete` sono presenti nel codice ma attualmente disabilitati (commentati). Possono essere riabilitati per scenari di analisi standalone del profilo.

**Parametri di `extract_skills_from_cv`**:
- `cv_text` — testo del CV come stringa (preferito)
- `cv_filename` — file `.txt` nella cartella `/info` (fallback)
- `confidence_threshold` — soglia minima di confidenza (default: `0.6`; abbassare a `0.4` se si ottengono troppo poche skill)

---

### `JOB-MATCHER` — Ricerca offerte (Server2-A.py)

Interfaccia con la **Adzuna Jobs API**, che aggrega offerte da centinaia di job board e siti aziendali. La scelta di Adzuna garantisce API ufficiali stabili e la presenza di coordinate geografiche nelle risposte, essenziali per la fase di visualizzazione mappa.

| Tool | Descrizione |
|---|---|
| `search_jobs_by_skills` | Ricerca primaria: una skill obbligatoria (`what`) + skill complementari (`what_or`) |

La strategia di ricerca segue una logica a due livelli: la skill con confidenza più alta diventa il parametro obbligatorio (`what`); le skill complementari formano un insieme alternativo (`what_or`), di cui almeno una deve essere presente nell'annuncio.

> Il tool `search_jobs_by_title` (ricerca per titolo professionale sintetizzato) è presente nel codice ma attualmente disabilitato. Può essere riabilitato come fallback quando `search_jobs_by_skills` restituisce 0 risultati.

---

## Stack tecnologico

| Componente | Tecnologia | Ruolo |
|---|---|---|
| Interfaccia utente | OpenWebUI | Chat frontend, hosting locale dell'LLM |
| Modello linguistico | GPT-4o (OpenAI API) o qualsiasi LLM compatibile | Interpretazione del linguaggio naturale e sintesi delle risposte |
| Bridge MCP–HTTP | mcpo | Converte server MCP STDIO in endpoint OpenAPI REST |
| Agente orchestratore | `JobSearchAgent-A2A.py` (FastMCP) | Pipeline A2A: coordina tutti i sotto-agenti |
| Estrazione competenze | `Server1-LC.py` (FastMCP, locale) | Interfaccia con Lightcast Skills API via OAuth2 |
| Ricerca offerte | `Server2-A.py` (FastMCP, locale) | Interfaccia con Adzuna Jobs API |
| Rendering mappa | `Server3-Maps.py` (FastMCP, remoto) | Google Maps Static API; hostato su Render.com |
| Geocoding | Nominatim (OpenStreetMap) | Conversione nomi città in coordinate; nessuna API key richiesta |
| Container | Docker / Docker Compose | Deploy di OpenWebUI in locale |

---

## Aggiungere un nuovo server MCP

L'architettura è progettata per essere facilmente estendibile. L'aggiunta di un nuovo agente specializzato (es. ricerca su LinkedIn, revisione del CV) richiede solo tre operazioni:

1. Crea `MCP-Servers/ServerN-XX.py` seguendo la struttura degli esistenti.

2. Aggiungi una voce in `config.json`:

```json
"my-new-server": {
  "command": "python3",
  "args": ["MCP-Servers/ServerN-XX.py"],
  "env": { "PYTHONPATH": "." }
}
```

3. Registra il nuovo endpoint in OpenWebUI:

```
Type: OpenAPI
URL:  http://host.docker.internal:8000/my-new-server
OpenAPI Spec: openapi.json
Auth: None
```

Per integrare il nuovo agente nella pipeline A2A, aggiungi il suo endpoint in `JobSearchAgent-A2A.py` e registralo in `a2a_agents.json` — senza modificare nessun altro componente del sistema.

---

## Differenze rispetto ai sistemi esistenti

Il sistema si differenzia dai principali MCP server per la ricerca del lavoro esistenti (LinkedIn MCP Server, Indeed MCP Server ufficiale, JobSpy MCP Server) su tre aspetti:

- **API ufficiali**: utilizza esclusivamente Lightcast e Adzuna tramite API stabili e autenticate, senza web scraping.
- **Estrazione semantica delle competenze**: la ricerca parte dall'analisi del CV, non da keyword inserite manualmente dall'utente.
- **Architettura ibrida MCP + A2A**: combina server locali e remoti tramite protocollo A2A, un approccio che nessuno dei sistemi esistenti adotta.

---

## Limitazioni note

- **Filtro seniority assente**: l'API Adzuna non espone un parametro dedicato; la ricerca per keyword restituisce offerte di qualsiasi livello di esperienza.
- **Offerte in smart working**: le offerte che riportano come localizzazione solo il paese di sede vengono escluse dalla mappa (non georeferenziabili in modo significativo) ma rimangono visibili nella tabella testuale.
- **Terminologia accademica**: per CV con nomenclatura prevalentemente accademica, Lightcast può estrarre termini con confidenza nella fascia 0.60–0.70 che non corrispondono alla nomenclatura usata negli annunci reali.
