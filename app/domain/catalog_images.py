"""Stable product-family photos for the customer catalogue.

The family is based on the product name rather than its slug because supplier
imports use opaque ``excel-…`` slugs. Dimensions and brands share a photo only
when they describe the same kind of material.
"""

from __future__ import annotations


def photo_filename(category_slug: str, product_name: str) -> str:
    name = product_name.casefold()

    if category_slug == "plita-va-fanera":
        if "osb" in name:
            return "osb.webp"
        if any(token in name for token in ("dsp", "дсп")):
            return "particleboard.webp"
        if any(token in name for token in ("hdf", "dvp", "хдф", "двп")):
            return "fiberboard.webp"
        if "laminat" in name or "ламина" in name:
            return "laminated-plywood.webp"
        return "plywood.webp"

    if category_slug == "yogoch":
        return "lumber.webp"

    simple = {
        "gipsokarton": "drywall.webp",
        "gisht-va-bloklar": "bricks.webp",
        "sement-va-qorishmalar": "cement.webp",
        "boyoq-va-lak": "paint.webp",
        "plitka": "tiles.webp",
    }
    if category_slug in simple:
        return simple[category_slug]

    if category_slug != "mahkamlash-materiallari":
        return "no-photo.svg"

    if any(token in name for token in ("kryuchok", "крючок")):
        return "hooks.webp"
    if any(token in name for token in ("zaklepka", "заклепка")):
        return "rivets.webp"
    if any(token in name for token in ("shpilka", "шпилька")):
        return "threaded-rods.webp"
    if any(token in name for token in ("zontik", "зонтик")):
        return "insulation-fixings.webp"
    if any(
        token in name for token in ("chopiq", "dyubel", "дюбел", "gazoblok", "probka", "пробка")
    ):
        return "wall-plugs.webp"
    if any(token in name for token in ("anker", "анкер", "tsanga", "цанга")):
        return "anchors.webp"
    if any(token in name for token in ("gayka", "гайка", "mufta", "муфта")):
        return "nuts.webp"
    if any(token in name for token in ("grover", "гровер", "rezina", "резина")):
        return "washers.webp"
    if any(token in name for token in ("shayba", "шайба")) and not any(
        token in name for token in ("press", "пресс")
    ):
        return "washers.webp"
    if any(token in name for token in ("podves", "подвес")):
        return "hangers.webp"
    if any(token in name for token in ("bolt", "болт", "gluxar", "глухар")):
        return "bolts.webp"
    if any(token in name for token in ("mix ", "мих ")):
        return "nails.webp"
    if any(token in name for token in ("krovelniy", "кровельный")):
        return "roofing-screws.webp"
    if any(
        token in name
        for token in (
            "samorez",
            "саморез",
            "press",
            "пресс",
            "potay",
            "поттай",
            "gribok",
            "грибок",
            "stashka",
            "сташка",
            "chervyak",
            "червяк",
            "medved",
            "медвед",
            "yevro",
            "евро",
            "sariq",
            "сарик",
            "qora",
            "кора",
            "oq ",
            "ок ",
        )
    ):
        return "screws.webp"
    return "no-photo.svg"
