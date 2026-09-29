from pathlib import Path

from fastapi.templating import Jinja2Templates

from app.core.i18n import DEFAULT_LANG, t
from app.web.storefront.deps import ASSET_VERSION
from app.web.storefront.pricing import format_money
from app.web.storefront.session import LANG_COOKIE, normalize_lang

templates = Jinja2Templates(
    directory=[
        str(Path(__file__).parent / "templates"),
        str(Path(__file__).parent / "storefront" / "templates"),
    ]
)

templates.env.globals.update(
    t=t,
    asset_version=ASSET_VERSION,
    format_money=format_money,
    legacy_lang=lambda request: normalize_lang(request.cookies.get(LANG_COOKIE)) or DEFAULT_LANG,
)
