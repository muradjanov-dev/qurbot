"""Cron schedule definitions matching the SPEC §10 job table."""

from __future__ import annotations

from arq import cron
from arq.cron import CronJob

from app.workers.tasks import (
    abandon_baskets,
    admin_digest,
    mark_price_staleness,
    nudge_shops,
    recompute_trust_scores,
    remind_unconfirmed_orders,
    rollup_metrics,
)

CRON_JOBS: list[CronJob] = [
    cron(mark_price_staleness, minute=0),  # hourly
    cron(nudge_shops, hour=9, minute=0),  # daily 09:00
    cron(recompute_trust_scores, hour=3, minute=0),  # daily 03:00
    cron(rollup_metrics, hour=4, minute=0),  # daily 04:00
    cron(admin_digest, hour=8, minute=0),  # daily 08:00
    cron(abandon_baskets, minute={0, 30}),  # every 30 min
    # Every 5 minutes: a customer who pressed confirm is waiting, and an
    # order nobody has touched is the one failure the customer sees.
    cron(remind_unconfirmed_orders, minute={0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55}),
]
