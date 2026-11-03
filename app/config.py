"""Settings for connecting to your Trello boards and Dust workspace, read once at startup."""

import os
from dataclasses import dataclass

# Each list is a ticket stage. Lists are found by name, so setting up a board only
# requires its id.
SUPPORT_LISTS = {
    "drafts": "Drafts",
    "new": "New reports",
    "investigating": "Investigating",
    "needs_info": "Needs information",
    "escalated": "Escalated to engineering",
}
ENGINEERING_LISTS = {
    "triage": "Triage",
    "in_progress": "In progress",
    "fix_merged": "Fix merged",
    "released": "Released",
}


@dataclass(frozen=True)
class Settings:
    trello_api_key: str
    trello_token: str
    trello_app_secret: str  # proves that incoming events really come from Trello
    trello_webhook_callback_url: str  # the address Trello sends board events to
    support_board_id: str
    engineering_board_id: str
    dust_webhook_url: str
    dust_webhook_secret: str
    mcp_bearer_token: str


def load_settings() -> Settings:
    env = os.environ
    return Settings(
        trello_api_key=env["TRELLO_API_KEY"],
        trello_token=env["TRELLO_TOKEN"],
        trello_app_secret=env["TRELLO_APP_SECRET"],
        trello_webhook_callback_url=env["TRELLO_WEBHOOK_CALLBACK_URL"],
        support_board_id=env["TRELLO_SUPPORT_BOARD_ID"],
        engineering_board_id=env["TRELLO_ENGINEERING_BOARD_ID"],
        dust_webhook_url=env["DUST_WEBHOOK_URL"],
        dust_webhook_secret=env.get("DUST_WEBHOOK_SECRET", ""),
        mcp_bearer_token=env["MCP_BEARER_TOKEN"],
    )
