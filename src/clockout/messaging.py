from dataclasses import dataclass

import requests
from requests.exceptions import RequestException


@dataclass(frozen=True, slots=True)
class SendResult:
    success: bool
    status_code: int | None = None
    error: str | None = None


def build_payload(message_text: str) -> dict[str, object]:
    return {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.2",
                    "body": [
                        {
                            "type": "TextBlock",
                            "text": message_text,
                        }
                    ],
                },
            }
        ],
    }


class MessagingClient:
    def __init__(
        self,
        webhook_url: str,
        session: requests.Session | None = None,
    ) -> None:
        self._webhook_url = webhook_url
        self._session = requests.Session() if session is None else session

    def send(self, message_text: str) -> SendResult:
        try:
            response = self._session.post(
                self._webhook_url,
                json=build_payload(message_text),
            )
        except RequestException:
            return SendResult(success=False, error="Network request failed")

        if 200 <= response.status_code < 300:
            return SendResult(success=True, status_code=response.status_code)

        return SendResult(
            success=False,
            status_code=response.status_code,
            error="HTTP request failed",
        )