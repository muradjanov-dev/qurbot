from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app

START_UPDATE = {
    "update_id": 1,
    "message": {
        "message_id": 1,
        "date": 1,
        "chat": {"id": 1, "type": "private"},
        "from": {"id": 1, "is_bot": False, "first_name": "Test"},
        "text": "/start",
        "entities": [{"type": "bot_command", "offset": 0, "length": 6}],
    },
}


def test_webhook_accepts_valid_update() -> None:
    with patch("aiogram.Bot.__call__", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = True
        with TestClient(app) as client:
            response = client.post(settings.webhook_path, json=START_UPDATE)

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_webhook_rejects_bad_secret_header() -> None:
    with TestClient(app) as client:
        response = client.post(
            settings.webhook_path,
            json=START_UPDATE,
            headers={"x-telegram-bot-api-secret-token": "wrong"},
        )

    assert response.status_code == 403
