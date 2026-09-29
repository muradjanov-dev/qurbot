"""Single-house order status, delivery fields, audit history and Telegram outbox."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from html import escape
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.bot.formatters.common import format_qty, format_uzs
from app.bot.keyboards.inline import get_admin_order_decision_keyboard
from app.core.config import settings
from app.core.order_delivery_i18n import ORDER_DELIVERY_MESSAGES
from app.db.models.order import Order, OrderItem, OrderShopPart
from app.db.models.order_workflow import OrderEvent, OrderNotification
from app.db.models.user import User
from app.services.house_shop import get_house_shop, is_admin

WORKFLOW_STATUSES = frozenset(
    {"new", "confirmed", "collecting", "in_transit", "fulfilled", "cancelled"}
)
ACTIVE_TRANSITIONS: dict[str, frozenset[str]] = {
    "new": frozenset({"confirmed", "cancelled"}),
    "confirmed": frozenset({"collecting", "cancelled"}),
    "collecting": frozenset({"in_transit", "cancelled"}),
    "in_transit": frozenset({"fulfilled", "cancelled"}),
    "fulfilled": frozenset(),
    "cancelled": frozenset(),
}
PUBLIC_ORDER_EVENT_KINDS = frozenset(
    {"order_created", "status_changed", "status_corrected", "courier_contact_updated"}
)
SUPPORTED_LANGUAGES = frozenset({"uz_latn", "uz_cyrl", "ru"})
MAX_COURIER_COST_UZS = Decimal("999999999999.99")
COURIER_COST_CENT = Decimal("0.01")


class WorkflowError(Exception):
    """Expected workflow rejection with a transport-friendly HTTP status."""

    def __init__(self, code: str, status_code: int, current_revision: int | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code
        self.current_revision = current_revision


def public_order_event(event: OrderEvent) -> dict[str, Any] | None:
    """Return the privacy-safe timeline projection for a customer.

    Audit reasons and admin-only delivery edits stay out of this projection.
    Only a normal cancellation has a public reason. Courier contact snapshots
    are included only on the explicitly public in-transit contact event.
    """
    if event.kind not in PUBLIC_ORDER_EVENT_KINDS:
        return None

    projected: dict[str, Any] = {
        "kind": event.kind,
        "from_status": event.from_status,
        "to_status": event.to_status,
        "created_at": event.created_at,
    }
    details = event.details if isinstance(event.details, dict) else {}
    if event.kind == "status_changed" and event.to_status == "cancelled":
        projected["public_reason"] = details.get("public_reason")
    if event.kind == "courier_contact_updated":
        contact = details.get("public_contact")
        projected["public_contact"] = contact if isinstance(contact, dict) else {}
    return projected


class OrderWorkflowService:
    """Apply order workflow edits without taking ownership of the transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_event(
        self, order: Order, actor: User, source: str = "web"
    ) -> OrderEvent | None:
        """Record order creation and enqueue admin plus optional web receipt DMs.

        Test orders are intentionally excluded from production history and the
        notification queue. The checkout transaction still owns the commit.
        """
        locked_order = await self._lock_order(order.id)
        if await self._is_test_order(locked_order):
            return None
        await self._assert_current_house(locked_order)

        existing = await self.session.scalar(
            select(OrderEvent)
            .where(OrderEvent.order_id == locked_order.id, OrderEvent.kind == "order_created")
            .order_by(OrderEvent.id)
            .limit(1)
        )
        if existing is not None:
            return existing

        event = OrderEvent(
            order_id=locked_order.id,
            actor_user_id=actor.id,
            kind="order_created",
            from_status=None,
            to_status=locked_order.status,
            reason="",
            details={"source": source},
        )
        self.session.add(event)
        await self.session.flush()

        customer = await self.session.get(User, locked_order.user_id)
        parts = list(
            (
                await self.session.scalars(
                    select(OrderShopPart)
                    .options(
                        selectinload(OrderShopPart.items).selectinload(OrderItem.canonical_product)
                    )
                    .where(OrderShopPart.order_id == locked_order.id)
                    .order_by(OrderShopPart.id)
                )
            ).all()
        )
        for recipient_tg_id, admin_lang in await self._admin_recipients():
            order_url = self._public_order_url(locked_order.id)
            order_link = ""
            keyboard = get_admin_order_decision_keyboard(locked_order.id).model_dump(
                mode="json", exclude_none=True
            )
            if order_url is not None:
                open_label = self._message("delivery_notification_admin_open_order", admin_lang)
                keyboard.get("inline_keyboard", []).append([{"text": open_label, "url": order_url}])
                order_link = (
                    f'\n<a href="{escape(order_url, quote=True)}">' f"{escape(open_label)}</a>"
                )
            items_block, totals_block = self._admin_order_breakdown(
                parts, admin_lang, locked_order.grand_total_quoted
            )
            comment_line = (
                self._message(
                    "delivery_notification_admin_comment",
                    admin_lang,
                    comment=self._escape_limited(locked_order.comment, 300, source_limit=300),
                )
                if locked_order.comment
                else ""
            )
            message = self._message(
                "delivery_notification_admin_order_created",
                admin_lang,
                order_id=locked_order.id,
                customer_name=self._escape_limited(
                    locked_order.contact_name or (customer.full_name if customer else "") or "-",
                    80,
                    source_limit=100,
                ),
                phone=self._escape_limited(locked_order.contact_phone, 50, source_limit=50),
                address=self._escape_limited(locked_order.delivery_address, 240, source_limit=400),
                comment_line=comment_line,
                items_block=items_block,
                totals_block=totals_block,
                channel=(
                    self._message("delivery_notification_admin_channel_web", admin_lang)
                    if source == "web"
                    else ""
                ),
                order_link=order_link,
            )
            if len(message) > 3900:
                message = self._message(
                    "delivery_notification_admin_order_created",
                    admin_lang,
                    order_id=locked_order.id,
                    customer_name=self._escape_limited(
                        locked_order.contact_name
                        or (customer.full_name if customer else "")
                        or "-",
                        40,
                        source_limit=50,
                    ),
                    phone=self._escape_limited(locked_order.contact_phone, 30, source_limit=30),
                    address=self._escape_limited(
                        locked_order.delivery_address, 100, source_limit=120
                    ),
                    comment_line="",
                    items_block=self._message(
                        "delivery_notification_admin_items_truncated", admin_lang
                    ),
                    totals_block=totals_block,
                    channel="",
                    order_link=order_link,
                )
            if len(message) > 4000:
                message = self._message(
                    "delivery_notification_admin_order_summary",
                    admin_lang,
                    order_id=locked_order.id,
                    items_summary=self._message(
                        "delivery_notification_admin_items_truncated", admin_lang
                    ),
                    totals_block=totals_block,
                    order_link=order_link,
                )
            admin_notification = OrderNotification(
                event_id=event.id,
                order_id=locked_order.id,
                recipient_tg_id=recipient_tg_id,
                kind="admin_order_created",
                text=message,
                payload={"reply_markup": keyboard},
            )
            self.session.add(admin_notification)
            await self.session.flush()

            if locked_order.delivery_lat is not None and locked_order.delivery_lng is not None:
                self.session.add(
                    OrderNotification(
                        event_id=event.id,
                        order_id=locked_order.id,
                        recipient_tg_id=recipient_tg_id,
                        kind="admin_order_location",
                        text="",
                        payload={
                            "latitude": float(locked_order.delivery_lat),
                            "longitude": float(locked_order.delivery_lng),
                            "reply_to_notification_id": admin_notification.id,
                        },
                    )
                )

        if source == "web" and self._eligible_customer(customer):
            assert customer is not None and customer.tg_id is not None
            status_label = self._status_label(locked_order.status, self._language(customer))
            self.session.add(
                OrderNotification(
                    event_id=event.id,
                    order_id=locked_order.id,
                    recipient_tg_id=customer.tg_id,
                    kind="customer_order_ack",
                    text=self._message(
                        "delivery_notification_customer_order_ack",
                        self._language(customer),
                        order_id=locked_order.id,
                        status=status_label,
                    ),
                )
            )

        await self.session.flush()
        return event

    async def change_status(
        self,
        order_id: int,
        actor: User,
        target: str,
        expected_revision: int | None,
        reason: str = "",
        correction: bool = False,
        expected_status: str | None = None,
    ) -> Order:
        order = await self._lock_order(order_id)
        await self._authorize_admin(actor)
        await self._assert_editable(order)
        self._check_revision(order, expected_revision)
        self._check_expected_status(order, expected_status)

        target_status = target.strip()
        if target_status not in WORKFLOW_STATUSES:
            raise WorkflowError("invalid_status", 422, order.workflow_revision)
        if target_status == order.status:
            return order

        clean_reason = reason.strip()
        if correction and not clean_reason:
            raise WorkflowError("reason_required", 422, order.workflow_revision)
        if target_status == "cancelled" and not clean_reason and not correction:
            raise WorkflowError("reason_required", 422, order.workflow_revision)
        if order.status not in WORKFLOW_STATUSES:
            raise WorkflowError("legacy_status", 409, order.workflow_revision)
        if not correction and target_status not in ACTIVE_TRANSITIONS[order.status]:
            raise WorkflowError("invalid_transition", 409, order.workflow_revision)
        if target_status in {"in_transit", "fulfilled"} and not self._has_courier(order):
            raise WorkflowError("courier_required", 422, order.workflow_revision)

        from_status = order.status
        order.status = target_status
        order.workflow_revision += 1
        if target_status == "cancelled" and not correction:
            order.cancel_reason = clean_reason
        elif target_status == "cancelled" and correction:
            # A private correction explanation must never become the legacy
            # field that customer pages historically display as a cancel reason.
            if from_status != "cancelled":
                order.cancel_reason = None
        else:
            order.cancel_reason = None
        await self._sync_house_parts(order, target_status)

        event_kind = "status_corrected" if correction else "status_changed"
        event = OrderEvent(
            order_id=order.id,
            actor_user_id=actor.id,
            kind=event_kind,
            from_status=from_status,
            to_status=target_status,
            reason=clean_reason,
            details={
                "source": "admin",
                "correction": correction,
                "public_reason": (
                    clean_reason if target_status == "cancelled" and not correction else None
                ),
            },
        )
        self.session.add(event)
        await self.session.flush()

        customer = await self.session.get(User, order.user_id)
        if self._eligible_customer(customer):
            assert customer is not None and customer.tg_id is not None
            lang = self._language(customer)
            status_label = self._status_label(target_status, lang)
            if correction:
                template = "delivery_notification_customer_correction"
                values = {"order_id": order.id, "status": status_label}
                notification_kind = "customer_status_correction"
            elif target_status == "cancelled":
                template = "delivery_notification_customer_cancelled"
                values = {
                    "order_id": order.id,
                    "reason": escape(clean_reason),
                }
                notification_kind = "customer_status"
            elif target_status == "in_transit":
                vehicle_line = ""
                if order.courier_vehicle:
                    vehicle_label = self._message("delivery_courier_vehicle_label", lang)
                    vehicle_line = f"\n{vehicle_label}: {escape(order.courier_vehicle)}"
                template = "delivery_notification_customer_departure"
                values = {
                    "order_id": order.id,
                    "courier_name": escape(order.courier_name or ""),
                    "courier_phone": escape(order.courier_phone or ""),
                    "vehicle_line": vehicle_line,
                }
                notification_kind = "customer_departure"
            else:
                template = "delivery_notification_customer_status"
                values = {"order_id": order.id, "status": status_label}
                notification_kind = "customer_status"
            self.session.add(
                OrderNotification(
                    event_id=event.id,
                    order_id=order.id,
                    recipient_tg_id=customer.tg_id,
                    kind=notification_kind,
                    text=self._message(template, lang, **values),
                )
            )

        await self.session.flush()
        return order

    async def update_courier(
        self,
        order_id: int,
        actor: User,
        name: str | None,
        phone: str | None,
        vehicle: str | None,
        cost_uzs: Decimal | None,
        expected_revision: int,
    ) -> Order:
        order = await self._lock_order(order_id)
        await self._authorize_admin(actor)
        await self._assert_editable(order)
        self._check_revision(order, expected_revision)

        clean_name = self._optional_text(name, 120, "courier_name")
        clean_phone = self._optional_text(phone, 50, "courier_phone")
        clean_vehicle = self._optional_text(vehicle, 100, "courier_vehicle")
        clean_cost = self._validate_cost(cost_uzs)
        if order.status in {"in_transit", "fulfilled"} and not (clean_name and clean_phone):
            raise WorkflowError("courier_required", 422, order.workflow_revision)

        before = {
            "courier_name": order.courier_name,
            "courier_phone": order.courier_phone,
            "courier_vehicle": order.courier_vehicle,
            "courier_cost_uzs": str(order.courier_cost_uzs)
            if order.courier_cost_uzs is not None
            else None,
        }
        after = {
            "courier_name": clean_name,
            "courier_phone": clean_phone,
            "courier_vehicle": clean_vehicle,
            "courier_cost_uzs": str(clean_cost) if clean_cost is not None else None,
        }
        changed_fields = [field for field in before if before[field] != after[field]]
        if not changed_fields:
            return order

        contact_changed = bool(
            {"courier_name", "courier_phone"}.intersection(changed_fields)
            and order.status == "in_transit"
        )
        order.courier_name = clean_name
        order.courier_phone = clean_phone
        order.courier_vehicle = clean_vehicle
        order.courier_cost_uzs = clean_cost
        order.workflow_revision += 1
        event = OrderEvent(
            order_id=order.id,
            actor_user_id=actor.id,
            kind="courier_contact_updated" if contact_changed else "courier_updated",
            from_status=order.status,
            to_status=order.status,
            reason="",
            details=(
                {
                    "public_contact": {
                        "courier_name": clean_name,
                        "courier_phone": clean_phone,
                    }
                }
                if contact_changed
                else {"changed_fields": changed_fields, "before": before, "after": after}
            ),
        )
        if contact_changed:
            event.details["private_changes"] = {
                "changed_fields": changed_fields,
                "before": before,
                "after": after,
            }
        self.session.add(event)
        await self.session.flush()

        if contact_changed:
            customer = await self.session.get(User, order.user_id)
            if self._eligible_customer(customer):
                assert customer is not None and customer.tg_id is not None
                self.session.add(
                    OrderNotification(
                        event_id=event.id,
                        order_id=order.id,
                        recipient_tg_id=customer.tg_id,
                        kind="customer_courier_contact",
                        text=self._message(
                            "delivery_notification_customer_courier_contact",
                            self._language(customer),
                            order_id=order.id,
                            courier_name=escape(clean_name or ""),
                            courier_phone=escape(clean_phone or ""),
                        ),
                    )
                )

        await self.session.flush()
        return order

    async def update_note(
        self,
        order_id: int,
        actor: User,
        note: str | None,
        is_problem: bool,
        expected_revision: int,
    ) -> Order:
        order = await self._lock_order(order_id)
        await self._authorize_admin(actor)
        await self._assert_editable(order)
        self._check_revision(order, expected_revision)

        clean_note = self._optional_text(note, 10_000, "delivery_note")
        if order.delivery_note == clean_note and order.delivery_problem is is_problem:
            return order

        before = {"delivery_note": order.delivery_note, "delivery_problem": order.delivery_problem}
        order.delivery_note = clean_note
        order.delivery_problem = is_problem
        order.workflow_revision += 1
        self.session.add(
            OrderEvent(
                order_id=order.id,
                actor_user_id=actor.id,
                kind="delivery_note_updated",
                from_status=order.status,
                to_status=order.status,
                reason="",
                details={
                    "before": before,
                    "after": {"delivery_note": clean_note, "delivery_problem": is_problem},
                },
            )
        )
        await self.session.flush()
        return order

    async def retry_notification(
        self,
        order_id: int,
        notification_id: int,
        actor: User,
    ) -> OrderNotification:
        order = await self._lock_order(order_id)
        await self._authorize_admin(actor)
        await self._assert_current_house(order)
        if await self._is_test_order(order):
            raise WorkflowError("test_order", 404)

        result = await self.session.execute(
            select(OrderNotification)
            .where(
                OrderNotification.id == notification_id,
                OrderNotification.order_id == order.id,
            )
            .with_for_update()
        )
        notification = result.scalar_one_or_none()
        if notification is None:
            raise WorkflowError("notification_not_found", 404, order.workflow_revision)
        if notification.status != "failed":
            raise WorkflowError("notification_not_failed", 409, order.workflow_revision)

        self.session.add(
            OrderEvent(
                order_id=order.id,
                actor_user_id=actor.id,
                kind="notification_retry",
                from_status=order.status,
                to_status=order.status,
                reason="",
                details={
                    "notification_id": notification.id,
                    "notification_kind": notification.kind,
                    "previous_attempts": notification.attempts,
                },
            )
        )
        await self.session.flush()
        notification.status = "pending"
        notification.available_at = datetime.now(UTC)
        notification.lease_until = None
        notification.lease_token = None
        notification.last_error = None
        notification.attempts = 0
        await self.session.flush()
        return notification

    async def _lock_order(self, order_id: int) -> Order:
        result = await self.session.execute(
            select(Order)
            .where(Order.id == order_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        order = result.scalar_one_or_none()
        if order is None:
            raise WorkflowError("order_not_found", 404)
        return order

    async def _authorize_admin(self, actor: User) -> None:
        if (
            actor.is_blocked
            or not is_admin(actor)
            or actor.is_test
            or actor.tg_id in settings.test_tg_ids
        ):
            raise WorkflowError("forbidden", 403)

    async def _assert_editable(self, order: Order) -> None:
        await self._assert_current_house(order)
        if await self._is_test_order(order):
            raise WorkflowError("test_order", 404, order.workflow_revision)
        if order.status == "partially_fulfilled":
            raise WorkflowError("legacy_status", 409, order.workflow_revision)

    async def _assert_current_house(self, order: Order) -> None:
        house = await get_house_shop(self.session)
        if house is None:
            raise WorkflowError("house_shop_unavailable", 409, order.workflow_revision)
        shop_ids = list(
            (
                await self.session.scalars(
                    select(OrderShopPart.shop_id)
                    .where(OrderShopPart.order_id == order.id)
                    .with_for_update()
                )
            ).all()
        )
        if not shop_ids or any(shop_id != house.id for shop_id in shop_ids):
            raise WorkflowError("not_current_house", 404, order.workflow_revision)

    async def _sync_house_parts(self, order: Order, target_status: str) -> None:
        parts = list(
            (
                await self.session.scalars(
                    select(OrderShopPart)
                    .where(OrderShopPart.order_id == order.id)
                    .with_for_update()
                )
            ).all()
        )
        response = {
            "new": "pending",
            "cancelled": "rejected",
        }.get(target_status, "accepted")
        for part in parts:
            if part.status == response and part.shop_response == response:
                continue
            part.status = response
            part.shop_response = response
            part.responded_at = None if response == "pending" else datetime.now(UTC)

    async def _is_test_order(self, order: Order) -> bool:
        if order.is_test:
            return True
        customer = await self.session.get(User, order.user_id)
        return bool(
            customer is not None and (customer.is_test or customer.tg_id in settings.test_tg_ids)
        )

    async def _admin_recipients(self) -> list[tuple[int, str]]:
        configured_ids = set(settings.admin_tg_ids)
        test_ids = set(settings.test_tg_ids)
        filters: list[Any] = [User.role == "admin"]
        if configured_ids:
            filters.append(User.tg_id.in_(configured_ids))
        stmt = select(User).where(or_(*filters), User.tg_id.is_not(None), User.is_test.is_(False))
        if test_ids:
            stmt = stmt.where(User.tg_id.not_in(test_ids))
        users = list((await self.session.scalars(stmt)).all())
        known_by_tg_id = {user.tg_id: user for user in users if user.tg_id is not None}
        recipients = {
            user.tg_id: self._language(user)
            for user in users
            if user.role == "admin"
            and not user.is_blocked
            and not user.is_test
            and user.tg_id is not None
            and user.tg_id not in test_ids
        }
        for tg_id in configured_ids:
            if tg_id in test_ids:
                continue
            user = known_by_tg_id.get(tg_id)
            if user is None or (not user.is_blocked and not user.is_test):
                recipients[tg_id] = self._language(user)
        return sorted(recipients.items())

    def _eligible_customer(self, customer: User | None) -> bool:
        return bool(
            customer is not None
            and customer.tg_id is not None
            and not customer.is_blocked
            and not customer.is_test
            and customer.tg_id not in settings.test_tg_ids
        )

    def _language(self, user: User | None) -> str:
        if user is not None and user.lang in SUPPORTED_LANGUAGES:
            return user.lang
        default = settings.default_lang
        return default if default in SUPPORTED_LANGUAGES else "uz_latn"

    def _public_order_url(self, order_id: int) -> str | None:
        for candidate in (settings.webhook_base_url, settings.storefront_webapp_url):
            if not candidate:
                continue
            parts = urlsplit(candidate.strip())
            if parts.scheme in {"http", "https"} and parts.netloc:
                order_url = f"{parts.scheme}://{parts.netloc}/manage/orders/{order_id}"
                return order_url if len(order_url) <= 300 else None
        return None

    def _admin_order_breakdown(
        self, parts: list[OrderShopPart], lang: str, quoted_total: Decimal
    ) -> tuple[str, str]:
        lines_by_part: list[str] = []
        item_text_length = 0
        item_text_limit = 2200
        truncated = False
        items_total = Decimal("0")
        delivery_total = Decimal("0")
        for part in parts:
            items_total += part.subtotal
            delivery_total += part.delivery_fee
            lines: list[str] = []
            for item in part.items:
                item_line = self._message(
                    "delivery_notification_admin_item_line",
                    lang,
                    product=self._escape_limited(self._localized_product_name(item, lang), 120),
                    qty=format_qty(item.qty),
                    unit=self._escape_limited(item.unit_code, 32),
                    line_total=format_uzs(item.line_total),
                )
                separator_length = 1 if item_text_length else 0
                if item_text_length + separator_length + len(item_line) <= item_text_limit:
                    lines.append(item_line)
                    item_text_length += separator_length + len(item_line)
                else:
                    truncated = True

            group_total = self._message(
                "delivery_notification_admin_group_total",
                lang,
                subtotal=format_uzs(part.subtotal),
                delivery=format_uzs(part.delivery_fee),
            )
            separator_length = 1 if item_text_length else 0
            if item_text_length + separator_length + len(group_total) <= item_text_limit:
                lines.append(group_total)
                item_text_length += separator_length + len(group_total)
            else:
                truncated = True
            if lines:
                lines_by_part.append("\n".join(lines))

        if truncated:
            marker = self._message("delivery_notification_admin_items_truncated", lang)
            if item_text_length + len(marker) + 1 <= item_text_limit:
                lines_by_part.append(marker)

        totals_block = self._message(
            "delivery_notification_admin_totals",
            lang,
            items_total=format_uzs(items_total),
            delivery_total=format_uzs(delivery_total),
            total=format_uzs(quoted_total),
        )
        return "\n\n".join(lines_by_part), totals_block

    def _escape_limited(self, value: str, limit: int, *, source_limit: int | None = None) -> str:
        input_limit = source_limit if source_limit is not None else limit
        source_truncated = len(value) > input_limit
        value = value[:input_limit]
        escaped = escape(value, quote=True)
        if len(escaped) <= limit:
            if source_truncated:
                with_ellipsis = escape(f"{value}…", quote=True)
                if len(with_ellipsis) <= limit:
                    return with_ellipsis
            return escaped

        low, high = 0, len(value)
        while low < high:
            middle = (low + high + 1) // 2
            candidate = escape(f"{value[:middle]}…", quote=True)
            if len(candidate) <= limit:
                low = middle
            else:
                high = middle - 1
        return escape(f"{value[:low]}…", quote=True)

    def _localized_product_name(self, item: OrderItem, lang: str) -> str:
        product = item.canonical_product
        if product is None:
            return f"#{item.canonical_id}"
        return {
            "uz_latn": product.name_uz,
            "uz_cyrl": product.name_uz_cyrl,
            "ru": product.name_ru,
        }[lang]

    def _status_label(self, status: str, lang: str) -> str:
        key = f"delivery_status_{status}"
        return ORDER_DELIVERY_MESSAGES[key][lang]

    def _message(self, key: str, lang: str, **values: object) -> str:
        return ORDER_DELIVERY_MESSAGES[key][lang].format(**values)

    def _check_revision(self, order: Order, expected_revision: int | None) -> None:
        if expected_revision is not None and expected_revision != order.workflow_revision:
            raise WorkflowError("stale_revision", 409, order.workflow_revision)

    def _check_expected_status(self, order: Order, expected_status: str | None) -> None:
        if expected_status is not None and expected_status != order.status:
            raise WorkflowError("stale_status", 409, order.workflow_revision)

    def _has_courier(self, order: Order) -> bool:
        return bool(order.courier_name and order.courier_name.strip() and order.courier_phone)

    def _optional_text(self, value: str | None, max_length: int, code: str) -> str | None:
        clean = value.strip() if value is not None else ""
        if len(clean) > max_length:
            raise WorkflowError(f"invalid_{code}", 422)
        return clean or None

    def _validate_cost(self, cost_uzs: Decimal | None) -> Decimal | None:
        if cost_uzs is None:
            return None
        if not isinstance(cost_uzs, Decimal) or not cost_uzs.is_finite() or cost_uzs < 0:
            raise WorkflowError("invalid_courier_cost", 422)
        if cost_uzs > MAX_COURIER_COST_UZS or cost_uzs != cost_uzs.quantize(COURIER_COST_CENT):
            raise WorkflowError("invalid_courier_cost", 422)
        return cost_uzs
