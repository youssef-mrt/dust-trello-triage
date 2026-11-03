import pytest

from app.dust import DustError
from app.workflow import ToolRefused, is_new_report

# ---- Event classification and duplicate handling ------------------------------------


def test_only_a_card_arriving_in_new_reports_starts_a_run(env):
    card = env.support_card(list_key="drafts")
    sup = env.boards.support
    comment = {"action": {"id": "a1", "type": "commentCard", "data": {"card": {"id": card}}}}
    elsewhere = env.moved_action(card, sup["drafts"], sup["needs_info"])
    from_drafts = env.moved_action(card, sup["drafts"], sup["new"])
    back_from_needs_info = env.moved_action(card, sup["needs_info"], sup["new"])

    assert not is_new_report(comment["action"], env.boards)
    assert not is_new_report(elsewhere["action"], env.boards)
    assert is_new_report(from_drafts["action"], env.boards)
    assert is_new_report(back_from_needs_info["action"], env.boards)
    assert is_new_report(env.created_action(env.support_card())["action"], env.boards)


def test_duplicate_webhook_delivery_starts_one_investigation(env):
    card = env.support_card()
    payload = env.created_action(card, action_id="same-action")

    env.workflow.handle_trello_action(payload)
    outcome = env.workflow.handle_trello_action(payload)  # Trello redelivers the same event

    assert outcome.startswith("duplicate")
    assert len(env.dust.events) == 1
    assert env.dust.events[0]["support_card"]["description"] == "Customer says it is broken."
    assert env.card_list(card) == "Investigating"


def test_failed_dust_call_is_retried_on_redelivery(env):
    card = env.support_card()
    payload = env.created_action(card, action_id="retry-me")
    env.dust.fail_next = True

    with pytest.raises(DustError):
        env.workflow.handle_trello_action(payload)
    assert env.card_list(card) == "New reports"  # left in place for the retry
    env.workflow.handle_trello_action(payload)  # Trello's retry

    assert len(env.dust.events) == 1
    assert env.card_list(card) == "Investigating"


# ---- Approval-gated escalation ---------------------------------------------------------


def test_escalation_refused_unless_under_investigation(env):
    card = env.support_card()
    with pytest.raises(ToolRefused):
        env.create_issue(card)
    assert env.trello.board_cards("eng-board") == []


def test_escalation_happens_once_even_if_retried(env):
    card = env.support_card()
    env.investigate(card)

    first = env.create_issue(card)
    second = env.create_issue(card)

    assert second["engineering_card_url"] == first["engineering_card_url"]
    assert len(env.trello.board_cards("eng-board")) == 1
    assert env.card_list(card) == "Escalated to engineering"


def test_linking_to_existing_issue_creates_no_duplicate(env):
    issue = env.engineering_card("Scheduled exports time out")
    card = env.support_card()
    env.investigate(card)

    env.workflow.link_to_engineering_issue(card, issue, "Same timeout")
    env.create_issue(card)  # a later create attempt returns the existing escalation

    assert len(env.trello.board_cards("eng-board")) == 1
    assert [i["linked_support_reports"] for i in env.workflow.list_engineering_issues()] == [1]
