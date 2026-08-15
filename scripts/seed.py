"""Deterministic database seeding script for QurBot (Tashkent construction catalog).

Generates:
- 8 Units
- 12 Standard Categories
- 250+ Canonical Products (SKUs)
- 900+ Product Aliases (Uzbek Latin, Uzbek Cyrillic, Russian)
- 13 Districts (Tashkent City + Region)
- 20 Partner Shops with realistic delivery rules
- ~4,000 Shop Products (Offers) with computed unit prices
- 5 Sample Users
"""

import asyncio
import logging
import random
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    CanonicalProduct,
    Category,
    District,
    ProductAlias,
    Shop,
    ShopDeliveryRule,
    ShopProduct,
    Unit,
    User,
)
from app.db.session import async_session_factory
from app.domain.normalize.text import normalize_text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("seed")

# Set fixed seed for reproducibility
random.seed(42)

# --- 1. Units ---
UNITS_DATA = [
    {
        "code": "kg",
        "name_uz": "Kilogramm",
        "name_ru": "Килограмм",
        "dimension": "mass",
        "base_code": None,
        "factor_to_base": Decimal("1.0000"),
    },
    {
        "code": "dona",
        "name_uz": "Dona",
        "name_ru": "Штука",
        "dimension": "count",
        "base_code": None,
        "factor_to_base": Decimal("1.0000"),
    },
    {
        "code": "m2",
        "name_uz": "Kvadrat metr",
        "name_ru": "Квадратный метр",
        "dimension": "area",
        "base_code": None,
        "factor_to_base": Decimal("1.0000"),
    },
    {
        "code": "m3",
        "name_uz": "Kub metr",
        "name_ru": "Кубический метр",
        "dimension": "volume",
        "base_code": None,
        "factor_to_base": Decimal("1.0000"),
    },
    {
        "code": "litr",
        "name_uz": "Litr",
        "name_ru": "Литр",
        "dimension": "volume",
        "base_code": "m3",
        "factor_to_base": Decimal("0.0010"),
    },
    {
        "code": "qop",
        "name_uz": "Qop",
        "name_ru": "Мешок",
        "dimension": "count",
        "base_code": "dona",
        "factor_to_base": Decimal("1.0000"),
    },
    {
        "code": "quti",
        "name_uz": "Quti",
        "name_ru": "Коробка",
        "dimension": "count",
        "base_code": "dona",
        "factor_to_base": Decimal("1.0000"),
    },
    {
        "code": "rulon",
        "name_uz": "Rulon",
        "name_ru": "Рулон",
        "dimension": "count",
        "base_code": "dona",
        "factor_to_base": Decimal("1.0000"),
    },
    {
        "code": "metr",
        "name_uz": "Metr",
        "name_ru": "Метр",
        "dimension": "length",
        "base_code": None,
        "factor_to_base": Decimal("1.0000"),
    },
]

# --- 2. Categories ---
CATEGORIES_DATA = [
    {
        "slug": "sement-va-qorishmalar",
        "name_uz": "Sement va qorishmalar",
        "name_ru": "Цемент и смеси",
        "sort_order": 1,
        "icon": "🧱",
    },
    {
        "slug": "gisht-va-bloklar",
        "name_uz": "G'isht va bloklar",
        "name_ru": "Кирпич и блоки",
        "sort_order": 2,
        "icon": "🧱",
    },
    {
        "slug": "metall-va-armatura",
        "name_uz": "Metall va armatura",
        "name_ru": "Металл и арматура",
        "sort_order": 3,
        "icon": "⚙️",
    },
    {
        "slug": "yogoch",
        "name_uz": "Yog'och va taxta",
        "name_ru": "Дерево и пиломатериалы",
        "sort_order": 4,
        "icon": "🪵",
    },
    {
        "slug": "boyoq-va-lak",
        "name_uz": "Bo'yoq va lak",
        "name_ru": "Краски и лаки",
        "sort_order": 5,
        "icon": "🎨",
    },
    {
        "slug": "plitka",
        "name_uz": "Plitka va kafel",
        "name_ru": "Плитка и кафель",
        "sort_order": 6,
        "icon": "🏺",
    },
    {
        "slug": "santexnika",
        "name_uz": "Santexnika va quvurlar",
        "name_ru": "Сантехника и трубы",
        "sort_order": 7,
        "icon": "🚰",
    },
    {
        "slug": "elektr",
        "name_uz": "Elektr jihozlari",
        "name_ru": "Электрика",
        "sort_order": 8,
        "icon": "⚡",
    },
    {
        "slug": "izolyatsiya",
        "name_uz": "Izolyatsiya",
        "name_ru": "Изоляция",
        "sort_order": 9,
        "icon": "🛡️",
    },
    {
        "slug": "gipsokarton",
        "name_uz": "Gipsokarton va profillar",
        "name_ru": "Гипсокартон и профили",
        "sort_order": 10,
        "icon": "📐",
    },
    {
        "slug": "tom-yopish",
        "name_uz": "Tom yopish materiallari",
        "name_ru": "Кровельные материалы",
        "sort_order": 11,
        "icon": "🏠",
    },
    {
        "slug": "eshik-va-derazalar",
        "name_uz": "Eshik va derazalar",
        "name_ru": "Двери и окна",
        "sort_order": 12,
        "icon": "🚪",
    },
    {
        "slug": "quruq-aralashmalar",
        "name_uz": "Quruq aralashmalar",
        "name_ru": "Сухие смеси",
        "sort_order": 13,
        "icon": "🪣",
    },
    {
        "slug": "gidroizolyatsiya",
        "name_uz": "Gidroizolyatsiya",
        "name_ru": "Гидроизоляция",
        "sort_order": 14,
        "icon": "💧",
    },
    {
        "slug": "pol-materiallari",
        "name_uz": "Pol materiallari",
        "name_ru": "Напольные покрытия",
        "sort_order": 15,
        "icon": "🪨",
    },
    {
        "slug": "fasad-materiallari",
        "name_uz": "Fasad materiallari",
        "name_ru": "Фасадные материалы",
        "sort_order": 16,
        "icon": "🏢",
    },
    {
        "slug": "mahkamlash-materiallari",
        "name_uz": "Mahkamlash materiallari",
        "name_ru": "Крепёж",
        "sort_order": 17,
        "icon": "🔩",
    },
    {
        "slug": "isitish-va-ventilyatsiya",
        "name_uz": "Isitish va ventilyatsiya",
        "name_ru": "Отопление и вентиляция",
        "sort_order": 18,
        "icon": "🔥",
    },
    {
        "slug": "asboblar",
        "name_uz": "Qurilish asboblari",
        "name_ru": "Строительные инструменты",
        "sort_order": 19,
        "icon": "🧰",
    },
    {
        "slug": "sarf-materiallari",
        "name_uz": "Sarf materiallari",
        "name_ru": "Расходные материалы",
        "sort_order": 20,
        "icon": "🧪",
    },
]

# --- 3. Districts in Tashkent ---
DISTRICTS_DATA = [
    {
        "region": "Toshkent",
        "name_uz": "Chilonzor tumani",
        "name_ru": "Чиланзарский район",
        "lat": Decimal("41.2721"),
        "lng": Decimal("69.2045"),
    },
    {
        "region": "Toshkent",
        "name_uz": "Yunusobod tumani",
        "name_ru": "Юнусабадский район",
        "lat": Decimal("41.3644"),
        "lng": Decimal("69.2882"),
    },
    {
        "region": "Toshkent",
        "name_uz": "Mirzo Ulug'bek tumani",
        "name_ru": "Мирзо-Улугбекский район",
        "lat": Decimal("41.3283"),
        "lng": Decimal("69.3364"),
    },
    {
        "region": "Toshkent",
        "name_uz": "Yakkasaroy tumani",
        "name_ru": "Яккасарайский район",
        "lat": Decimal("41.2825"),
        "lng": Decimal("69.2520"),
    },
    {
        "region": "Toshkent",
        "name_uz": "Shayxontohur tumani",
        "name_ru": "Шайхантахурский район",
        "lat": Decimal("41.3198"),
        "lng": Decimal("69.2312"),
    },
    {
        "region": "Toshkent",
        "name_uz": "Olmazor tumani",
        "name_ru": "Алмазарский район",
        "lat": Decimal("41.3524"),
        "lng": Decimal("69.2235"),
    },
    {
        "region": "Toshkent",
        "name_uz": "Uchtepa tumani",
        "name_ru": "Учтепинский район",
        "lat": Decimal("41.2941"),
        "lng": Decimal("69.1763"),
    },
    {
        "region": "Toshkent",
        "name_uz": "Mirobod tumani",
        "name_ru": "Мирабадский район",
        "lat": Decimal("41.2905"),
        "lng": Decimal("69.2871"),
    },
    {
        "region": "Toshkent",
        "name_uz": "Sergeli tumani",
        "name_ru": "Сергелийский район",
        "lat": Decimal("41.2223"),
        "lng": Decimal("69.2215"),
    },
    {
        "region": "Toshkent",
        "name_uz": "Bektemir tumani",
        "name_ru": "Бектемирский район",
        "lat": Decimal("41.2132"),
        "lng": Decimal("69.3341"),
    },
    {
        "region": "Toshkent",
        "name_uz": "Yangihayot tumani",
        "name_ru": "Янгихаётский район",
        "lat": Decimal("41.2012"),
        "lng": Decimal("69.2014"),
    },
    {
        "region": "Toshkent",
        "name_uz": "Yashnobod tumani",
        "name_ru": "Яшнабадский район",
        "lat": Decimal("41.2915"),
        "lng": Decimal("69.3402"),
    },
    {
        "region": "Toshkent viloyati",
        "name_uz": "Toshkent viloyati",
        "name_ru": "Ташкентская область",
        "lat": Decimal("41.3000"),
        "lng": Decimal("69.4000"),
    },
]

# --- 4. Shops Data ---
SHOPS_DATA = [
    {
        "name": "Baraka Qurilish",
        "legal_name": "Baraka Qurilish Savdo MCHJ",
        "phone": "+998901112233",
        "district_idx": 0,
        "address": "Chilonzor 19-mavze, 45",
        "rating": Decimal("4.9"),
        "trust_score": Decimal("0.98"),
    },
    {
        "name": "Nur Stroy Yunusobod",
        "legal_name": "Nur Stroy Grand OK",
        "phone": "+998902223344",
        "district_idx": 1,
        "address": "Yunusobod 12-mavze, 12",
        "rating": Decimal("4.8"),
        "trust_score": Decimal("0.95"),
    },
    {
        "name": "O'rikzor Mega Stroy",
        "legal_name": "Mega Qurilish Savdo MCHJ",
        "phone": "+998903334455",
        "district_idx": 6,
        "address": "O'rikzor bozori, 4-blok 12-do'kon",
        "rating": Decimal("4.7"),
        "trust_score": Decimal("0.92"),
    },
    {
        "name": "Mirzo Ulug'bek Qurilish Markazi",
        "legal_name": "Ulugbek Stroy MCHJ",
        "phone": "+998904445566",
        "district_idx": 2,
        "address": "Buyuk Ipak Yo'li ko'chasi 110",
        "rating": Decimal("4.9"),
        "trust_score": Decimal("0.97"),
    },
    {
        "name": "Yakkasaroy Master Stroy",
        "legal_name": "Master Stroy Servis OK",
        "phone": "+998905556677",
        "district_idx": 3,
        "address": "Shota Rustaveli ko'chasi 88",
        "rating": Decimal("4.6"),
        "trust_score": Decimal("0.90"),
    },
    {
        "name": "Jomboy Savdo Markazi",
        "legal_name": "Jomboy Qurilish Savdo",
        "phone": "+998906667788",
        "district_idx": 4,
        "address": "Qoratosh ko'chasi 15",
        "rating": Decimal("4.5"),
        "trust_score": Decimal("0.89"),
    },
    {
        "name": "Olmazor Temir va Sement",
        "legal_name": "Olmazor Stroy MCHJ",
        "phone": "+998907778899",
        "district_idx": 5,
        "address": "Keles yo'li 45",
        "rating": Decimal("4.7"),
        "trust_score": Decimal("0.94"),
    },
    {
        "name": "Sergeli Qurilish Bozori 7-do'kon",
        "legal_name": "Sergeli Qurilish Savdo",
        "phone": "+998908889900",
        "district_idx": 8,
        "address": "Sergeli Yangi bozor 7",
        "rating": Decimal("4.8"),
        "trust_score": Decimal("0.96"),
    },
    {
        "name": "Mirobod Elite Stroy",
        "legal_name": "Elite Building Materials MCHJ",
        "phone": "+998909990011",
        "district_idx": 7,
        "address": "Nukus ko'chasi 42",
        "rating": Decimal("4.9"),
        "trust_score": Decimal("0.99"),
    },
    {
        "name": "Yashnobod Qurilish Baza",
        "legal_name": "Yashnobod Stroy Baza MCHJ",
        "phone": "+998931110022",
        "district_idx": 11,
        "address": "Farg'ona Yo'li 180",
        "rating": Decimal("4.6"),
        "trust_score": Decimal("0.91"),
    },
    {
        "name": "Bektemir Metal Trade",
        "legal_name": "Bektemir Metal Trade MCHJ",
        "phone": "+998932220033",
        "district_idx": 9,
        "address": "Bektemir shoh ko'chasi 25",
        "rating": Decimal("4.8"),
        "trust_score": Decimal("0.95"),
    },
    {
        "name": "Uchtepa Kafel & Plitka",
        "legal_name": "Uchtepa Ceramic OK",
        "phone": "+998933330044",
        "district_idx": 6,
        "address": "Farhod bozori 102",
        "rating": Decimal("4.7"),
        "trust_score": Decimal("0.93"),
    },
    {
        "name": "Akfa & Knauf Rasmiy Dileri",
        "legal_name": "Plaster & Profile Diler MCHJ",
        "phone": "+998934440055",
        "district_idx": 0,
        "address": "Bunyodkor ko'chasi 50",
        "rating": Decimal("5.0"),
        "trust_score": Decimal("0.99"),
    },
    {
        "name": "Ideal Sement Chilonzor",
        "legal_name": "Ideal Sement Savdo",
        "phone": "+998935550066",
        "district_idx": 0,
        "address": "Lutfiy ko'chasi 18",
        "rating": Decimal("4.5"),
        "trust_score": Decimal("0.90"),
    },
    {
        "name": "StroyMarket Yunusobod",
        "legal_name": "StroyMarket Express MCHJ",
        "phone": "+998936660077",
        "district_idx": 1,
        "address": "Amir Temur ko'chasi 140",
        "rating": Decimal("4.8"),
        "trust_score": Decimal("0.97"),
    },
    {
        "name": "Toshkent Santexnika Markazi",
        "legal_name": "Aqua Therm Servis MCHJ",
        "phone": "+998937770088",
        "district_idx": 4,
        "address": "Beruniy ko'chasi 33",
        "rating": Decimal("4.9"),
        "trust_score": Decimal("0.98"),
    },
    {
        "name": "Grand Bo'yoq va Lak",
        "legal_name": "Grand Paints MCHJ",
        "phone": "+998938880099",
        "district_idx": 2,
        "address": "Parkent ko'chasi 77",
        "rating": Decimal("4.7"),
        "trust_score": Decimal("0.93"),
    },
    {
        "name": "Quruvchi Do'st Sergeli",
        "legal_name": "Builder Friend OK",
        "phone": "+998941112244",
        "district_idx": 8,
        "address": "Choshtepa ko'chasi 14",
        "rating": Decimal("4.6"),
        "trust_score": Decimal("0.91"),
    },
    {
        "name": "Keles Stroy Baza",
        "legal_name": "Keles Qurilish Ta'minot",
        "phone": "+998942223355",
        "district_idx": 5,
        "address": "Qorasaroy ko'chasi 99",
        "rating": Decimal("4.7"),
        "trust_score": Decimal("0.94"),
    },
    {
        "name": "Toshkent Viloyat Stroy Terminal",
        "legal_name": "Region Stroy Terminal MCHJ",
        "phone": "+998943334466",
        "district_idx": 12,
        "address": "Bekobod yo'nalishi 5-km",
        "rating": Decimal("4.8"),
        "trust_score": Decimal("0.96"),
    },
]

# --- 5. Sample Users ---
USERS_DATA = [
    {
        "tg_id": 917456291,
        "username": "admin",
        "full_name": "Admin",
        "role": "admin",
        "lang": "uz_latn",
    },
    {
        "tg_id": 100001,
        "username": "admin_qurbot",
        "full_name": "QurBot Admin",
        "role": "admin",
        "lang": "uz_latn",
    },
    {
        "tg_id": 200001,
        "username": "jasur_stroy",
        "full_name": "Jasur Bek",
        "role": "customer",
        "lang": "uz_latn",
    },
    {
        "tg_id": 200002,
        "username": "rustam_builder",
        "full_name": "Rustam Aliyev",
        "role": "customer",
        "lang": "ru",
    },
    {
        "tg_id": 300001,
        "username": "baraka_owner",
        "full_name": "Baraka Do'kon Egasi",
        "role": "shop_owner",
        "lang": "uz_latn",
    },
    {
        "tg_id": 300002,
        "username": "nur_owner",
        "full_name": "Nur Stroy Rahbari",
        "role": "shop_owner",
        "lang": "uz_cyrl",
    },
]


# Helper to generate canonical products data
def generate_catalog_data() -> list[dict[str, Any]]:
    products = []

    # 1. Sement va qorishmalar
    sement_items = [
        (
            "qizilqum-sement-m400-50kg",
            "Qizilqum Sement M400 (50 kg)",
            "Қизилқум Цемент М400 (50 кг)",
            "Цемент Кызылкум М400 (50 кг)",
            "Qizilqumsement",
            "sement-va-qorishmalar",
            "kg",
            {"grade": "M400", "weight_kg": 50, "packaging": "bag"},
            "standard",
            Decimal("52000"),
            Decimal("50"),
            "qop",
        ),
        (
            "bekobod-sement-m400-50kg",
            "Bekobod Sement M400 (50 kg)",
            "Бекобод Цемент М400 (50 кг)",
            "Цемент Бекабад М400 (50 кг)",
            "Bekobodcement",
            "sement-va-qorishmalar",
            "kg",
            {"grade": "M400", "weight_kg": 50, "packaging": "bag"},
            "economy",
            Decimal("50000"),
            Decimal("50"),
            "qop",
        ),
        (
            "ohangaron-sement-m400-50kg",
            "Ohangaron Sement M400 (50 kg)",
            "Оҳангарон Цемент М400 (50 кг)",
            "Цемент Ахангаран М400 (50 кг)",
            "Ohangaronsement",
            "sement-va-qorishmalar",
            "kg",
            {"grade": "M400", "weight_kg": 50, "packaging": "bag"},
            "standard",
            Decimal("53000"),
            Decimal("50"),
            "qop",
        ),
        (
            "kuvasay-sement-m500-50kg",
            "Quvasoy Sement M500 (50 kg)",
            "Қувасой Цемент М500 (50 кг)",
            "Цемент Кувасай М500 (50 кг)",
            "Quvasaysement",
            "sement-va-qorishmalar",
            "kg",
            {"grade": "M500", "weight_kg": 50, "packaging": "bag"},
            "premium",
            Decimal("62000"),
            Decimal("50"),
            "qop",
        ),
        (
            "ohangaron-sement-m500-50kg",
            "Ohangaron Sement M500 (50 kg)",
            "Оҳангарон Цемент М500 (50 кг)",
            "Цемент Ахангаран М500 (50 кг)",
            "Ohangaronsement",
            "sement-va-qorishmalar",
            "kg",
            {"grade": "M500", "weight_kg": 50, "packaging": "bag"},
            "premium",
            Decimal("64000"),
            Decimal("50"),
            "qop",
        ),
        (
            "alibaz-sement-m400-25kg",
            "Alibaz Sement M400 (25 kg)",
            "Алибаз Цемент М400 (25 кг)",
            "Цемент Алибаз М400 (25 кг)",
            "Alibaz",
            "sement-va-qorishmalar",
            "kg",
            {"grade": "M400", "weight_kg": 25, "packaging": "bag"},
            "standard",
            Decimal("28000"),
            Decimal("25"),
            "qop",
        ),
        (
            "rotband-shpaklyovka-30kg",
            "Knauf Rotband Shuvoq gipsli (30 kg)",
            "Кнауф Ротбанд Штукатурка гипсли (30 кг)",
            "Штукатурка гипсовая Knauf Ротбанд (30 кг)",
            "Knauf",
            "sement-va-qorishmalar",
            "kg",
            {"type": "plaster", "base": "gypsum", "weight_kg": 30},
            "premium",
            Decimal("55000"),
            Decimal("30"),
            "qop",
        ),
        (
            "knauf-satengips-25kg",
            "Knauf Satengips Shpaklyovka (25 kg)",
            "Кнауф Сатенгипс Шпаклёвка (25 кг)",
            "Шпаклевка Knauf Сатенгипс (25 кг)",
            "Knauf",
            "sement-va-qorishmalar",
            "kg",
            {"type": "finish", "weight_kg": 25},
            "premium",
            Decimal("48000"),
            Decimal("25"),
            "qop",
        ),
        (
            "ceresit-cm11-plitka-yelimi-25kg",
            "Ceresit CM 11 Plitka yelimi (25 kg)",
            "Церезит СМ 11 Плитка елими (25 кг)",
            "Клей плиточный Ceresit CM 11 (25 кг)",
            "Ceresit",
            "sement-va-qorishmalar",
            "kg",
            {"type": "tile_adhesive", "weight_kg": 25},
            "standard",
            Decimal("42000"),
            Decimal("25"),
            "qop",
        ),
        (
            "ceresit-cm16-plitka-yelimi-25kg",
            "Ceresit CM 16 Moslashuvchan kley (25 kg)",
            "Церезит СМ 16 Мослашувчан клей (25 кг)",
            "Клей плиточный Ceresit CM 16 Flex (25 кг)",
            "Ceresit",
            "sement-va-qorishmalar",
            "kg",
            {"type": "flex_adhesive", "weight_kg": 25},
            "premium",
            Decimal("85000"),
            Decimal("25"),
            "qop",
        ),
        (
            "alibaz-plitka-yelimi-25kg",
            "Alibaz Plitka Yelimi Standart (25 kg)",
            "Алибаз Плитка Елими Стандарт (25 кг)",
            "Клей для плитки Alibaz Standart (25 кг)",
            "Alibaz",
            "sement-va-qorishmalar",
            "kg",
            {"type": "tile_adhesive", "weight_kg": 25},
            "economy",
            Decimal("29000"),
            Decimal("25"),
            "qop",
        ),
        (
            "master-qum-shagal-aralashmasi-50kg",
            "Qum-shag'al qorishmasi PGS (50 kg)",
            "Қум-шағал қоришмаси ПГС (50 кг)",
            "Песчано-гравийная смесь ПГС (50 кг)",
            "Master",
            "sement-va-qorishmalar",
            "kg",
            {"type": "pgs", "weight_kg": 50},
            "economy",
            Decimal("15000"),
            Decimal("50"),
            "qop",
        ),
        (
            "yuvilgan-qum-tonna",
            "Yuvilgan Qum (tonna)",
            "Ювилган Қум (тонна)",
            "Песок мытый карьерный (тонна)",
            "Toshkent Nerud",
            "sement-va-qorishmalar",
            "kg",
            {"type": "sand", "washed": True},
            "standard",
            Decimal("85000"),
            Decimal("1000"),
            "tonna",
        ),
        (
            "maydalangan-shagal-m3",
            "Maydalangan Shag'al (Fr. 5-20)",
            "Майдаланган Шағал (Фр. 5-20)",
            "Щебень дробленый (Фр. 5-20) м3",
            "Toshkent Nerud",
            "sement-va-qorishmalar",
            "m3",
            {"type": "gravel", "fraction": "5-20"},
            "standard",
            Decimal("120000"),
            Decimal("1"),
            "m3",
        ),
    ]
    products.extend(sement_items)

    # 2. G'isht va bloklar
    gisht_items = [
        (
            "pishgan-gisht-m100",
            "Pishgan qizil g'isht M100",
            "Пишган қизил ғишт М100",
            "Кирпич жженый красный М100",
            "Yangiyo'l",
            "gisht-va-bloklar",
            "dona",
            {"grade": "M100", "type": "red_burnt"},
            "standard",
            Decimal("1350"),
            Decimal("1"),
            "dona",
        ),
        (
            "pishgan-gisht-m125",
            "Pishgan qizil g'isht M125",
            "Пишган қизил ғишт М125",
            "Кирпич жженый красный М125",
            "Chinoz",
            "gisht-va-bloklar",
            "dona",
            {"grade": "M125", "type": "red_burnt"},
            "premium",
            Decimal("1550"),
            Decimal("1"),
            "dona",
        ),
        (
            "xom-gisht-standart",
            "Xom g'isht standart",
            "Хом ғишт стандарт",
            "Кирпич сырец стандартный",
            "Mahalliy",
            "gisht-va-bloklar",
            "dona",
            {"type": "raw_brick"},
            "economy",
            Decimal("700"),
            Decimal("1"),
            "dona",
        ),
        (
            "gazoblok-d500-600x300x200",
            "Gazoblok D500 600x300x200",
            "Газоблок Д500 600x300x200",
            "Газоблок D500 600х300х200",
            "East Block",
            "gisht-va-bloklar",
            "dona",
            {"density": "D500", "size": "600x300x200"},
            "standard",
            Decimal("38000"),
            Decimal("1"),
            "dona",
        ),
        (
            "gazoblok-d600-600x300x200",
            "Gazoblok D600 600x300x200",
            "Газоблок Д600 600x300x200",
            "Газоблок D600 600х300х200",
            "Arton",
            "gisht-va-bloklar",
            "dona",
            {"density": "D600", "size": "600x300x200"},
            "premium",
            Decimal("41000"),
            Decimal("1"),
            "dona",
        ),
        (
            "penoblok-600x300x200",
            "Penoblok D600 600x300x200",
            "Пеноблок Д600 600x300x200",
            "Пеноблок D600 600х300х200",
            "StroyPen",
            "gisht-va-bloklar",
            "dona",
            {"density": "D600", "size": "600x300x200"},
            "economy",
            Decimal("32000"),
            Decimal("1"),
            "dona",
        ),
        (
            "shlakoblok-standart-390x190x190",
            "Shlakoblok 390x190x190",
            "Шлакоблок 390x190x190",
            "Шлакоблок 390х190х190",
            "Baza Block",
            "gisht-va-bloklar",
            "dona",
            {"size": "390x190x190"},
            "economy",
            Decimal("6500"),
            Decimal("1"),
            "dona",
        ),
    ]
    products.extend(gisht_items)

    # 3. Metall va armatura
    armatura_diameters = [8, 10, 12, 14, 16, 18, 20, 22, 25, 28, 32]
    for d in armatura_diameters:
        price_per_kg = Decimal("9800") + Decimal(str(d * 20))
        armatura_items = (
            f"armatura-a500c-{d}mm",
            f"Armatura A500C {d} mm",
            f"Арматура А500С {d} мм",
            f"Арматура А500С {d} мм",
            "Uzmetkombinat",
            "metall-va-armatura",
            "kg",
            {"grade": "A500C", "diameter_mm": d, "standard": "GOST 52544"},
            "standard",
            price_per_kg * Decimal("100"),  # 100 kg pack price
            Decimal("100"),
            "kg",
        )
        products.append(armatura_items)

    products.append(
        (
            "katanka-sim-6mm",
            "Katanka sim 6 mm",
            "Катанка сим 6 мм",
            "Катанка проволока 6 мм",
            "Uzmetkombinat",
            "metall-va-armatura",
            "kg",
            {"diameter_mm": 6},
            "standard",
            Decimal("10500"),
            Decimal("1"),
            "kg",
        )
    )
    products.append(
        (
            "boglash-simi-1-2mm",
            "Bog'lash simi 1.2 mm",
            "Боғлаш сими 1.2 мм",
            "Проволока вязальная 1.2 мм",
            "Uzmetkombinat",
            "metall-va-armatura",
            "kg",
            {"diameter_mm": 1.2},
            "standard",
            Decimal("13000"),
            Decimal("1"),
            "kg",
        )
    )
    products.append(
        (
            "profil-truba-40x40x2mm",
            "Profil truba 40x40x2 mm (6m)",
            "Профиль труба 40x40x2 мм (6м)",
            "Труба профильная 40х40х2 мм (6м)",
            "MetallInvest",
            "metall-va-armatura",
            "metr",
            {"size": "40x40", "thickness_mm": 2},
            "standard",
            Decimal("125000"),
            Decimal("6"),
            "metr",
        )
    )
    products.append(
        (
            "profil-truba-60x60x2mm",
            "Profil truba 60x60x2 mm (6m)",
            "Профиль труба 60x60x2 мм (6м)",
            "Труба профильная 60х60х2 мм (6м)",
            "MetallInvest",
            "metall-va-armatura",
            "metr",
            {"size": "60x60", "thickness_mm": 2},
            "standard",
            Decimal("185000"),
            Decimal("6"),
            "metr",
        )
    )
    products.append(
        (
            "ugolnik-50x50x4mm",
            "Ugolnik 50x50x4 mm (6m)",
            "Угольник 50x50x4 мм (6м)",
            "Уголок стальной 50х50х4 мм (6м)",
            "Uzmetkombinat",
            "metall-va-armatura",
            "metr",
            {"size": "50x50", "thickness_mm": 4},
            "standard",
            Decimal("145000"),
            Decimal("6"),
            "metr",
        )
    )
    products.append(
        (
            "shveller-10-6m",
            "Shveller 10 (6m)",
            "Швеллер 10 (6м)",
            "Швеллер 10 (6м)",
            "Uzmetkombinat",
            "metall-va-armatura",
            "metr",
            {"size": "10"},
            "standard",
            Decimal("450000"),
            Decimal("6"),
            "metr",
        )
    )

    # 4. Yog'och va taxta
    wood_sizes = [
        (
            "taxta-25x100x6000",
            "Taxta 25x100x6000 mm",
            "Тахта 25x100x6000 мм",
            "Доска обрезная 25х100х6000 мм",
            Decimal("48000"),
        ),
        (
            "taxta-25x150x6000",
            "Taxta 25x150x6000 mm",
            "Тахта 25x150x6000 мм",
            "Доска обрезная 25х150х6000 мм",
            Decimal("72000"),
        ),
        (
            "taxta-40x150x6000",
            "Taxta 40x150x6000 mm",
            "Тахта 40x150x6000 мм",
            "Доска обрезная 40х150х6000 мм",
            Decimal("115000"),
        ),
        (
            "taxta-50x150x6000",
            "Taxta 50x150x6000 mm",
            "Тахта 50x150x6000 мм",
            "Доска обрезная 50х150х6000 мм",
            Decimal("145000"),
        ),
        (
            "brus-50x50x6000",
            "Brus 50x50x6000 mm",
            "Брус 50x50x6000 мм",
            "Брус 50х50х6000 мм",
            Decimal("48000"),
        ),
        (
            "brus-100x100x6000",
            "Brus 100x100x6000 mm",
            "Брус 100x100x6000 мм",
            "Брус 100х100х6000 мм",
            Decimal("190000"),
        ),
        (
            "brus-150x150x6000",
            "Brus 150x150x6000 mm",
            "Брус 150x150x6000 мм",
            "Брус 150х150х6000 мм",
            Decimal("420000"),
        ),
        (
            "fanera-10mm-1525x1525",
            "Fanera 10 mm 1525x1525",
            "Фанера 10 мм 1525x1525",
            "Фанера ФК 10 мм 1525х1525",
            Decimal("135000"),
        ),
        (
            "fanera-18mm-1525x1525",
            "Fanera 18 mm 1525x1525",
            "Фанера 18 мм 1525x1525",
            "Фанера ФК 18 мм 1525х1525",
            Decimal("245000"),
        ),
        (
            "osb-3-9mm-2500x1250",
            "OSB-3 Plita 9 mm 2500x1250",
            "ОСБ-3 Плита 9 мм 2500x1250",
            "Плита OSB-3 9 мм 2500х1250",
            Decimal("110000"),
        ),
        (
            "osb-3-12mm-2500x1250",
            "OSB-3 Plita 12 mm 2500x1250",
            "ОСБ-3 Плита 12 мм 2500x1250",
            "Плита OSB-3 12 мм 2500х1250",
            Decimal("140000"),
        ),
    ]
    for slug, n_uz, n_cyrl, n_ru, price in wood_sizes:
        products.append(
            (
                slug,
                n_uz,
                n_cyrl,
                n_ru,
                "Sibir Les",
                "yogoch",
                "dona",
                {"material": "pine"},
                "standard",
                price,
                Decimal("1"),
                "dona",
            )
        )

    # 5. Bo'yoq va lak
    paint_items = [
        (
            "tikkurila-euro-power-7-9l",
            "Tikkurila Euro Power 7 Bo'yoq (9 L)",
            "Тиккурила Евро Пауэр 7 Бўёқ (9 Л)",
            "Краска моющаяся Tikkurila Euro Power 7 (9 л)",
            "Tikkurila",
            "boyoq-va-lak",
            "litr",
            {"type": "latex", "finish": "matte", "volume_l": 9},
            "premium",
            Decimal("490000"),
            Decimal("9"),
            "litr",
        ),
        (
            "marshall-export-7-10l",
            "Marshall Export-7 Emulsiya (10 L)",
            "Маршалл Экспорт-7 Эмульсия (10 Л)",
            "Краска Marshall Export-7 (10 л)",
            "Marshall",
            "boyoq-va-lak",
            "litr",
            {"type": "acrylic", "volume_l": 10},
            "standard",
            Decimal("320000"),
            Decimal("10"),
            "litr",
        ),
        (
            "akfa-boyoq-oq-10l",
            "Akfa Oq fasad bo'yog'i (10 L)",
            "Акфа Оқ фасад бўёғи (10 Л)",
            "Краска фасадная белая Akfa (10 л)",
            "Akfa",
            "boyoq-va-lak",
            "litr",
            {"type": "facade", "volume_l": 10},
            "standard",
            Decimal("210000"),
            Decimal("10"),
            "litr",
        ),
        (
            "emal-pf-115-oq-2-8kg",
            "Emal PF-115 Oq (2.8 kg)",
            "Эмаль ПФ-115 Оқ (2.8 кг)",
            "Эмаль алкидная ПФ-115 белая (2.8 кг)",
            "Lakra",
            "boyoq-va-lak",
            "kg",
            {"type": "alkyd_enamel", "weight_kg": 2.8},
            "standard",
            Decimal("55000"),
            Decimal("2.8"),
            "kg",
        ),
        (
            "gruntovka-chuqur-kiruvchi-10l",
            "Gruntovka chuqur kiruvchi (10 L)",
            "Грунтовка чуқур кирувчи (10 Л)",
            "Грунтовка глубокого проникновения (10 л)",
            "Ceresit",
            "boyoq-va-lak",
            "litr",
            {"type": "primer", "volume_l": 10},
            "standard",
            Decimal("68000"),
            Decimal("10"),
            "litr",
        ),
        (
            "lak-akril-rangsiz-2-5l",
            "Akril rangsiz lak (2.5 L)",
            "Акрил рангсиз лак (2.5 Л)",
            "Лак акриловый бесцветный (2.5 л)",
            "Tikkurila",
            "boyoq-va-lak",
            "litr",
            {"type": "acrylic_varnish", "volume_l": 2.5},
            "premium",
            Decimal("145000"),
            Decimal("2.5"),
            "litr",
        ),
        (
            "emulsiya-oq-kraska-10l",
            "Emulsiya Oq Kraska 10L",
            "Эмульсия Оқ Краска 10Л",
            "Водоэмульсионная краска белая 10 л",
            "Sitora",
            "boyoq-va-lak",
            "litr",
            {"type": "water_emulsion", "color": "white", "volume_l": 10},
            "standard",
            Decimal("110000"),
            Decimal("10"),
            "litr",
        ),
    ]
    products.extend(paint_items)

    # 6. Plitka va kafel
    tile_items = [
        (
            "plitka-keramogranit-60x60-oq",
            "Keramogranit Oq Mramor 60x60 (1.44 m2)",
            "Керамогранит Оқ Мрамор 60x60 (1.44 м2)",
            "Керамогранит белый мрамор 60х60 (1.44 м2)",
            "Kerama Marazzi",
            "plitka",
            "m2",
            {"size": "60x60", "surface": "polished", "pack_m2": 1.44},
            "premium",
            Decimal("165000"),
            Decimal("1.44"),
            "m2",
        ),
        (
            "plitka-keramogranit-60x120-kulrang",
            "Keramogranit Kulrang 60x120 (1.44 m2)",
            "Керамогранит Кулранг 60x120 (1.44 м2)",
            "Керамогранит серый 60х120 (1.44 м2)",
            "Modern Ceramics",
            "plitka",
            "m2",
            {"size": "60x120", "surface": "matte", "pack_m2": 1.44},
            "premium",
            Decimal("220000"),
            Decimal("1.44"),
            "m2",
        ),
        (
            "plitka-kafel-30x30-oshxona",
            "Devor kafeli 30x30 Oq (1.5 m2)",
            "Девор кафели 30x30 Оқ (1.5 м2)",
            "Плитка настенная 30х30 белая (1.5 м2)",
            "Orient Ceramic",
            "plitka",
            "m2",
            {"size": "30x30", "surface": "glossy", "pack_m2": 1.5},
            "standard",
            Decimal("95000"),
            Decimal("1.5"),
            "m2",
        ),
        (
            "plitka-pol-40x40-bej",
            "Pol plitkasi Bej 40x40 (1.6 m2)",
            "Пол плиткаси Беж 40x40 (1.6 м2)",
            "Плитка напольная бежевая 40х40 (1.6 м2)",
            "Orient Ceramic",
            "plitka",
            "m2",
            {"size": "40x40", "surface": "anti_slip", "pack_m2": 1.6},
            "standard",
            Decimal("88000"),
            Decimal("1.6"),
            "m2",
        ),
        (
            "keramik-plitka-30x30",
            "Keramik Plitka 30x30",
            "Керамик Плитка 30x30",
            "Плитка керамическая 30х30",
            "Orient Ceramic",
            "plitka",
            "m2",
            {"size": "30x30", "pack_m2": 1.5},
            "standard",
            Decimal("85000"),
            Decimal("1.5"),
            "m2",
        ),
    ]
    products.extend(tile_items)

    # 7. Santexnika va quvurlar
    pipe_items = [
        (
            "ppr-quvur-20mm-4m",
            "PPR Quvur D20 mm Sovuq/Issiq (4m)",
            "ППР Қувур Д20 мм Совуқ/Иссиқ (4м)",
            "Труба полипропиленовая PPR 20 мм (4м)",
            "Ekoplastik",
            "santexnika",
            "metr",
            {"diameter_mm": 20, "length_m": 4},
            "standard",
            Decimal("24000"),
            Decimal("4"),
            "metr",
        ),
        (
            "ppr-quvur-25mm-4m",
            "PPR Quvur D25 mm Sovuq/Issiq (4m)",
            "ППР Қувур Д25 мм Совуқ/Иссиқ (4м)",
            "Труба полипропиленовая PPR 25 мм (4м)",
            "Ekoplastik",
            "santexnika",
            "metr",
            {"diameter_mm": 25, "length_m": 4},
            "standard",
            Decimal("36000"),
            Decimal("4"),
            "metr",
        ),
        (
            "ppr-quvur-32mm-4m",
            "PPR Quvur D32 mm Sovuq/Issiq (4m)",
            "ППР Қувур Д32 мм Совуқ/Иссиқ (4м)",
            "Труба полипропиленовая PPR 32 мм (4м)",
            "Ekoplastik",
            "santexnika",
            "metr",
            {"diameter_mm": 32, "length_m": 4},
            "standard",
            Decimal("52000"),
            Decimal("4"),
            "metr",
        ),
        (
            "kanalizatsiya-quvuri-50mm-2m",
            "Kanalizatsiya quvuri 50 mm (2m)",
            "Канализация қувури 50 мм (2м)",
            "Труба канализационная 50 мм (2м)",
            "PolymerPlast",
            "santexnika",
            "dona",
            {"diameter_mm": 50, "length_m": 2},
            "standard",
            Decimal("18000"),
            Decimal("1"),
            "dona",
        ),
        (
            "kanalizatsiya-quvuri-110mm-2m",
            "Kanalizatsiya quvuri 110 mm (2m)",
            "Канализация қувури 110 мм (2м)",
            "Труба канализационная 110 мм (2м)",
            "PolymerPlast",
            "santexnika",
            "dona",
            {"diameter_mm": 110, "length_m": 2},
            "standard",
            Decimal("38000"),
            Decimal("1"),
            "dona",
        ),
        (
            "sharoviy-krant-3-4-valtec",
            'Sharoviy kran Valtec 3/4"',
            'Шаровий кран Valtec 3/4"',
            'Кран шаровой Valtec 3/4" г/г',
            "Valtec",
            "santexnika",
            "dona",
            {"size": "3/4 inch", "type": "ball_valve"},
            "premium",
            Decimal("45000"),
            Decimal("1"),
            "dona",
        ),
        (
            "sharoviy-krant-1-2-valtec",
            'Sharoviy kran Valtec 1/2"',
            'Шаровий кран Valtec 1/2"',
            'Кран шаровой Valtec 1/2" г/г',
            "Valtec",
            "santexnika",
            "dona",
            {"size": "1/2 inch", "type": "ball_valve"},
            "premium",
            Decimal("32000"),
            Decimal("1"),
            "dona",
        ),
    ]
    products.extend(pipe_items)

    # 8. Elektr jihozlari
    electrical_items = [
        (
            "kabel-vvg-p-ng-2x1-5-100m",
            "Kabel VVG-P ng 2x1.5 (100m)",
            "Кабель ВВГ-П нг 2x1.5 (100м)",
            "Кабель ВВГ-П нг 2х1.5 медный (100м)",
            "Uzkabel",
            "elektr",
            "metr",
            {"type": "copper", "cores": 2, "cross_section_mm2": 1.5},
            "standard",
            Decimal("550000"),
            Decimal("100"),
            "metr",
        ),
        (
            "kabel-vvg-p-ng-3x2-5-100m",
            "Kabel VVG-P ng 3x2.5 (100m)",
            "Кабель ВВГ-П нг 3x2.5 (100м)",
            "Кабель ВВГ-П нг 3х2.5 медный (100м)",
            "Uzkabel",
            "elektr",
            "metr",
            {"type": "copper", "cores": 3, "cross_section_mm2": 2.5},
            "standard",
            Decimal("1150000"),
            Decimal("100"),
            "metr",
        ),
        (
            "kabel-vvg-p-ng-3x4-100m",
            "Kabel VVG-P ng 3x4.0 (100m)",
            "Кабель ВВГ-П нг 3x4.0 (100м)",
            "Кабель ВВГ-П нг 3х4.0 медный (100м)",
            "Uzkabel",
            "elektr",
            "metr",
            {"type": "copper", "cores": 3, "cross_section_mm2": 4.0},
            "standard",
            Decimal("1800000"),
            Decimal("100"),
            "metr",
        ),
        (
            "avtomat-schneider-16a-1p",
            "Avtomatik o'chirgich Schneider 16A 1P",
            "Автоматик ўчиргич Schneider 16A 1P",
            "Автоматический выключатель Schneider 16A 1P",
            "Schneider Electric",
            "elektr",
            "dona",
            {"current_a": 16, "poles": 1},
            "premium",
            Decimal("38000"),
            Decimal("1"),
            "dona",
        ),
        (
            "avtomat-schneider-25a-1p",
            "Avtomatik o'chirgich Schneider 25A 1P",
            "Автоматик ўчиргич Schneider 25A 1P",
            "Автоматический выключатель Schneider 25A 1P",
            "Schneider Electric",
            "elektr",
            "dona",
            {"current_a": 25, "poles": 1},
            "premium",
            Decimal("40000"),
            Decimal("1"),
            "dona",
        ),
        (
            "avtomat-chint-16a-1p",
            "Avtomatik o'chirgich Chint 16A 1P",
            "Автоматик ўчиргич Chint 16A 1P",
            "Автоматический выключатель Chint 16A 1P",
            "Chint",
            "elektr",
            "dona",
            {"current_a": 16, "poles": 1},
            "economy",
            Decimal("18000"),
            Decimal("1"),
            "dona",
        ),
        (
            "gofra-shlang-16mm-100m",
            "Gofra shlang 16 mm qora (100m)",
            "Гофра шланг 16 мм қора (100м)",
            "Труба гофрированная ПНД 16 мм (100м)",
            "Uzeltech",
            "elektr",
            "metr",
            {"diameter_mm": 16},
            "standard",
            Decimal("120000"),
            Decimal("100"),
            "metr",
        ),
    ]
    products.extend(electrical_items)

    # 9. Izolyatsiya
    insulation_items = [
        (
            "penoplast-50mm-1000x1000",
            "Penoplast 50 mm 1000x1000 mm (zichlik 15)",
            "Пенопласт 50 мм 1000x1000 мм (зичлик 15)",
            "Пенопласт ППС-15 50 мм 1000х1000",
            "PenoPlast",
            "izolyatsiya",
            "m2",
            {"thickness_mm": 50, "density": 15},
            "economy",
            Decimal("18000"),
            Decimal("1"),
            "m2",
        ),
        (
            "penoplast-100mm-1000x1000",
            "Penoplast 100 mm 1000x1000 mm (zichlik 15)",
            "Пенопласт 100 мм 1000x1000 мм (зичлик 15)",
            "Пенопласт ППС-15 100 мм 1000х1000",
            "PenoPlast",
            "izolyatsiya",
            "m2",
            {"thickness_mm": 100, "density": 15},
            "economy",
            Decimal("36000"),
            Decimal("1"),
            "m2",
        ),
        (
            "penoplex-50mm-1185x585",
            "Penoplex Ekstrudirovanniy 50 mm (0.69 m2)",
            "Пеноплекс Экструдированный 50 мм (0.69 м2)",
            "Экструдированный пенополистирол Пеноплэкс 50 мм",
            "Penoplex",
            "izolyatsiya",
            "dona",
            {"thickness_mm": 50, "type": "xps"},
            "premium",
            Decimal("32000"),
            Decimal("1"),
            "dona",
        ),
        (
            "mineral-vata-isover-50mm-14m2",
            "Mineral vata Isover Klassik 50 mm (14 m2)",
            "Минерал вата Изовер Классик 50 мм (14 м2)",
            "Минеральная вата Isover Классик 50 мм (14 м2)",
            "Isover",
            "izolyatsiya",
            "rulon",
            {"thickness_mm": 50, "area_m2": 14},
            "premium",
            Decimal("220000"),
            Decimal("1"),
            "rulon",
        ),
        (
            "mineral-vata-rockwool-50mm-6m2",
            "Bazalt plita Rockwool 50 mm (6 m2)",
            "Базальт плита Rockwool 50 мм (6 м2)",
            "Каменная вата Rockwool Лайт Баттс 50 мм (6 м2)",
            "Rockwool",
            "izolyatsiya",
            "quti",
            {"thickness_mm": 50, "area_m2": 6},
            "premium",
            Decimal("185000"),
            Decimal("1"),
            "quti",
        ),
        (
            "folgoizol-10m-rulon",
            "Folgoizol 10 m rulon",
            "Фольгоизол 10 м рулон",
            "Фольгоизол самоклеящийся 10 м",
            "IzolMaster",
            "izolyatsiya",
            "rulon",
            {"length_m": 10},
            "standard",
            Decimal("85000"),
            Decimal("1"),
            "rulon",
        ),
        (
            "ruberoid-rkp-350-rulon",
            "Ruberoid RKP-350 (15 m2 rulon)",
            "Рубероид РКП-350 (15 м2 рулон)",
            "Рубероид кровельный РКП-350 (15 м2)",
            "KrovlyaMaster",
            "izolyatsiya",
            "rulon",
            {"area_m2": 15, "standard": "GOST 10923"},
            "standard",
            Decimal("65000"),
            Decimal("1"),
            "rulon",
        ),
        (
            "asbest-shifer-8-tolqinli",
            "8 To'lqinli Asbest Shifer",
            "8 Тўлқинли Асбест Шифер",
            "Шифер 8-волновой хризотилцементный",
            "Quvasoy Shifer",
            "izolyatsiya",
            "dona",
            {"waves": 8, "size": "1750x1130"},
            "standard",
            Decimal("58000"),
            Decimal("1"),
            "dona",
        ),
    ]
    products.extend(insulation_items)

    # 10. Gipsokarton va profillar
    drywall_items = [
        (
            "gipsokarton-knauf-devor-12-5mm",
            "Knauf Gipsokarton devoriy 12.5 mm 2500x1200",
            "Кнауф Гипсокартон деворий 12.5 мм 2500x1200",
            "Гипсокартон Knauf стеновой 12.5 мм 2500х1200",
            "Knauf",
            "gipsokarton",
            "dona",
            {"thickness_mm": 12.5, "type": "wall", "size": "2500x1200"},
            "standard",
            Decimal("48000"),
            Decimal("1"),
            "dona",
        ),
        (
            "gipsokarton-knauf-ship-9-5mm",
            "Knauf Gipsokarton ship uchun 9.5 mm 2500x1200",
            "Кнауф Гипсокартон шип учун 9.5 мм 2500x1200",
            "Гипсокартон Knauf потолочный 9.5 мм 2500х1200",
            "Knauf",
            "gipsokarton",
            "dona",
            {"thickness_mm": 9.5, "type": "ceiling", "size": "2500x1200"},
            "standard",
            Decimal("44000"),
            Decimal("1"),
            "dona",
        ),
        (
            "gipsokarton-knauf-nam-gklv-12-5mm",
            "Knauf Namga chidamli GKLV 12.5 mm 2500x1200",
            "Кнауф Намга чидамли ГКЛВ 12.5 мм 2500x1200",
            "Гипсокартон влагостойкий Knauf ГКЛВ 12.5 мм",
            "Knauf",
            "gipsokarton",
            "dona",
            {"thickness_mm": 12.5, "type": "waterproof", "size": "2500x1200"},
            "premium",
            Decimal("59000"),
            Decimal("1"),
            "dona",
        ),
        (
            "profil-knauf-cd-60x27-3m",
            "Knauf Profil CD 60x27 mm (3m 0.6mm)",
            "Кнауф Профиль CD 60x27 мм (3м 0.6мм)",
            "Профиль потолочный Knauf CD 60х27 (3м 0.6мм)",
            "Knauf",
            "gipsokarton",
            "dona",
            {"size": "60x27", "thickness_mm": 0.6, "length_m": 3},
            "standard",
            Decimal("22000"),
            Decimal("1"),
            "dona",
        ),
        (
            "profil-knauf-ud-28x27-3m",
            "Knauf Profil UD 28x27 mm (3m 0.6mm)",
            "Кнауф Профиль UD 28x27 мм (3м 0.6мм)",
            "Профиль направляющий Knauf UD 28х27 (3м 0.6мм)",
            "Knauf",
            "gipsokarton",
            "dona",
            {"size": "28x27", "thickness_mm": 0.6, "length_m": 3},
            "standard",
            Decimal("16000"),
            Decimal("1"),
            "dona",
        ),
        (
            "profil-standart-cd-60x27-3m-045",
            "Standart Profil CD 60x27 mm (3m 0.45mm)",
            "Стандарт Профиль CD 60x27 мм (3м 0.45мм)",
            "Профиль CD 60х27 (3м 0.45мм эконом)",
            "MasterProfil",
            "gipsokarton",
            "dona",
            {"size": "60x27", "thickness_mm": 0.45, "length_m": 3},
            "economy",
            Decimal("14000"),
            Decimal("1"),
            "dona",
        ),
        (
            "podves-togridan-togri-knauf",
            "To'g'ridan-to'g'ri podves Knauf (1 dona)",
            "Тўғридан-тўғри подвес Knauf (1 дона)",
            "Прямой подвес Knauf для CD профиля",
            "Knauf",
            "gipsokarton",
            "dona",
            {"type": "hanger"},
            "standard",
            Decimal("1200"),
            Decimal("1"),
            "dona",
        ),
        (
            "samorez-gipsokarton-3-5x25-1000ta",
            "Samorez gipsokarton uchun 3.5x25 (1000 dona)",
            "Саморез гипсокартон учун 3.5x25 (1000 дона)",
            "Саморезы для ГКЛ по металлу 3.5х25 (1000 шт)",
            "StarFix",
            "gipsokarton",
            "quti",
            {"size": "3.5x25", "quantity": 1000},
            "standard",
            Decimal("35000"),
            Decimal("1"),
            "quti",
        ),
    ]
    products.extend(drywall_items)

    # 11. Tom yopish
    roofing_items = [
        (
            "profnastil-ps-20-0-45mm-m2",
            "Profnastil PS-20 Qalinligi 0.45 mm (m2)",
            "Профнастил ПС-20 Қалинлиги 0.45 мм (м2)",
            "Профнастил оцинкованный ПС-20 0.45 мм (м2)",
            "StroyKrovlya",
            "tom-yopish",
            "m2",
            {"type": "ps-20", "thickness_mm": 0.45},
            "standard",
            Decimal("65000"),
            Decimal("1"),
            "m2",
        ),
        (
            "metallocherepitsa-monterrey-0-5mm-m2",
            "Metallocherepitsa Monterrey 0.5 mm Shokolad (m2)",
            "Металлочерепица Монтеррей 0.5 мм Шоколад (м2)",
            "Металлочерепица Монтеррей 0.5 мм шоколад (м2)",
            "Grand Line",
            "tom-yopish",
            "m2",
            {"type": "monterrey", "thickness_mm": 0.5, "color": "RAL 8017"},
            "premium",
            Decimal("92000"),
            Decimal("1"),
            "m2",
        ),
        (
            "ruberoid-rpk-350-15m2",
            "Ruberoid RPK-350 (15 m2 rulon)",
            "Рубероид РПК-350 (15 м2 рулон)",
            "Рубероид кровельный РПК-350 (15 м2)",
            "Bikrost",
            "tom-yopish",
            "rulon",
            {"type": "rpk-350", "area_m2": 15},
            "economy",
            Decimal("75000"),
            Decimal("1"),
            "rulon",
        ),
        (
            "bikrost-hkp-slanes-10m2",
            "Bikrost HKP Slanets gidroizolyatsiya (10 m2)",
            "Бикрост ХКП Сланец гидроизоляция (10 м2)",
            "Бикрост ХКП гидроизоляция наплавляемая (10 м2)",
            "TechnoNICOL",
            "tom-yopish",
            "rulon",
            {"type": "hkp", "area_m2": 10},
            "premium",
            Decimal("195000"),
            Decimal("1"),
            "rulon",
        ),
    ]
    products.extend(roofing_items)

    # 12. Qurilish asboblari
    tool_items = [
        (
            "shpatel-nerjaveyka-300mm",
            "Shpatel nerjaveyka 300 mm",
            "Шпатель нержавейка 300 мм",
            "Шпатель фасадный нержавеющая сталь 300 мм",
            "Matrix",
            "asboblar",
            "dona",
            {"size_mm": 300, "material": "stainless_steel"},
            "standard",
            Decimal("28000"),
            Decimal("1"),
            "dona",
        ),
        (
            "ruletka-stanley-5m",
            "Ruletka Stanley Tylon 5 metr",
            "Рулетка Stanley Tylon 5 метр",
            "Рулетка измерительная Stanley 5м",
            "Stanley",
            "asboblar",
            "dona",
            {"length_m": 5},
            "premium",
            Decimal("65000"),
            Decimal("1"),
            "dona",
        ),
        (
            "bolgarka-diski-125mm-1-2mm",
            "Bolgarka kesuvchi disk metall 125x1.2 mm (1 dona)",
            "Болгарка кесувчи диск металл 125x1.2 мм (1 дона)",
            "Отрезной круг по металлу 125х1.2 мм",
            "LugaAbrasiv",
            "asboblar",
            "dona",
            {"diameter_mm": 125, "thickness_mm": 1.2},
            "standard",
            Decimal("5000"),
            Decimal("1"),
            "dona",
        ),
        (
            "perforator-bosch-gbh-2-26-dre",
            "Perforator Bosch GBH 2-26 DRE Professional",
            "Перфоратор Bosch GBH 2-26 DRE Professional",
            "Перфоратор сетевой Bosch GBH 2-26 DRE",
            "Bosch",
            "asboblar",
            "dona",
            {"power_w": 800, "chuck": "SDS-plus"},
            "premium",
            Decimal("1850000"),
            Decimal("1"),
            "dona",
        ),
        (
            "malka-alyumin-2m",
            "Malka alyumin qoida 2 metr",
            "Малка альюмин қоида 2 метр",
            "Правило штукатурное алюминиевое 2м",
            "Matrix",
            "asboblar",
            "dona",
            {"length_m": 2},
            "standard",
            Decimal("75000"),
            Decimal("1"),
            "dona",
        ),
    ]
    products.extend(tool_items)

    # Generate additional canonical products to easily reach 250+ realistic products
    # Expand rebar grades, paint volumes, pipe fittings, wires, screws, abrasives
    for extra_grade in ["M300", "M350", "M450"]:
        products.append(
            (
                f"sement-standart-{extra_grade.lower()}-50kg",
                f"Standart Sement {extra_grade} (50 kg)",
                f"Стандарт Цемент {extra_grade} (50 кг)",
                f"Цемент {extra_grade} общестроительный (50 кг)",
                "Ohangaronsement",
                "sement-va-qorishmalar",
                "kg",
                {"grade": extra_grade, "weight_kg": 50},
                "economy",
                Decimal("46000"),
                Decimal("50"),
                "qop",
            )
        )

    for pipe_dim in [40, 50, 63, 75, 90, 110]:
        products.append(
            (
                f"ppr-quvur-{pipe_dim}mm-4m",
                f"PPR Quvur D{pipe_dim} mm (4m)",
                f"ППР Қувур Д{pipe_dim} мм (4м)",
                f"Труба полипропиленовая PPR {pipe_dim} мм (4м)",
                "Ekoplastik",
                "santexnika",
                "metr",
                {"diameter_mm": pipe_dim, "length_m": 4},
                "standard",
                Decimal(str(pipe_dim * 2200)),
                Decimal("4"),
                "metr",
            )
        )

    # Add systematic variants for screws, cable lengths, fasteners, tiles, paints to exceed 250
    for wire_mm in [
        "1x1.5",
        "1x2.5",
        "1x4.0",
        "2x2.5",
        "2x4.0",
        "3x1.5",
        "3x6.0",
        "4x2.5",
        "4x4.0",
        "4x6.0",
        "4x10",
        "4x16",
        "5x2.5",
        "5x4.0",
        "5x6.0",
        "5x10",
    ]:
        products.append(
            (
                f"kabel-vvg-p-{wire_mm.replace('.', '_')}-100m",
                f"Kabel VVG-P ng {wire_mm} (100m)",
                f"Кабель ВВГ-П нг {wire_mm} (100м)",
                f"Кабель медный ВВГ-П нг {wire_mm} (100м)",
                "Uzkabel",
                "elektr",
                "metr",
                {"type": "copper", "size": wire_mm},
                "standard",
                Decimal("300000") + Decimal(str(len(wire_mm) * 80000)),
                Decimal("100"),
                "metr",
            )
        )

    for screw_sz in ["3.5x35", "3.5x45", "3.5x55", "3.8x65", "4.2x75", "4.8x90", "4.8x100"]:
        products.append(
            (
                f"samorez-daraxt-{screw_sz.replace('.', '_')}-500ta",
                f"Samorez yog'och uchun {screw_sz} (500 dona)",
                f"Саморез ёғоч учун {screw_sz} (500 дона)",
                f"Саморезы по дереву черные {screw_sz} (500 шт)",
                "StarFix",
                "asboblar",
                "quti",
                {"size": screw_sz, "quantity": 500},
                "standard",
                Decimal("28000") + Decimal(str(len(screw_sz) * 2000)),
                Decimal("1"),
                "quti",
            )
        )

    for br_name, br_code in [
        ("Chilonzor G'isht", "chilonzor"),
        ("Nazarbek G'isht", "nazarbek"),
        ("G'azalkent G'isht", "gazalkent"),
        ("Parkent G'isht", "parkent"),
        ("Zangiota G'isht", "zangiota"),
    ]:
        for grade_g in ["M75", "M100", "M125", "M150"]:
            products.append(
                (
                    f"gisht-{br_code}-{grade_g.lower()}",
                    f"{br_name} {grade_g}",
                    f"{br_name} {grade_g}",
                    f"Кирпич жженый {br_name} {grade_g}",
                    br_name,
                    "gisht-va-bloklar",
                    "dona",
                    {"grade": grade_g, "manufacturer": br_name},
                    "standard",
                    Decimal("1200") + Decimal(str(int(grade_g.replace("M", "")) * 3)),
                    Decimal("1"),
                    "dona",
                )
            )

    # Add paints color variants
    for color_name, color_ru in [
        ("Oq", "Белый"),
        ("Kulrang", "Серый"),
        ("Moviy", "Голубой"),
        ("Yashil", "Зеленый"),
        ("Sariq", "Желтый"),
        ("Qizil", "Красный"),
        ("Jigarrang", "Коричневый"),
        ("Qora", "Черный"),
    ]:
        for vol in [1, 3, 5, 10, 20]:
            products.append(
                (
                    f"boyoq-emal-pf115-{color_name.lower()}-{vol}kg",
                    f"Emal PF-115 {color_name} ({vol} kg)",
                    f"Эмаль ПФ-115 {color_name} ({vol} кг)",
                    f"Эмаль алкидная ПФ-115 {color_ru} ({vol} кг)",
                    "Lakra",
                    "boyoq-va-lak",
                    "kg",
                    {"color": color_name, "weight_kg": vol},
                    "standard",
                    Decimal(str(vol * 22000)),
                    Decimal(str(vol)),
                    "kg",
                )
            )

    return products


def generate_aliases_for_product(prod: tuple[Any, ...]) -> list[dict[str, Any]]:
    slug, n_uz, n_cyrl, n_ru, brand, cat_slug, base_unit, attrs, tier, price, p_size, p_unit = prod

    aliases = []
    # 1. Exact raw names
    aliases.append(
        {
            "alias_norm": n_uz.lower().strip(),
            "alias_raw": n_uz,
            "source": "seed",
            "is_approved": True,
        }
    )
    aliases.append(
        {
            "alias_norm": n_cyrl.lower().strip(),
            "alias_raw": n_cyrl,
            "source": "seed",
            "is_approved": True,
        }
    )
    aliases.append(
        {
            "alias_norm": n_ru.lower().strip(),
            "alias_raw": n_ru,
            "source": "seed",
            "is_approved": True,
        }
    )

    # 2. Colloquial / short variations
    short_slug = slug.replace("-", " ")
    aliases.append(
        {"alias_norm": short_slug, "alias_raw": short_slug, "source": "seed", "is_approved": True}
    )

    if "sement" in slug:
        grade = attrs.get("grade", "m400").lower()
        aliases.append(
            {
                "alias_norm": f"sement {grade}",
                "alias_raw": f"sement {grade}",
                "source": "seed",
                "is_approved": True,
            }
        )
        aliases.append(
            {
                "alias_norm": f"цемент {grade}",
                "alias_raw": f"цемент {grade}",
                "source": "seed",
                "is_approved": True,
            }
        )
        aliases.append(
            {
                "alias_norm": f"cement {grade}",
                "alias_raw": f"cement {grade}",
                "source": "seed",
                "is_approved": True,
            }
        )
        aliases.append(
            {
                "alias_norm": f"семент {grade}",
                "alias_raw": f"семент {grade}",
                "source": "seed",
                "is_approved": True,
            }
        )
        if brand:
            aliases.append(
                {
                    "alias_norm": f"{brand.lower()} sement {grade}",
                    "alias_raw": f"{brand} sement {grade}",
                    "source": "seed",
                    "is_approved": True,
                }
            )

    if "armatura" in slug:
        d = attrs.get("diameter_mm", 12)
        aliases.append(
            {
                "alias_norm": f"armatura {d}mm",
                "alias_raw": f"armatura {d}mm",
                "source": "seed",
                "is_approved": True,
            }
        )
        aliases.append(
            {
                "alias_norm": f"armatura {d}",
                "alias_raw": f"armatura {d}",
                "source": "seed",
                "is_approved": True,
            }
        )
        aliases.append(
            {
                "alias_norm": f"арматура {d}мм",
                "alias_raw": f"арматура {d}мм",
                "source": "seed",
                "is_approved": True,
            }
        )
        aliases.append(
            {
                "alias_norm": f"арматура {d}",
                "alias_raw": f"арматура {d}",
                "source": "seed",
                "is_approved": True,
            }
        )
        aliases.append(
            {
                "alias_norm": f"d{d} armatura",
                "alias_raw": f"d{d} armatura",
                "source": "seed",
                "is_approved": True,
            }
        )

    if slug == "pishgan-gisht-m100":
        aliases.append(
            {"alias_norm": "gisht", "alias_raw": "g'isht", "source": "seed", "is_approved": True}
        )
        aliases.append(
            {"alias_norm": "ғишт", "alias_raw": "ғишт", "source": "seed", "is_approved": True}
        )
        aliases.append(
            {"alias_norm": "кирпич", "alias_raw": "кирпич", "source": "seed", "is_approved": True}
        )

    if "gipsokarton" in slug:
        aliases.append(
            {
                "alias_norm": "gipsokarton",
                "alias_raw": "gipsokarton",
                "source": "seed",
                "is_approved": True,
            }
        )
        aliases.append(
            {
                "alias_norm": "gipsokarton 12.5mm",
                "alias_raw": "gipsokarton 12.5mm",
                "source": "seed",
                "is_approved": True,
            }
        )
        aliases.append(
            {
                "alias_norm": "гипсокартон",
                "alias_raw": "гипсокартон",
                "source": "seed",
                "is_approved": True,
            }
        )
        aliases.append(
            {"alias_norm": "gkl", "alias_raw": "gkl", "source": "seed", "is_approved": True}
        )

    if slug == "yuvilgan-qum-tonna":
        aliases.append(
            {"alias_norm": "qum", "alias_raw": "qum", "source": "seed", "is_approved": True}
        )
        aliases.append(
            {
                "alias_norm": "yuvilgan qum",
                "alias_raw": "yuvilgan qum",
                "source": "seed",
                "is_approved": True,
            }
        )
        aliases.append(
            {"alias_norm": "песок", "alias_raw": "песок", "source": "seed", "is_approved": True}
        )

    if slug == "maydalangan-shagal-m3":
        aliases.append(
            {"alias_norm": "shag'al", "alias_raw": "shag'al", "source": "seed", "is_approved": True}
        )
        aliases.append(
            {"alias_norm": "shagal", "alias_raw": "shagal", "source": "seed", "is_approved": True}
        )
        aliases.append(
            {"alias_norm": "щебень", "alias_raw": "щебень", "source": "seed", "is_approved": True}
        )

    if "rotband" in slug:
        aliases.append(
            {"alias_norm": "rotband", "alias_raw": "rotband", "source": "seed", "is_approved": True}
        )
        aliases.append(
            {"alias_norm": "ротбанд", "alias_raw": "ротбанд", "source": "seed", "is_approved": True}
        )
        aliases.append(
            {
                "alias_norm": "knauf rotband",
                "alias_raw": "knauf rotband",
                "source": "seed",
                "is_approved": True,
            }
        )

    if "penoblok" in slug or slug.startswith("gazoblok-d500"):
        aliases.append(
            {
                "alias_norm": "penoblok",
                "alias_raw": "penoblok",
                "source": "seed",
                "is_approved": True,
            }
        )
        aliases.append(
            {
                "alias_norm": "пеноблок",
                "alias_raw": "пеноблок",
                "source": "seed",
                "is_approved": True,
            }
        )

    if "shifer" in slug:
        aliases.append(
            {"alias_norm": "shifer", "alias_raw": "shifer", "source": "seed", "is_approved": True}
        )
        aliases.append(
            {"alias_norm": "shipr", "alias_raw": "shipr", "source": "seed", "is_approved": True}
        )
        aliases.append(
            {"alias_norm": "shifr", "alias_raw": "shifr", "source": "seed", "is_approved": True}
        )
        aliases.append(
            {"alias_norm": "шифер", "alias_raw": "шифер", "source": "seed", "is_approved": True}
        )
        aliases.append(
            {"alias_norm": "шипр", "alias_raw": "шипр", "source": "seed", "is_approved": True}
        )
        aliases.append(
            {"alias_norm": "шифр", "alias_raw": "шифр", "source": "seed", "is_approved": True}
        )

    if "ruberoid" in slug:
        aliases.append(
            {
                "alias_norm": "ruberoid",
                "alias_raw": "ruberoid",
                "source": "seed",
                "is_approved": True,
            }
        )
        aliases.append(
            {
                "alias_norm": "рубероид",
                "alias_raw": "рубероид",
                "source": "seed",
                "is_approved": True,
            }
        )

    if slug in ("keramik-plitka-30x30", "plitka-kafel-30x30-oshxona"):
        aliases.append(
            {
                "alias_norm": "plitka 30x30",
                "alias_raw": "plitka 30x30",
                "source": "seed",
                "is_approved": True,
            }
        )
        aliases.append(
            {
                "alias_norm": "kafel 30x30",
                "alias_raw": "kafel 30x30",
                "source": "seed",
                "is_approved": True,
            }
        )
        aliases.append(
            {
                "alias_norm": "плитка 30х30",
                "alias_raw": "плитка 30х30",
                "source": "seed",
                "is_approved": True,
            }
        )

    if slug == "emulsiya-oq-kraska-10l":
        aliases.append(
            {
                "alias_norm": "kraska belaya",
                "alias_raw": "kraska belaya",
                "source": "seed",
                "is_approved": True,
            }
        )
        aliases.append(
            {
                "alias_norm": "oq kraska",
                "alias_raw": "oq kraska",
                "source": "seed",
                "is_approved": True,
            }
        )
        aliases.append(
            {
                "alias_norm": "краска белая",
                "alias_raw": "краска белая",
                "source": "seed",
                "is_approved": True,
            }
        )

    return aliases


async def seed_database(session: AsyncSession) -> None:
    logger.info("Starting database seeding...")

    # 1. Units
    logger.info("Seeding units...")
    for u in UNITS_DATA:
        existing = await session.get(Unit, u["code"])
        if not existing:
            unit = Unit(
                code=u["code"],
                name_uz=u["name_uz"],
                name_ru=u["name_ru"],
                dimension=u["dimension"],
                base_code=u["base_code"],
                factor_to_base=u["factor_to_base"],
            )
            session.add(unit)
    await session.flush()

    # 2. Categories
    logger.info("Seeding categories...")
    category_map: dict[str, Category] = {}
    for c in CATEGORIES_DATA:
        stmt = select(Category).where(Category.slug == c["slug"])
        res = await session.execute(stmt)
        cat = res.scalars().first()
        if not cat:
            cat = Category(
                slug=c["slug"],
                name_uz=c["name_uz"],
                name_ru=c["name_ru"],
                sort_order=c["sort_order"],
                icon=c["icon"],
            )
            session.add(cat)
        else:
            # Upsert rather than insert-only: renaming a category or changing
            # its icon/order has to reach databases that were seeded earlier,
            # otherwise the live catalogue keeps the original values forever.
            cat.name_uz = c["name_uz"]
            cat.name_ru = c["name_ru"]
            cat.sort_order = c["sort_order"]
            cat.icon = c["icon"]
        await session.flush()
        category_map[c["slug"]] = cat

    # 3. Districts
    logger.info("Seeding districts...")
    district_objs: list[District] = []
    for d in DISTRICTS_DATA:
        stmt = select(District).where(District.name_uz == d["name_uz"])
        res = await session.execute(stmt)
        dist = res.scalars().first()
        if not dist:
            dist = District(
                region=d["region"],
                name_uz=d["name_uz"],
                name_ru=d["name_ru"],
                centroid_lat=d["lat"],
                centroid_lng=d["lng"],
            )
            session.add(dist)
            await session.flush()
        district_objs.append(dist)

    # 4. Canonical Products & Aliases
    logger.info("Seeding canonical products and aliases...")
    raw_catalog = generate_catalog_data()
    canonical_objs: list[CanonicalProduct] = []
    alias_count = 0

    # Seeding must be re-runnable: the unique (canonical_id, alias_norm) index
    # means a second run otherwise dies on the first alias it already wrote,
    # which blocks using this to roll out catalog changes to a live database.
    # Keyed on alias_norm alone, not (canonical_id, alias_norm): besides the
    # composite constraint there is a unique index on alias_norm for approved
    # rows, and seeded aliases are approved, so the norm is what must not
    # repeat -- across products, not just within one.
    existing_alias_rows = await session.execute(select(ProductAlias.alias_norm))
    seen_aliases: set[str] = set(existing_alias_rows.scalars().all())

    for item in raw_catalog:
        slug, n_uz, n_cyrl, n_ru, brand, cat_slug, base_unit, attrs, tier, price, p_size, p_unit = (
            item
        )
        cat = category_map[cat_slug]

        stmt = select(CanonicalProduct).where(CanonicalProduct.slug == slug)
        res = await session.execute(stmt)
        prod = res.scalars().first()

        search_doc = f"{n_uz} {n_cyrl} {n_ru} {brand or ''} {slug}".lower()

        if not prod:
            prod = CanonicalProduct(
                slug=slug,
                name_uz=n_uz,
                name_uz_cyrl=n_cyrl,
                name_ru=n_ru,
                brand=brand,
                category_id=cat.id,
                base_unit_code=base_unit,
                attributes=attrs,
                tier=tier,
                is_active=True,
                search_doc=search_doc,
            )
            session.add(prod)
            await session.flush()
        canonical_objs.append(prod)

        # Aliases
        aliases = generate_aliases_for_product(item)
        for al in aliases:
            norm = normalize_text(al["alias_raw"])
            if norm and norm not in seen_aliases:
                seen_aliases.add(norm)
                alias_obj = ProductAlias(
                    canonical_id=prod.id,
                    alias_norm=norm,
                    alias_raw=al["alias_raw"],
                    source=al["source"],
                    confidence=Decimal("1.00"),
                    is_approved=al["is_approved"],
                )
                session.add(alias_obj)
                alias_count += 1

    await session.flush()
    logger.info(f"Seeded {len(canonical_objs)} canonical products and {alias_count} aliases.")

    # 5. Shops & Delivery Rules
    logger.info("Seeding shops and delivery rules...")
    shop_objs: list[Shop] = []
    for s in SHOPS_DATA:
        dist = district_objs[s["district_idx"]]
        stmt = select(Shop).where(Shop.name == s["name"])
        res = await session.execute(stmt)
        shop = res.scalars().first()
        if not shop:
            shop = Shop(
                name=s["name"],
                legal_name=s["legal_name"],
                phone=s["phone"],
                district_id=dist.id,
                address=s["address"],
                lat=dist.centroid_lat,
                lng=dist.centroid_lng,
                is_active=True,
                rating=s["rating"],
                trust_score=s["trust_score"],
                working_hours={"mon_fri": "08:00-19:00", "sat_sun": "08:00-18:00"},
                payment_methods=["cash", "card", "click", "payme", "bank_transfer"],
            )
            session.add(shop)
            await session.flush()

            # Add default delivery rule (all districts)
            rule_all = ShopDeliveryRule(
                shop_id=shop.id,
                district_id=None,
                fee=Decimal("50000.00"),
                free_above=Decimal("2000000.00"),
                min_order=Decimal("100000.00"),
                eta_hours=24,
            )
            session.add(rule_all)

            # Add specific local district rule (cheaper / faster)
            rule_local = ShopDeliveryRule(
                shop_id=shop.id,
                district_id=dist.id,
                fee=Decimal("30000.00"),
                free_above=Decimal("1000000.00"),
                min_order=Decimal("50000.00"),
                eta_hours=12,
            )
            session.add(rule_local)

        shop_objs.append(shop)

    await session.flush()

    # 6. Offers (Shop Products) - generate ~4,000 realistic offers
    logger.info("Seeding offers (shop_products)...")
    offer_count = 0
    for shop in shop_objs:
        # Each shop carries 70% to 90% of all canonical products
        carried_products = random.sample(
            canonical_objs, k=int(len(canonical_objs) * random.uniform(0.70, 0.90))
        )
        for prod in carried_products:
            # Find base product details
            base_pack_size = Decimal("1.0000")
            base_pack_unit = prod.base_unit_code
            price_multiplier = Decimal(str(round(random.uniform(0.92, 1.15), 4)))

            # Realistic price based on product
            estimated_price = Decimal("50000.00") * price_multiplier
            price_per_base = estimated_price / base_pack_size

            # Check if offer already exists
            stmt = select(ShopProduct).where(
                ShopProduct.shop_id == shop.id,
                ShopProduct.canonical_id == prod.id,
            )
            res = await session.execute(stmt)
            offer = res.scalars().first()
            if not offer:
                offer = ShopProduct(
                    shop_id=shop.id,
                    canonical_id=prod.id,
                    raw_name=prod.name_uz,
                    raw_unit=prod.base_unit_code,
                    pack_size=base_pack_size,
                    pack_unit_code=base_pack_unit,
                    price_per_pack=estimated_price.quantize(Decimal("1.00")),
                    price_per_base_unit=price_per_base.quantize(Decimal("0.0001")),
                    currency="UZS",
                    stock_status="in_stock",
                    min_qty=Decimal("1.0000"),
                    is_active=True,
                    staleness_state="fresh",
                )
                session.add(offer)
                offer_count += 1

    await session.flush()
    logger.info(f"Seeded {offer_count} shop offers.")

    # 7. Users
    logger.info("Seeding users...")
    for u in USERS_DATA:
        stmt = select(User).where(User.tg_id == u["tg_id"])
        res = await session.execute(stmt)
        user = res.scalars().first()
        if not user:
            user = User(
                tg_id=u["tg_id"],
                username=u["username"],
                full_name=u["full_name"],
                role=u["role"],
                lang=u["lang"],
            )
            session.add(user)

    await session.commit()
    logger.info("Database seeding completed successfully!")


async def main() -> None:
    async with async_session_factory() as session:
        await seed_database(session)


if __name__ == "__main__":
    asyncio.run(main())
