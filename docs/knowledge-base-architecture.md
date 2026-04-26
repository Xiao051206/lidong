# Hermes Knowledge-Base Architecture

Default layout for this repo:

```text
Hermes
|- OpenViking memory provider
|  |- GitHub repos and repo wikis (ingested)
|  `- Wikipedia pages (ingested)
`- GitHub MCP server
   `- Live repository / issue / PR access
```

## Why This Split

- OpenViking is the persistent store. It is where long-lived knowledge lives after ingestion and where Hermes can run semantic search (`viking_search`) and deep reads (`viking_read`).
- GitHub MCP stays live. It is the right place for current repo state, issues, PRs, and anything that should not be snapshotted into the persistent store.
- Wikipedia is treated as reference content. The practical approach is to ingest the specific pages you care about instead of trying to mirror the whole site.

## Files Added By The Bootstrap

Running [scripts/bootstrap_knowledge_base.py](/d:/hermes-agent-main/scripts/bootstrap_knowledge_base.py:1) creates:

- `~/.hermes/config.yaml`
- `~/.hermes/.env`
- `~/.hermes/.env.example`
- `~/.hermes/knowledge_base_sources.yaml`

The config enables:

- `memory.provider: openviking`
- `mcp_servers.github` using `@modelcontextprotocol/server-github`

## Knowledge Flow

1. Put durable knowledge sources into `~/.hermes/knowledge_base_sources.yaml`.
2. Run [scripts/openviking_ingest.py](/d:/hermes-agent-main/scripts/openviking_ingest.py:1) to queue them into OpenViking.
3. Query durable knowledge through OpenViking tools.
4. Query live GitHub state through the GitHub MCP server.

## Manual Steps Still Required

1. Start an OpenViking server or point `OPENVIKING_ENDPOINT` at a remote instance.
2. Fill `GITHUB_TOKEN` and `OPENVIKING_API_KEY` in `~/.hermes/.env` if needed.
3. Ensure `npx` is available for the GitHub MCP server.
4. Run the ingest script after updating `knowledge_base_sources.yaml`.

## Typical Commands

```powershell
. .\venv\bin\activate.ps1
python scripts\bootstrap_knowledge_base.py
python scripts\openviking_ingest.py --dry-run
python scripts\openviking_ingest.py
```

## Suggested Source Strategy

- GitHub repo root URL: ingest the repository itself.
- GitHub repo wiki URL: ingest the wiki when the repo uses one.
- Wikipedia: ingest only the pages that matter to your workflows.
- Use GitHub MCP for anything time-sensitive or writable.
