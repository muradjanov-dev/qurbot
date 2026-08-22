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
    llm_enabled: bool = True
    llm_prompt_version: str = "v1"

    # Background Jobs (arq) — thresholds & weights (§10)
    price_staleness_aging_days: int = 5
    price_staleness_stale_days: int = 7
    trust_score_freshness_weight: float = 0.5
    trust_score_accept_rate_weight: float = 0.3
    trust_score_rating_weight: float = 0.2
    trust_score_window_days: int = 30
    basket_abandon_hours: int = 24

    # Admin Web (§11)
    admin_basic_auth_user: str = "admin"
    admin_basic_auth_password: str = "placeholder_admin_password"
    admin_llm_cost_window_days: int = 30

    # Rate limiting (§9, Phase 9 hardening)
    throttle_limit_per_minute: int = 20
    throttle_quote_limit_per_minute: int = 3

    # Observability (Phase 9 hardening)
    sentry_dsn: str | None = None


    @property
    def webhook_path(self) -> str:
        return f"/webhook/{self.webhook_secret}"

    @property
    def webhook_url(self) -> str:
        return f"{self.webhook_base_url}{self.webhook_path}"


settings = Settings()
