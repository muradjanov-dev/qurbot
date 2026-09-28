from datetime import UTC, datetime

from app.core.i18n import t
from app.db.models.conversation import ConversationJob
from app.services.chat_progress import _DONE_SLOT, progress


def test_completed_cart_conflict_is_not_reported_as_ready() -> None:
    now = datetime.now(UTC)
    job = ConversationJob(id=1, status="completed", error="cart_changed", created_at=now)

    slot, text, slow = progress(job, "uz_latn", now)

    assert slot == _DONE_SLOT
    assert text == t("web_chat_failed", lang="uz_latn")
    assert text != t("sales_progress_ready", lang="uz_latn")
    assert not slow


def test_successfully_completed_job_shows_ready() -> None:
    now = datetime.now(UTC)
    job = ConversationJob(id=2, status="completed", created_at=now)

    _slot, text, _slow = progress(job, "uz_cyrl", now)

    assert text == t("sales_progress_ready", lang="uz_cyrl")
