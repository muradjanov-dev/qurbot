import hashlib
from decimal import Decimal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "local"
    log_level: str = "INFO"

    # Telegram
    bot_token: str = "placeholder_token"
    webhook_secret: str = "placeholder_secret"
    webhook_base_url: str = "http://localhost:8000"
    register_webhook: bool = True
    # How often to re-check that Telegram still points at this deployment.
    # Registering once at startup does not survive a rolling deploy's outgoing
    # container deleting the webhook the new one just set -- and that failure
    # is silent: /health stays green while the bot answers nobody. 0 disables.
    webhook_watchdog_interval_seconds: int = 300
    admin_tg_ids: list[int] = [917456291, 576437661, 3896397, 1630243859]
    # Super admins may grant/revoke admin rights. Kept separate from
    # admin_tg_ids so a promoted admin cannot promote further admins.
    super_admin_tg_ids: list[int] = [917456291]

    # Database
    database_url: str = "postgresql+asyncpg://qurbot:qurbot@localhost:5432/qurbot"
    database_echo: bool = False
    database_pool_size: int = 20
    database_max_overflow: int = 10

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    # FSM state lives in Redis so an in-progress wizard survives a restart or a
    # second web replica (SPEC §2). Set false only for local dev without Redis --
    # durable draft data is persisted to Postgres regardless, so this controls
    # convenience, not data safety.
    fsm_use_redis: bool = True

    # Shop product listings (photo upload wizard)
    listing_max_photos: int = 3
    listing_max_photo_bytes: int = 5 * 1024 * 1024
    listing_max_name_len: int = 255
    listing_max_description_len: int = 2000

    # Basket quantity bounds. A negative quantity cannot be ordered, and a
    # 12-digit one is a typo rather than an order, so both are refused instead
    # of being priced.
    basket_max_qty: int = 1_000_000

    # What customers are told to expect for delivery. This is the promise the
    # business makes, deliberately separate from the per-shop eta_hours the
    # optimizer uses to rank offers.
    delivery_eta_min_hours: int = 24
    delivery_eta_max_hours: int = 48

    # Loyalty: pebbles ("toshcha") granted per order, as a fraction of its
    # total. Other earning rules are planned; they become extra ledger rows
    # rather than a change here.
    pebble_rate_per_order: Decimal = Decimal("0.001")

    # Catalogue scope. Only these categories are offered to customers and only
    # their products can be matched -- quoting something we cannot actually
    # source is worse than saying we do not carry it. Empty list = no
    # restriction, which is how the full catalogue is switched back on.
    # The catalogue is currently one supplier's sheet-goods price list, so
    # this is the only category with anything behind it. Adding a supplier
    # means adding their category here in the same change.
    enabled_category_slugs: list[str] = [
        "plita-va-fanera",
    ]

    # Reverse geocoding for saved delivery addresses. Yandex is used when a key
    # is present (much better Uzbek street coverage); without one it falls back
    # to keyless Nominatim, which is coarser but works out of the box.
    yandex_geocoder_api_key: str | None = None
    geocoding_timeout_seconds: float = 6.0
    # A pin further than this from every district centroid is treated as
    # outside the service area rather than snapped to the nearest one.
    district_match_max_km: float = 40.0
    # Shortest text accepted as a typed delivery address. A courier needs at
    # least a street and a number; one short word ("Izza") is someone testing
    # the box, not somewhere a lorry of plywood can be sent.
    min_delivery_address_length: int = 8

    # Rows per page in the customer-facing catalogue list. Telegram starts
    # truncating inline keyboards well before this becomes a message-length
    # problem, so the page size is what keeps the list scrollable.
    customer_products_page_size: int = 20
    # Rows per page when a shop owner checks a staged price list. Twenty fits
    # a phone screen without scrolling past what the eye can still check.
    import_preview_page_size: int = 20

    # Matching Pipeline Thresholds (§6)
    match_auto_accept_threshold: float = 0.82
    match_margin_threshold: float = 0.12
    match_ask_user_threshold: float = 0.55
    # pg_trgm word_similarity floor for the fuzzy fallback search. Measured
    # against real misspellings: "paner"->Fanera scores 0.33 and
    # "smnt"->Sement 0.40, while unrelated products sit at ~0.2, so 0.3
    # separates them. This only decides which rows become candidates; the
    # scorer and then the LLM still re-rank whatever comes back.
    match_trigram_threshold: float = 0.3
    # Below this a candidate is not worth offering as a "did you mean". The
    # search always returns its best guess, and for a product we do not carry
    # that guess can be a different material entirely -- plywood suggested for
    # gipsokarton, because both are 15 mm. Saying "we do not have it, call us"
    # is more use than a confident wrong list.
    match_suggest_floor: float = 0.45

    # LLM Settings (§6 & §7)
    openai_api_key: str = "placeholder_openai_key"
    openai_base_url: str | None = None
    llm_model: str = "gpt-5.6-luna"
    llm_timeout_seconds: float = 30.0
    llm_max_retries: int = 2
    # Reasoning models spend part of this budget on hidden reasoning tokens
    # before emitting any answer, so a 300-token cap can be consumed entirely
    # by reasoning and return an empty completion.
    llm_max_completion_tokens: int = 2000
    llm_daily_token_budget: int = 100000
    # How much of the daily budget may be spent before the admins are told.
    # Running out is invisible from the outside -- the model simply stops
    # answering -- so the warning has to arrive while there is still room to
    # raise the budget.
    llm_budget_warn_ratio: float = 0.9
    # A guidance reply is read on a phone by someone who is already unsure
    # what to type. Past a few lines it stops being help and becomes another
    # wall of text, so an over-long answer is cut rather than sent.
    llm_guide_max_chars: int = 700
    llm_enabled: bool = True
    llm_prompt_version: str = "v1"
    # Below this the model's answer is not trusted enough to become an alias
    # the catalog will reuse forever. An approved alias short-circuits Stage 1
    # on every future basket, so a wrong one is expensive to notice.
    llm_alias_writeback_min_confidence: float = 0.70

    # Where a customer is sent when the catalog cannot help: an out-of-stock
    # product or an empty category. Kept here rather than in the string
    # catalogue so it changes in one place across all three languages.
    support_phone: str = "+998935394994"

    # Background Jobs (arq) — thresholds & weights (§10)
    price_staleness_aging_days: int = 5
    price_staleness_stale_days: int = 7
    trust_score_freshness_weight: float = 0.5
    trust_score_accept_rate_weight: float = 0.3
    trust_score_rating_weight: float = 0.2
    trust_score_window_days: int = 30
    basket_abandon_hours: int = 24
    # How long an order may sit unconfirmed before the admins are reminded.
    # A customer who has pressed "confirm" is waiting; ten minutes of silence
    # on our side is already long, and nothing else in the system notices.
    order_confirm_reminder_minutes: int = 10

    # Admin Web (§11)
    admin_basic_auth_user: str = "admin"
    admin_basic_auth_password: str = "placeholder_admin_password"
    admin_llm_cost_window_days: int = 30

    # Rate limiting (§9, Phase 9 hardening)
    throttle_limit_per_minute: int = 20
    throttle_quote_limit_per_minute: int = 3

    # Observability (Phase 9 hardening)
    sentry_dsn: str | None = None

    # ── Customer web app / storefront ─────────────────────────────────────
    # The website is the same product as the bot, so identity is the same
    # too: a visitor signs in with Telegram and lands on the very `users` row
    # the bot writes. Nothing here introduces a second account system.
    web_enabled: bool = True
    # Signs the session cookie. Left unset it is derived from the bot token,
    # which every deployment already has -- one less secret to forget. Set it
    # explicitly to keep sessions alive across a bot-token rotation.
    web_session_secret: str | None = None
    web_session_max_age_days: int = 30
    # How old a Telegram login payload may be before it is refused. Telegram's
    # own guidance; a replayed older payload is treated as an attack.
    web_login_max_age_seconds: int = 86400
    # BotFather username (without @) that the Login Widget is bound to. Without
    # it the widget cannot render, and only the Mini App path can sign anyone in.
    telegram_login_bot_username: str | None = None
    # Deliberately opt-in and never implied by app_env: `app_env` defaults to
    # "local", so keying a login bypass on it would leave one live in any
    # deployment that forgot to set it.
    web_dev_login_enabled: bool = False
    web_catalog_page_size: int = 24
    web_orders_page_size: int = 20
    web_shop_products_page_size: int = 20
    # Largest price file the web upload accepts, mirroring what the bot takes.
    web_max_upload_bytes: int = 5 * 1024 * 1024

    @property
    def web_session_key(self) -> bytes:
        """Key used to sign browser session cookies."""
        if self.web_session_secret:
            return self.web_session_secret.encode()
        return hashlib.sha256(f"qurbot-web-session:{self.bot_token}".encode()).digest()

    @property
    def webhook_path(self) -> str:
        return f"/webhook/{self.webhook_secret}"

    @property
    def webhook_url(self) -> str:
        return f"{self.webhook_base_url}{self.webhook_path}"

    @property
    def webhook_url_is_public(self) -> bool:
        """Whether `webhook_url` is somewhere Telegram could actually deliver.

        Telegram accepts HTTPS only, so anything else means this process was
        started without its webhook settings and fell back to the
        `http://localhost:8000` default. That is not a harmless misconfig: the
        watchdog would see the real deployment's registration, call it lost,
        and try to repoint Telegram at localhost. Today Telegram refuses the
        non-HTTPS URL and the theft fails by luck; a service pointed at any
        *other* valid HTTPS host would succeed and silently kill the bot.
        """
        return self.webhook_base_url.startswith("https://")


settings = Settings()
