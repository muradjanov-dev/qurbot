"""Isolated real HTTP/worker smoke. Retains synthetic staging-only transcripts."""

import asyncio
import json
from uuid import uuid4

import httpx
from starlette.requests import Request

from app.core.config import settings
from app.db.models.user import User
from app.db.session import async_session_factory, engine
from app.web.storefront.security import csrf_token
from app.web.storefront.session import SESSION_COOKIE, sign_session


def sign_in(client: httpx.AsyncClient, user: User) -> None:
    cookie = sign_session(user_id=user.id, tg_id=user.tg_id)
    client.cookies.clear()
    client.cookies.set(SESSION_COOKIE, cookie)
    request = Request(
        {"type": "http", "headers": [(b"cookie", f"{SESSION_COOKIE}={cookie}".encode())]}
    )
    client.headers["X-CSRF-Token"] = csrf_token(request)


async def run() -> dict[str, object]:
    if (
        settings.app_env != "staging"
        or settings.telegram_notifications_enabled
        or settings.agent_enabled
    ):
        raise RuntimeError("requires isolated staging with model and Telegram transport disabled")
    marker = uuid4().hex
    ids = [-int(marker[:12], 16) - offset for offset in range(3)]
    async with async_session_factory() as session:
        customer = User(tg_id=ids[0], full_name="STAGING chat smoke")
        first = User(tg_id=ids[1], full_name="STAGING operator 1", role="admin")
        second = User(tg_id=ids[2], full_name="STAGING operator 2", role="admin")
        session.add_all([customer, first, second])
        await session.commit()
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8000", timeout=10) as client:
        sign_in(client, customer)
        assert (await client.get("/chat")).status_code == 200
        payload = {"request_id": marker, "text": "STAGING: fanera haqida savol"}
        request = await client.post("/api/chat/messages", json=payload)
        assert request.status_code == 202, request.text
        job = request.json()
        repeat = (await client.post("/api/chat/messages", json=payload)).json()
        assert repeat["id"] == job["id"]
        for _ in range(30):
            result = (await client.get(f"/api/chat/jobs/{job['id']}")).json()
            if result["status"] == "completed":
                break
            await asyncio.sleep(1)
        assert result["status"] == "completed", result
        assert result["error"] == "agent_unavailable" and result["response"]["text"]
        handoff = await client.post("/api/chat/handoff")
        assert handoff.status_code == 200, handoff.text
        conversation_id = handoff.json()["id"]
        sign_in(client, first)
        claim = await client.post(f"/api/chat/operator/{conversation_id}/claim")
        assert claim.status_code == 200, claim.text
        sign_in(client, second)
        assert (await client.post(f"/api/chat/operator/{conversation_id}/claim")).status_code == 409
        assert (await client.get(f"/api/chat/jobs/{job['id']}")).status_code == 404
        sign_in(client, first)
        reply = await client.post(
            f"/api/chat/operator/{conversation_id}/messages",
            json={
                "request_id": marker,
                "text": "STAGING operator reply",
            },
        )
        assert reply.status_code == 200, reply.text
        sign_in(client, customer)
        history = (await client.get("/api/chat")).json()
        assert any(row["text"] == "STAGING operator reply" for row in history["messages"])
        sign_in(client, first)
        assert (await client.post(f"/api/chat/operator/{conversation_id}/close")).status_code == 200
        sign_in(client, customer)
        assert (await client.get("/api/chat")).json()["status"] == "ai"
    await engine.dispose()
    return {
        "ok": True,
        "checks": [
            "HTTP",
            "worker_queue",
            "request_dedup",
            "fallback",
            "handoff",
            "claim_conflict",
            "ownership",
            "operator_reply",
            "resume_ai",
        ],
    }


if __name__ == "__main__":
    print(json.dumps(asyncio.run(run())))
