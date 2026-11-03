import itertools

import pytest

from app.config import ENGINEERING_LISTS, SUPPORT_LISTS
from app.dust import DustError
from app.trello import TrelloError
from app.workflow import Boards, Workflow

_ids = itertools.count(1)


def new_id(prefix: str) -> str:
    return f"{prefix}{next(_ids)}"


class FakeTrello:
    """Just enough of TrelloClient to exercise the workflow, including the trigger-list guard."""

    def __init__(self):
        self.lists = {}  # list id -> (board id, name)
        self.cards = {}
        self.comments = {}
        self.attachments = {}
        self.protected_list_ids = frozenset()

    def add_list(self, board_id, name):
        list_id = new_id("list")
        self.lists[list_id] = (board_id, name)
        return list_id

    def board_lists(self, board_id):
        return [{"id": lid, "name": name} for lid, (bid, name) in self.lists.items() if bid == board_id]

    def create_card(self, list_id, name, desc):
        card_id = new_id("card")
        self.cards[card_id] = {"id": card_id, "name": name, "desc": desc, "idList": list_id}
        return self.get_card(card_id)

    def get_card(self, card_id):
        card = dict(self.cards[card_id])
        board_id, list_name = self.lists[card["idList"]]
        return {
            **card,
            "idBoard": board_id,
            "shortUrl": f"https://trello.test/c/{card_id}",
            "list": {"name": list_name},
        }

    def board_cards(self, board_id):
        return [self.get_card(c) for c in self.cards if self.lists[self.cards[c]["idList"]][0] == board_id]

    def move_card(self, card_id, list_id):
        if list_id in self.protected_list_ids:
            raise TrelloError("Refusing to move a card into a workflow trigger list (would self-trigger).")
        self.cards[card_id]["idList"] = list_id

    def add_comment(self, card_id, text):
        self.comments.setdefault(card_id, []).append(text)

    def get_comments(self, card_id):
        return [{"text": t} for t in self.comments.get(card_id, [])]

    def attach_link(self, card_id, url, name):
        self.attachments.setdefault(card_id, []).append({"name": name, "url": url})

    def get_attachments(self, card_id):
        return self.attachments.get(card_id, [])


class FakeDust:
    def __init__(self):
        self.events = []
        self.fail_next = False

    def send(self, event):
        if self.fail_next:
            self.fail_next = False
            raise DustError("Dust unavailable")
        self.events.append(event)


class Env:
    def __init__(self):
        self.trello = FakeTrello()
        self.dust = FakeDust()
        for name in SUPPORT_LISTS.values():
            self.trello.add_list("support-board", name)
        for name in ENGINEERING_LISTS.values():
            self.trello.add_list("eng-board", name)
        self.boards = Boards.resolve(self.trello, "support-board", "eng-board")
        self.trello.protected_list_ids = self.boards.trigger_list_ids()
        self.workflow = Workflow(self.trello, self.dust, self.boards)

    def support_card(self, name="Report", list_key="new"):
        return self.trello.create_card(self.boards.support[list_key], name, "Customer says it is broken.")["id"]

    def engineering_card(self, name="Issue", list_key="in_progress", desc=""):
        return self.trello.create_card(self.boards.engineering[list_key], name, desc)["id"]

    def card_list(self, card_id):
        return self.trello.get_card(card_id)["list"]["name"]

    # Trello webhook payloads, trimmed to the fields the workflow reads.
    def created_action(self, card_id, action_id=None):
        return {
            "action": {
                "id": action_id or new_id("action"),
                "type": "createCard",
                "data": {"card": {"id": card_id}, "list": {"id": self.trello.cards[card_id]["idList"]}},
            }
        }

    def moved_action(self, card_id, before_id, after_id, action_id=None):
        """Simulates a human moving a card in Trello (bypasses the integration's guard)."""
        self.trello.cards[card_id]["idList"] = after_id
        return {
            "action": {
                "id": action_id or new_id("action"),
                "type": "updateCard",
                "data": {"card": {"id": card_id}, "listBefore": {"id": before_id}, "listAfter": {"id": after_id}},
            }
        }

    def investigate(self, card_id):
        """The card is under investigation, as after a new report event."""
        self.trello.cards[card_id]["idList"] = self.boards.support["investigating"]

    def create_issue(self, card_id):
        return self.workflow.create_engineering_issue(
            card_id, "Title", "Summary", "Impact", ["Step 1"], "Expected", "Actual", ["Evidence"]
        )


@pytest.fixture
def env():
    return Env()
