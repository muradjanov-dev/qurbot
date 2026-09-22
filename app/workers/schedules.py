"""Cron schedule definitions matching the SPEC §10 job table."""

from __future__ import annotations

from arq import cron
from arq.cron import CronJob

from app.core.config import settings
from app.services.chat_progress import update_chat_progress
from app.services.conversation_service import (
    deliver_conversation_notifications,
    process_conversation_jobs,
)
from app.workers.tasks import (
    abandon_baskets,
    admin_digest,
    ai_cost_report,
    mark_price_staleness,
    nudge_shops,
    recompute_trust_scores,
    remind_unconfirmed_orders,
    rollup_metrics,
)

CRON_JOBS: list[CronJob] = [
    cron(process_conversation_jobs, second=set(range(0, 60, 5))),
    # Matches settings.chat_progress_rotate_seconds: the carousel can only
    # turn as often as the worker is awake to edit the message.
    cron(
        update_chat_progress,
        second=set(range(0, 60, settings.chat_progress_rotate_seconds)),
    ),
    cron(deliver_conversation_notifications, second=set(range(0, 60, 5))),
    cron(mark_price_staleness, minute=0),  # hourly
    cron(nudge_shops, hour=9, minute=0),  # daily 09:00
    cron(recompute_trust_scores, hour=3, minute=0),  # daily 03:00
    cron(rollup_metrics, hour=4, minute=0),  # daily 04:00
    cron(admin_digest, hour=8, minute=0),  # daily 08:00
    # End of the Tashkent day (worker clock is UTC): today's AI bill.
    cron(
        ai_cost_report,
        hour=settings.ai_cost_report_hour_utc,
        minute=settings.ai_cost_report_minute,
    ),
    cron(abandon_baskets, minute={0, 30}),  # every 30 min
    # Every 5 minutes: a customer who pressed confirm is waiting, and an
    # order nobody has touched is the one failure the customer sees.
    cron(remind_unconfirmed_orders, minute={0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55}),
]
