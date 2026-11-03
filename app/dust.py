"""Notifies Dust when a report needs the triage agent. Each event
opens a conversation in the team's shared Pod."""

import hashlib
import hmac
import json

import requests


class DustError(RuntimeError):
    pass


class DustTrigger:
    def __init__(self, webhook_url: str, secret: str = ""):
        self.webhook_url = webhook_url
        self.secret = secret

    def send(self, event: dict) -> None:
        body = json.dumps(event, separators=(",", ":")).encode()
        headers = {"Content-Type": "application/json"}
        if self.secret:
            # Signed so Dust only accepts events from this integration (X-Dust-Signature: sha256=<hex>).
            digest = hmac.new(self.secret.encode(), body, hashlib.sha256).hexdigest()
            headers["X-Dust-Signature"] = f"sha256={digest}"
        try:
            response = requests.post(self.webhook_url, data=body, headers=headers, timeout=15)
        except requests.RequestException as exc:
            raise DustError(f"Dust trigger call failed: {exc}") from exc
        if response.status_code >= 300:
            raise DustError(f"Dust trigger returned {response.status_code}: {response.text[:200]}")
