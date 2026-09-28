from unittest.mock import Mock

import pytest
import requests

from clockout.messaging import MessagingClient, SendResult, build_payload


WEBHOOK_URL = "https://example.invalid/workflow"
MESSAGE = "I'll be home on time tonight."
RESPONSE_BODY = "private response body"


def test_build_payload_matches_teams_workflows_adaptive_card_shape() -> None:
    payload = build_payload(MESSAGE)

    assert payload == {
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
                            "text": MESSAGE,
                        }
                    ],
                },
            }
        ],
    }
    assert payload["type"] == "message"
    assert len(payload["attachments"]) == 1
    attachment = payload["attachments"][0]
    assert attachment["contentType"] == "application/vnd.microsoft.card.adaptive"
    assert attachment["content"]["type"] == "AdaptiveCard"
    assert len(attachment["content"]["body"]) == 1
    assert attachment["content"]["body"][0] == {
        "type": "TextBlock",
        "text": MESSAGE,
    }
    assert payload != {"text": MESSAGE}


@pytest.mark.parametrize("status_code", range(200, 300))
def test_send_treats_all_2xx_statuses_as_success(status_code: int) -> None:
    session = Mock()
    session.post.return_value = Mock(status_code=status_code)
    client = MessagingClient(WEBHOOK_URL, session=session)

    result = client.send(MESSAGE)

    assert result == SendResult(success=True, status_code=status_code)
    session.post.assert_called_once_with(
        WEBHOOK_URL,
        json=build_payload(MESSAGE),
    )


@pytest.mark.parametrize("status_code", [100, 199, 300, 301, 418, 500, 599])
def test_send_returns_sanitized_failure_for_non_2xx_statuses(
    status_code: int,
    caplog: pytest.LogCaptureFixture,
) -> None:
    session = Mock()
    session.post.return_value = Mock(
        status_code=status_code,
        text=RESPONSE_BODY,
    )
    client = MessagingClient(WEBHOOK_URL, session=session)

    with caplog.at_level("DEBUG"):
        result = client.send(MESSAGE)

    assert result == SendResult(
        success=False,
        status_code=status_code,
        error="HTTP request failed",
    )
    for rendered in (str(result), repr(result), result.error or "", caplog.text):
        assert WEBHOOK_URL not in rendered
        assert RESPONSE_BODY not in rendered
    session.post.assert_called_once_with(
        WEBHOOK_URL,
        json=build_payload(MESSAGE),
    )


@pytest.mark.parametrize(
    "exception_type",
    [
        requests.exceptions.ConnectionError,
        requests.exceptions.Timeout,
        requests.exceptions.RequestException,
    ],
)
def test_send_returns_sanitized_failure_for_network_exception(
    exception_type: type[requests.exceptions.RequestException],
    caplog: pytest.LogCaptureFixture,
) -> None:
    session = Mock()
    exception_text = f"connection failed for {WEBHOOK_URL}: {RESPONSE_BODY}"
    session.post.side_effect = exception_type(exception_text)
    client = MessagingClient(WEBHOOK_URL, session=session)

    with caplog.at_level("DEBUG"):
        result = client.send(MESSAGE)

    assert result == SendResult(success=False, error="Network request failed")
    for rendered in (str(result), repr(result), result.error or "", caplog.text):
        assert WEBHOOK_URL not in rendered
        assert RESPONSE_BODY not in rendered
    session.post.assert_called_once_with(
        WEBHOOK_URL,
        json=build_payload(MESSAGE),
    )