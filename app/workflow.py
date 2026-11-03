"""The support-to-engineering workflow rules.

Every action that matters (investigating, asking for details, escalating, linking) goes
through here, so the rules live in one place and are tested. All workflow state lives in
Trello: the list a card is in is its status, and attachments link reports to issues.
"""

from dataclasses import dataclass

from app.config import ENGINEERING_LISTS, SUPPORT_LISTS
from app.dust import DustTrigger
from app.trello import TrelloClient


class ToolRefused(ValueError):
    """An action the workflow rules don't allow. The agent explains the reason to support."""


@dataclass(frozen=True)
class Boards:
    support_board_id: str
    engineering_board_id: str
    support: dict[str, str]  # list key (see config.SUPPORT_LISTS) -> Trello list id
    engineering: dict[str, str]

    @classmethod
    def resolve(cls, trello: TrelloClient, support_board_id: str, engineering_board_id: str) -> "Boards":
        def ids(board_id: str, names: dict[str, str]) -> dict[str, str]:
            by_name = {lst["name"]: lst["id"] for lst in trello.board_lists(board_id)}
            missing = [n for n in names.values() if n not in by_name]
            if missing:
                raise RuntimeError(f"Board {board_id} is missing lists {missing}; run scripts/demo.py setup")
            return {key: by_name[name] for key, name in names.items()}

        return cls(
            support_board_id,
            engineering_board_id,
            ids(support_board_id, SUPPORT_LISTS),
            ids(engineering_board_id, ENGINEERING_LISTS),
        )

    def trigger_list_ids(self) -> frozenset[str]:
        """Lists that start the workflow when a person moves a card into them."""
        return frozenset({self.support["new"]})

    def engineering_status(self, list_id: str) -> str:
        return next((ENGINEERING_LISTS[k] for k, lid in self.engineering.items() if lid == list_id), "unknown")


def is_new_report(action: dict, boards: Boards) -> bool:
    """Only a card arriving in New reports needs the agent; everything else is ignored."""
    data = action.get("data", {})
    arrived_in = data.get("listAfter") or (data.get("list") if action.get("type") == "createCard" else None)
    return (arrived_in or {}).get("id") == boards.support["new"]


class Workflow:
    def __init__(self, trello: TrelloClient, dust: DustTrigger, boards: Boards):
        self.trello = trello
        self.dust = dust
        self.boards = boards

    # ---- Trello webhook entry point -------------------------------------------------

    def handle_trello_action(self, payload: dict) -> str:
        action = payload.get("action") or {}
        if not is_new_report(action, self.boards):
            return "ignored"
        card = self.trello.get_card(action["data"]["card"]["id"])
        # Trello may deliver the same event twice. The first delivery moved the card on,
        # so a card no longer in New reports has already been handled.
        if card["idList"] != self.boards.support["new"]:
            return "duplicate (already handled)"
        # The report travels with the event, so the agent starts from it directly.
        report = {
            "id": card["id"],
            "title": card["name"],
            "url": card["shortUrl"],
            "description": card["desc"],
            "comments": self.trello.get_comments(card["id"]),
        }
        # Dust first: if it fails, the card stays in New reports and Trello's automatic
        # retry (after 30s, 60s, 120s) tries again.
        self.dust.send({"event": "new_report", "support_card": report})
        self.trello.move_card(card["id"], self.boards.support["investigating"])
        return "investigation started"

    # ---- Operations exposed as MCP tools --------------------------------------------

    def list_engineering_issues(self) -> list[dict]:
        # All open issues: the agent compares symptoms to catch duplicates.
        return [
            {
                "id": c["id"],
                "title": c["name"],
                "status": self.boards.engineering_status(c["idList"]),
                "url": c["shortUrl"],
                "description": c["desc"],
                "linked_support_reports": len(self._links(c["id"], "Support")),
            }
            for c in self.trello.board_cards(self.boards.engineering_board_id)
        ]

    def request_more_information(self, support_card_id: str, summary: str, questions: list[str]) -> str:
        self._support_card(support_card_id)
        self.trello.add_comment(
            support_card_id,
            f"❓ More information needed\n{summary}\n\nPlease ask the customer:\n"
            + "\n".join(f"- [ ] {q}" for q in questions)
            + "\n\nAdd the answers as a comment, then move this card back to “New reports” to reinvestigate.",
        )
        self.trello.move_card(support_card_id, self.boards.support["needs_info"])
        return "Card moved to Needs information. It will be reinvestigated when support moves it back."

    def create_engineering_issue(
        self,
        support_card_id: str,
        title: str,
        summary: str,
        customer_impact: str,
        steps_to_reproduce: list[str],
        expected_behavior: str,
        actual_behavior: str,
        evidence: list[str],
    ) -> dict:
        def escalate(report_card: dict) -> dict:
            desc = "\n\n".join(
                [
                    f"## Summary\n{summary}",
                    f"## Customer impact\n{customer_impact}",
                    "## Steps to reproduce\n" + "\n".join(f"{i}. {s}" for i, s in enumerate(steps_to_reproduce, 1)),
                    f"## Expected\n{expected_behavior}",
                    f"## Actual\n{actual_behavior}",
                    "## Evidence\n" + "\n".join(f"- {e}" for e in evidence),
                    f"## Linked support reports\n- {report_card['shortUrl']}",
                    "_Created by the support triage agent after support approval in Dust._",
                ]
            )
            issue = self.trello.create_card(self.boards.engineering["triage"], title, desc)
            self.trello.attach_link(issue["id"], report_card["shortUrl"], f"Support: {report_card['name']}")
            return issue

        return self._escalate(support_card_id, escalate, "created")

    def link_to_engineering_issue(self, support_card_id: str, engineering_card_id: str, reason: str) -> dict:
        issue = self._engineering_card(engineering_card_id)

        def escalate(report_card: dict) -> dict:
            self.trello.add_comment(
                engineering_card_id,
                f"🔗 Another customer report linked: {report_card['name']} ({report_card['shortUrl']})\n{reason}",
            )
            self.trello.attach_link(engineering_card_id, report_card["shortUrl"], f"Support: {report_card['name']}")
            return issue

        return self._escalate(support_card_id, escalate, "linked")

    def _escalate(self, support_card_id: str, do_escalate, verb: str) -> dict:
        """Rules for the two actions that need a person's approval.

        Dust asks a support team member to approve before either action runs. These
        checks add that the action is valid: the report is under investigation (it sits in
        Investigating), and it is escalated only once, even if the request is repeated.
        """
        report_card = self._support_card(support_card_id)
        existing = self._links(support_card_id, "Engineering")
        if existing or report_card["idList"] == self.boards.support["escalated"]:
            return {
                "engineering_card_url": existing[0]["url"] if existing else None,
                "note": "Already escalated earlier; nothing new was created.",
            }
        if report_card["idList"] != self.boards.support["investigating"]:
            raise ToolRefused(
                f"This report is in '{report_card['list']['name']}', not 'Investigating'. "
                "Only a report under investigation can be escalated."
            )
        issue = do_escalate(report_card)
        # Attach first: it is what marks the report as escalated if a later step fails.
        self.trello.attach_link(support_card_id, issue["shortUrl"], f"Engineering: {issue['name']}")
        self.trello.add_comment(
            support_card_id, f"🚀 Escalated: {verb} engineering issue {issue['name']} ({issue['shortUrl']})"
        )
        self.trello.move_card(support_card_id, self.boards.support["escalated"])
        return {"engineering_card_id": issue["id"], "engineering_card_url": issue["shortUrl"], "action": verb}

    # ---- Helpers ----------------------------------------------------------------------

    def _links(self, card_id: str, board_name: str) -> list[dict]:
        """Cross-board links are attachments named "Support: ..." or "Engineering: ..."."""
        return [a for a in self.trello.get_attachments(card_id) if a["name"].startswith(f"{board_name}: ")]

    def _support_card(self, card_id: str) -> dict:
        return self._card(card_id, self.boards.support_board_id, "Support")

    def _engineering_card(self, card_id: str) -> dict:
        return self._card(card_id, self.boards.engineering_board_id, "Engineering")

    def _card(self, card_id: str, board_id: str, board_name: str) -> dict:
        card = self.trello.get_card(card_id)
        if card["idBoard"] != board_id:
            raise ToolRefused(f"{card_id} is not a card on the {board_name} board.")
        # An archived ticket is closed: an old conversation must not act on it.
        if card.get("closed"):
            raise ToolRefused(f"{card['name']!r} is archived; work on the current ticket instead.")
        return card
