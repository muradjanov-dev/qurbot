"""Deterministic database seeding script for QurBot (Tashkent construction catalog).

The catalogue is transcribed from supplier price lists -- currently fanera.uz
(sheet goods: plywood, OSB-3, HDF, DVP, DSP). Every product carries the source
it came from and that supplier's list price, so an operator can tell a real row
from a placeholder. Re-running the script republishes prices onto the rows that
already exist, which is how a new price list is rolled out.

Seeds:
- 9 Units
- 20 Standard Categories
- Canonical Products + search aliases (Uzbek Latin, Uzbek Cyrillic, Russian)
- 13 Districts (Tashkent City + Region)
- Demo market (shops, offers, sample users) -- skipped by `--catalog-only`,
  which is what deploys run
"""

import asyncio
import logging
import random
import re
import sys
from dataclasses import dataclass
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
    ShopProductPriceTier,
    Unit,
    User,
)
from app.db.session import async_session_factory
from app.domain.normalize.text import normalize_query, normalize_text

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
    # The fastener list prices some rows per box and others per pack, and
    # charges differently for the two, so they cannot share a unit.
    {
        "code": "pachka",
        "name_uz": "Pachka",
        "name_ru": "Пачка",
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
        "slug": "plita-va-fanera",
        "name_uz": "Fanera, MDF, DSP va boshqa plitalar",
        "name_ru": "Фанера, МДФ, ДСП и другие плиты",
        "sort_order": 21,
        "icon": "🪚",
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
        "name_uz": "Zangiota tumani",
        "name_ru": "Зангиатинский район",
        "lat": Decimal("41.2136"),
        "lng": Decimal("69.1067"),
    },
    {
        "region": "Toshkent viloyati",
        "name_uz": "Qibray tumani",
        "name_ru": "Кибрайский район",
        "lat": Decimal("41.3906"),
        "lng": Decimal("69.4744"),
    },
    {
        "region": "Toshkent viloyati",
        "name_uz": "Yangiyo'l tumani",
        "name_ru": "Янгиюльский район",
        # The district centre, deliberately apart from the town's own row: two
        # identical centroids make the nearest-point match a coin toss.
        "lat": Decimal("41.0906"),
        "lng": Decimal("69.0186"),
    },
    {
        "region": "Toshkent viloyati",
        "name_uz": "Chirchiq shahri",
        "name_ru": "город Чирчик",
        "lat": Decimal("41.4689"),
        "lng": Decimal("69.5822"),
    },
    {
        "region": "Toshkent viloyati",
        "name_uz": "Olmaliq shahri",
        "name_ru": "город Алмалык",
        "lat": Decimal("40.8447"),
        "lng": Decimal("69.5983"),
    },
    {
        "region": "Toshkent viloyati",
        "name_uz": "Ohangaron tumani",
        "name_ru": "Ахангаранский район",
        "lat": Decimal("40.9167"),
        "lng": Decimal("69.6353"),
    },
    {
        "region": "Toshkent viloyati",
        "name_uz": "Bekobod tumani",
        "name_ru": "Бекабадский район",
        "lat": Decimal("40.2206"),
        "lng": Decimal("69.2694"),
    },
    {
        "region": "Toshkent viloyati",
        "name_uz": "Parkent tumani",
        "name_ru": "Паркентский район",
        "lat": Decimal("41.2939"),
        "lng": Decimal("69.6767"),
    },
    {
        "region": "Toshkent viloyati",
        "name_uz": "Piskent tumani",
        "name_ru": "Пскентский район",
        "lat": Decimal("40.8925"),
        "lng": Decimal("69.3419"),
    },
    {
        "region": "Toshkent viloyati",
        "name_uz": "Bo'ka tumani",
        "name_ru": "Букинский район",
        "lat": Decimal("40.8114"),
        "lng": Decimal("69.2036"),
    },
    {
        "region": "Toshkent viloyati",
        "name_uz": "Bo'stonliq tumani",
        "name_ru": "Бостанлыкский район",
        "lat": Decimal("41.5583"),
        "lng": Decimal("69.7708"),
    },
    {
        "region": "Toshkent viloyati",
        "name_uz": "Quyi Chirchiq tumani",
        "name_ru": "Куйичирчикский район",
        "lat": Decimal("40.9803"),
        "lng": Decimal("69.4553"),
    },
    {
        "region": "Toshkent viloyati",
        "name_uz": "O'rta Chirchiq tumani",
        "name_ru": "Уртачирчикский район",
        "lat": Decimal("41.0311"),
        "lng": Decimal("69.3564"),
    },
    {
        "region": "Toshkent viloyati",
        "name_uz": "Yuqori Chirchiq tumani",
        "name_ru": "Юкоричирчикский район",
        "lat": Decimal("41.1900"),
        "lng": Decimal("69.6100"),
    },
    {
        "region": "Toshkent viloyati",
        "name_uz": "Toshkent tumani",
        "name_ru": "Ташкентский район",
        "lat": Decimal("41.1503"),
        "lng": Decimal("69.3986"),
    },
    {
        "region": "Toshkent viloyati",
        "name_uz": "Nurafshon shahri",
        "name_ru": "город Нурафшан",
        "lat": Decimal("40.9908"),
        "lng": Decimal("69.3492"),
    },
    {
        "region": "Toshkent viloyati",
        "name_uz": "Chinoz tumani",
        "name_ru": "Чиназский район",
        "lat": Decimal("40.9367"),
        "lng": Decimal("68.7681"),
    },
    {
        "region": "Toshkent viloyati",
        "name_uz": "Oqqo'rg'on tumani",
        "name_ru": "Аккурганский район",
        "lat": Decimal("40.8892"),
        "lng": Decimal("69.0322"),
    },
    {
        "region": "Toshkent viloyati",
        "name_uz": "Yangiyo'l shahri",
        "name_ru": "город Янгиюль",
        "lat": Decimal("41.1128"),
        "lng": Decimal("69.0464"),
    },
    {
        "region": "Toshkent viloyati",
        "name_uz": "Angren shahri",
        "name_ru": "город Ангрен",
        "lat": Decimal("41.0167"),
        "lng": Decimal("70.1436"),
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


# --- 6. Catalogue -------------------------------------------------------
# The catalogue is transcribed from supplier price lists, one section per
# list. Nothing here is invented: a row exists because a supplier published
# it, and `reference_price` is None wherever the list says "Kelishiladi"
# (negotiable) rather than a number. None is not zero -- a zero would win
# every optimiser comparison it took part in.
#
# Held back from the fanera.uz list until the supplier confirms the printed
# values, because transcribing them faithfully would put a product in the
# catalogue that cannot exist:
#
#   * Section 5, DSP (4 rows) -- thickness printed as "1.6" on every row, at
#     2750x1830 and 3500x1750. A 1.6 mm sheet that size is not a product;
#     16 mm is the standard, but guessing that is not transcription.
#   * Section 3, HDF "Oq" 2800x2071 -- the other two HDF rows say 2070.
#
# Re-add them here once confirmed; nothing else in the pipeline needs to know.


@dataclass(frozen=True)
class CatalogItem:
    """One catalogue row, as published by a supplier."""

    slug: str
    name_uz: str
    name_uz_cyrl: str
    name_ru: str
    brand: str | None
    category_slug: str
    base_unit: str
    attributes: dict[str, Any]
    tier: str
    reference_price: Decimal | None
    pack_size: Decimal
    pack_unit: str
    source: str
    source_ref: str | None


SOURCE_SUPPLIER = "supplier"
FANERA_UZ = "fanera.uz"

# Sheet goods are sold and quoted per sheet, so the unit is `dona` and the
# dimensions live in attributes -- thickness and size are what buyers name.
_SHEET_CATEGORY = "plita-va-fanera"
_SHEET_UNIT = "dona"


def _cyr_size(size: str) -> str:
    """Swap the Latin x for the Cyrillic kha, as the price lists write it."""
    return size.replace("x", "х")


def _slug_num(value: str) -> str:
    """Turn 6.5 into 6-5, so a thickness stays readable inside a slug."""
    return value.replace(".", "-")


def _thickness(value: str) -> float | int:
    number = float(value)
    return int(number) if number.is_integer() else number


def _sheet_item(
    slug: str,
    name_uz: str,
    name_uz_cyrl: str,
    name_ru: str,
    *,
    brand: str | None,
    attributes: dict[str, Any],
    tier: str,
    reference_price: Decimal | None,
) -> CatalogItem:
    return CatalogItem(
        slug=slug,
        name_uz=name_uz,
        name_uz_cyrl=name_uz_cyrl,
        name_ru=name_ru,
        brand=brand,
        category_slug=_SHEET_CATEGORY,
        base_unit=_SHEET_UNIT,
        attributes=attributes,
        tier=tier,
        reference_price=reference_price,
        pack_size=Decimal("1"),
        pack_unit=_SHEET_UNIT,
        source=SOURCE_SUPPLIER,
        source_ref=FANERA_UZ,
    )


# fanera.uz section 1 -- laminated plywood, all 2440x1220x18.
# (slug part, brand, origin uz, origin ru, price)
_LAMINATED_PLYWOOD: list[tuple[str, str | None, str, str, Decimal | None]] = [
    ("sibply", "SibPly", "Rossiya", "Россия", Decimal("423000")),
    ("siyply", "SiyPly", "Rossiya", "Россия", None),
    (
        "murashinsky",
        "Murashinsky",
        "Rossiya",
        "Россия",
        Decimal("435000"),
    ),
    ("segezha", "SEGEZHA", "Rossiya", "Россия", Decimal("423000")),
    ("xitoy", None, "Xitoy", "Китай", None),
]

# fanera.uz section 2 -- birch plywood. Grade ("navli") is part of the SKU
# because the list prices the same thickness differently per grade: 3 mm is
# 54 000 at 2x4, 52 000 at 3x3 and 48 000 at 4x4.
# (size, grade, thickness mm, price)
_BIRCH_PLYWOOD: list[tuple[str, str, str, Decimal | None]] = [
    ("1525x1525", "2x4", "3", Decimal("54000")),
    ("1525x1525", "2x4", "4", Decimal("68000")),
    ("1525x1525", "3x3", "3", Decimal("52000")),
    ("1525x1525", "3x3", "4", Decimal("65000")),
    ("1525x1525", "3x3", "5", Decimal("82000")),
    ("1525x1525", "3x3", "6", Decimal("97000")),
    ("1525x1525", "3x3", "8", Decimal("121000")),
    ("1525x1525", "3x3", "10", Decimal("151000")),
    ("1525x1525", "3x3", "12", Decimal("157000")),
    ("1525x1525", "3x3", "15", Decimal("212000")),
    ("1525x1525", "3x3", "18", Decimal("254000")),
    ("1525x1525", "3x3", "21", Decimal("296000")),
    ("1525x1525", "4x4", "3", Decimal("48000")),
    ("1525x1525", "4x4", "4", Decimal("60000")),
    ("1525x1525", "3x3", "14", None),
    ("1525x1525", "3x3", "30", None),
    ("1525x1525", "4x4", "14", Decimal("194000")),
    ("2440x1220", "2x4", "3", None),
    ("2440x1220", "2x4", "4", Decimal("121000")),
    ("2440x1220", "2x4", "5", None),
    ("2440x1220", "2x4", "6", Decimal("163000")),
    ("2440x1220", "2x4", "6.5", None),
    ("2440x1220", "2x4", "8", None),
    ("2440x1220", "2x4", "9", Decimal("230000")),
    ("2440x1220", "2x4", "10", None),
    ("2440x1220", "2x4", "12", Decimal("278000")),
    ("2440x1220", "2x4", "15", Decimal("315000")),
    ("2440x1220", "2x4", "18", Decimal("363000")),
    ("2440x1220", "2x4", "21", Decimal("448000")),
    ("2440x1220", "2x4", "24", None),
    ("2440x1220", "2x4", "27", None),
    ("2440x1220", "2x4", "30", None),
]

# fanera.uz section 3 -- HDF and DVP. The list writes thickness as "2.5 (3)":
# the nominal sheet is 2.5 mm and the trade name is 3 mm, so both are kept.
# (slug, uz, cyrl, ru, brand, size, nominal mm, trade mm, material, price)
_HARDBOARDS: list[tuple[str, str, str, str, str | None, str, str, str, str, Decimal | None]] = [
    (
        "hdf-kronospan-2-5mm-2440x1830",
        "HDF plita Kronospan 2.5 mm (2440x1830)",
        "ХДФ плита Kronospan 2.5 мм (2440х1830)",
        "ХДФ плита Kronospan 2.5 мм (2440х1830)",
        "Kronospan",
        "2440x1830",
        "2.5",
        "3",
        "hdf",
        None,
    ),
    (
        "hdf-kronospan-3-2mm-2800x2070",
        "HDF plita Kronospan 3.2 mm (2800x2070)",
        "ХДФ плита Kronospan 3.2 мм (2800х2070)",
        "ХДФ плита Kronospan 3.2 мм (2800х2070)",
        "Kronospan",
        "2800x2070",
        "3.2",
        "4",
        "hdf",
        None,
    ),
    (
        "dvp-t-2-5mm-2745x1700",
        "DVP plita (T markasi) 2.5 mm (2745x1700)",
        "ДВП плита (Т маркаси) 2.5 мм (2745х1700)",
        "ДВП плита (марка Т) 2.5 мм (2745х1700)",
        None,
        "2745x1700",
        "2.5",
        "3",
        "hardboard",
        Decimal("60000"),
    ),
    (
        "dvp-t-3-2mm-2745x1700",
        "DVP plita (T markasi) 3.2 mm (2745x1700)",
        "ДВП плита (Т маркаси) 3.2 мм (2745х1700)",
        "ДВП плита (марка Т) 3.2 мм (2745х1700)",
        None,
        "2745x1700",
        "3.2",
        "4",
        "hardboard",
        Decimal("65000"),
    ),
]

# fanera.uz section 4 -- OSB-3, all 2500x1250. (thickness mm, price)
_OSB3: list[tuple[str, Decimal | None]] = [
    ("6", Decimal("109000")),
    ("8", Decimal("116000")),
    ("9", Decimal("118000")),
    ("12", Decimal("155000")),
    ("15", Decimal("194000")),
    ("18", Decimal("230000")),
    ("21", None),
]


def _laminated_plywood_items() -> list[CatalogItem]:
    size, thickness = "2440x1220", "18"
    items = []
    for slug_part, brand, origin_uz, origin_ru, price in _LAMINATED_PLYWOOD:
        label_uz = f" {brand}" if brand else f" ({origin_uz})"
        label_ru = f" {brand}" if brand else f" ({origin_ru})"
        items.append(
            _sheet_item(
                f"fanera-laminat-{slug_part}-{thickness}mm-{size}",
                f"Fanera laminatsiyalangan{label_uz} {thickness} mm ({size})",
                f"Фанера ламинатсияланган{label_ru} {thickness} мм ({_cyr_size(size)})",
                f"Фанера ламинированная{label_ru} {thickness} мм ({_cyr_size(size)})",
                brand=brand,
                attributes={
                    "thickness_mm": _thickness(thickness),
                    "size": size,
                    "material": "laminated_plywood",
                },
                tier="premium",
                reference_price=price,
            )
        )
    return items


def _birch_plywood_items() -> list[CatalogItem]:
    items = []
    for size, grade, thickness, price in _BIRCH_PLYWOOD:
        items.append(
            _sheet_item(
                f"fanera-bereza-{grade}-{_slug_num(thickness)}mm-{size}",
                f"Fanera berezovaya {grade} {thickness} mm ({size})",
                f"Фанера березовая {_cyr_size(grade)} {thickness} мм ({_cyr_size(size)})",
                f"Фанера березовая {_cyr_size(grade)} {thickness} мм ({_cyr_size(size)})",
                brand=None,
                attributes={
                    "thickness_mm": _thickness(thickness),
                    "size": size,
                    "material": "birch_plywood",
                    "grade": grade,
                },
                tier="standard",
                reference_price=price,
            )
        )
    return items


def _hardboard_items() -> list[CatalogItem]:
    items = []
    for slug, uz, cyrl, ru, brand, size, nominal, trade, material, price in _HARDBOARDS:
        items.append(
            _sheet_item(
                slug,
                uz,
                cyrl,
                ru,
                brand=brand,
                attributes={
                    "thickness_mm": _thickness(nominal),
                    "thickness_trade_mm": _thickness(trade),
                    "size": size,
                    "material": material,
                },
                tier="economy",
                reference_price=price,
            )
        )
    return items


def _osb3_items() -> list[CatalogItem]:
    size = "2500x1250"
    items = []
    for thickness, price in _OSB3:
        items.append(
            _sheet_item(
                f"osb3-{_slug_num(thickness)}mm-{size}",
                f"OSB-3 plita {thickness} mm ({size})",
                f"ОСБ-3 плита {thickness} мм ({_cyr_size(size)})",
                f"ОСБ-3 плита {thickness} мм ({_cyr_size(size)})",
                brand=None,
                attributes={
                    "thickness_mm": _thickness(thickness),
                    "size": size,
                    "material": "osb3",
                },
                tier="standard",
                reference_price=price,
            )
        )
    return items


# Sawn timber, transcribed from the wagon manifests. Every board is 6 m long,
# so the SKU is thickness x width; the volume of one board comes out of those
# three numbers and is carried as an attribute, because timber is bought by the
# cubic metre as often as by the piece.
#
# (thickness mm, width mm, grade or None, species or None)
_TIMBER: list[tuple[int, int, str | None, str | None]] = [
    (17, 110, "3/4", None),
    (17, 140, "3/4", None),
    (20, 90, None, None),
    (20, 108, None, None),
    (20, 110, None, None),
    (20, 135, None, None),
    (20, 140, None, None),
    (20, 170, None, None),
    (31, 108, None, None),
    (31, 135, None, None),
    (31, 165, None, None),
    (31, 185, None, None),
    (35, 108, None, None),
    (35, 135, None, None),
    (35, 165, None, None),
    (35, 185, None, None),
    (37, 108, None, None),
    (37, 135, None, None),
    (37, 165, None, None),
    (37, 185, None, None),
    (38, 108, None, None),
    (38, 138, None, None),
    (38, 168, None, None),
    (38, 188, None, None),
    (42, 108, None, None),
    (42, 135, None, None),
    (42, 165, None, None),
    (42, 185, None, None),
    (45, 140, None, "listvennitsa"),
    (45, 170, None, "listvennitsa"),
    (45, 190, None, "listvennitsa"),
]

_TIMBER_LENGTH_MM = 6000
_TIMBER_CATEGORY = "yogoch"


def _timber_items() -> list[CatalogItem]:
    """One SKU per section, priced on request until the price list arrives."""
    items: list[CatalogItem] = []
    for thickness, width, grade, species in _TIMBER:
        volume_m3 = round(thickness / 1000 * width / 1000 * _TIMBER_LENGTH_MM / 1000, 5)
        label = f"{thickness}x{width}x{_TIMBER_LENGTH_MM} mm"
        species_uz = " listvennitsa" if species else ""
        species_ru = " лиственница" if species else ""
        grade_part = f" {grade} sort" if grade else ""
        grade_part_ru = f" {grade} сорт" if grade else ""

        attributes: dict[str, Any] = {
            "thickness_mm": thickness,
            "width_mm": width,
            "length_mm": _TIMBER_LENGTH_MM,
            "volume_m3": volume_m3,
            "material": "timber",
        }
        if grade:
            attributes["grade"] = grade
        if species:
            attributes["species"] = species

        slug_species = f"-{species}" if species else ""
        slug_grade = f"-{grade.replace('/', '-')}" if grade else ""
        items.append(
            CatalogItem(
                slug=f"taxta{slug_species}{slug_grade}-{thickness}x{width}x{_TIMBER_LENGTH_MM}",
                name_uz=f"Taxta{species_uz} {label}{grade_part}",
                name_uz_cyrl=f"Тахта{species_uz} {label}{grade_part}",
                name_ru=f"Доска{species_ru} {label}{grade_part_ru}",
                brand=None,
                category_slug=_TIMBER_CATEGORY,
                base_unit="dona",
                attributes=attributes,
                tier="standard",
                # Priced on request: the manifests carry dimensions and counts,
                # not money. NULL is what makes the catalogue say "kelishiladi"
                # rather than quote a number nobody agreed to.
                reference_price=None,
                pack_size=Decimal("1"),
                pack_unit="dona",
                source=SOURCE_SUPPLIER,
                source_ref="vagon",
            )
        )
    return items


# Metiz -- the fastener price list: samorez, anker, mix, bolt, gayka and the
# rest. Transcribed from the supplier's four-page prays.
#
# Three things about this list shape the code below.
#
# * **The unit is part of the price.** The same trade sells by the piece, by
#   the kilo, by the box and by the pack, and which one a row uses is not
#   guessable from the product -- kровельный saмorez is quoted per box in one
#   block and per kilo in the next. So the unit travels with the block.
# * **A row often names a size range, not a size.** "4.2x13-76" and
#   "3x13-16-20-25" are one price covering every size in between; that range is
#   the product, not a row we failed to split. It is kept verbatim, and the
#   sizes it names are expanded into aliases so a customer asking for one of
#   them lands on it.
# * **The names are written the way the list writes them**, in the mixed
#   Russian-Uzbek of the trade. What a customer types instead ("sarik" for
#   "sariq", "shurup" for "samorez") is handled once in the slang table, not
#   duplicated here.
_METIZ_CATEGORY = "mahkamlash-materiallari"
_METIZ_SOURCE_REF = "metiz-prays"


@dataclass(frozen=True)
class MetizGroup:
    """One titled block of the fastener price list.

    `rows` are (size label, price in dollars) exactly as printed. `keywords`
    are what a customer types for this family -- already transliterated and
    de-slanged, because that is the form an alias has to be in to be found.
    """

    key: str
    name_uz: str
    name_uz_cyrl: str
    name_ru: str
    unit: str
    keywords: tuple[str, ...]
    rows: tuple[tuple[str, str], ...]
    brand: str | None = None


_METIZ: list[MetizGroup] = [
    MetizGroup(
        key="oq-anker",
        name_uz="Oq anker",
        name_uz_cyrl="Оқ анкер",
        name_ru="Анкер белый",
        unit="dona",
        keywords=("oq anker", "ok anker", "anker oq"),
        rows=(
            ("10x72", "0.072"),
            ("10x92", "0.084"),
            ("10x112", "0.096"),
            ("10x132", "0.108"),
            ("10x152", "0.132"),
            ("10x182", "0.156"),
            ("10x202", "0.174"),
        ),
    ),
    MetizGroup(
        key="sariq-anker",
        name_uz="Sariq anker",
        name_uz_cyrl="Сариқ анкер",
        name_ru="Анкер жёлтый",
        unit="dona",
        keywords=("sariq anker", "anker sariq"),
        rows=(
            ("8x40", "0.0396"),
            ("8x60", "0.0636"),
            ("8x80", "0.072"),
            ("8x100", "0.0804"),
            ("10x40", "0.078"),
            ("10x60", "0.0936"),
            ("10x80", "0.1056"),
            ("10x100", "0.12"),
            ("10x120", "0.156"),
            ("10x150", "0.18"),
            ("12x60", "0.15"),
            ("12x80", "0.168"),
            ("12x100", "0.18"),
            ("12x120", "0.216"),
            ("12x150", "0.288"),
            ("12x200", "0.456"),
            ("14x100", "0.288"),
            ("14x120", "0.348"),
            ("14x150", "0.456"),
            ("14x200", "0.576"),
            ("16x100", "0.42"),
            ("16x120", "0.54"),
            ("16x150", "0.648"),
            ("16x200", "0.756"),
            ("16x250", "1.104"),
            ("20x100", "0.864"),
            ("20x120", "0.912"),
            ("20x150", "0.996"),
            ("20x200", "1.26"),
            ("20x250", "1.5"),
            ("20x300", "2.22"),
            ("24x150", "1.92"),
            ("24x200", "2.4"),
            ("24x250", "3"),
        ),
    ),
    MetizGroup(
        key="anker-klin",
        name_uz="Anker klin",
        name_uz_cyrl="Анкер клин",
        name_ru="Анкер клин",
        unit="dona",
        keywords=("anker klin", "klin anker"),
        rows=(
            ("6x40", "0.0312"),
            ("6x60", "0.0444"),
        ),
    ),
    MetizGroup(
        key="mufta-soedinitel",
        name_uz="Mufta (biriktiruvchi)",
        name_uz_cyrl="Муфта (бириктирувчи)",
        name_ru="Муфта соединительная",
        unit="dona",
        keywords=("mufta", "mufta soedinitel", "soedinitel mufta"),
        rows=(
            ("6", "0.0324"),
            ("8", "0.0528"),
            ("10", "0.0684"),
            ("12", "0.132"),
        ),
    ),
    MetizGroup(
        key="medved-montajniy",
        name_uz="Medved montajniy",
        name_uz_cyrl="Медведь монтажний",
        name_ru="Медведь монтажный",
        unit="kg",
        keywords=("medved", "medved montajniy", "montajniy medved"),
        rows=(("7.5x72-202", "2.34"),),
    ),
    MetizGroup(
        key="krovelniy-samorez-rangli",
        name_uz="Krovelniy samorez rangli",
        name_uz_cyrl="Кровелний саморез рангли",
        name_ru="Кровельный саморез цветной",
        unit="quti",
        keywords=("krovelniy samorez rangli", "rangli samorez", "krovelniy rangli"),
        rows=(
            ("4.8x25", "93.6"),
            ("4.8x32", "99.6"),
            ("4.8x40", "90"),
            ("4.8x50", "73.2"),
            ("4.8x60", "73.2"),
            ("4.8x70", "73.2"),
        ),
    ),
    MetizGroup(
        key="krovelniy-sariq-metallga",
        name_uz="Krovelniy sariq (metallga)",
        name_uz_cyrl="Кровелний сариқ (металлга)",
        name_ru="Кровельный жёлтый (по металлу)",
        unit="kg",
        keywords=("krovelniy sariq", "sariq krovelniy", "krovelniy metallga"),
        rows=(("5.5x20-180", "2.34"),),
    ),
    MetizGroup(
        key="krovelniy-samorez-oq-kg",
        name_uz="Krovelniy samorez oq",
        name_uz_cyrl="Кровелний саморез оқ",
        name_ru="Кровельный саморез белый",
        unit="kg",
        keywords=(
            "krovelniy samorez oq",
            "krovelniy samorez ok",
            "oq krovelniy samorez",
            "samorez krovelniy oq",
        ),
        rows=(("6.3x25-200", "2.88"),),
    ),
    MetizGroup(
        key="krovelniy-samorez-oq",
        name_uz="Krovelniy samorez oq",
        name_uz_cyrl="Кровелний саморез оқ",
        name_ru="Кровельный саморез белый",
        unit="quti",
        keywords=(
            "krovelniy samorez oq",
            "krovelniy samorez ok",
            "oq krovelniy samorez",
            "samorez krovelniy oq",
        ),
        rows=(
            ("4.8x25", "84"),
            ("4.8x32", "93.6"),
            ("4.8x40", "85.2"),
            ("4.8x50", "67.2"),
            ("4.8x60", "72"),
            ("4.8x70", "69.6"),
        ),
    ),
    MetizGroup(
        key="qora-samorez-goldvalley",
        name_uz="Qora samorez Goldvalley",
        name_uz_cyrl="Қора саморез Голдваллей",
        name_ru="Саморез чёрный Goldvalley",
        unit="kg",
        keywords=("samorez goldvalley", "qora samorez goldvalley", "goldvalley samorez"),
        brand="Goldvalley",
        rows=(
            ("16-19", "2.4"),
            ("25-100", "2.1"),
        ),
    ),
    MetizGroup(
        key="dyubel-gvozd",
        name_uz="Dyubel-gvozd",
        name_uz_cyrl="Дюбел-гвозд",
        name_ru="Дюбель-гвоздь",
        unit="kg",
        keywords=("dyubel gvozd", "dyubel mix", "dyubel", "gvozd dyubel"),
        rows=(
            ("6x40", "2.22"),
            ("6x60", "2.22"),
            ("6x80", "2.22"),
            ("8x60", "2.22"),
            ("8x80", "2.22"),
            ("8x100", "2.22"),
            ("8x120", "2.52"),
        ),
    ),
    MetizGroup(
        key="sariq-samorez",
        name_uz="Sariq samorez",
        name_uz_cyrl="Сариқ саморез",
        name_ru="Саморез жёлтый",
        unit="kg",
        keywords=("sariq samorez", "samorez sariq"),
        rows=(
            ("3x13-16-20-25", "3.24"),
            ("4x16-6x150", "2.28"),
        ),
    ),
    MetizGroup(
        key="oq-samorez",
        name_uz="Oq samorez",
        name_uz_cyrl="Оқ саморез",
        name_ru="Саморез белый",
        unit="kg",
        keywords=("oq samorez", "ok samorez", "samorez oq"),
        rows=(
            ("3x13-16-20-25", "3.24"),
            # Printed "3,5/16 - 4x16": this list uses the slash where it
            # elsewhere uses an x.
            ("3.5x16-4x16", "2.76"),
        ),
    ),
    MetizGroup(
        key="press-shayba-ostriy",
        name_uz="Press shayba (o'tkir)",
        name_uz_cyrl="Пресс шайба (ўткир)",
        name_ru="Пресс-шайба острая",
        unit="kg",
        keywords=("press shayba ostriy", "ostriy press shayba"),
        rows=(("4.2x13-76", "2.16"),),
    ),
    MetizGroup(
        key="press-shayba-sverlo",
        name_uz="Press shayba (parmali)",
        name_uz_cyrl="Пресс шайба (пармали)",
        name_ru="Пресс-шайба со сверлом",
        unit="kg",
        keywords=("press shayba sverlo", "sverlo press shayba"),
        rows=(("4.2x13-76", "2.22"),),
    ),
    MetizGroup(
        key="potay-samorez",
        name_uz="Potay samorez",
        name_uz_cyrl="Потай саморез",
        name_ru="Саморез потайной",
        unit="kg",
        keywords=("potay samorez", "samorez potay", "potay"),
        rows=(
            ("4.2x16;19;25;32", "2.22"),
            ("4.2x40;50;60;70;80;100", "2.22"),
        ),
    ),
    MetizGroup(
        key="gribok-samorez",
        name_uz="Gribok samorez",
        name_uz_cyrl="Грибок саморез",
        name_ru="Саморез грибок",
        unit="kg",
        keywords=("gribok samorez", "samorez gribok", "gribok"),
        rows=(
            ("4.8x16;19;25;32", "2.22"),
            ("4.8x40;50;60;70;80;100", "2.22"),
        ),
    ),
    MetizGroup(
        key="mix",
        name_uz="Mix",
        name_uz_cyrl="Мих",
        name_ru="Гвозди",
        unit="kg",
        keywords=("mix", "mix gvozd"),
        rows=(
            ("16-20", "1.74"),
            ("25", "1.62"),
            ("30-40", "1.5"),
            ("50-60", "1.104"),
            ("70-200", "0.912"),
        ),
    ),
    MetizGroup(
        key="dyubel",
        name_uz="Dyubel",
        name_uz_cyrl="Дюбел",
        name_ru="Дюбель",
        unit="kg",
        keywords=("dyubel",),
        rows=(("30-100", "2.04"),),
    ),
    MetizGroup(
        key="zaklepka-orbita",
        name_uz="Zaklepka Orbita",
        name_uz_cyrl="Заклепка Орбита",
        name_ru="Заклёпка Orbita",
        unit="pachka",
        keywords=("zaklepka orbita", "orbita zaklepka"),
        brand="Orbita",
        rows=(
            ("3.2x11", "4.08"),
            ("3.2x13", "4.68"),
            ("3.2x17", "4.8"),
            ("4x8", "5.52"),
            ("4x10", "5.64"),
            ("4x13", "6.36"),
            ("4x16", "3.36"),
            ("4x20", "3.6"),
            ("5x11", "4.44"),
            ("5x13", "4.68"),
            ("5x16", "5.16"),
            ("5x20", "5.88"),
            ("5x25", "6.72"),
            ("6x16", "4.92"),
            ("6x20", "5.28"),
            ("6x25", "6"),
            ("5x16x16", "6.84"),
            ("5x20x16", "6.84"),
            ("5x25x16", "6.84"),
        ),
    ),
    MetizGroup(
        key="rezina-shayba",
        name_uz="Rezina shayba",
        name_uz_cyrl="Резина шайба",
        name_ru="Резиновая шайба",
        unit="kg",
        keywords=("rezina shayba", "shayba rezina", "rezinali shayba"),
        rows=(
            ("4.8x14", "3"),
            ("5.5x19", "2.64"),
            ("6.3x25", "2.4"),
        ),
    ),
    MetizGroup(
        key="podves-agraf",
        name_uz="Podves (agraf)",
        name_uz_cyrl="Подвес (аграф)",
        name_ru="Подвес (аграф)",
        # The price list leaves this block's unit column occupied by the
        # thickness ("Аграф | 0,7 | 38,4"), so the unit is not printed. 38.4 and
        # 49.2 sit exactly in the band this list uses for a box (evro stashka
        # 36, chopiq 38.4-80.4) and nowhere near its per-piece prices, so a box
        # is what the numbers say. Worth a word with the supplier before the
        # first order goes out on it.
        unit="quti",
        keywords=("podves agraf", "agraf", "podves"),
        rows=(
            ("0.7", "38.4"),
            ("1", "49.2"),
        ),
    ),
    MetizGroup(
        key="chervyak-bolt",
        name_uz="Chervyak bolt",
        name_uz_cyrl="Червяк болт",
        name_ru="Червячный болт",
        unit="kg",
        keywords=("chervyak bolt", "bolt chervyak", "chervyak"),
        rows=(("8x80-10x120", "2.04"),),
    ),
    MetizGroup(
        key="gluxar",
        name_uz="Gluxar",
        name_uz_cyrl="Глухар",
        name_ru="Глухарь",
        unit="kg",
        keywords=("gluxar",),
        rows=(("6x50-12x150", "2.04"),),
    ),
    MetizGroup(
        key="shayba",
        name_uz="Shayba (katta va kichik)",
        name_uz_cyrl="Шайба (катта ва кичик)",
        name_ru="Шайба (большая и малая)",
        unit="kg",
        keywords=("shayba", "katta shayba", "kichik shayba"),
        rows=(
            ("m4;m5", "2.04"),
            ("m6-m24", "1.86"),
        ),
    ),
    MetizGroup(
        key="stashka-vint-mebel",
        name_uz="Stashka vint (mebel)",
        name_uz_cyrl="Сташка винт (мебел)",
        name_ru="Стяжка винт мебельная",
        unit="kg",
        keywords=("stashka vint", "mebel stashka", "vint mebel", "stashka"),
        rows=(("6x16-6x100", "1.8"),),
    ),
    MetizGroup(
        key="evro-stashka",
        name_uz="Yevro stashka",
        name_uz_cyrl="Евро сташка",
        name_ru="Евро стяжка",
        unit="quti",
        keywords=("yevro stashka", "evro stashka", "stashka"),
        rows=(("6.3x50", "36"),),
    ),
    MetizGroup(
        key="tsanga-orbita",
        name_uz="Tsanga Orbita",
        name_uz_cyrl="Цанга Орбита",
        name_ru="Цанга Orbita",
        unit="dona",
        keywords=("tsanga orbita", "orbita tsanga"),
        brand="Orbita",
        rows=(
            ("m6", "0.018"),
            ("m8", "0.024"),
            ("m10", "0.0444"),
            ("m12", "0.132"),
            ("m14", "0.168"),
            ("m16", "0.204"),
        ),
    ),
    MetizGroup(
        key="tsanga-turk",
        name_uz="Tsanga (turk)",
        name_uz_cyrl="Цанга (турк)",
        name_ru="Цанга турецкая",
        unit="dona",
        keywords=("tsanga turk", "turk tsanga"),
        rows=(
            ("m8", "0.0444"),
            ("m10", "0.168"),
        ),
    ),
    MetizGroup(
        key="kryuchok-sariq",
        name_uz="Kryuchok sariq (ilmoq)",
        name_uz_cyrl="Крючок сариқ (илмоқ)",
        name_ru="Крючок жёлтый",
        unit="dona",
        keywords=("kryuchok sariq", "sariq kryuchok", "ilmoq sariq"),
        rows=(
            ("m6x60", "0.18"),
            ("m6x80", "0.204"),
            ("m8x60", "0.324"),
            ("m8x100", "0.372"),
            ("m10x80", "0.564"),
            ("m10x120", "0.636"),
            ("m12x100", "0.924"),
        ),
    ),
    MetizGroup(
        key="kryuchok-yopiq",
        name_uz="Kryuchok yopiq (ilmoq)",
        name_uz_cyrl="Крючок ёпиқ (илмоқ)",
        name_ru="Крючок закрытый",
        unit="dona",
        keywords=("kryuchok yopiq", "yopiq kryuchok", "ilmoq yopiq"),
        rows=(
            ("m6x60", "0.18"),
            ("m8x60", "0.324"),
            ("m10x80", "0.564"),
        ),
    ),
    MetizGroup(
        key="kryuchok-oq-yogochga",
        name_uz="Kryuchok oq (yog'ochga)",
        name_uz_cyrl="Крючок оқ (ёғочга)",
        name_ru="Крючок белый по дереву",
        unit="dona",
        keywords=("kryuchok oq", "yogochga kryuchok", "ilmoq oq"),
        rows=(
            ("6", "0.0132"),
            ("8", "0.0204"),
            ("10", "0.0264"),
            ("12", "0.0384"),
            ("14", "0.06"),
            ("16", "0.084"),
        ),
    ),
    MetizGroup(
        key="gayka-oq",
        name_uz="Gayka oq",
        name_uz_cyrl="Гайка оқ",
        name_ru="Гайка белая",
        unit="kg",
        keywords=("gayka oq", "ok gayka"),
        rows=(
            ("3", "2.64"),
            ("4", "2.28"),
            ("5", "2.16"),
            ("6-8-10-12-14", "1.86"),
            ("16-18-20-24", "1.86"),
        ),
    ),
    MetizGroup(
        key="shpilka-097",
        name_uz="Shpilka 0.97 m",
        name_uz_cyrl="Шпилька 0,97 м",
        name_ru="Шпилька 0,97 м",
        unit="dona",
        keywords=("shpilka 0.97", "shpilka 097"),
        rows=(
            ("6", "0.264"),
            ("8", "0.456"),
            ("10", "0.72"),
            ("12", "1.02"),
            ("14", "1.5"),
            ("16", "2.04"),
            ("18", "3.36"),
            ("20", "4.2"),
            ("24", "6.6"),
        ),
    ),
    MetizGroup(
        key="chopiq-kulrang",
        name_uz="Chopiq kulrang (m/plast)",
        name_uz_cyrl="Чопиқ кулранг (м/пласт)",
        name_ru="Чопик серый (м/пласт)",
        unit="quti",
        keywords=("chopik kulrang", "kulrang chopik", "seriy chopik"),
        rows=(
            ("6x30", "68.4"),
            ("6x40", "74.4"),
            ("8x40", "61.2"),
            ("10", "75.6"),
            ("12", "68.4"),
        ),
    ),
    MetizGroup(
        key="chopiq-qizil",
        name_uz="Chopiq qizil (m/plast)",
        name_uz_cyrl="Чопиқ қизил (м/пласт)",
        name_ru="Чопик красный (м/пласт)",
        unit="quti",
        keywords=("chopik qizil", "qizil chopik", "krasniy chopik"),
        rows=(
            ("6x30", "38.4"),
            ("6x40", "45.6"),
            ("8x40", "54"),
            ("8x50", "64.8"),
            ("8x60", "52.8"),
            ("10", "75.6"),
            ("12", "68.4"),
            ("14", "80.4"),
            ("babochka", "60"),
            ("driva", "72"),
            ("zontik shay", "60"),
        ),
    ),
    MetizGroup(
        key="bolt",
        name_uz="Bolt",
        name_uz_cyrl="Болт",
        name_ru="Болт",
        unit="kg",
        keywords=("bolt",),
        rows=(
            ("6x16-6x100", "1.8"),
            ("8x16-8x120", "1.8"),
            ("10x20-10x150", "1.68"),
            ("12x30-12x150", "1.68"),
            ("14x30-14x200", "1.68"),
            ("16x30-16x200", "1.68"),
        ),
    ),
    MetizGroup(
        key="zabivnoy-anker",
        name_uz="Zabivnoy anker",
        name_uz_cyrl="Забивной анкер",
        name_ru="Забивной анкер",
        unit="dona",
        keywords=("zabivnoy anker", "anker zabivnoy"),
        rows=(
            ("8x100", "0.12"),
            ("10x80", "0.144"),
            ("10x100", "0.168"),
            ("10x120", "0.216"),
            ("10x150", "0.276"),
            ("12x100", "0.264"),
            ("12x120", "0.336"),
            ("12x150", "0.42"),
            ("14x100", "0.504"),
            ("14x150", "0.696"),
            ("16x120", "0.756"),
            ("16x150", "0.936"),
        ),
    ),
    MetizGroup(
        key="anker-kryuchok",
        name_uz="Anker kryuchok (ilmoq)",
        name_uz_cyrl="Анкер крючок (илмоқ)",
        name_ru="Анкер крючок",
        unit="dona",
        keywords=("anker kryuchok", "kryuchok anker"),
        rows=(
            ("m8x60", "0.156"),
            ("m8x100", "0.204"),
            ("m10x80", "0.324"),
            ("m10x120", "0.444"),
            ("m12x120", "0.864"),
        ),
    ),
    MetizGroup(
        key="anker-kryuchok-yopiq",
        name_uz="Anker kryuchok yopiq",
        name_uz_cyrl="Анкер крючок ёпиқ",
        name_ru="Анкер крючок закрытый",
        unit="dona",
        keywords=("anker kryuchok yopiq", "yopiq anker kryuchok"),
        rows=(
            ("m8x60", "0.156"),
            ("m10x80", "0.324"),
            ("m12x120", "0.864"),
        ),
    ),
    MetizGroup(
        key="grover-shayba",
        name_uz="Grover shayba",
        name_uz_cyrl="Гровер шайба",
        name_ru="Гровер шайба",
        unit="kg",
        keywords=("grover shayba", "grover", "shayba grover"),
        rows=(("6-8-10-12", "1.92"),),
    ),
    MetizGroup(
        key="shpilka-1m",
        name_uz="Shpilka 1 m (original)",
        name_uz_cyrl="Шпилька 1 м (оригинал)",
        name_ru="Шпилька 1 м оригинал",
        unit="dona",
        keywords=("shpilka 1 m", "shpilka original", "shpilka 1m"),
        rows=(
            ("8", "0.624"),
            ("10", "0.9"),
            ("12", "1.248"),
        ),
    ),
    MetizGroup(
        key="shpilka-2m",
        name_uz="Shpilka 2 m",
        name_uz_cyrl="Шпилька 2 м",
        name_ru="Шпилька 2 м",
        unit="dona",
        keywords=("shpilka 2 m", "shpilka 2m"),
        rows=(
            ("8", "1.32"),
            ("10", "1.92"),
            ("12", "3.12"),
        ),
    ),
    MetizGroup(
        key="zontik-mplast",
        name_uz="Zontik (m/plast)",
        name_uz_cyrl="Зонтик (м/пласт)",
        name_ru="Зонтик (м/пласт)",
        unit="pachka",
        keywords=("zontik", "zontik mplast", "zontik dyubel"),
        rows=(
            ("80", "3.96"),
            ("110", "5.28"),
            ("120", "5.64"),
            ("150", "3.24"),
            ("termo 120", "36"),
            ("termo 150", "33"),
        ),
    ),
    MetizGroup(
        key="qora-samorez-mexmash",
        name_uz="Qora samorez Mexmash",
        name_uz_cyrl="Қора саморез Мехмаш",
        name_ru="Саморез чёрный Мехмаш",
        unit="kg",
        keywords=("qora samorez mexmash", "samorez mexmash", "mexmash samorez"),
        brand="Mexmash",
        rows=(
            ("16-19", "2.604"),
            ("25-100", "2.316"),
        ),
    ),
    MetizGroup(
        key="rezba-zaklepka",
        name_uz="Rezbali zaklepka",
        name_uz_cyrl="Резбали заклепка",
        name_ru="Резьбовая заклёпка",
        unit="dona",
        keywords=("rezba zaklepka", "rezbali zaklepka", "zaklepka rezba"),
        rows=(
            ("4", "0.012"),
            ("5", "0.018"),
            ("6", "0.024"),
            ("8", "0.0336"),
            ("10", "0.0528"),
            ("12", "0.102"),
        ),
    ),
    MetizGroup(
        key="kryuchok-armstrong",
        name_uz="Kryuchok Armstrong",
        name_uz_cyrl="Крючок Армстронг",
        name_ru="Крючок Армстронг",
        unit="dona",
        keywords=("kryuchok armstrong", "armstrong kryuchok", "armstron kryuchok"),
        brand="Armstrong",
        rows=(("6x40", "0.024"),),
    ),
    MetizGroup(
        key="krovelniy-samorez-oq-metallga",
        name_uz="Krovelniy samorez oq (metallga)",
        name_uz_cyrl="Кровелний саморез оқ (металлга)",
        name_ru="Кровельный саморез белый (по металлу)",
        unit="kg",
        keywords=("krovelniy samorez oq metallga", "krovelniy samorez metallga"),
        rows=(
            ("5.5x25-150", "3.24"),
            ("6.3x25-200", "3.24"),
        ),
    ),
    MetizGroup(
        key="gayka-shaybali",
        name_uz="Gayka shaybali",
        name_uz_cyrl="Гайка шайбали",
        name_ru="Гайка с шайбой",
        unit="kg",
        keywords=("gayka shaybali", "shaybali gayka"),
        rows=(("6-8-10-12", "2.64"),),
    ),
    MetizGroup(
        key="gayka-samakontr",
        name_uz="Gayka samakontr",
        name_uz_cyrl="Гайка самаконтр",
        name_ru="Гайка самоконтрящаяся",
        unit="kg",
        keywords=("gayka samakontr", "samakontr gayka"),
        rows=(("6-8-10-12", "2.64"),),
    ),
    MetizGroup(
        key="gayka-barashka",
        name_uz="Gayka barashka",
        name_uz_cyrl="Гайка барашка",
        name_ru="Гайка-барашек",
        unit="kg",
        keywords=("gayka barashka", "barashka gayka"),
        rows=(("m6-m8-m10", "3.12"),),
    ),
    MetizGroup(
        key="gazoblok-probka",
        name_uz="Gazoblok probka",
        name_uz_cyrl="Газаблок пробка",
        name_ru="Пробка для газоблока",
        unit="dona",
        keywords=("gazoblok probka", "probka gazoblok", "gazablok probka", "probka"),
        rows=(
            ("5x30", "0.0192"),
            ("6x32", "0.0264"),
            ("8x38", "0.048"),
            ("10x60", "0.096"),
        ),
    ),
    MetizGroup(
        key="kryuchok-babochka",
        name_uz="Kryuchok babochka",
        name_uz_cyrl="Крючок бабочка",
        name_ru="Крючок бабочка",
        unit="dona",
        keywords=("kryuchok babochka", "babochka kryuchok", "babochka"),
        rows=(
            ("m4", "0.132"),
            ("m5", "0.192"),
            ("m6", "0.264"),
            ("m8", "0.396"),
        ),
    ),
]


# Row labels that are a word rather than a size, and how the list writes them
# in Cyrillic. Only these few need it; every other label is digits and an x.
_METIZ_LABEL_CYRL = {
    "babochka": "бабочка",
    "driva": "дрива",
    "zontik shay": "зонтик шай",
    "termo 120": "термо 120",
    "termo 150": "термо 150",
}

_SIZE_PREFIX_REGEX = re.compile(r"^(\d+(?:\.\d+)?)x(.+)$")
_LABEL_SEPARATORS = re.compile(r"[-;]")

# Every whole number this price list prints as part of a size. A range is
# expanded against this ladder rather than against every integer inside it: the
# list is its own authority on which lengths the trade actually stocks, so
# nothing here is a size we made up.
_METIZ_SIZE_LADDER: tuple[int, ...] = tuple(
    sorted(
        {
            int(number)
            for group in _METIZ
            for label, _price in group.rows
            for number in re.findall(r"\d+", label)
        }
    )
)


_FULL_SIZE_REGEX = re.compile(r"^(\d+(?:\.\d+)?)x(\d+)$")


def _ladder_between(low: str, high: str) -> list[str]:
    """The sizes this price list names between two bounds, inclusive.

    Empty when the bounds are equal or out of order, so a caller can tell "no
    span" from "a span of one".
    """
    if low == high:
        return [low]
    try:
        start, end = float(low), float(high)
    except ValueError:
        return []
    if start >= end:
        return []
    return [str(step) for step in _METIZ_SIZE_LADDER if start <= step <= end]


def expand_metiz_label(label: str) -> list[str]:
    """The sizes a price-list label covers, as a customer would name one.

    "4.2x13-76" is one price for every screw between 13 and 76 mm long; the
    person ordering asks for "4.2x25" and never for the range. Splitting the
    label back into the sizes it stands for is what lets that query find this
    row -- and it cannot mis-price anything, because the supplier set one price
    for the whole span.

    Three shapes have to be told apart:

    * two whole sizes -- "12x30-12x150", "4x16-6x150" -- a span over the
      length, and over the diameter too when the ends disagree on it;
    * two bare numbers after a shared diameter -- "4.2x13-76", "16-19" -- a
      span over the length alone;
    * three or more parts -- "3x13-16-20-25", "4.2x16;19;25;32" -- not a span
      at all but a list of sizes the row spells out, taken as printed.

    A span is filled from `_METIZ_SIZE_LADDER`, the sizes this same price list
    names elsewhere, so nothing is offered that the supplier never mentioned.
    """
    if not _LABEL_SEPARATORS.search(label):
        return [label]

    whole = [p.strip() for p in _LABEL_SEPARATORS.split(label) if p.strip()]
    sizes: list[str] = [label]

    if len(whole) == 2:
        ends = [_FULL_SIZE_REGEX.match(part) for part in whole]
        low, high = ends[0], ends[1]
        if low is not None and high is not None:
            # The printed ends first: a fractional diameter such as 3.5 is a
            # real size but never lands on the ladder of whole numbers.
            sizes.extend(whole)
            diameters = _ladder_between(low.group(1), high.group(1))
            for diameter in diameters or [low.group(1)]:
                for length in _ladder_between(low.group(2), high.group(2)):
                    sizes.append(f"{diameter}x{length}")
            if len(sizes) > 1:
                return list(dict.fromkeys(sizes))

    prefix = ""
    rest = label
    head = _SIZE_PREFIX_REGEX.match(label)
    if head:
        prefix, rest = head.group(1), head.group(2)

    parts = [p.strip() for p in _LABEL_SEPARATORS.split(rest) if p.strip()]

    if len(parts) == 2 and all(part.isdigit() for part in parts):
        for step in _ladder_between(parts[0], parts[1]):
            sizes.append(f"{prefix}x{step}" if prefix else step)
        if len(sizes) > 1:
            return list(dict.fromkeys(sizes))

    for part in parts:
        sizes.append(part if "x" in part or not prefix else f"{prefix}x{part}")
    return list(dict.fromkeys(sizes))


def _metiz_slug(group_key: str, label: str) -> str:
    tail = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")
    return f"{group_key}-{tail}"


def _metiz_items() -> list[CatalogItem]:
    """The fastener price list, one SKU per printed row."""
    items: list[CatalogItem] = []
    for group in _METIZ:
        for label, price_usd in group.rows:
            label_cyrl = _METIZ_LABEL_CYRL.get(label, label.replace("x", "х"))
            attributes: dict[str, Any] = {"material": group.key.replace("-", "_")}
            if "x" in label:
                attributes["size"] = label
            head = re.match(r"^m?(\d+(?:\.\d+)?)", label)
            if head:
                attributes["diameter_mm"] = _thickness(head.group(1))
            if label.startswith("m") and re.fullmatch(r"m\d+", label):
                attributes["grade"] = label

            items.append(
                CatalogItem(
                    slug=_metiz_slug(group.key, label),
                    name_uz=f"{group.name_uz} {label}",
                    name_uz_cyrl=f"{group.name_uz_cyrl} {label_cyrl}",
                    name_ru=f"{group.name_ru} {label_cyrl}",
                    brand=group.brand,
                    category_slug=_METIZ_CATEGORY,
                    base_unit=group.unit,
                    attributes=attributes,
                    tier="standard",
                    reference_price=_uzs(price_usd),
                    pack_size=Decimal("1"),
                    pack_unit=group.unit,
                    source=SOURCE_SUPPLIER,
                    source_ref=_METIZ_SOURCE_REF,
                )
            )
    return items


def generate_metiz_aliases(group: MetizGroup, label: str) -> list[str]:
    """Every phrasing that should land on one fastener row.

    Built by crossing the family words a customer types with the sizes the
    label names, then run through the same normalizer a query goes through --
    an alias only earns its keep if it is in the exact form Stage 1 hashes.
    """
    forms: list[str] = [f"{group.name_uz} {label}"]
    # The list titles these blocks "ОК" and "САРИК"; the words are oq and
    # sariq. Both spellings reach us, and "ok" is too common a word to put in
    # the slang table, so it is carried here where it can only mean the colour.
    keywords = list(group.keywords)
    keywords.extend(k.replace("oq", "ok") for k in group.keywords if "oq" in k)
    for keyword in keywords:
        for size in expand_metiz_label(label):
            forms.append(f"{keyword} {size}")
            if size.startswith("m") and re.match(r"^m\d", size):
                # "kryuchok 6x60" for a row printed "m6x60": the thread letter
                # is on the price list, not in the message.
                forms.append(f"{keyword} {size[1:]}")
    if group.brand:
        forms.append(f"{group.brand} {label}")
    return forms


_METIZ_ROWS_BY_SLUG: dict[str, tuple[MetizGroup, str]] = {
    _metiz_slug(group.key, label): (group, label)
    for group in _METIZ
    for label, _price in group.rows
}


def _metiz_alias_rows(item: CatalogItem) -> list[dict[str, Any]]:
    """Alias rows for one fastener SKU, in the form Stage 1 looks them up by.

    Normalized here rather than lower-cased, unlike the sheet-goods aliases
    above. A metiz query arrives transliterated, de-slanged and with its
    decimal comma repaired ("саморез 4,2х25" -> "samorez 4.2x25"); an alias
    stored any other way is a row that can never be hit.
    """
    group, label = _METIZ_ROWS_BY_SLUG[item.slug]
    aliases: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in generate_metiz_aliases(group, label):
        norm = normalize_query(raw).text_norm
        if not norm or norm in seen:
            continue
        seen.add(norm)
        aliases.append(
            {
                "alias_norm": norm,
                "alias_raw": raw,
                "source": "seed",
                "is_approved": True,
            }
        )
    return aliases


def generate_catalog_data() -> list[CatalogItem]:
    """The whole catalogue, in price-list order."""
    items: list[CatalogItem] = []
    items.extend(_laminated_plywood_items())
    items.extend(_birch_plywood_items())
    items.extend(_timber_items())
    items.extend(_hardboard_items())
    items.extend(_osb3_items())
    items.extend(_metiz_items())
    return items


# Short forms buyers actually type, per material. The catalogue is all sheet
# goods, so a thickness plus one of these words is the whole query most of the
# time: "fanera 12", "osb 9", "dvp 3.2".
_MATERIAL_KEYWORDS: dict[str, tuple[str, ...]] = {
    # "fanera berezovaya" / "фанера березовая" are how the product is named on
    # the price list itself, and customers copy that wording straight across.
    "birch_plywood": (
        "fanera",
        "faner",
        "фанера",
        "fanera berezovaya",
        "фанера березовая",
        "fanera bereza",
    ),
    "laminated_plywood": (
        "laminat fanera",
        "fanera laminat",
        "ламинированная фанера",
    ),
    "osb3": ("osb", "osb-3", "osb3", "осб", "осб-3"),
    "hdf": ("hdf", "хдф"),
    "hardboard": ("dvp", "двп"),
}


# What a sheet size is called out loud. Seeded rather than computed: the
# arithmetic does not close -- 1.5 by 1.5 metres is 1500x1500 and the sheet is
# 1525x1525 -- so only the naming knows they are the same thing.
_SIZE_SPOKEN_AS: dict[str, tuple[str, ...]] = {
    "1525x1525": ("1.5x1.5", "1.50x1.50", "1.52x1.52", "1.525x1.525"),
    "2440x1220": ("1.22x2.44", "2.44x1.22"),
}


def generate_aliases_for_product(item: CatalogItem) -> list[dict[str, Any]]:
    """Search aliases for one catalogue row.

    Seeded aliases are approved, and an approved alias_norm must be unique
    across the whole catalogue, so the caller drops any that collide. Ordering
    therefore matters: the most specific forms come first, and the bare
    "material + thickness" shorthands last, where a collision costs least.
    """
    if item.category_slug == _METIZ_CATEGORY:
        return _metiz_alias_rows(item)

    raw_forms: list[str] = [item.name_uz, item.name_uz_cyrl, item.name_ru]
    raw_forms.append(item.slug.replace("-", " "))

    attrs = item.attributes
    thickness = attrs.get("thickness_mm")
    size = attrs.get("size")
    grade = attrs.get("grade")
    keywords = _MATERIAL_KEYWORDS.get(str(attrs.get("material")), ())

    if thickness is not None:
        for keyword in keywords:
            if grade:
                raw_forms.append(f"{keyword} {grade} {thickness}mm")
                raw_forms.append(f"{keyword} {grade} {thickness}")
            if size:
                raw_forms.append(f"{keyword} {thickness}mm {size}")
                # And the size as people say it out loud, in metres. This has
                # to be an alias rather than a conversion: 1.5 x 1.5 metres is
                # 1500x1500, the sheet is 1525x1525, and no arithmetic bridges
                # that gap -- only knowing that this is what the sheet is
                # called. Straight off the unmatched queue, where "1.50x1.50",
                # "1.52x1.52" and "1.525x1.525" all appear.
                for spoken in _SIZE_SPOKEN_AS.get(str(size), ()):
                    raw_forms.append(f"{keyword} {spoken} {thickness}mm")
                    raw_forms.append(f"{keyword} {thickness}mm {spoken}")
            if item.brand:
                raw_forms.append(f"{keyword} {item.brand} {thickness}")
            raw_forms.append(f"{keyword} {thickness}mm")
            # The spaced form is how the price list itself prints a thickness
            # ("18 mm"), and customers copy it across with the space intact.
            raw_forms.append(f"{keyword} {thickness} mm")
            raw_forms.append(f"{keyword} {thickness}")

    if item.brand:
        raw_forms.append(item.brand)
        # A plant name is often the whole query for boards that differ only by
        # who made them: "dsp kronospan", "дсп пермь".
        for keyword in keywords:
            raw_forms.append(f"{keyword} {item.brand}")

    aliases: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in raw_forms:
        norm = raw.lower().strip()
        if not norm or norm in seen:
            continue
        seen.add(norm)
        aliases.append(
            {
                "alias_norm": norm,
                "alias_raw": raw,
                "source": "seed",
                "is_approved": True,
            }
        )
    return aliases


# Our own plywood price list. Quoted per sheet in dollars, with a wholesale
# price that applies from a given number of sheets upward -- "10.2$, 10$ from
# 200". Converted once here at a written-down rate rather than at a rate that
# lives in someone's head; when the rate moves, this constant moves with it and
# every price follows.
USD_TO_UZS = Decimal("11820.48")  # O'zbekiston MB, 02.09.2026

OUR_SHOP_NAME = "QurBot"
OUR_SHOP_PHONE = "+998935394994"

# (size, grade, thickness mm, retail $, wholesale $, wholesale from N sheets)
_OUR_PLYWOOD_PRICES: list[tuple[str, str, str, str, str, int]] = [
    ("1525x1525", "3x3", "3", "4.6", "4.3", 390),
    ("1525x1525", "4x4", "3", "4.2", "4.0", 390),
    ("1525x1525", "3x3", "4", "5.6", "5.2", 300),
    ("1525x1525", "3x3", "5", "7.5", "7.0", 160),
    ("1525x1525", "3x3", "6", "8.5", "8.0", 130),
    ("1525x1525", "3x3", "8", "10.5", "10.2", 150),
    ("1525x1525", "3x3", "10", "12.5", "12.0", 120),
    ("1525x1525", "3x3", "12", "13.5", "13.3", 66),
    ("1525x1525", "3x3", "14", "16.5", "16.0", 56),
    ("1525x1525", "3x3", "15", "18.5", "18.0", 54),
    ("1525x1525", "3x3", "18", "21.5", "21.0", 66),
    ("1525x1525", "3x3", "21", "25.5", "25.0", 57),
    ("1525x1525", "3x3", "30", "38.0", "37.0", 52),
    ("2440x1220", "2x4", "4", "10.2", "10.0", 200),
    ("2440x1220", "2x4", "6", "13.5", "13.0", 132),
    ("2440x1220", "2x4", "9", "19.5", "19.0", 132),
    ("2440x1220", "2x4", "12", "23.0", "22.5", 66),
    ("2440x1220", "2x4", "15", "26.5", "26.0", 52),
    ("2440x1220", "2x4", "18", "32.0", "31.8", 66),
    ("2440x1220", "2x4", "21", "38.0", "37.5", 19),
]


def _uzs(usd: str) -> Decimal:
    """Dollars to so'm, rounded to whole so'm -- nobody quotes tiyin."""
    return (Decimal(usd) * USD_TO_UZS).quantize(Decimal("1"))


def our_priced_rows() -> list[tuple[str, str, str | None, int | None]]:
    """Every product we quote a price on ourselves.

    (product slug, retail $, wholesale $ or None, wholesale from N or None).
    The plywood list steps down at a quantity; the fastener list is one price
    per row. Exposed so tests can assert "our own offers and no others"
    without repeating the number.
    """
    rows: list[tuple[str, str, str | None, int | None]] = [
        (
            f"fanera-bereza-{grade}-{_slug_num(thickness)}mm-{size}",
            retail_usd,
            wholesale_usd,
            from_qty,
        )
        for size, grade, thickness, retail_usd, wholesale_usd, from_qty in _OUR_PLYWOOD_PRICES
    ]
    rows.extend(
        (_metiz_slug(group.key, label), price_usd, None, None)
        for group in _METIZ
        for label, price_usd in group.rows
    )
    return rows


async def seed_own_offers(session: AsyncSession) -> int:
    """Create or refresh QurBot's own offers, with their wholesale tiers.

    Runs inside the catalogue-only path because these are real prices a
    customer can order against, not demo data: skipping them on deploy would
    leave the catalogue priced by nobody.
    """
    district_stmt = select(District).order_by(District.id).limit(1)
    district = (await session.execute(district_stmt)).scalars().first()
    if district is None:
        logger.warning("seed_own_offers: no districts yet, skipping")
        return 0

    shop_stmt = select(Shop).where(Shop.name == OUR_SHOP_NAME)
    shop = (await session.execute(shop_stmt)).scalars().first()
    if shop is None:
        shop = Shop(
            name=OUR_SHOP_NAME,
            phone=OUR_SHOP_PHONE,
            district_id=district.id,
            address="Toshkent",
            is_active=True,
        )
        session.add(shop)
        await session.flush()

    written = 0
    for slug, retail_usd, wholesale_usd, from_qty in our_priced_rows():
        canonical = (
            (await session.execute(select(CanonicalProduct).where(CanonicalProduct.slug == slug)))
            .scalars()
            .first()
        )
        if canonical is None:
            logger.warning("seed_own_offers: no canonical product for %s", slug)
            continue

        price = _uzs(retail_usd)
        offer_stmt = select(ShopProduct).where(
            ShopProduct.shop_id == shop.id,
            ShopProduct.canonical_id == canonical.id,
        )
        offer = (await session.execute(offer_stmt)).scalars().first()
        if offer is None:
            offer = ShopProduct(
                shop_id=shop.id,
                canonical_id=canonical.id,
                raw_name=canonical.name_uz,
                raw_unit=canonical.base_unit_code,
                pack_size=Decimal("1"),
                pack_unit_code=canonical.base_unit_code,
                price_per_pack=price,
                price_per_base_unit=price,
                stock_status="in_stock",
                staleness_state="fresh",
                updated_by="admin",
                is_active=True,
            )
            session.add(offer)
            await session.flush()
        else:
            offer.price_per_pack = price
            offer.price_per_base_unit = price
            offer.stock_status = "in_stock"
            offer.staleness_state = "fresh"
            offer.is_active = True

        written += 1
        if wholesale_usd is None or from_qty is None:
            continue

        wholesale = _uzs(wholesale_usd)
        tier_stmt = select(ShopProductPriceTier).where(
            ShopProductPriceTier.shop_product_id == offer.id,
            ShopProductPriceTier.min_qty == Decimal(from_qty),
        )
        tier = (await session.execute(tier_stmt)).scalars().first()
        if tier is None:
            session.add(
                ShopProductPriceTier(
                    shop_product_id=offer.id,
                    min_qty=Decimal(from_qty),
                    price_per_pack=wholesale,
                )
            )
        else:
            tier.price_per_pack = wholesale

    await session.flush()
    logger.info("Seeded %d own offers with wholesale tiers.", written)
    return written


async def seed_database(session: AsyncSession, catalog_only: bool = False) -> None:
    """Populate reference and catalogue data, and optionally the demo market.

    `catalog_only` seeds units, categories, districts, canonical products and
    aliases but stops before shops, offers and demo users. That is what a live
    deployment wants when the catalogue changes: new products become
    matchable without re-creating placeholder shops or synthetic offers
    alongside real ones.
    """
    logger.info("Starting database seeding (catalog_only=%s)...", catalog_only)

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
        cat = category_map[item.category_slug]

        stmt = select(CanonicalProduct).where(CanonicalProduct.slug == item.slug)
        res = await session.execute(stmt)
        prod = res.scalars().first()

        search_doc = " ".join(
            str(part)
            for part in (
                item.name_uz,
                item.name_uz_cyrl,
                item.name_ru,
                item.brand or "",
                item.attributes.get("size", ""),
                item.attributes.get("grade", ""),
                item.slug,
            )
            if part
        ).lower()

        if not prod:
            prod = CanonicalProduct(
                slug=item.slug,
                name_uz=item.name_uz,
                name_uz_cyrl=item.name_uz_cyrl,
                name_ru=item.name_ru,
                brand=item.brand,
                category_id=cat.id,
                base_unit_code=item.base_unit,
                attributes=item.attributes,
                tier=item.tier,
                source=item.source,
                source_ref=item.source_ref,
                reference_price=item.reference_price,
                is_active=True,
                search_doc=search_doc,
            )
            session.add(prod)
            await session.flush()
        else:
            # A price list is republished, not re-created: prices move with the
            # order day (fanera.uz says so in as many words), so re-seeding has
            # to reach rows that already exist or the catalogue silently keeps
            # whatever the first run happened to load.
            prod.name_uz = item.name_uz
            prod.name_uz_cyrl = item.name_uz_cyrl
            prod.name_ru = item.name_ru
            prod.brand = item.brand
            prod.category_id = cat.id
            prod.base_unit_code = item.base_unit
            prod.attributes = item.attributes
            prod.tier = item.tier
            prod.source = item.source
            prod.source_ref = item.source_ref
            prod.reference_price = item.reference_price
            prod.is_active = True
            prod.search_doc = search_doc
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

    # A product dropped from the price list has to be dropped here too. Seeding
    # is otherwise insert-or-update only, so a row removed from the source data
    # would sit in the live catalogue forever -- which is what happened to the
    # DSP rows once they were held back for confirmation.
    #
    # Deactivated rather than deleted: an order may reference it, and
    # is_active=False already takes it out of matching and out of every
    # customer surface, while an operator can still see it. Only supplier rows
    # are touched; anything an admin or a shop added is not ours to retire.
    current_slugs = {item.slug for item in raw_catalog}
    retired = (
        (
            await session.execute(
                select(CanonicalProduct).where(
                    CanonicalProduct.source == SOURCE_SUPPLIER,
                    CanonicalProduct.is_active.is_(True),
                    CanonicalProduct.slug.notin_(current_slugs),
                )
            )
        )
        .scalars()
        .all()
    )
    for product in retired:
        product.is_active = False
    if retired:
        await session.flush()
        logger.info("Retired %d products no longer on any price list.", len(retired))

    # Our own prices are real, orderable offers -- they belong to the catalogue
    # pass, not the demo market that follows it.
    await seed_own_offers(session)

    if catalog_only:
        logger.info("catalog_only: stopping before shops, offers and demo users.")
        return

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
    catalog_only = "--catalog-only" in sys.argv
    async with async_session_factory() as session:
        await seed_database(session, catalog_only=catalog_only)


if __name__ == "__main__":
    asyncio.run(main())
