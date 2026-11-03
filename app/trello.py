"""Connects the integration to your Trello boards: reads tickets, posts comments and moves
cards between stages on behalf of the triage agent."""

import base64
import hashlib
import hmac
from typing import Any

import requests

API = "https://api.trello.com/1"


class TrelloError(RuntimeError):
    pass


def verify_webhook_signature(body: bytes, signature: str, callback_url: str, app_secret: str) -> bool:
    """Check that an event really comes from Trello (base64 HMAC-SHA1 of body + callback URL)."""
    digest = hmac.new(app_secret.encode(), body + callback_url.encode(), hashlib.sha1).digest()
    expected = base64.b64encode(digest).decode()
    return hmac.compare_digest(expected, signature or "")


class TrelloClient:
    def __init__(self, api_key: str, token: str, protected_list_ids: frozenset[str] = frozenset()):
        self.protected_list_ids = protected_list_ids
        self._http = requests.Session()
        self._http.headers["Authorization"] = f'OAuth oauth_consumer_key="{api_key}", oauth_token="{token}"'

    def _request(self, method: str, path: str, **kwargs) -> Any:
        try:
            response = self._http.request(method, API + path, timeout=30, **kwargs)
        except requests.RequestException as exc:
            raise TrelloError(f"Trello {method} {path} failed: {exc}") from exc
        if response.status_code >= 400:
            raise TrelloError(f"Trello {method} {path} -> {response.status_code}: {response.text[:200]}")
        return response.json() if response.content else None

    # Reads
    def get_card(self, card_id: str) -> dict:
        return self._request(
            "GET",
            f"/cards/{card_id}",
            params={"fields": "name,desc,idBoard,idList,shortUrl,closed", "list": "true"},
        )

    def get_comments(self, card_id: str) -> list[dict]:
        actions = self._request("GET", f"/cards/{card_id}/actions", params={"filter": "commentCard"})
        return [
            {"author": a["memberCreator"]["fullName"], "date": a["date"], "text": a["data"]["text"]}
            for a in reversed(actions)
        ]

    def get_attachments(self, card_id: str) -> list[dict]:
        return self._request("GET", f"/cards/{card_id}/attachments", params={"fields": "name,url"})

    def board_lists(self, board_id: str) -> list[dict]:
        return self._request("GET", f"/boards/{board_id}/lists", params={"fields": "name"})

    def board_cards(self, board_id: str) -> list[dict]:
        return self._request("GET", f"/boards/{board_id}/cards/open", params={"fields": "name,desc,idList,shortUrl"})

    # Writes
    def create_card(self, list_id: str, name: str, desc: str) -> dict:
        return self._request("POST", "/cards", params={"idList": list_id, "name": name, "desc": desc, "pos": "top"})

    def move_card(self, card_id: str, list_id: str) -> None:
        if list_id in self.protected_list_ids:
            raise TrelloError("Refusing to move a card into a workflow trigger list (would self-trigger).")
        self._request("PUT", f"/cards/{card_id}", params={"idList": list_id})

    def add_comment(self, card_id: str, text: str) -> None:
        self._request("POST", f"/cards/{card_id}/actions/comments", params={"text": text})

    def attach_link(self, card_id: str, url: str, name: str) -> None:
        self._request("POST", f"/cards/{card_id}/attachments", params={"url": url, "name": name})

    # Board setup (used by the demo scripts)
    def create_board(self, name: str) -> dict:
        return self._request("POST", "/boards", params={"name": name, "defaultLists": "false"})

    def create_list(self, board_id: str, name: str, pos: int | str) -> dict:
        return self._request("POST", "/lists", params={"idBoard": board_id, "name": name, "pos": pos})

    def my_open_boards(self) -> list[dict]:
        return self._request("GET", "/members/me/boards", params={"filter": "open", "fields": "name,url"})

    def get_board(self, board_id: str) -> dict:
        return self._request("GET", f"/boards/{board_id}", params={"fields": "name,url"})

    def archive_card(self, card_id: str) -> None:
        self._request("PUT", f"/cards/{card_id}", params={"closed": "true"})

    def list_webhooks(self, token: str) -> list[dict]:
        return self._request("GET", f"/tokens/{token}/webhooks")

    def create_webhook(self, model_id: str, callback_url: str, description: str) -> dict:
        return self._request(
            "POST", "/webhooks", params={"idModel": model_id, "callbackURL": callback_url, "description": description}
        )

    def delete_webhook(self, webhook_id: str) -> None:
        self._request("DELETE", f"/webhooks/{webhook_id}")
