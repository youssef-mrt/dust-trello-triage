"""The integration service: receives Trello board events and gives the Dust agent a
safe, workflow-shaped set of Trello tools.

Routes:
  HEAD/POST /trello/webhook  Trello events (signature-verified)
  POST      /mcp             MCP over Streamable HTTP (bearer token)
  GET       /health
"""

import hmac
import json
import logging
from contextlib import asynccontextmanager
from functools import cache
from typing import Annotated

from fastapi import FastAPI, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from pydantic import Field

from app.config import load_settings
from app.dust import DustTrigger
from app.trello import TrelloClient, TrelloError, verify_webhook_signature
from app.workflow import Boards, ToolRefused, Workflow

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("app")

settings = load_settings()


@cache
def workflow() -> Workflow:
    """Connects to Trello on first use, so the service starts even if Trello is briefly unavailable."""
    trello = TrelloClient(settings.trello_api_key, settings.trello_token)
    boards = Boards.resolve(trello, settings.support_board_id, settings.engineering_board_id)
    trello.protected_list_ids = boards.trigger_list_ids()
    return Workflow(
        trello=trello,
        dust=DustTrigger(settings.dust_webhook_url, settings.dust_webhook_secret),
        boards=boards,
    )


def _guarded(tool: str, call):
    """When a business rule blocks an action, the agent gets the reason so it can explain it
    to the support team. Every tool call is logged."""
    try:
        result = call()
    except (ToolRefused, TrelloError) as exc:
        log.info("tool %s: refused: %s", tool, exc)
        raise ToolError(str(exc)) from exc
    except Exception:
        log.exception("tool %s: failed", tool)
        raise
    log.info("tool %s: ok", tool)
    return result


mcp = MCPServer(
    name="trello-support-triage",
    instructions=(
        "Tools for triaging customer bug reports on the Support Trello board against the "
        "Engineering Trello board. Trello is the source of truth for tickets and statuses."
    ),
)

READ = ToolAnnotations(read_only_hint=True, open_world_hint=False)
WRITE = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=False)
# The two actions that change the Engineering board. The hint tells clients they are consequential;
# the approval itself is enforced by setting both tools to High stake in Dust.
APPROVAL_REQUIRED = ToolAnnotations(read_only_hint=False, destructive_hint=True, open_world_hint=False)

CardId = Annotated[str, Field(description="Trello card id (24 hex chars), as returned by the other tools.")]


@mcp.tool(annotations=READ)
def list_engineering_issues() -> list[dict]:
    """List every open issue on the Engineering board in full: id, title, status (Triage,
    In progress, Fix merged, Released), description, and how many support reports are already
    linked. Compare them with the report's symptoms, not just its wording."""
    return _guarded("list_engineering_issues", lambda: workflow().list_engineering_issues())


@mcp.tool(annotations=WRITE)
def request_more_information(
    support_card_id: CardId,
    summary: Annotated[str, Field(description="What is known so far and why it is not enough to act on.")],
    questions: Annotated[
        list[str], Field(min_length=1, description="Specific questions support should ask the customer, one per item.")
    ],
) -> str:
    """Flag a report as incomplete. Posts a checklist of questions on the support card and
    moves it to 'Needs information'. Support moves it back to 'New reports' once answered,
    which triggers a new investigation automatically."""
    return _guarded(
        "request_more_information",
        lambda: workflow().request_more_information(support_card_id, summary, questions),
    )


@mcp.tool(annotations=APPROVAL_REQUIRED)
def create_engineering_issue(
    support_card_id: CardId,
    title: Annotated[str, Field(description="Short, symptom-first title, e.g. 'PDF invoices show $ for CHF'.")],
    summary: str,
    customer_impact: Annotated[str, Field(description="Who is affected, how badly, any workaround.")],
    steps_to_reproduce: list[str],
    expected_behavior: str,
    actual_behavior: str,
    evidence: list[str],
) -> dict:
    """Create a structured card in Engineering 'Triage' and link it to the support report.
    Call it when no existing issue matches: Dust asks a support team member to approve
    before it runs. Safe to retry: a report is escalated at most once."""
    return _guarded(
        "create_engineering_issue",
        lambda: workflow().create_engineering_issue(
            support_card_id,
            title,
            summary,
            customer_impact,
            steps_to_reproduce,
            expected_behavior,
            actual_behavior,
            evidence,
        ),
    )


@mcp.tool(annotations=APPROVAL_REQUIRED)
def link_to_engineering_issue(
    support_card_id: CardId,
    engineering_card_id: CardId,
    reason: Annotated[str, Field(description="Why this report is the same problem, citing the matching evidence.")],
) -> dict:
    """Link a support report to an existing engineering issue instead of creating a duplicate,
    so engineering sees the extra customer impact. Call it when an existing issue matches:
    Dust asks a support team member to approve before it runs."""
    return _guarded(
        "link_to_engineering_issue",
        lambda: workflow().link_to_engineering_issue(support_card_id, engineering_card_id, reason),
    )


mcp_app = mcp.streamable_http_app(
    stateless_http=True,
    json_response=True,
    # Public service protected by the access token (the SDK's host check is meant for local servers).
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    # A mounted app's own startup hook doesn't run, so start the MCP session manager here.
    async with mcp.session_manager.run():
        yield


# No /docs or /openapi.json: the service is public and has nothing to browse.
app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
expected_auth = f"Bearer {settings.mcp_bearer_token}".encode()


@app.middleware("http")
async def protect_mcp(request: Request, call_next):
    """Only Dust, holding the shared access token, can use the Trello tools."""
    if request.url.path.startswith("/mcp"):
        if not hmac.compare_digest(request.headers.get("authorization", "").encode(), expected_auth):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        if request.method == "GET":
            # No server-to-client stream (stateless server). Otherwise each session holds a
            # connection open until Cloud Run's 5-minute timeout. The MCP spec allows 405 here.
            return Response(status_code=405, headers={"Allow": "POST"})
    return await call_next(request)


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.api_route("/trello/webhook", methods=["HEAD", "POST"])
async def trello_webhook(request: Request) -> Response:
    if request.method == "HEAD":
        return Response(status_code=200)  # Trello checks this address is reachable before sending events
    body = await request.body()  # raw bytes: the signature covers them exactly
    signature = request.headers.get("x-trello-webhook", "")
    if not verify_webhook_signature(body, signature, settings.trello_webhook_callback_url, settings.trello_app_secret):
        return JSONResponse({"error": "invalid signature"}, status_code=401)
    try:
        outcome = await run_in_threadpool(workflow().handle_trello_action, json.loads(body))
    except Exception:
        log.exception("Webhook processing failed; returning 500 so Trello retries")
        return JSONResponse({"error": "processing failed"}, status_code=500)
    log.info("trello webhook: %s", outcome)
    return JSONResponse({"outcome": outcome})


app.mount("/", mcp_app)
