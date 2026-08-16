import os
import re
import json
import math
import random
import statistics
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from dataclasses import dataclass, asdict
from datetime import date, timedelta, datetime, timezone

from flask import Flask, request, render_template_string, jsonify
import psycopg
from psycopg.rows import dict_row

app = Flask(__name__)

# =========================================================
# HLF PAS — Piyasa Arama Sistemi
# Mimari:
#   UI -> PostgreSQL cache -> analyze
#   Açık kullanıcı onayıyla /api/sync -> Apify Search Scraper Pro -> PostgreSQL
#   Normal filtreleme/aramanın Apify maliyeti yoktur.
#
# Railway Variables:
#   PAS_PROVIDER=demo
#   PAS_PROVIDER=apify
#   PAS_PROVIDER=authorized_sahibinden
#
# Apify için:
#   APIFY_API_TOKEN=...
#   APIFY_API_TOKEN=...
#   APIFY_TIMEOUT=300                              (opsiyonel)
# Actor kod içinde sabit: clearpath~sahibinden-scraper-pro
# DATABASE_URL Railway PostgreSQL bağlantısıdır.
# PAS_SYNC_MAX_RESULTS=200 (tek mahalle güncellemesinde üst sınır)
# =========================================================

DISTRICTS = [
    {"name": "Kadıköy", "side": "anadolu", "favorite": True},
    {"name": "Beykoz", "side": "anadolu", "favorite": True},
    {"name": "Üsküdar", "side": "anadolu", "favorite": True},
    {"name": "Ataşehir", "side": "anadolu", "favorite": False},
    {"name": "Maltepe", "side": "anadolu", "favorite": False},
    {"name": "Kartal", "side": "anadolu", "favorite": False},
    {"name": "Çekmeköy", "side": "anadolu", "favorite": False},
    {"name": "Beşiktaş", "side": "avrupa", "favorite": False},
    {"name": "Şişli", "side": "avrupa", "favorite": False},
    {"name": "Bakırköy", "side": "avrupa", "favorite": False},
    {"name": "Bahçelievler", "side": "avrupa", "favorite": False},
]

NEIGHBORHOODS = {
    "Kadıköy": [
        "19 Mayıs", "Suadiye", "Zühtüpaşa", "Acıbadem", "Bostancı",
        "Caddebostan", "Caferağa", "Dumlupınar", "Eğitim", "Erenköy",
        "Fenerbahçe", "Feneryolu", "Fikirtepe", "Göztepe", "Hasanpaşa",
        "Koşuyolu", "Kozyatağı", "Merdivenköy", "Sahrayıcedit",
        "Osmanağa", "Rasimpaşa"
    ],
    "Beykoz": [
        "Acarlar", "Baklacı", "Çiftlik", "İshaklı", "Zerzevatçı",
        "Mahmutşevketpaşa", "Kılıçlı", "Bozhane", "Cumhuriyet", "Göllü",
        "Paşamandıra", "Öğümce", "Çengeldere", "Yavuz Selim", "Fatih",
        "Riva", "Soğuksu", "Anadolu Hisarı", "Anadolu Kavağı",
        "Beykoz Merkez", "Çamlıbahçe", "Çiğdem", "Çubuklu", "Göksu",
        "Göztepe", "Gümüşsuyu", "İncirköy", "Kanlıca", "Kavacık",
        "Ortaçeşme", "Paşabahçe", "Rüzgarlıbahçe", "Tokatköy", "Yalıköy",
        "Yeni Mahalle", "Örnekköy", "Akbaba", "Alibahadır", "Anadolufeneri",
        "Dereseki", "Elmalı", "Görele", "Kaynarca", "Polonezköy",
        "Poyrazköy", "Acarkent (Bölge)", "Çavuşbaşı (Bölge)"
    ],
    "Üsküdar": [
        "Acıbadem", "Altunizade", "Bahçelievler", "Barbaros", "Beylerbeyi",
        "Bulgurlu", "Burhaniye", "Cumhuriyet", "Ferah", "Güzeltepe",
        "İcadiye", "Kandilli", "Kirazlıtepe", "Kısıklı", "Kuleli",
        "Kuzguncuk", "Küçüksu", "Küplüce", "Mehmet Akif Ersoy",
        "Murat Reis", "Selami Ali", "Selimiye", "Ünalan", "Valide-i Atik",
        "Yavuztürk", "Ahmediye", "Aziz Mahmut Hüdayi", "Çengelköy",
        "Küçük Çamlıca", "Mimar Sinan", "Sultantepe", "Zeynep Kamil",
        "Salacak"
    ],
    "Ataşehir": [
        "Barbaros", "Küçükbakkalköy", "Esatpaşa", "İnönü", "Kayışdağı",
        "Yenisahra", "Fetih", "Mevlana", "Mimar Sinan", "Mustafa Kemal",
        "Yenişehir", "Aşık Veysel", "Ferhatpaşa", "Örnek", "Atatürk",
        "Yeni Çamlıca", "İçerenköy"
    ],
    "Maltepe": [
        "Zümrütevler", "Esenkent", "Çınar", "Cevizli", "Büyükbakkalköy",
        "Başıbüyük", "Bağlarbaşı", "Aydınevler", "Altayçeşme", "Altıntepe",
        "Feyzullah", "Fındıklı", "Girne", "Gülensu", "Gülsuyu",
        "İdealtepe", "Küçükyalı Merkez", "Yalı"
    ],
    "Kartal": [
        "Esentepe", "Cevizli", "Yukarı", "Petrol İş", "Orhantepe",
        "Çavuşoğlu", "Karlıktepe", "Kordonboyu", "Yalı", "Yakacık Yeni",
        "Topselvi", "Cumhuriyet", "Hürriyet", "Yakacık Çarşı",
        "Soğanlık Yeni", "Orta", "Gümüşpınar", "Uğur Mumcu", "Atalar",
        "Yunus"
    ],
    "Çekmeköy": [
        "Merkez", "Hamidiye", "Çamlık", "Nişantepe", "Mehmet Akif",
        "Soğukpınar", "Mimar Sinan", "Çatalmeşe", "Ekşioğlu", "Alemdağ",
        "Cumhuriyet", "Kirazlıdere", "Güngören", "Taşdelen", "Aydınlar",
        "Ömerli", "Sultançiftliği", "Hüseyinli", "Koçullu", "Reşadiye",
        "Sırapınar"
    ],
    "Beşiktaş": [
        "Gayrettepe", "Abbasağa", "Akat", "Arnavutköy", "Balmumcu",
        "Bebek", "Cihannüma", "Dikilitaş", "Etiler", "Konaklar",
        "Kuruçeşme", "Kültür", "Levazım", "Mecidiye", "Muradiye",
        "Nisbetiye", "Ortaköy", "Levent", "Sinanpaşa", "Türkali",
        "Vişnezade", "Yıldız", "Ulus"
    ],
    "Şişli": [
        "Bozkurt", "Cumhuriyet", "Ergenekon", "Duatepe", "19 Mayıs",
        "İnönü", "İzzet Paşa", "Kaptanpaşa", "Kuştepe", "Eskişehir",
        "Esentepe", "Feriköy", "Fulya", "Gülbahar", "Halaskargazi",
        "Halide Edip Adıvar", "Halil Rıfat Paşa", "Harbiye", "Mecidiyeköy",
        "Mahmut Şevket Paşa", "Meşrutiyet", "Paşa", "Şişli Merkez",
        "Teşvikiye", "Yayla"
    ],
    "Bakırköy": [
        "Ataköy 1. Kısım", "Ataköy 2. 5. 6. Kısım",
        "Ataköy 3-4-11. Kısım", "Ataköy 7-8-9-10. Kısım",
        "Basınköy", "Kartaltepe", "Osmaniye", "Sakızağacı", "Cevizlik",
        "Şenlikköy", "Yenimahalle", "Yeşilköy", "Yeşilyurt",
        "Zeytinlik", "Zuhuratbaba"
    ],
    "Bahçelievler": [
        "Bahçelievler", "Cumhuriyet", "Çobançeşme", "Fevzi Çakmak",
        "Hürriyet", "Kocasinan Merkez", "Siyavuşpaşa", "Soğanlı",
        "Şirinevler", "Yenibosna Merkez", "Zafer"
    ],
}

DISTRICT_BASE_M2 = {
    "Kadıköy": 145000,
    "Beykoz": 118000,
    "Üsküdar": 132000,
    "Ataşehir": 111000,
    "Maltepe": 91000,
    "Kartal": 80000,
    "Çekmeköy": 73000,
    "Beşiktaş": 190000,
    "Şişli": 142000,
    "Bakırköy": 124000,
    "Bahçelievler": 78000,
}

ROOMS = ["1+1", "2+1", "3+1", "4+1", "5+1 ve üzeri"]


def parse_int(value):
    """TL, m² ve benzeri sayısal alanları güvenli biçimde tam sayıya çevirir."""
    if value in (None, ""):
        return None

    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)

    text = str(value).strip()
    if not text:
        return None

    # Para birimi, m² gibi yazıları temizle.
    text = re.sub(r"[^\d,.\-]", "", text)
    if not text:
        return None

    try:
        if "," in text and "." in text:
            # 22.000.000,00 veya 22,000,000.00
            if text.rfind(",") > text.rfind("."):
                text = text.replace(".", "").replace(",", ".")
            else:
                text = text.replace(",", "")
        elif "," in text:
            parts = text.split(",")
            if len(parts) > 1 and all(p.isdigit() for p in parts) and len(parts[-1]) == 3:
                text = "".join(parts)
            else:
                text = text.replace(",", ".")
        elif "." in text:
            parts = text.split(".")
            if len(parts) > 1 and all(p.isdigit() for p in parts) and len(parts[-1]) == 3:
                text = "".join(parts)

        return int(float(text))
    except (TypeError, ValueError):
        return None


def stable_seed(text):
    total = 0
    for i, ch in enumerate(str(text), start=1):
        total += i * ord(ch)
    return total % 10_000_000


def normalize_place_name(value):
    text = str(value or "").strip()
    text = re.sub(
        r"\s+(Mahallesi|Mah\.|Mh\.|Mah|Mh)$",
        "",
        text,
        flags=re.IGNORECASE,
    )
    return text.strip()


def sahibinden_slug(value):
    text = normalize_place_name(value).casefold()
    replacements = {
        "ı": "i", "ğ": "g", "ü": "u",
        "ş": "s", "ö": "o", "ç": "c",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def sahibinden_search_url(district, neighborhood=None):
    district_slug = sahibinden_slug(district)
    if neighborhood:
        neighborhood_slug = sahibinden_slug(neighborhood)
        # Search Scraper Pro için sade, yerel Türkçe Sahibinden arama URL'si.
        # Örnek: /satilik-daire/istanbul-kadikoy-suadiye
        return (
            "https://www.sahibinden.com/satilik-daire/"
            f"istanbul-{district_slug}-{neighborhood_slug}"
        )
    return (
        "https://www.sahibinden.com/satilik-daire/"
        f"istanbul-{district_slug}"
    )




@dataclass
class Listing:
    id: str
    district: str
    neighborhood: str
    title: str
    price: int
    gross_m2: int
    net_m2: int
    rooms: str
    listing_date: str
    building_age: int | None = None
    source: str = "demo"

    @property
    def gross_price_m2(self):
        return round(self.price / self.gross_m2) if self.price and self.gross_m2 else None

    @property
    def net_price_m2(self):
        return round(self.price / self.net_m2) if self.price and self.net_m2 else None

    def to_dict(self):
        d = asdict(self)
        d["gross_price_m2"] = self.gross_price_m2
        d["net_price_m2"] = self.net_price_m2
        return d


# =========================================================
# PostgreSQL — HLF PAS kalıcı ilan hafızası
# =========================================================

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()


def db_configured():
    return bool(DATABASE_URL)


def db_connect():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL tanımlı değil.")
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def init_db():
    """Tablolar yoksa otomatik oluşturur."""
    if not db_configured():
        return

    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS pas_listings (
                    id TEXT PRIMARY KEY,
                    district TEXT NOT NULL,
                    neighborhood TEXT NOT NULL,
                    title TEXT NOT NULL DEFAULT '',
                    price BIGINT,
                    gross_m2 INTEGER,
                    net_m2 INTEGER,
                    rooms TEXT NOT NULL DEFAULT '',
                    listing_date TEXT NOT NULL DEFAULT '',
                    building_age INTEGER,
                    source TEXT NOT NULL DEFAULT '',
                    url TEXT NOT NULL DEFAULT '',
                    active BOOLEAN NOT NULL DEFAULT TRUE,
                    first_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    last_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
            # Mevcut Railway/Postgres tablosu daha önce oluşturulduysa
            # bina yaşı kolonunu güvenli biçimde ekle.
            cur.execute("""
                ALTER TABLE pas_listings
                ADD COLUMN IF NOT EXISTS building_age INTEGER
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_pas_listings_location
                ON pas_listings (district, neighborhood)
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_pas_listings_active
                ON pas_listings (active)
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS pas_sync_state (
                    scope_key TEXT PRIMARY KEY,
                    district TEXT NOT NULL,
                    neighborhood TEXT NOT NULL,
                    last_sync TIMESTAMPTZ,
                    last_result_count INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT NOT NULL DEFAULT ''
                )
            """)
        conn.commit()


def _listing_matches_filters(row, filters):
    requested_rooms = str(filters.get("rooms") or "").strip()
    min_m2 = parse_int(filters.get("min_m2"))
    max_m2 = parse_int(filters.get("max_m2"))
    min_price = parse_int(filters.get("min_price"))
    max_price = parse_int(filters.get("max_price"))
    net_m2_min = parse_int(filters.get("net_m2_min"))
    net_m2_max = parse_int(filters.get("net_m2_max"))
    gross_m2_min = parse_int(filters.get("gross_m2_min"))
    gross_m2_max = parse_int(filters.get("gross_m2_max"))
    building_age_min = parse_int(filters.get("building_age_min"))
    building_age_max = parse_int(filters.get("building_age_max"))

    if requested_rooms and row.rooms and row.rooms != requested_rooms:
        return False
    if min_m2 is not None and (row.gross_m2 is None or row.gross_m2 < min_m2):
        return False
    if max_m2 is not None and (row.gross_m2 is None or row.gross_m2 > max_m2):
        return False
    if min_price is not None and (row.price is None or row.price < min_price):
        return False
    if max_price is not None and (row.price is None or row.price > max_price):
        return False

    if net_m2_min is not None:
        if not row.net_price_m2 or row.net_price_m2 < net_m2_min:
            return False
    if net_m2_max is not None:
        if not row.net_price_m2 or row.net_price_m2 > net_m2_max:
            return False
    if gross_m2_min is not None:
        if not row.gross_price_m2 or row.gross_price_m2 < gross_m2_min:
            return False
    if gross_m2_max is not None:
        if not row.gross_price_m2 or row.gross_price_m2 > gross_m2_max:
            return False

    if building_age_min is not None:
        if row.building_age is None or row.building_age < building_age_min:
            return False
    if building_age_max is not None:
        if row.building_age is None or row.building_age > building_age_max:
            return False

    return True


def save_listings_to_db(listings):
    """İlan no üzerinden upsert. Aynı ilan tekrar ücretli arama nedeni olmaz."""
    if not listings:
        return {"saved": 0, "new": 0, "updated": 0}

    init_db()
    new_count = 0
    updated_count = 0

    with db_connect() as conn:
        with conn.cursor() as cur:
            for item in listings:
                url = getattr(item, "_listing_url", "") or ""

                cur.execute(
                    "SELECT id FROM pas_listings WHERE id = %s",
                    (str(item.id),),
                )
                exists = cur.fetchone() is not None

                cur.execute("""
                    INSERT INTO pas_listings (
                        id, district, neighborhood, title, price,
                        gross_m2, net_m2, rooms, listing_date, building_age,
                        source, url, active, first_seen, last_seen, updated_at
                    )
                    VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, TRUE, NOW(), NOW(), NOW()
                    )
                    ON CONFLICT (id) DO UPDATE SET
                        district = EXCLUDED.district,
                        neighborhood = EXCLUDED.neighborhood,
                        title = EXCLUDED.title,
                        price = EXCLUDED.price,
                        gross_m2 = EXCLUDED.gross_m2,
                        net_m2 = EXCLUDED.net_m2,
                        rooms = EXCLUDED.rooms,
                        listing_date = EXCLUDED.listing_date,
                        building_age = EXCLUDED.building_age,
                        source = EXCLUDED.source,
                        url = CASE
                            WHEN EXCLUDED.url <> '' THEN EXCLUDED.url
                            ELSE pas_listings.url
                        END,
                        active = TRUE,
                        last_seen = NOW(),
                        updated_at = NOW()
                """, (
                    str(item.id),
                    item.district,
                    item.neighborhood,
                    item.title or "",
                    item.price,
                    item.gross_m2,
                    item.net_m2,
                    item.rooms or "",
                    item.listing_date or "",
                    item.building_age,
                    item.source or "",
                    url,
                ))

                if exists:
                    updated_count += 1
                else:
                    new_count += 1

        conn.commit()

    return {
        "saved": len(listings),
        "new": new_count,
        "updated": updated_count,
    }


def load_listings_from_db(filters):
    """Ana PAS araması: sadece PostgreSQL. Apify çağrısı YOK."""
    init_db()

    districts = filters.get("districts") or []
    selected_neighborhoods = filters.get("neighborhoods") or {}

    if not districts:
        return []

    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    id, district, neighborhood, title, price,
                    gross_m2, net_m2, rooms, listing_date, building_age, source, url
                FROM pas_listings
                WHERE active = TRUE
                  AND district = ANY(%s)
                ORDER BY listing_date DESC NULLS LAST, updated_at DESC
            """, (districts,))
            rows = cur.fetchall()

    requested_pairs = set()
    for district in districts:
        for neighborhood in selected_neighborhoods.get(district) or []:
            requested_pairs.add(
                (
                    sahibinden_slug(district),
                    sahibinden_slug(neighborhood),
                )
            )

    listings = []
    for row in rows:
        if requested_pairs:
            pair = (
                sahibinden_slug(row["district"]),
                sahibinden_slug(row["neighborhood"]),
            )
            if pair not in requested_pairs:
                continue

        item = Listing(
            id=str(row["id"]),
            district=row["district"] or "",
            neighborhood=row["neighborhood"] or "",
            title=row["title"] or "İlan",
            price=parse_int(row["price"]),
            gross_m2=parse_int(row["gross_m2"]),
            net_m2=parse_int(row["net_m2"]),
            rooms=row["rooms"] or "",
            listing_date=row["listing_date"] or "",
            building_age=parse_int(row["building_age"]),
            source=row["source"] or "cache",
        )
        item._listing_url = row["url"] or ""

        if _listing_matches_filters(item, filters):
            listings.append(item)

    return listings


def sync_scope_key(district, neighborhood):
    return f"{sahibinden_slug(district)}::{sahibinden_slug(neighborhood)}"


def record_sync_state(district, neighborhood, result_count=0, error=""):
    init_db()
    key = sync_scope_key(district, neighborhood)

    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO pas_sync_state (
                    scope_key, district, neighborhood,
                    last_sync, last_result_count, last_error
                )
                VALUES (%s, %s, %s, NOW(), %s, %s)
                ON CONFLICT (scope_key) DO UPDATE SET
                    district = EXCLUDED.district,
                    neighborhood = EXCLUDED.neighborhood,
                    last_sync = NOW(),
                    last_result_count = EXCLUDED.last_result_count,
                    last_error = EXCLUDED.last_error
            """, (key, district, neighborhood, result_count, error or ""))
        conn.commit()


def get_sync_state(district, neighborhood):
    if not db_configured():
        return None

    init_db()
    key = sync_scope_key(district, neighborhood)

    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT last_sync, last_result_count, last_error
                FROM pas_sync_state
                WHERE scope_key = %s
            """, (key,))
            row = cur.fetchone()

    if not row:
        return None

    last_sync = row["last_sync"]
    return {
        "last_sync": last_sync.isoformat() if last_sync else None,
        "last_result_count": row["last_result_count"],
        "last_error": row["last_error"],
    }


class DatabaseListingProvider:
    name = "postgresql"

    def configured(self):
        return db_configured()

    def search(self, filters):
        if not self.configured():
            raise RuntimeError("DATABASE_URL tanımlı değil.")
        return load_listings_from_db(filters)


class ListingProvider:
    """Veri kaynağı entegrasyonları için ortak arayüz."""

    name = "base"

    def search(self, filters):
        raise NotImplementedError


class DemoListingProvider(ListingProvider):
    """Gerçek veri çekmeden geliştirme/test için deterministik örnek ilan üretir."""

    name = "demo"

    def search(self, filters):
        districts = filters.get("districts") or []
        selected_neighborhoods = filters.get("neighborhoods") or {}
        requested_rooms = filters.get("rooms") or ""

        min_m2 = parse_int(filters.get("min_m2"))
        max_m2 = parse_int(filters.get("max_m2"))
        min_price = parse_int(filters.get("min_price"))
        max_price = parse_int(filters.get("max_price"))
        net_m2_min = parse_int(filters.get("net_m2_min"))
        net_m2_max = parse_int(filters.get("net_m2_max"))
        gross_m2_min = parse_int(filters.get("gross_m2_min"))
        gross_m2_max = parse_int(filters.get("gross_m2_max"))
        building_age_min = parse_int(filters.get("building_age_min"))
        building_age_max = parse_int(filters.get("building_age_max"))

        rows = []

        for district in districts:
            nbs = selected_neighborhoods.get(district) or NEIGHBORHOODS.get(district, [])[:5]
            base_m2 = DISTRICT_BASE_M2.get(district, 90000)

            for neighborhood in nbs:
                seed = stable_seed(f"{district}|{neighborhood}")
                rng = random.Random(seed)

                for i in range(8):
                    gross = rng.randint(55, 220)
                    net = max(40, round(gross * rng.uniform(0.78, 0.92)))
                    rooms = rng.choice(ROOMS)

                    neighborhood_factor = 0.88 + (stable_seed(neighborhood) % 30) / 100
                    listing_factor = rng.uniform(0.88, 1.18)
                    price_m2 = int(base_m2 * neighborhood_factor * listing_factor)
                    price = int(round((price_m2 * gross) / 50000) * 50000)

                    listed = date.today() - timedelta(days=rng.randint(0, 45))
                    building_age = rng.randint(0, 35)

                    row = Listing(
                        id=f"DEMO-{stable_seed(district + neighborhood + str(i))}",
                        district=district,
                        neighborhood=neighborhood,
                        title=f"{neighborhood} {rooms} {gross} m² daire",
                        price=price,
                        gross_m2=gross,
                        net_m2=net,
                        rooms=rooms,
                        listing_date=listed.isoformat(),
                        building_age=building_age,
                    )

                    if requested_rooms and requested_rooms != row.rooms:
                        continue
                    if min_m2 is not None and row.gross_m2 < min_m2:
                        continue
                    if max_m2 is not None and row.gross_m2 > max_m2:
                        continue
                    if min_price is not None and row.price < min_price:
                        continue
                    if max_price is not None and row.price > max_price:
                        continue
                    if net_m2_min is not None and row.net_price_m2 < net_m2_min:
                        continue
                    if net_m2_max is not None and row.net_price_m2 > net_m2_max:
                        continue
                    if gross_m2_min is not None and row.gross_price_m2 < gross_m2_min:
                        continue
                    if gross_m2_max is not None and row.gross_price_m2 > gross_m2_max:
                        continue
                    if building_age_min is not None and row.building_age < building_age_min:
                        continue
                    if building_age_max is not None and row.building_age > building_age_max:
                        continue

                    rows.append(row)

        return rows


class AuthorizedSahibindenProvider(ListingProvider):
    """Yetkili Sahibinden API bağlantısı için iskelet."""

    name = "authorized_sahibinden"

    def __init__(self):
        self.base_url = os.environ.get("SAHIBINDEN_API_BASE_URL", "").strip().rstrip("/")
        self.api_key = os.environ.get("SAHIBINDEN_API_KEY", "").strip()
        self.auth_scheme = os.environ.get("SAHIBINDEN_API_AUTH_SCHEME", "Bearer").strip()
        self.search_path = os.environ.get("SAHIBINDEN_API_SEARCH_PATH", "").strip()
        self.timeout = parse_int(os.environ.get("SAHIBINDEN_API_TIMEOUT", "15")) or 15

    def configured(self):
        return bool(self.base_url and self.api_key and self.search_path)

    def _headers(self):
        return {
            "Accept": "application/json",
            "Authorization": f"{self.auth_scheme} {self.api_key}".strip(),
            "User-Agent": "PAS/1.0",
        }

    def _request_json(self, url):
        req = Request(url, headers=self._headers(), method="GET")
        try:
            with urlopen(req, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise RuntimeError(f"Sahibinden API HTTP hatası: {exc.code}") from exc
        except URLError as exc:
            raise RuntimeError("Sahibinden API bağlantısı kurulamadı.") from exc
        except json.JSONDecodeError as exc:
            raise RuntimeError("Sahibinden API geçersiz JSON döndürdü.") from exc

    def _build_query(self, filters):
        from urllib.parse import urlencode

        params = {}
        districts = filters.get("districts") or []
        neighborhoods = filters.get("neighborhoods") or {}

        if districts:
            params["districts"] = ",".join(districts)

        flat_neighborhoods = []
        for district in districts:
            for nb in neighborhoods.get(district) or []:
                flat_neighborhoods.append(f"{district}:{nb}")

        if flat_neighborhoods:
            params["neighborhoods"] = "|".join(flat_neighborhoods)

        for key in [
            "rooms", "min_m2", "max_m2", "min_price", "max_price",
            "net_m2_min", "net_m2_max", "gross_m2_min", "gross_m2_max",
        ]:
            value = filters.get(key)
            if value not in (None, ""):
                params[key] = value

        return urlencode(params)

    def _normalize_item(self, item):
        def first(*keys, default=None):
            for key in keys:
                if key in item and item.get(key) not in (None, ""):
                    return item.get(key)
            return default

        district = str(first("district", "districtName", "ilce", default="")).strip()
        neighborhood = str(first("neighborhood", "neighborhoodName", "mahalle", default="")).strip()
        title = str(first("title", "listingTitle", "baslik", default="İlan")).strip()
        price = parse_int(first("price", "salePrice", "fiyat"))
        gross_m2 = parse_int(first("grossM2", "gross_m2", "brutM2", "areaGross"))
        net_m2 = parse_int(first("netM2", "net_m2", "netM2Value", "areaNet"))
        rooms = str(first("rooms", "roomCount", "oda", default="")).strip()
        listing_date = str(
            first("listingDate", "date", "createdAt", "ilanTarihi", default=date.today().isoformat())
        )[:10]
        listing_id = str(first("id", "listingId", "ilanNo", default=stable_seed(title + district)))

        if not district or not neighborhood or not price or not gross_m2 or not net_m2:
            return None

        return Listing(
            id=listing_id,
            district=district,
            neighborhood=neighborhood,
            title=title,
            price=price,
            gross_m2=gross_m2,
            net_m2=net_m2,
            rooms=rooms,
            listing_date=listing_date,
            source=self.name,
        )

    def search(self, filters):
        if not self.configured():
            raise RuntimeError("Yetkili Sahibinden API yapılandırması eksik.")

        url = f"{self.base_url}/{self.search_path.lstrip('/')}"
        query = self._build_query(filters)
        if query:
            url += "?" + query

        payload = self._request_json(url)
        raw_items = (
            payload.get("data")
            or payload.get("items")
            or payload.get("listings")
            or payload.get("results")
            or []
        )

        listings = []
        for item in raw_items:
            if isinstance(item, dict):
                normalized = self._normalize_item(item)
                if normalized:
                    listings.append(normalized)

        return listings


class ApifyListingProvider(ListingProvider):
    """
    HLF PAS güncelleme sağlayıcısı.

    Actor:
      clearpath~sahibinden-scraper-pro

    Maliyet/Test modu:
      enrichment=False
      includeDetails=False
      extractPhoneNumbers=False
      maxResults<=3

    Böylece yalnızca base/search-summary çıktısı kullanılır.
    Telefon ve enriched-detail add-on çağrılmaz.

    Normal PAS filtrelemesi Actor'ı çalıştırmaz.
    Actor yalnızca /api/sync ile, kullanıcının açıkça
    "Yeni ilanları güncelle" demesi halinde çalışır.
    """

    name = "apify_sync"
    ACTOR_ID = "clearpath~sahibinden-scraper-pro"

    def __init__(self):
        self.api_token = os.environ.get("APIFY_API_TOKEN", "").strip()
        self.actor_id = self.ACTOR_ID
        # TEST MODU: Sistem oturana kadar her güncellemede en fazla 3 ilan.
        # Daha sonra bu üst sınırı artırabiliriz.
        self.max_results = parse_int(
            os.environ.get("PAS_SYNC_MAX_RESULTS", "3")
        ) or 3
        self.max_results = max(1, min(self.max_results, 3))
        self.timeout = parse_int(os.environ.get("APIFY_TIMEOUT", "300")) or 300

    def configured(self):
        return bool(self.api_token)

    def _run_actor(self, actor_input):
        url = (
            f"https://api.apify.com/v2/acts/{self.actor_id}"
            "/run-sync-get-dataset-items"
            "?clean=true"
        )

        body = json.dumps(actor_input, ensure_ascii=False).encode("utf-8")

        req = Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": f"Bearer {self.api_token}",
                "User-Agent": "HLF-PAS/2.1",
            },
            method="POST",
        )

        try:
            with urlopen(req, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))

            if isinstance(payload, list):
                return payload
            if isinstance(payload, dict):
                return (
                    payload.get("items")
                    or payload.get("data")
                    or payload.get("results")
                    or []
                )
            return []

        except HTTPError as exc:
            try:
                detail = exc.read().decode("utf-8", errors="ignore")[:1200]
            except Exception:
                detail = ""
            raise RuntimeError(
                f"Apify HTTP hatası: {exc.code}. {detail}"
            ) from exc
        except URLError as exc:
            raise RuntimeError(
                f"Apify bağlantı hatası: {exc.reason}"
            ) from exc
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "Apify geçerli JSON döndürmedi."
            ) from exc

    @staticmethod
    def _pick(mapping, *keys):
        if not isinstance(mapping, dict):
            return None
        for key in keys:
            value = mapping.get(key)
            if value not in (None, ""):
                return value
        return None

    @staticmethod
    def _norm_key(value):
        text = str(value or "").casefold()
        replacements = {
            "ı": "i", "ğ": "g", "ü": "u",
            "ş": "s", "ö": "o", "ç": "c",
            "²": "2",
        }
        for src, dst in replacements.items():
            text = text.replace(src, dst)
        return re.sub(r"[^a-z0-9]+", "", text)

    def _attribute_value(self, item, *aliases):
        """
        Search-summary çıktısındaki farklı attribute şekillerinden
        Brüt m² / Net m² / Oda Sayısı gibi alanları bulur.
        """
        raw = item.get("rawSummary") if isinstance(item.get("rawSummary"), dict) else {}

        candidates = [
            item.get("summaryAttributes"),
            item.get("searchAttributes"),
            item.get("attributes"),
            raw.get("summaryAttributes"),
            raw.get("searchAttributes"),
            raw.get("attributes"),
        ]

        wanted = {self._norm_key(x) for x in aliases}

        for source in candidates:
            if isinstance(source, dict):
                for key, value in source.items():
                    if self._norm_key(key) in wanted and value not in (None, ""):
                        return value

            elif isinstance(source, list):
                for row in source:
                    if not isinstance(row, dict):
                        continue
                    key = (
                        row.get("name")
                        or row.get("label")
                        or row.get("title")
                        or row.get("key")
                    )
                    value = (
                        row.get("value")
                        or row.get("text")
                        or row.get("displayValue")
                    )
                    if self._norm_key(key) in wanted and value not in (None, ""):
                        return value

        return None

    def _normalize_item(self, item, fallback_district, fallback_neighborhood):
        raw = item.get("rawSummary") if isinstance(item.get("rawSummary"), dict) else {}

        location = item.get("location")
        if not isinstance(location, dict):
            location = {}

        address_obj = item.get("address")
        if not isinstance(address_obj, dict):
            address_obj = {}

        listing_id = str(
            self._pick(item, "id", "listingId", "adId", "classifiedId")
            or self._pick(raw, "id", "listingId", "adId", "classifiedId")
            or ""
        ).strip()

        listing_url = str(
            self._pick(item, "url", "listingUrl", "href", "sourceUrl")
            or self._pick(raw, "url", "listingUrl", "href", "sourceUrl")
            or ""
        ).strip()

        if listing_url.startswith("/"):
            listing_url = "https://www.sahibinden.com" + listing_url

        if not listing_id and listing_url:
            match = re.search(r"(\d{8,})", listing_url)
            if match:
                listing_id = match.group(1)

        title = str(
            self._pick(item, "title", "listingTitle", "adTitle")
            or self._pick(raw, "title", "listingTitle", "adTitle")
            or "İlan"
        ).strip()

        district = normalize_place_name(
            self._pick(item, "district", "districtName", "town", "ilce")
            or self._pick(raw, "district", "districtName", "town", "ilce")
            or self._pick(location, "district", "districtName", "town")
            or self._pick(address_obj, "district", "districtName", "town")
            or fallback_district
        )

        neighborhood = normalize_place_name(
            self._pick(
                item,
                "quarter", "neighborhood", "neighborhoodName", "mahalle"
            )
            or self._pick(
                raw,
                "quarter", "neighborhood", "neighborhoodName", "mahalle"
            )
            or self._pick(
                location,
                "quarter", "neighborhood", "neighborhoodName"
            )
            or self._pick(
                address_obj,
                "quarter", "neighborhood", "neighborhoodName"
            )
            or fallback_neighborhood
        )

        price = parse_int(
            self._pick(
                item,
                "price", "salePrice", "amount", "priceValue",
                "formattedPrice"
            )
            or self._pick(
                raw,
                "price", "salePrice", "amount", "priceValue",
                "formattedPrice"
            )
        )

        gross_m2 = parse_int(
            self._pick(
                item,
                "grossSize", "grossM2", "gross_m2", "grossSquareMeters",
                "areaGross", "size", "m2", "squareMeters"
            )
            or self._pick(
                raw,
                "grossSize", "grossM2", "gross_m2", "grossSquareMeters",
                "areaGross", "size", "m2", "squareMeters"
            )
            or self._attribute_value(
                item,
                "m² (Brüt)", "m2 (Brüt)", "Brüt m²", "Brüt m2",
                "Brüt", "m²", "m2"
            )
        )

        net_m2 = parse_int(
            self._pick(
                item,
                "netSize", "netM2", "net_m2", "netSquareMeters", "areaNet"
            )
            or self._pick(
                raw,
                "netSize", "netM2", "net_m2", "netSquareMeters", "areaNet"
            )
            or self._attribute_value(
                item,
                "m² (Net)", "m2 (Net)", "Net m²", "Net m2", "Net"
            )
        )

        rooms_value = (
            self._pick(item, "rooms", "roomCount", "room", "roomInfo")
            or self._pick(raw, "rooms", "roomCount", "room", "roomInfo")
            or self._attribute_value(
                item,
                "Oda Sayısı", "Oda", "Oda Sayisi", "roomCount", "rooms"
            )
            or ""
        )
        rooms = str(rooms_value).strip()

        building_age = parse_int(
            self._pick(
                item,
                "buildingAge", "building_age", "buildingAgeYears",
                "ageOfBuilding", "buildingYearAge"
            )
            or self._pick(
                raw,
                "buildingAge", "building_age", "buildingAgeYears",
                "ageOfBuilding", "buildingYearAge"
            )
            or self._attribute_value(
                item,
                "Bina Yaşı", "Bina Yasi", "Bina Yaşı (Yıl)",
                "Bina Yaşı (Yil)", "buildingAge", "Building Age"
            )
        )

        listed_at = str(
            self._pick(
                item,
                "listedAt", "listingDate", "createdAt", "date", "dateCreated"
            )
            or self._pick(
                raw,
                "listedAt", "listingDate", "createdAt", "date", "dateCreated"
            )
            or ""
        ).strip()
        listing_date = listed_at[:10] if listed_at else ""

        # Bir ilanı kaydetmek için kimlik ve fiyat temel olarak yeterlidir.
        # İlçe/mahalle, seçilen hedef mahalleden fallback edilir.
        if not listing_id or not price:
            return None

        listing = Listing(
            id=listing_id,
            district=district or fallback_district,
            neighborhood=neighborhood or fallback_neighborhood,
            title=title,
            price=price,
            gross_m2=gross_m2,
            net_m2=net_m2,
            rooms=rooms,
            listing_date=listing_date,
            building_age=building_age,
            source="sahibinden-scraper-pro",
        )
        listing._listing_url = listing_url
        return listing

    def sync_neighborhood(self, district, neighborhood):
        if not self.configured():
            raise RuntimeError("APIFY_API_TOKEN tanımlı değil.")

        start_url = sahibinden_search_url(district, neighborhood)

        # Search Scraper Pro maliyet güvenliği:
        # Güncel input şemasında `enrichment` varsayılan TRUE olduğundan
        # burada açıkça FALSE gönderiyoruz.
        actor_input = {
            "startUrls": [start_url],

            # ÖNEMLİ: Bu Actor'ın güncel şemasında `enrichment`
            # varsayılan olarak TRUE. Açık bırakılırsa detay + telefon
            # zenginleştirmesi ve ek maliyet devreye girebilir.
            # Test modunda kesin olarak kapatıyoruz.
            "enrichment": False,

            # Eski/yedek uyumluluk anahtarları da kapalı kalsın.
            "includeDetails": False,
            "extractPhoneNumbers": False,

            # Sistem oturana kadar maksimum 3 ilan.
            "maxResults": self.max_results,
        }

        raw_items = self._run_actor(actor_input)

        listings = []
        seen_ids = set()

        for item in raw_items:
            if not isinstance(item, dict):
                continue

            normalized = self._normalize_item(
                item,
                fallback_district=district,
                fallback_neighborhood=neighborhood,
            )
            if not normalized:
                continue

            # Actor gerçek konum döndürdüyse yanlış mahalleyi kabul etme.
            # Konum yoksa hedef mahalle fallback edildiği için kayıt korunur.
            actual_district = sahibinden_slug(normalized.district)
            actual_neighborhood = sahibinden_slug(normalized.neighborhood)

            if actual_district and actual_district != sahibinden_slug(district):
                continue
            if actual_neighborhood and actual_neighborhood != sahibinden_slug(neighborhood):
                continue

            if str(normalized.id) in seen_ids:
                continue

            seen_ids.add(str(normalized.id))
            listings.append(normalized)

        return listings

    def search(self, filters):
        raise RuntimeError(
            "Apify normal aramada kullanılmıyor. "
            "Yeni ilanlar için /api/sync kullanın."
        )

def build_provider():
    # HLF PAS v2: normal arama her zaman PostgreSQL kayıtlarından yapılır.
    if db_configured():
        return DatabaseListingProvider()

    # DATABASE_URL yoksa sistem bozulmasın diye demo fallback.
    return DemoListingProvider()


PROVIDER = build_provider()
APIFY_SYNC_PROVIDER = ApifyListingProvider()

try:
    init_db()
except Exception as _db_init_exc:
    print(f"HLF PAS DB init warning: {_db_init_exc}")


def percentile(values, p):
    if not values:
        return None
    vals = sorted(values)
    if len(vals) == 1:
        return vals[0]
    k = (len(vals) - 1) * p
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return vals[int(k)]
    return round(vals[f] * (c - k) + vals[c] * (k - f))


def analyze(listings):
    if not listings:
        return {
            "count": 0,
            "median_price": None,
            "avg_price": None,
            "median_gross_m2_price": None,
            "avg_gross_m2_price": None,
            "median_net_m2_price": None,
            "avg_net_m2_price": None,
            "avg_building_age": None,
            "q1_gross_m2_price": None,
            "q3_gross_m2_price": None,
            "by_neighborhood": [],
        }

    prices = [x.price for x in listings if x.price]
    m2s = [x.gross_price_m2 for x in listings if x.gross_price_m2]
    net_m2s = [x.net_price_m2 for x in listings if x.net_price_m2]
    building_ages = [
        x.building_age for x in listings
        if x.building_age is not None
    ]

    grouped = {}
    for x in listings:
        key = f"{x.district} · {x.neighborhood}"
        grouped.setdefault(key, []).append(x)

    by_neighborhood = []
    for key, rows in grouped.items():
        row_prices = [x.price for x in rows if x.price]
        row_m2s = [x.gross_price_m2 for x in rows if x.gross_price_m2]
        row_building_ages = [
            x.building_age for x in rows
            if x.building_age is not None
        ]
        if not row_prices or not row_m2s:
            continue
        by_neighborhood.append({
            "name": key,
            "count": len(rows),
            "median_price": round(statistics.median(row_prices)),
            "median_gross_m2_price": round(statistics.median(row_m2s)),
            "avg_building_age": (
                round(statistics.mean(row_building_ages), 1)
                if row_building_ages else None
            ),
        })

    by_neighborhood.sort(key=lambda x: x["median_gross_m2_price"], reverse=True)

    return {
        "count": len(listings),
        "median_price": round(statistics.median(prices)) if prices else None,
        "avg_price": round(statistics.mean(prices)) if prices else None,
        "median_gross_m2_price": round(statistics.median(m2s)) if m2s else None,
        "avg_gross_m2_price": round(statistics.mean(m2s)) if m2s else None,
        "median_net_m2_price": round(statistics.median(net_m2s)) if net_m2s else None,
        "avg_net_m2_price": round(statistics.mean(net_m2s)) if net_m2s else None,
        "avg_building_age": (
            round(statistics.mean(building_ages), 1)
            if building_ages else None
        ),
        "q1_gross_m2_price": percentile(m2s, 0.25),
        "q3_gross_m2_price": percentile(m2s, 0.75),
        "by_neighborhood": by_neighborhood,
    }


def opportunity_analysis(listings):
    if not listings:
        return []

    groups = {}
    for item in listings:
        groups.setdefault((item.district, item.neighborhood), []).append(item)

    result = []

    for item in listings:
        peers = groups[(item.district, item.neighborhood)]
        net_values = [x.net_price_m2 for x in peers if x.net_price_m2]
        gross_values = [x.gross_price_m2 for x in peers if x.gross_price_m2]

        median_net = statistics.median(net_values) if net_values else None
        median_gross = statistics.median(gross_values) if gross_values else None

        net_delta = (
            ((item.net_price_m2 / median_net) - 1) * 100
            if median_net and item.net_price_m2
            else None
        )
        gross_delta = (
            ((item.gross_price_m2 / median_gross) - 1) * 100
            if median_gross and item.gross_price_m2
            else None
        )

        deltas = [v for v in (net_delta, gross_delta) if v is not None]
        avg_delta = statistics.mean(deltas) if deltas else 0
        score = max(0, min(100, round(50 - avg_delta * 2)))

        if score >= 70:
            label = "Dikkat çekici"
        elif score >= 58:
            label = "Piyasanın altında"
        elif score <= 35:
            label = "Piyasanın üstünde"
        else:
            label = "Piyasa civarı"

        result.append({
            "id": item.id,
            "opportunity_score": score,
            "opportunity_label": label,
            "net_vs_neighborhood_pct": round(net_delta, 1) if net_delta is not None else None,
            "gross_vs_neighborhood_pct": round(gross_delta, 1) if gross_delta is not None else None,
        })

    return result


def provider_status():
    if isinstance(PROVIDER, DatabaseListingProvider):
        return {
            "mode": "postgresql",
            "configured": PROVIDER.configured(),
            "label": "HLF PAS kayıt sistemi · PostgreSQL",
        }

    return {
        "mode": "demo",
        "configured": True,
        "label": "Demo veri",
    }


PAGE = r"""
<!doctype html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>HLF PAS</title>
<style>
*{box-sizing:border-box}
body{margin:0;padding:14px;background:#f4f5f7;color:#18202b;font-family:Arial,Helvetica,sans-serif}
.container{max-width:900px;margin:auto}
h1{font-size:46px;margin:0}
.subtitle{color:#6b7280;margin:4px 0 18px}
.card{background:#fff;border-radius:18px;padding:16px;margin-bottom:14px;box-shadow:0 4px 18px rgba(0,0,0,.07)}
.title{font-size:19px;font-weight:800;margin-bottom:11px}
.small{font-size:13px;color:#6b7280}
.badge{display:inline-block;padding:5px 8px;border-radius:999px;background:#eef2f7;font-size:12px;font-weight:700}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.check{display:flex;align-items:center;gap:8px;padding:10px;border:1px solid #d9dde3;border-radius:11px;background:#fff}
.check input{width:18px;height:18px}
.favorite{background:#fffaf0;border:1px solid #eadfbe;border-radius:12px;padding:11px;margin-bottom:10px}
.segmented{display:grid;grid-template-columns:repeat(3,1fr);gap:7px;margin-bottom:12px}
.seg input{display:none}
.seg span{display:block;text-align:center;padding:11px 5px;border:1px solid #d9dde3;border-radius:10px;font-weight:700}
.seg input:checked+span{background:#1f2937;color:white;border-color:#1f2937}
details{border:1px solid #d9dde3;border-radius:12px;padding:0 11px;margin-top:9px}
summary{padding:11px 0;font-weight:800;cursor:pointer}
.neighborhood-box{border:1px solid #d9dde3;border-radius:12px;margin-top:10px;overflow:hidden}
.neighborhood-head{background:#f2f3f5;padding:10px 12px;font-weight:800;display:flex;justify-content:space-between}
.neighborhoods{padding:9px;display:grid;grid-template-columns:1fr 1fr;gap:7px}
label.field{display:block;font-weight:800;margin:10px 0 5px}
input[type=number],input[type=text],select{width:100%;padding:11px;border:1px solid #d9dde3;border-radius:10px;font-size:16px}
.pair{display:grid;grid-template-columns:1fr 1fr;gap:9px}
.primary{width:100%;margin-top:14px;padding:15px;border:0;border-radius:11px;background:#181818;color:#fff;font-size:18px;font-weight:800}
.primary:disabled{opacity:.55}
.secondary{width:100%;margin-top:9px;padding:13px;border:1px solid #ccd2da;border-radius:11px;background:#fff;color:#18202b;font-size:16px;font-weight:800}
.secondary:disabled{opacity:.55}
.sync-note{margin-top:8px;font-size:12px;color:#6b7280}
.hidden{display:none!important}
.metrics{display:grid;grid-template-columns:repeat(2,1fr);gap:8px}
.metric{padding:12px;border:1px solid #e1e5ea;border-radius:12px}
.metric .k{font-size:12px;color:#6b7280}
.metric .v{font-size:20px;font-weight:800;margin-top:3px}
.table-wrap{overflow-x:auto}
a{cursor:pointer}
.listing-clickable{cursor:pointer}
.listing-clickable:hover{background:#f7f8fa}
.open-listing{font-size:12px;font-weight:700;text-decoration:underline}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{padding:10px 8px;border-bottom:1px solid #eceff3;text-align:left;white-space:nowrap}
th{font-size:12px;color:#6b7280}
.notice{background:#eef6ff;border:1px solid #cfe3ff;border-radius:10px;padding:10px;font-size:13px}
.error{background:#fff1f1;border:1px solid #f4c4c4;border-radius:10px;padding:10px;font-size:13px}
@media(max-width:600px){
 .grid,.neighborhoods,.pair,.metrics{grid-template-columns:1fr 1fr}
}
</style>
</head>
<body>
<div class="container">
<h1>HLF PAS</h1>
<div class="subtitle">Piyasa Arama Sistemi <span class="small">v2.4-test3</span></div>

<div class="card">
<div class="notice">
<strong>Veri sağlayıcı:</strong> {{ provider_status.label }}.
{% if provider_status.mode == "postgresql" %}
Normal aramalar kayıtlı veriden yapılır ve Apify ücreti oluşturmaz.
Yeni ilanlar yalnızca "Yeni ilanları güncelle" düğmesiyle alınır.
{% else %}
Şu an demo veri kullanılıyor.
{% endif %}
</div>
</div>

<form id="pasForm">
<div class="card">
<div class="title">Bölge seçimi</div>

<div class="segmented">
<label class="seg"><input type="radio" name="side" value="all" checked><span>Tümü</span></label>
<label class="seg"><input type="radio" name="side" value="anadolu"><span>Anadolu</span></label>
<label class="seg"><input type="radio" name="side" value="avrupa"><span>Avrupa</span></label>
</div>

<div class="favorite">
<strong>★ Favoriler</strong>
<div id="favorites" class="grid" style="margin-top:8px"></div>
</div>

<details>
<summary>11 İlçe</summary>
<div id="districts" class="grid" style="padding-bottom:10px"></div>
</details>

<div id="neighborhoodArea"></div>
</div>

<div class="card">
<div class="title">İlan filtreleri</div>

<div class="pair">
<div><label class="field">Min m²</label><input name="min_m2" type="number" min="0"></div>
<div><label class="field">Max m²</label><input name="max_m2" type="number" min="0"></div>
</div>

<div class="pair">
<div><label class="field">Min Fiyat</label><input name="min_price" type="number" min="0"></div>
<div><label class="field">Max Fiyat</label><input name="max_price" type="number" min="0"></div>
</div>

<div class="pair">
<div><label class="field">Min Bina Yaşı</label><input name="building_age_min" type="number" min="0"></div>
<div><label class="field">Max Bina Yaşı</label><input name="building_age_max" type="number" min="0"></div>
</div>

<details>
<summary>Net m² satış fiyatı</summary>
<div class="pair" style="padding-bottom:10px">
<div><label class="field">Min TL/m²</label><input name="net_m2_min" type="number" min="0"></div>
<div><label class="field">Max TL/m²</label><input name="net_m2_max" type="number" min="0"></div>
</div>
</details>

<details>
<summary>Brüt m² satış fiyatı</summary>
<div class="pair" style="padding-bottom:10px">
<div><label class="field">Min TL/m²</label><input name="gross_m2_min" type="number" min="0"></div>
<div><label class="field">Max TL/m²</label><input name="gross_m2_max" type="number" min="0"></div>
</div>
</details>

<label class="field">Oda Sayısı</label>
<select name="rooms">
<option value="">Farketmez</option>
<option>1+1</option>
<option>2+1</option>
<option>3+1</option>
<option>4+1</option>
<option>5+1 ve üzeri</option>
</select>

<button class="primary" id="searchButton" type="submit">Kayıtlı İlanları Analiz Et</button>
<button class="secondary" id="syncButton" type="button">Yeni İlanları Güncelle (Apify)</button>
<div class="sync-note">Normal analiz ücretsizdir. Güncelleme yalnızca seçili tek mahalle için Apify kullanır.</div>
</div>
</form>

<div id="errorBox" class="card hidden"><div class="error" id="errorText"></div></div>
<div id="syncBox" class="card hidden"><div class="notice" id="syncText"></div></div>

<div id="resultsCard" class="card hidden">
<div class="title">Piyasa özeti <span class="badge" id="providerBadge"></span></div>
<div class="metrics">
<div class="metric"><div class="k">İlan sayısı</div><div class="v" id="mCount">-</div></div>
<div class="metric"><div class="k">Medyan fiyat</div><div class="v" id="mMedianPrice">-</div></div>
<div class="metric"><div class="k">Ort. fiyat</div><div class="v" id="mAvgPrice">-</div></div>
<div class="metric"><div class="k">Medyan brüt TL/m²</div><div class="v" id="mMedianM2">-</div></div>
<div class="metric"><div class="k">Medyan net TL/m²</div><div class="v" id="mMedianNetM2">-</div></div>
<div class="metric"><div class="k">Ort. bina yaşı</div><div class="v" id="mAvgBuildingAge">-</div></div>
</div>

<div class="title" style="margin-top:16px">Mahalle karşılaştırması</div>
<div class="table-wrap">
<table>
<thead><tr><th>Bölge</th><th>İlan</th><th>Medyan fiyat</th><th>Medyan TL/m²</th><th>Ort. bina yaşı</th></tr></thead>
<tbody id="neighborhoodStats"></tbody>
</table>
</div>

<div class="title" style="margin-top:16px">İlanlar</div>
<div class="table-wrap">
<table>
<thead><tr><th>Mahalle</th><th>Oda</th><th>Bina yaşı</th><th>Brüt</th><th>Net</th><th>Fiyat</th><th>Brüt TL/m²</th><th>Net TL/m²</th><th>Mahalleye göre</th><th>PAS puanı</th><th>Tarih</th></tr></thead>
<tbody id="listingRows"></tbody>
</table>
</div>
</div>
</div>

<script>
const DISTRICTS={{ districts_json|safe }};
const NEIGHBORHOODS={{ neighborhoods_json|safe }};
let selectedDistricts=new Set();
let selectedNeighborhoods={};

function esc(s){
 return String(s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
}
function fmtMoney(n){
 if(n===null||n===undefined)return "-";
 return new Intl.NumberFormat("tr-TR").format(n)+" ₺";
}
function sideValue(){
 return document.querySelector('input[name="side"]:checked')?.value||"all";
}
function districtHtml(d){
 const checked=selectedDistricts.has(d.name)?"checked":"";
 return `<label class="check"><input class="districtCheck" type="checkbox" value="${esc(d.name)}" ${checked}><span>${esc(d.name)}${d.favorite?" ★":""}</span></label>`;
}
function renderDistricts(){
 const side=sideValue();
 const visible=DISTRICTS.filter(d=>side==="all"||d.side===side);
 document.getElementById("districts").innerHTML=visible.map(districtHtml).join("");
 document.getElementById("favorites").innerHTML=visible.filter(d=>d.favorite).map(districtHtml).join("");
 bindDistricts();
}
function syncCopies(name,checked){
 document.querySelectorAll(".districtCheck").forEach(cb=>{if(cb.value===name)cb.checked=checked});
}
function slugDom(s){
 return s.toLocaleLowerCase("tr-TR").normalize("NFD").replace(/[\u0300-\u036f]/g,"").replace(/[^a-z0-9]+/g,"-");
}
function bindDistricts(){
 document.querySelectorAll(".districtCheck").forEach(cb=>{
  cb.onchange=()=>{
   syncCopies(cb.value,cb.checked);
   if(cb.checked){
    selectedDistricts.add(cb.value);
    renderNeighborhoodBlock(cb.value);
   }else{
    selectedDistricts.delete(cb.value);
    document.getElementById("nb-"+slugDom(cb.value))?.remove();
    syncSelectedNeighborhoods();
   }
  };
 });
}
function syncSelectedNeighborhoods(){
 const fresh={};
 selectedDistricts.forEach(district=>{
  const wrap=document.getElementById("nb-"+slugDom(district));
  if(!wrap){
   fresh[district]=[];
   return;
  }
  fresh[district]=[...wrap.querySelectorAll(".neighborhoodCheck:checked")].map(x=>x.value);
 });
 selectedNeighborhoods=fresh;
}

function renderNeighborhoodBlock(district){
 const id="nb-"+slugDom(district);
 const existing=document.getElementById(id);
 if(existing){
  existing.remove();
 }
 const list=NEIGHBORHOODS[district]||[];
 const selected=new Set(selectedNeighborhoods[district]||[]);
 const wrap=document.createElement("div");
 wrap.className="neighborhood-box";
 wrap.id=id;
 wrap.innerHTML=`
  <div class="neighborhood-head"><span>${esc(district)} mahalleleri</span><span class="small">${list.length} seçenek</span></div>
  <div class="neighborhoods">
   ${list.map(n=>`<label class="check"><input class="neighborhoodCheck" type="checkbox" value="${esc(n)}" ${selected.has(n)?"checked":""}><span>${esc(n)}</span></label>`).join("")}
  </div>
 `;
 document.getElementById("neighborhoodArea").appendChild(wrap);
 wrap.querySelectorAll(".neighborhoodCheck").forEach(cb=>{
  cb.onchange=()=>{
   syncSelectedNeighborhoods();
  };
 });
 syncSelectedNeighborhoods();
}

document.querySelectorAll('input[name="side"]').forEach(el=>{
 el.addEventListener("change",renderDistricts);
});

// iPhone/Safari uyumluluğu:
// fetch() yerine XMLHttpRequest kullanıyoruz. Bazı Safari sürümlerinde
// fetch(relativeUrl, options) DOMException:
// "The string did not match the expected pattern." üretebiliyor.
function postJson(path,payload){
 return new Promise((resolve,reject)=>{
  try{
   const xhr=new XMLHttpRequest();
   const url=window.location.origin + path;
   xhr.open("POST",url,true);
   xhr.setRequestHeader("Content-Type","application/json; charset=UTF-8");
   xhr.setRequestHeader("Accept","application/json");
   xhr.onreadystatechange=()=>{
    if(xhr.readyState!==4)return;
    let data={};
    try{
     data=xhr.responseText ? JSON.parse(xhr.responseText) : {};
    }catch(parseErr){
     reject(new Error("Sunucu geçerli JSON döndürmedi. HTTP "+xhr.status));
     return;
    }
    resolve({ok:xhr.status>=200&&xhr.status<300,status:xhr.status,data});
   };
   xhr.onerror=()=>reject(new Error("Sunucuya bağlantı kurulamadı."));
   xhr.ontimeout=()=>reject(new Error("İstek zaman aşımına uğradı."));
   xhr.timeout=360000;
   xhr.send(JSON.stringify(payload));
  }catch(err){
   reject(new Error("İstek hazırlanamadı: "+(err.message||String(err))));
  }
 });
}

document.getElementById("pasForm").addEventListener("submit",async e=>{
 e.preventDefault();
 const errorBox=document.getElementById("errorBox");
 const resultsCard=document.getElementById("resultsCard");
 errorBox.classList.add("hidden");

 if(selectedDistricts.size===0){
  document.getElementById("errorText").textContent="En az bir ilçe seçin.";
  errorBox.classList.remove("hidden");
  return;
 }

 const button=document.getElementById("searchButton");
 const oldText=button.textContent;
 button.disabled=true;
 button.textContent="Veriler hazırlanıyor…";

 syncSelectedNeighborhoods();
 const formData=new FormData(e.target);
 const payload={
  districts:[...selectedDistricts],
  neighborhoods:selectedNeighborhoods,
  rooms:formData.get("rooms")||"",
  min_m2:formData.get("min_m2")||"",
  max_m2:formData.get("max_m2")||"",
  min_price:formData.get("min_price")||"",
  max_price:formData.get("max_price")||"",
  building_age_min:formData.get("building_age_min")||"",
  building_age_max:formData.get("building_age_max")||"",
  net_m2_min:formData.get("net_m2_min")||"",
  net_m2_max:formData.get("net_m2_max")||"",
  gross_m2_min:formData.get("gross_m2_min")||"",
  gross_m2_max:formData.get("gross_m2_max")||""
 };

 try{
  const result=await postJson("/api/search",payload);
  const data=result.data;
  if(!result.ok||!data.ok)throw new Error(data.error||("Arama başarısız. HTTP "+result.status));

  document.getElementById("providerBadge").textContent=data.provider;
  document.getElementById("mCount").textContent=data.analysis.count;
  document.getElementById("mMedianPrice").textContent=fmtMoney(data.analysis.median_price);
  document.getElementById("mAvgPrice").textContent=fmtMoney(data.analysis.avg_price);
  document.getElementById("mMedianM2").textContent=fmtMoney(data.analysis.median_gross_m2_price);
  document.getElementById("mMedianNetM2").textContent=fmtMoney(data.analysis.median_net_m2_price);
  document.getElementById("mAvgBuildingAge").textContent=
   data.analysis.avg_building_age==null ? "-" : data.analysis.avg_building_age+" yıl";

  document.getElementById("neighborhoodStats").innerHTML=
   data.analysis.by_neighborhood.map(r=>`
    <tr>
     <td>${esc(r.name)}</td>
     <td>${r.count}</td>
     <td>${fmtMoney(r.median_price)}</td>
     <td>${fmtMoney(r.median_gross_m2_price)}</td>
     <td>${r.avg_building_age==null?"-":r.avg_building_age+" yıl"}</td>
    </tr>
   `).join("");

  document.getElementById("listingRows").innerHTML=
   data.listings.map(r=>{
    const href = r.url ? esc(String(r.url)) : "";
    const place = `${esc(r.district)} · ${esc(r.neighborhood)}`;
    const openText = href ? `<span class="open-listing">İlanı aç ↗</span>` : "";

    return `
    <tr class="${href?"listing-clickable":""}" ${href?`data-url="${href}"`:""}>
     <td><strong>${place}</strong><div class="small">${openText}</div></td>
     <td>${esc(r.rooms)}</td>
     <td>${r.building_age==null?"-":r.building_age+" yıl"}</td>
     <td>${r.gross_m2==null?"-":r.gross_m2+" m²"}</td>
     <td>${r.net_m2==null?"-":r.net_m2+" m²"}</td>
     <td>${fmtMoney(r.price)}</td>
     <td>${fmtMoney(r.gross_price_m2)}</td>
     <td>${fmtMoney(r.net_price_m2)}</td>
     <td>${r.net_vs_neighborhood_pct==null?"-":(r.net_vs_neighborhood_pct>0?"+":"")+r.net_vs_neighborhood_pct+"%"}</td>
     <td><strong>${r.opportunity_score ?? "-"}</strong><div class="small">${esc(r.opportunity_label||"")}</div></td>
     <td>${esc(r.listing_date)}</td>
    </tr>
   `;
   }).join("");

  document.querySelectorAll("#listingRows tr.listing-clickable").forEach(tr=>{
   tr.addEventListener("click",()=>{
    const url=tr.dataset.url;
    if(url){
     window.location.assign(url);
    }
   });
  });

  resultsCard.classList.remove("hidden");
 }catch(err){
  document.getElementById("errorText").textContent=err.message||"Beklenmeyen hata.";
  errorBox.classList.remove("hidden");
 }finally{
  button.disabled=false;
  button.textContent=oldText;
 }
});


document.getElementById("syncButton").addEventListener("click",async ()=>{
 const errorBox=document.getElementById("errorBox");
 const syncBox=document.getElementById("syncBox");
 errorBox.classList.add("hidden");
 syncBox.classList.add("hidden");

 syncSelectedNeighborhoods();

 const districts=[...selectedDistricts];
 const selectedPairs=[];
 districts.forEach(d=>{
  (selectedNeighborhoods[d]||[]).forEach(n=>selectedPairs.push([d,n]));
 });

 if(selectedPairs.length!==1){
  document.getElementById("errorText").textContent=
   "Güncelleme için tam olarak 1 mahalle seçin. Bu, gereksiz Apify maliyetini önler.";
  errorBox.classList.remove("hidden");
  return;
 }

 const [district,neighborhood]=selectedPairs[0];
 const button=document.getElementById("syncButton");
 const oldText=button.textContent;
 button.disabled=true;
 button.textContent="Yeni ilanlar kontrol ediliyor…";

 try{
  const result=await postJson("/api/sync",{district,neighborhood});
  const data=result.data;
  if(!result.ok||!data.ok)throw new Error(data.error||("Güncelleme başarısız. HTTP "+result.status));

  document.getElementById("syncText").textContent=
   `${district} · ${neighborhood}: ${data.received} sonuç alındı, `+
   `${data.new} yeni ilan eklendi, ${data.updated} mevcut ilan güncellendi.`;
  syncBox.classList.remove("hidden");

  // Safari/iPhone uyumluluğu:
  // Sync başarılı olduktan sonra formu otomatik tetiklemiyoruz.
  // Kullanıcı "Kayıtlı İlanları Analiz Et" düğmesine basarak
  // veritabanındaki güncel kayıtları analiz eder.
 }catch(err){
  document.getElementById("errorText").textContent=err.message||"Güncelleme hatası.";
  errorBox.classList.remove("hidden");
 }finally{
  button.disabled=false;
  button.textContent=oldText;
 }
});

renderDistricts();
</script>
</body>
</html>
"""


@app.route("/", methods=["GET", "POST"])
def home():
    return render_template_string(
        PAGE,
        districts_json=json.dumps(DISTRICTS, ensure_ascii=False),
        neighborhoods_json=json.dumps(NEIGHBORHOODS, ensure_ascii=False),
        provider_status=provider_status(),
    )


@app.post("/api/search")
def api_search():
    try:
        payload = request.get_json(silent=True) or {}
        districts = payload.get("districts") or []

        allowed = {d["name"] for d in DISTRICTS}
        districts = [d for d in districts if d in allowed]

        if not districts:
            return jsonify({
                "ok": False,
                "error": "Geçerli bir ilçe seçilmedi."
            }), 400

        raw_neighborhoods = payload.get("neighborhoods") or {}
        neighborhoods = {}

        for district in districts:
            allowed_nbs = set(NEIGHBORHOODS.get(district, []))
            requested = raw_neighborhoods.get(district) or []
            neighborhoods[district] = [
                n for n in requested if n in allowed_nbs
            ]

        filters = {
            "districts": districts,
            "neighborhoods": neighborhoods,
            "rooms": payload.get("rooms", ""),
            "min_m2": payload.get("min_m2", ""),
            "max_m2": payload.get("max_m2", ""),
            "min_price": payload.get("min_price", ""),
            "max_price": payload.get("max_price", ""),
            "building_age_min": payload.get("building_age_min", ""),
            "building_age_max": payload.get("building_age_max", ""),
            "net_m2_min": payload.get("net_m2_min", ""),
            "net_m2_max": payload.get("net_m2_max", ""),
            "gross_m2_min": payload.get("gross_m2_min", ""),
            "gross_m2_max": payload.get("gross_m2_max", ""),
        }

        listings = PROVIDER.search(filters)
        analysis = analyze(listings)
        opportunity = opportunity_analysis(listings)
        opportunity_by_id = {str(x["id"]): x for x in opportunity}

        listing_rows = []
        for item in listings:
            row = item.to_dict()
            row.update(opportunity_by_id.get(str(item.id), {}))
            row["url"] = getattr(item, "_listing_url", "")
            listing_rows.append(row)

        listing_rows.sort(
            key=lambda x: (
                x.get("opportunity_score") or 0,
                x.get("listing_date") or "",
            ),
            reverse=True,
        )

        sync_states = []
        for district in districts:
            for neighborhood in neighborhoods.get(district) or []:
                state = get_sync_state(district, neighborhood)
                if state:
                    sync_states.append({
                        "district": district,
                        "neighborhood": neighborhood,
                        **state,
                    })

        return jsonify({
            "ok": True,
            "provider": "kayıt",
            "analysis": analysis,
            "listings": listing_rows,
            "sync_states": sync_states,
            "database_configured": db_configured(),
        })

    except Exception as exc:
        return jsonify({
            "ok": False,
            "error": f"Kayıtlı veri hazırlanırken hata oluştu: {exc}"
        }), 500


@app.post("/api/sync")
def api_sync():
    """
    ÜCRETLİ işlem: yalnızca kullanıcının açıkça bastığı
    'Yeni İlanları Güncelle' düğmesiyle çalışır.
    """
    payload = request.get_json(silent=True) or {}
    district = str(payload.get("district") or "").strip()
    neighborhood = str(payload.get("neighborhood") or "").strip()

    allowed_districts = {d["name"] for d in DISTRICTS}
    if district not in allowed_districts:
        return jsonify({"ok": False, "error": "Geçersiz ilçe."}), 400

    if neighborhood not in set(NEIGHBORHOODS.get(district, [])):
        return jsonify({"ok": False, "error": "Geçersiz mahalle."}), 400

    try:
        listings = APIFY_SYNC_PROVIDER.sync_neighborhood(
            district, neighborhood
        )

        result = save_listings_to_db(listings)
        record_sync_state(
            district,
            neighborhood,
            result_count=len(listings),
            error="",
        )

        return jsonify({
            "ok": True,
            "district": district,
            "neighborhood": neighborhood,
            "received": len(listings),
            **result,
            "sync_limit": APIFY_SYNC_PROVIDER.max_results,
        })

    except Exception as exc:
        try:
            record_sync_state(
                district,
                neighborhood,
                result_count=0,
                error=str(exc)[:700],
            )
        except Exception:
            pass

        return jsonify({
            "ok": False,
            "error": (
                "Yeni ilan güncellemesi yapılamadı: "
                f"{exc}. Kayıtlı PAS verileri etkilenmedi."
            ),
        }), 502


@app.get("/api/provider-status")
def api_provider_status():
    return jsonify({
        "ok": True,
        **provider_status(),
        "database_configured": db_configured(),
        "sync_actor_id": APIFY_SYNC_PROVIDER.actor_id,
        "sync_max_results": APIFY_SYNC_PROVIDER.max_results,
        "sync_enrichment": False,
        "normal_search_uses_apify": False,
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
