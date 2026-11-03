# Trello × Dust: bug triage between support and engineering

A prototype for a support team that tracks bug reports in Trello. When a report lands in *New reports*, a Dust agent checks it is complete, compares it with existing engineering issues, and proposes either a new engineering issue or a link to an existing one. Support approves in a shared Dust Pod.

## How it works

1. A card arrives in *New reports* (created there, or moved from *Drafts* or back from *Needs information*). Nothing else triggers a run.
2. The service verifies Trello's signature, sends the report to the Dust trigger, and moves the card to *Investigating*.
3. The agent either asks for missing details (card → *Needs information*) or proposes creating or linking an engineering issue.
4. Dust asks support to approve. On approval, a structured card is created in Engineering *Triage*, or the report is linked to the matching issue; the support card moves to *Escalated to engineering*.

Trello holds the state.

| MCP tool | Dust approval | Enforced in code |
|---|---|---|
| `list_engineering_issues` | never ask | read-only |
| `request_more_information` | never ask | at least one question |
| `create_engineering_issue` | **High** | card must be in *Investigating*; escalated once |
| `link_to_engineering_issue` | **High** | same |

## Setup

Needs [uv](https://docs.astral.sh/uv/), gcloud with a billed project, a Trello account, and Dust admin access.

1. Create a Trello app (https://trello.com/power-ups/admin), generate a token, and fill `.env` from [.env.example](.env.example).
2. `uv run python -m scripts.demo setup` creates the boards and prints their ids for `.env`.
3. `./deploy.sh` deploys to Cloud Run, passing `.env` as environment variables, and prints the URL.
4. In Dust:
   - Add the MCP server (`<url>/mcp`, bearer token). Set the two escalation tools to **High** and the other two to **Never ask** (triggered runs have nobody to click).
   - Create the Pod, then create and publish `@support-triage` with [dust/agent-instructions.md](dust/agent-instructions.md).
   - Add a custom webhook source (`X-Dust-Signature`, sha256) and a trigger that posts into the Pod. Put its URL and secret in `.env` and re-run `./deploy.sh`.
5. `uv run python -m scripts.demo webhooks register`, then `uv run python -m scripts.demo reset` (it only touches `[DEMO]` boards).

Lint: `uv run ruff check . && uv run ruff format --check .`. Teardown: `scripts.demo webhooks delete`, then `gcloud projects delete <project>`.
