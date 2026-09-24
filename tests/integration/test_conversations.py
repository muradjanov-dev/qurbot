"""Shared-channel persistence, request replay, fencing and recovery without network."""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models.conversation import Conversation, ConversationJob, ConversationMessage
from app.db.models.user import User
from app.services import conversation_service as module
from app.services.conversation_service import ConversationConflict, ConversationService


@pytest.fixture
async def database(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'chat.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(module, "async_session_factory", factory)
    monkeypatch.setattr(module, "agent_available", lambda: False)
    async with factory() as session:
        session.add_all(
            [
                User(id=1, tg_id=11),
                User(id=2, tg_id=22, role="admin"),
                User(id=3, tg_id=33, role="admin"),
                User(id=4, tg_id=44),
            ]
        )
        await session.commit()
    yield factory
    await engine.dispose()


async def submit(factory, text="hello", request="one", channel="web"):
    async with factory() as session:
        user = await session.get(User, 1)
        result = await ConversationService(session).submit(user, text, request, channel)
        await session.commit()
        return result


async def test_seven_search_cards_survive_storage_and_web_snapshot(database) -> None:
    async with database() as session:
        user = await session.get(User, 1)
        service = ConversationService(session)
        conversation = await service.get_or_create(user)
        cards = [{"id": n, "name": f"Oq anker 10x{n}"} for n in range(7)]
        message = await service._append(conversation, "assistant", "Variants", "telegram", cards)
        await session.commit()
        from app.services.conversation_service import message_data

        assert len(message_data(message)["cards"]) == 7
        snapshot = await service.snapshot(user)
        assert len(snapshot["messages"][0]["cards"]) == 7


@pytest.mark.parametrize("first", ["fanera va OSB kerak", "fanera va taxta kerak"])
async def test_multi_product_request_asks_each_missing_size(database, monkeypatch, first):
    search = AsyncMock(return_value=("Mos mahsulotlar", []))
    monkeypatch.setattr(module, "deterministic_reply", search)
    monkeypatch.setattr(module, "warn_admins_of_ai_outage", AsyncMock())
    replies = ["12 mm", "1525x1525", "9 mm" if "OSB" in first else "38x168x6000 mm"]
    expected = ["sales_clarify_fanera_thickness", "sales_clarify_fanera_sheet_size"]
    expected.append("sales_clarify_osb_thickness" if "OSB" in first else "sales_clarify_taxta_size")
    from app.core.i18n import t

    for index, text in enumerate([first, *replies]):
        result = await submit(database, text, f"multi-{index}")
        await module.process_conversation({}, result["conversation_id"])
        async with database() as session:
            snapshot = await ConversationService(session).snapshot(await session.get(User, 1))
        answer = snapshot["messages"][-1]["text"]
        assert answer == (t(expected[index]) if index < 3 else "Mos mahsulotlar")
    search.assert_awaited_once()
    assert "fanera" in search.call_args.args[1]
    assert "1525x1525" in search.call_args.args[1]


async def test_clarification_keeps_original_request_after_unrelated_answer(database):
    """A wrong answer must not replace the product request being clarified."""
    from app.core.i18n import t

    expected = [
        t("sales_clarify_fanera_thickness"),
        t("sales_clarify_fanera_thickness"),
        t("sales_clarify_fanera_sheet_size"),
    ]
    for index, text in enumerate(["fanera va OSB kerak", "bilmayman", "12mm"]):
        result = await submit(database, text, f"clarify-retry-{index}")
        await module.process_conversation({}, result["conversation_id"])
        async with database() as session:
            snapshot = await ConversationService(session).snapshot(await session.get(User, 1))
        assert snapshot["messages"][-1]["text"] == expected[index]


async def test_clarification_accepts_new_material_request(database):
    from app.core.i18n import t

    for index, text in enumerate(["fanera kerak", "OSB kerak"]):
        result = await submit(database, text, f"change-material-{index}")
        await module.process_conversation({}, result["conversation_id"])
    async with database() as session:
        snapshot = await ConversationService(session).snapshot(await session.get(User, 1))
    assert snapshot["messages"][-1]["text"] == t("sales_clarify_osb_thickness")


async def test_clarification_repairs_existing_inconsistent_state(database):
    from app.core.i18n import t

    async with database() as session:
        user = await session.get(User, 1)
        conversation = await ConversationService(session).get_or_create(user)
        conversation.agent_state = {
            "clarification_query": "fanera 12 mm 1525x1525 va osb kerak",
            "clarification_key": "fanera_thickness",
        }
        await session.commit()
    job = await submit(database, "bilmayman", "repair-clarification")
    await module.process_conversation({}, job["conversation_id"])
    async with database() as session:
        snapshot = await ConversationService(session).snapshot(await session.get(User, 1))
    assert snapshot["messages"][-1]["text"] == t("sales_clarify_osb_thickness")


async def test_catalog_fallback_keeps_both_materials(database, monkeypatch):
    from app.services import ai_fallback
    from app.services.sales_agent import DbAgentTools

    monkeypatch.setattr(ai_fallback, "async_session_factory", database)

    async def search(self, name, args, cart):
        family = "fanera" if "fanera" in args["query"] else "osb"
        product_id = 1 if family == "fanera" else 2
        return {"products": [{"id": product_id, "name": family, "price_from_uzs": "1135"}]}

    monkeypatch.setattr(DbAgentTools, "run", search)
    answer, cards = await ai_fallback.deterministic_reply(
        1, "fanera 12 mm 1525x1525 va OSB 9 mm kerak", "uz_latn"
    )
    assert [card["name"] for card in cards] == ["fanera", "osb"]
    assert "1.135" in answer


async def test_channels_share_history_and_replays_do_not_duplicate(database):
    first = await submit(database)
    assert await submit(database) == first
    second = await submit(database, "bot", "two", "telegram")
    assert first["conversation_id"] == second["conversation_id"]
    with pytest.raises(ConversationConflict):
        await submit(database, "different", "one")
    async with database() as session:
        result = await ConversationService(session).snapshot(await session.get(User, 1))
        assert [message["text"] for message in result["messages"]] == ["hello", "bot"]
        with pytest.raises(LookupError):
            await ConversationService(session).get_job(await session.get(User, 4), first["id"])


async def test_worker_handles_oldest_once_and_keeps_safe_fallback(database):
    first = await submit(database)
    second = await submit(database, "second", "two")
    await module.process_conversation({}, first["conversation_id"])
    async with database() as session:
        assert (await session.get(ConversationJob, first["id"])).status == "completed"
        assert (await session.get(ConversationJob, second["id"])).status == "pending"
    await module.process_conversation({}, first["conversation_id"])
    await module.process_conversation({}, first["conversation_id"])
    async with database() as session:
        assert await session.scalar(select(func.count()).select_from(ConversationMessage)) == 4
        assert (await session.get(ConversationJob, first["id"])).error == "agent_unavailable"


async def test_claim_is_atomic_and_only_owner_may_reply_close(database):
    first = await submit(database)
    async with database() as session:
        await ConversationService(session).handoff(await session.get(User, 1))
        await session.commit()

    async def claim(admin_id):
        async with database() as session:
            try:
                await ConversationService(session).claim(
                    await session.get(User, admin_id), first["conversation_id"]
                )
                await session.commit()
                return admin_id
            except ConversationConflict:
                return None

    winners = [winner for winner in await asyncio.gather(claim(2), claim(3)) if winner]
    assert len(winners) == 1
    winner = winners[0]
    loser = 3 if winner == 2 else 2
    async with database() as session:
        service = ConversationService(session)
        with pytest.raises(ConversationConflict):
            await service.operator_reply(
                await session.get(User, loser), first["conversation_id"], "wrong", "r"
            )
        with pytest.raises(PermissionError):
            await service.queue(await session.get(User, 1))
        admin = await session.get(User, winner)
        response = await service.operator_reply(admin, first["conversation_id"], "help", "r")
        assert (
            await service.operator_reply(admin, first["conversation_id"], "help", "r") == response
        )
        await service.close(admin, first["conversation_id"])
        await session.commit()
    async with database() as session:
        assert (await session.get(ConversationJob, first["id"])).status == "human"
        assert (await session.get(Conversation, first["conversation_id"])).status == "ai"


async def test_claim_during_network_fences_reply_without_waiting_for_model(database, monkeypatch):
    """An admin taking over cuts off a reply still in flight.

    The fence sits on `claim`, not on `handoff`: merely asking for a human
    pings the admins and leaves the assistant working, so cancelling there
    would throw away an answer the customer still wants.
    """
    first = await submit(database)
    started, release = asyncio.Event(), asyncio.Event()

    async def reply(*args):
        started.set()
        await release.wait()
        return "must never appear"

    monkeypatch.setattr(module, "agent_available", lambda: True)
    monkeypatch.setattr(module.DurableAgent, "reply", reply)
    task = asyncio.create_task(module.process_conversation({}, first["conversation_id"]))
    await asyncio.wait_for(started.wait(), 5)
    async with database() as session:
        service = ConversationService(session)
        await asyncio.wait_for(service.handoff(await session.get(User, 1)), 2)
        admin = User(tg_id=917456291, role="admin")
        session.add(admin)
        await session.flush()
        await service.claim(admin, first["conversation_id"])
        await session.commit()
    release.set()
    await task
    async with database() as session:
        messages = (await session.scalars(select(ConversationMessage))).all()
        assert not any(message.text == "must never appear" for message in messages)


async def test_handoff_alone_keeps_the_assistant_answering(database, monkeypatch):
    """Asking for a human must not leave the customer with nobody.

    There are no dedicated operators here, only admins who answer when they
    can. A request that merely pings them used to switch the assistant off,
    so every later message was filed to the queue and answered with "an
    operator has been requested" -- indefinitely, if nobody claimed it.
    """
    monkeypatch.setattr(module, "agent_available", lambda: True)

    async def reply(self, text, lang, cart):
        return "still here"

    monkeypatch.setattr(module.DurableAgent, "reply", reply)
    async with database() as session:
        await ConversationService(session).handoff(await session.get(User, 1))
        await session.commit()

    job = await submit(
        database, text="fanera 10 mm 1525x1525", request="after-handoff", channel="telegram"
    )
    assert job["status"] == "pending", "the assistant still takes the message"
    await module.process_conversation({}, job["conversation_id"])
    async with database() as session:
        stored = await session.get(ConversationJob, job["id"])
        assert stored.status == "completed"
        answer = await session.get(ConversationMessage, stored.response_id)
        assert answer.text == "still here"


async def test_expired_worker_lease_is_recovered(database):
    first = await submit(database)
    async with database() as session:
        conversation = await session.get(Conversation, first["conversation_id"])
        conversation.lease_token = "old"
        conversation.lease_until = datetime.now(UTC) - timedelta(seconds=1)
        (await session.get(ConversationJob, first["id"])).status = "running"
        await session.commit()
    await module.process_conversation({}, first["conversation_id"])
    async with database() as session:
        assert (await session.get(ConversationJob, first["id"])).status == "completed"


async def test_outbox_retries_failure_and_never_repeats_success(database):
    await submit(database)
    async with database() as session:
        await ConversationService(session).handoff(await session.get(User, 1))
        await session.commit()
    bot = AsyncMock()
    await module.deliver_conversation_notifications({"bot": bot})
    count = bot.send_message.await_count
    assert count >= 2
    await module.deliver_conversation_notifications({"bot": bot})
    assert bot.send_message.await_count == count


async def test_disabled_notifications_retain_unclaimed_outbox(database, monkeypatch):
    from types import SimpleNamespace

    from app.db.models.conversation import ConversationNotification

    await submit(database)
    async with database() as session:
        await ConversationService(session).handoff(await session.get(User, 1))
        await session.commit()
    with monkeypatch.context() as disabled:
        disabled.setattr(module, "settings", SimpleNamespace(telegram_notifications_enabled=False))
        bot = AsyncMock()
        await module.deliver_conversation_notifications({"bot": bot})
        bot.send_message.assert_not_awaited()
    async with database() as session:
        rows = (await session.scalars(select(ConversationNotification))).all()
        assert rows
        assert all(
            row.sent_at is None and row.lease_token is None and row.lease_until is None
            for row in rows
        )
    await module.deliver_conversation_notifications({"bot": bot})
    assert bot.send_message.await_count == len(rows)


async def test_pending_limit_prevents_unbounded_model_queue(database):
    for index in range(getattr(module.settings, "conversation_pending_limit", 5)):
        await submit(database, "message", str(index))
    with pytest.raises(ConversationConflict, match="too_many_pending"):
        await submit(database, "third", "three")


async def test_tool_receipt_prevents_reapplying_cart_mutation(database, monkeypatch):
    from app.services.sales_agent import AgentCart
    from tests.integration.test_sales_agent_tools import _seed

    monkeypatch.setattr(module.settings, "enabled_category_slugs", [])
    async with database() as session:
        _, product_id = await _seed(session)
        await session.commit()
    first = await submit(database)
    async with database() as session:
        conversation = await session.get(Conversation, first["conversation_id"])
        conversation.lease_token = "worker"
        await session.commit()
    original = module.DbAgentTools.run
    calls = []

    async def recording(self, name, args, cart):
        calls.append(name)
        return await original(self, name, args, cart)

    monkeypatch.setattr(module.DbAgentTools, "run", recording)
    args = {"product_id": product_id, "qty": 2}
    tools = module.DurableTools(first["conversation_id"], 0, "worker", first["id"])
    search = await tools.run("search_products", {"query": "fanera"}, AgentCart())
    result = await tools.run("set_basket_item", args, AgentCart())
    recovered = module.DurableTools(first["conversation_id"], 0, "worker", first["id"])
    assert await recovered.run("search_products", {"query": "fanera"}, AgentCart()) == search
    assert await recovered.run("set_basket_item", args, AgentCart()) == result
    assert calls == ["search_products", "set_basket_item"]
    async with database() as session:
        job = await session.get(ConversationJob, first["id"])
        assert job.tool_results[1]["output"] == result
        assert job.tool_results[1]["name"] == "set_basket_item"
    divergent = module.DurableTools(first["conversation_id"], 0, "worker", first["id"])
    with pytest.raises(ConversationConflict, match="recovery_tool_mismatch"):
        await divergent.run("set_basket_item", {"product_id": product_id, "qty": 3}, AgentCart())


@pytest.mark.parametrize("checkout", [False, True])
async def test_telegram_outbox_cards_quantity_and_existing_confirmation(
    database, monkeypatch, checkout
):
    from types import SimpleNamespace

    from aiogram.types import Chat, Message

    from app.bot.handlers.ai_chat import prepare_confirmation, select_product, set_product_quantity
    from app.services.cart_service import CartService
    from tests.integration.test_sales_agent_tools import _seed

    monkeypatch.setattr(module.settings, "enabled_category_slugs", [])
    async with database() as session:
        _, product_id = await _seed(session)
        await session.commit()

    async def scripted_reply(self, text, lang, cart):
        await self.tools.run("search_products", {"query": "fanera"}, cart)
        if checkout:
            await self.tools.run("set_basket_item", {"product_id": product_id, "qty": 2}, cart)
            # Delivery is priced per district, so the agent settles where the
            # order is going before it can quote or take contact details.
            listed = await self.tools.run("get_delivery_options", {"region": "Toshkent"}, cart)
            chosen = await self.tools.run(
                "set_delivery_district", {"district_id": listed["districts"][0]["id"]}, cart
            )
            assert chosen["ok"], chosen
            await self.tools.run("get_quote", {}, cart)
            result = await self.tools.run(
                "prepare_order",
                {
                    "phone": "+998901234567",
                    "address": "Chilonzor 9-kvartal 12-uy",
                },
                cart,
            )
            assert result.get("ok"), result
        return "Fanera"

    monkeypatch.setattr(module, "agent_available", lambda: True)
    monkeypatch.setattr(module.DurableAgent, "reply", scripted_reply)
    first = await submit(database, channel="telegram")
    await module.process_conversation({}, first["conversation_id"])
    bot = AsyncMock()
    await module.deliver_conversation_notifications({"bot": bot})
    call = bot.send_message.await_args
    markup = call.kwargs["reply_markup"]
    buttons = [button for row in markup.inline_keyboard for button in row]
    prefix = "chat:checkout:" if checkout else "chat:product:"
    target = next(button for button in buttons if (button.callback_data or "").startswith(prefix))
    if not checkout:
        assert "151.000" in call.args[1]
    message = Message(message_id=1, date=datetime.now(UTC), chat=Chat(id=11, type="private"))
    callback = SimpleNamespace(data=target.callback_data, answer=AsyncMock(), message=message)
    monkeypatch.setattr(Message, "answer", AsyncMock())
    monkeypatch.setattr(Message, "edit_reply_markup", AsyncMock())
    async with database() as session:
        user = await session.get(User, 1)
        if checkout:
            state = AsyncMock()
            await prepare_confirmation(callback, state, session, user, "uz_latn")
            payload = state.update_data.await_args.kwargs
            assert payload["contact_phone"] == "+998901234567"
            assert payload["quote_cart_revision"] == 1
            assert payload["checkout_key"] == f"chat:{first['id']}"
            assert message.answer.await_args.kwargs["reply_markup"].inline_keyboard
        else:
            other = await session.get(User, 4)
            await select_product(callback, session, other, "uz_latn")
            message.answer.assert_not_awaited()
            assert callback.answer.await_args.kwargs["show_alert"] is True
            await select_product(callback, session, user, "uz_latn")
            assert not (await CartService(session).get(user.id)).lines
            selection = message.answer.await_args
            assert "1. " in selection.args[0]
            assert "151.000 so'm" in selection.args[0]
            quantities = selection.kwargs["reply_markup"].inline_keyboard[0]
            assert len(quantities) == 3
            callback.data = quantities[0].callback_data
            await set_product_quantity(callback, session, user, "uz_latn")
            assert not (await CartService(session).get(user.id)).lines
            from app.bot.handlers.guided_sales import add_quantity

            callback.data = (
                message.answer.await_args.kwargs["reply_markup"].inline_keyboard[0][0].callback_data
            )
            await add_quantity(callback, session, user, AsyncMock(), "uz_latn")
            snapshot = await CartService(session).get(user.id)
            assert snapshot.lines[0]["qty"] == "1"


async def test_failed_ai_falls_back_to_catalogue_search_with_buttons(database, monkeypatch):
    """A model failure must not end the conversation.

    Before this the customer got "the AI could not answer" and nothing else --
    no products, no buttons, no way to carry on -- while the admins were told
    nothing at all.
    """
    from app.services import ai_fallback
    from tests.integration.test_sales_agent_tools import _seed

    monkeypatch.setattr(module.settings, "enabled_category_slugs", [])
    async with database() as session:
        await _seed(session)
        await session.commit()

    monkeypatch.setattr(ai_fallback, "async_session_factory", database)
    monkeypatch.setattr(module, "async_session_factory", database)
    monkeypatch.setattr(module, "agent_available", lambda: True)

    warned: list[str] = []

    async def record(error: str) -> bool:
        warned.append(error)
        return True

    monkeypatch.setattr(module, "warn_admins_of_ai_outage", record)

    async def broken_reply(self, text, lang, cart):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(module.DurableAgent, "reply", broken_reply)

    first = await submit(
        database, text="fanera 10 mm 1525x1525", request="broken", channel="telegram"
    )
    await module.process_conversation({}, first["conversation_id"])

    async with database() as session:
        job = await session.get(ConversationJob, first["id"])
        assert job.status == "completed" and job.error
        answer = await session.get(ConversationMessage, job.response_id)
        # The catalogue answered, and the cards carry the same shape the agent
        # produces, so the existing product keyboards still apply.
        assert "fanera" in answer.text.lower() or "фанера" in answer.text.lower()
        assert answer.cards and answer.cards[0]["id"]

    # The admins hear about the outage once, not once per customer message.
    assert warned == ["tool_or_worker_error"]


async def test_customer_can_take_back_an_unclaimed_handoff(database):
    """Asking for an operator must not be a one-way door.

    `handoff` moves ai -> waiting and only `close` returns it, which an admin
    can call solely after claiming. A request nobody claimed therefore left the
    customer with no assistant at all: every later message was filed to the
    operator queue and answered with "an operator has been requested".
    """
    async with database() as session:
        service = ConversationService(session)
        user = await session.get(User, 1)
        await service.handoff(user, channel="telegram")
        await session.commit()
        assert (await service.get_or_create(user)).status == "waiting"

    async with database() as session:
        service = ConversationService(session)
        user = await session.get(User, 1)
        resumed = await service.resume_ai(user, channel="telegram")
        await session.commit()
        assert resumed["status"] == "ai"

    # A message now reaches the assistant again instead of the operator queue.
    async with database() as session:
        service = ConversationService(session)
        user = await session.get(User, 1)
        job = await service.submit(user, "fanera kerak", "after-resume", "telegram")
        await session.commit()
        assert job["status"] == "pending"


async def test_customer_can_leave_a_claimed_conversation(database):
    """It is the customer's conversation, so they can take it back.

    An admin who claims it and then goes quiet would otherwise hold it
    indefinitely, which is the same dead end in a different costume.
    """
    async with database() as session:
        service = ConversationService(session)
        user = await session.get(User, 1)
        await service.handoff(user, channel="telegram")
        conversation = await service.get_or_create(user)
        conversation.status = "human"
        conversation.operator_id = 2
        await session.commit()

    async with database() as session:
        service = ConversationService(session)
        user = await session.get(User, 1)
        result = await service.resume_ai(user, channel="telegram")
        await session.commit()
        assert result["status"] == "ai"
        assert (await service.get_or_create(user)).operator_id is None


async def test_resumed_assistant_does_not_reanswer_the_backlog(database, monkeypatch):
    """Coming back must not mean working through what a human was holding.

    A customer who asked about bricks while the conversation sat with an admin,
    then asked about boards once the assistant returned, got a reply that
    opened by reporting on the bricks.
    """
    seen: list[list[dict[str, str]]] = []

    async def reply(self, text, lang, cart):
        seen.append(list(cart.history))
        return "ok"

    monkeypatch.setattr(module, "agent_available", lambda: True)
    monkeypatch.setattr(module.DurableAgent, "reply", reply)

    async with database() as session:
        service = ConversationService(session)
        user = await session.get(User, 1)
        await service.handoff(user, channel="telegram")
        conversation = await service.get_or_create(user)
        conversation.status = "human"
        conversation.operator_id = 2
        await service.submit(user, "g'isht kerak", "held-one", "telegram")
        await session.commit()

    async with database() as session:
        service = ConversationService(session)
        await service.resume_ai(await session.get(User, 1), channel="telegram")
        await session.commit()

    job = await submit(
        database, text="taxta 38x168x6000 mm kerak", request="after", channel="telegram"
    )
    await module.process_conversation({}, job["conversation_id"])

    assert seen, "the assistant ran"
    carried = " ".join(entry["content"] for entry in seen[0])
    assert "g'isht" not in carried, "the backlog is not the assistant's to answer"
