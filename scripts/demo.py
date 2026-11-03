"""Demo helper: sets up and resets the boards. Everything else in the demo happens in Trello and Dust.

Usage (reads .env from the project folder):
  uv run python -m scripts.demo setup                  create the two [DEMO] boards and their lists
  uv run python -m scripts.demo reset                  archive demo cards and re-seed
  uv run python -m scripts.demo webhooks register|delete
  uv run python -m scripts.demo status                 print both boards
"""

import argparse
import os
import sys

from dotenv import load_dotenv

from app.config import ENGINEERING_LISTS, SUPPORT_LISTS
from app.trello import TrelloClient
from app.workflow import Boards
from demo.seed_data import CASES, ENGINEERING_ISSUES, PRE_ESCALATED_REPORT

DEMO_PREFIX = "[DEMO]"
load_dotenv()  # settings from .env; values already set in the shell take precedence


def trello() -> TrelloClient:
    # No protected lists: this script plays the humans, who may move cards anywhere.
    return TrelloClient(os.environ["TRELLO_API_KEY"], os.environ["TRELLO_TOKEN"])


def boards(client: TrelloClient) -> Boards:
    support_id, eng_id = os.environ["TRELLO_SUPPORT_BOARD_ID"], os.environ["TRELLO_ENGINEERING_BOARD_ID"]
    for board_id in (support_id, eng_id):
        # Reset archives every card on these boards, so refuse anything not created as a demo board.
        if not client.get_board(board_id)["name"].startswith(DEMO_PREFIX):
            sys.exit(f"Board {board_id} is not a {DEMO_PREFIX} board; refusing to touch it.")
    return Boards.resolve(client, support_id, eng_id)


def cmd_setup(args) -> None:
    """Safe to re-run: reuses existing demo boards and only adds missing lists."""
    client = trello()
    existing = {b["name"]: b for b in client.my_open_boards()}
    for label, lists, var in (
        ("Support", SUPPORT_LISTS, "TRELLO_SUPPORT_BOARD_ID"),
        ("Engineering", ENGINEERING_LISTS, "TRELLO_ENGINEERING_BOARD_ID"),
    ):
        name = f"{DEMO_PREFIX} BillingCompany {label}"
        board = existing.get(name) or client.create_board(name)
        present = {lst["name"] for lst in client.board_lists(board["id"])}
        for pos, list_name in enumerate(lists.values(), 1):
            if list_name not in present:
                # "top" keeps Drafts first on boards created before it existed.
                client.create_list(board["id"], list_name, "top" if pos == 1 else pos * 1000)
        print(f"{var}={board['id']}  # {board['url']}")


def cmd_reset(args) -> None:
    client = trello()
    b = boards(client)
    archived = 0
    for board_id in (b.support_board_id, b.engineering_board_id):
        for card in client.board_cards(board_id):
            client.archive_card(card["id"])
            archived += 1
    print(f"Archived {archived} demo cards.")

    # Seeding doesn't trigger the agent: nothing is created in New reports.
    issues = {}
    for issue in ENGINEERING_ISSUES:
        issues[issue["key"]] = client.create_card(b.engineering[issue["list"]], issue["name"], issue["desc"])
    linked_issue = issues[PRE_ESCALATED_REPORT["issue_key"]]
    report = client.create_card(b.support["escalated"], PRE_ESCALATED_REPORT["name"], PRE_ESCALATED_REPORT["desc"])
    client.attach_link(report["id"], linked_issue["shortUrl"], f"Engineering: {linked_issue['name']}")
    client.attach_link(linked_issue["id"], report["shortUrl"], f"Support: {report['name']}")
    # The three demo reports wait in Drafts; dragging one to New reports starts its case.
    for case in reversed(CASES.values()):  # cards go on top, so case 1 ends up first
        client.create_card(b.support["drafts"], case["name"], case["desc"])
    print(f"Seeded {len(issues)} engineering issues, 1 pre-escalated report and {len(CASES)} drafts.")


def cmd_webhooks(args) -> None:
    client = trello()
    if args.action == "delete":
        # Only this demo's webhooks: the token may have others.
        for hook in client.list_webhooks(os.environ["TRELLO_TOKEN"]):
            if hook["callbackURL"] != os.environ["TRELLO_WEBHOOK_CALLBACK_URL"]:
                continue
            client.delete_webhook(hook["id"])
            print("deleted", hook["id"])
    else:
        b = boards(client)
        url = os.environ["TRELLO_WEBHOOK_CALLBACK_URL"]
        # Only the Support board starts the workflow; the agent reads Engineering through its tools.
        hook = client.create_webhook(b.support_board_id, url, f"dust-trello-demo {b.support_board_id}")
        print("registered", hook["id"], "for board", b.support_board_id)


def cmd_status(args) -> None:
    client = trello()
    b = boards(client)
    for title, board_id in (("SUPPORT", b.support_board_id), ("ENGINEERING", b.engineering_board_id)):
        print(f"\n== {title}")
        cards = client.board_cards(board_id)
        for lst in client.board_lists(board_id):
            print(f"  {lst['name']}")
            for card in (c for c in cards if c["idList"] == lst["id"]):
                print(f"    - {card['name']}  [{card['id']}]")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(required=True)
    sub.add_parser("setup").set_defaults(fn=cmd_setup)
    sub.add_parser("reset").set_defaults(fn=cmd_reset)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    p = sub.add_parser("webhooks")
    p.add_argument("action", choices=["register", "delete"])
    p.set_defaults(fn=cmd_webhooks)
    args = parser.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
