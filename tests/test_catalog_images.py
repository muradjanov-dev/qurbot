"""Every live product must resolve to a local, relevant family photograph."""

import json
from pathlib import Path

from app.domain.catalog_images import photo_filename

ROOT = Path(__file__).parent
IMAGE_DIR = ROOT.parent / "app/web/storefront/static/images"


def test_live_catalog_image_coverage() -> None:
    products = json.loads((ROOT / "fixtures/active_catalog_images.json").read_text())
    assert len(products) == 393
    missing = []
    for product in products:
        filename = photo_filename(product["category"], product["name"])
        if filename == "no-photo.svg" or not (IMAGE_DIR / filename).is_file():
            missing.append(product["slug"])
    assert not missing, f"Missing suitable local image: {missing}"


def test_every_photo_has_a_source_and_license() -> None:
    credits = json.loads((IMAGE_DIR / "credits.json").read_text())
    credited = {item["file"] for item in credits}
    photos = {path.name for path in IMAGE_DIR.glob("*.webp")}
    assert photos == credited
    assert all(
        item["source"].startswith("https://")
        and item["license_url"].startswith("https://")
        and item["creator"]
        for item in credits
    )
