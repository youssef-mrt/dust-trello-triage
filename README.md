# Trello × Dust: bug triage between support and engineering

A prototype for a support team that tracks bug reports in Trello. When a report lands in *New reports*, a Dust agent checks it is complete, compares it with existing engineering issues, and proposes either a new engineering issue or a link to an existing one. Support approves in a shared Dust Pod.

## Value

- **Faster first response:** every report is triaged by the agent within two minutes of arriving, without waiting for someone to pick it up. Dust customer Wayflyer runs the same pattern on Jira, with [triage research done in under a minute](https://dust.tt/customers/how-wayflyer-built-a-self-tuning-support-flywheel-with-dust).
- **Less product team time lost:** incomplete reports go back to the customer before escalation, so the product owner doesn't chase missing details.
- **Less support team triage time:** the support team only validates escalations and bug deduplication. A similar setup used by Augment Code's own support team [cut daily triage from several hours to minutes](https://www.augmentcode.com/blog/automating-customer-feedback-and-support-with-ai-agents).

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

Checks: `uv run pytest -q && uv run ruff check . && uv run ruff format --check .` (6 tests on the workflow rules, with in-memory Trello and Dust). Teardown: `scripts.demo webhooks delete`, then `gcloud projects delete <project>`.

## Architecture

One Python service on Cloud Run using FastAPI. It receives Trello webhooks and serves the agent's tools over MCP. All workflow rules are in [workflow.py](app/workflow.py). There is no database: trello is the source of truth and a card's list is its status, and attachments link reports to issues.

## Authentication

- **Trello → service:** Trello's HMAC-SHA1 webhook signature. Invalid signatures get a 401.
- **Dust → service:** a bearer token on the MCP endpoint.
- **Service → Dust:** events signed with HMAC-SHA256.
- **Service → Trello:** API key and token in a header.

The service is public because Trello and Dust can't present Google credentials; the app authenticates them itself.

## Tradeoffs and limitations

### Missing features

- Having in the Pod files the bug report checklist, troubleshooting guides and release notes, so the agent can use them.
- When a fix is shipped by engineering, linked tickets aren't updated automatically.
- When a ticket needs information, we can have an agent draft response to customer on the crm.

### Scalability and robustness
- Trello holds the state: Simpler, but the checks aren't atomic: two agent instances can make different changes, and only one will apply while the other will be dropped silently. This choice was for simplicity and a production setting would use a database such as Firebase for the state.
- More extensive handling of errors on tool parameters for explicit feedback to the agent.
- Webhooks are processed synchronously: relying on Trello's retries. A production setting would use a queue for robustness and for handling high volume and downtime.
- The agent read all open engineering issues, which only works on a small board. Large boards may need a search tool.

## Time spent
- Around 4h spent on the implementation, excluding time exploring the Dust platform and its capabilities.

## How a customer deployment would differ

- OAuth for Trello and for the Dust MCP connection, with a bot account for the agent's actions.
- Secret Manager and a least-privilege service account.
- A queue with retries for the Dust call.
- A small store for atomic agent changes in Trello using a idempotency keys and an approval audit trail.
- Issue search, the customer's docs connected to the Pod, and the release follow-up.
