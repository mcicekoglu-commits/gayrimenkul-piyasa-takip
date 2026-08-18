import os
import re
import json
import math
import statistics
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from dataclasses import dataclass, asdict

from flask import Flask, request, render_template_string, jsonify
import psycopg
from psycopg.rows import dict_row

app = Flask(__name__)

# =========================================================
# HLF PAS v3.4 — Real Estate Actor'a geri dönüş
#
# Railway Variables:
#   DATABASE_URL=...
#   APIFY_API_TOKEN=...
#   APIFY_TIMEOUT=300   (opsiyonel)
#
# Güvenlik:
#   - Canlı güncelleme ilçe bazında; mahalle PostgreSQL'de filtrelenir
#   - extractPhoneNumbers = false
#   - API maxItems = 1
#   - API maxTotalChargeUsd = 0.10
#
# Önemli:
#   clearpath/sahibinden-real-estate Actor'ının güncel resmi input
#   şemasında city ve district var, mahalle filtresi YOK.
#   Bu yüzden canlı test ilçe bazında 1 ilan çeker ve seçilen mahalleyle
#   eşleşirse kaydeder; eşleşmezse DB'ye yazmaz.
#
#   Geçmiş başarılı Real Estate run'ları ise ücretsiz olarak okunup
#   seçilen mahalleye göre PostgreSQL'e aktarılabilir.
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

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
APIFY_API_TOKEN = os.environ.get("APIFY_API_TOKEN", "").strip()
APIFY_TIMEOUT = int(os.environ.get("APIFY_TIMEOUT", "300") or 300)

# ÇALIŞAN ESKİ ACTOR
ACTOR_ID = "clearpath~sahibinden-real-estate"

# Şimdilik kesin test limiti
SYNC_MAX_RESULTS = 1
SYNC_MAX_CHARGE_USD = 0.10


def parse_int(value):
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)

    text = re.sub(r"[^\d,.\-]", "", str(value).strip())
    if not text:
        return None

    try:
        if "," in text and "." in text:
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
    except Exception:
        return None


def normalize_place(value):
    text = str(value or "").strip()
    text = re.sub(r"\s+(Mahallesi|Mah\.|Mh\.|Mah|Mh)$", "", text, flags=re.I)
    return text.strip()


def slug(value):
    text = normalize_place(value).casefold()
    for a, b in {"ı":"i","ğ":"g","ü":"u","ş":"s","ö":"o","ç":"c"}.items():
        text = text.replace(a, b)
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


@dataclass
class Listing:
    id: str
    district: str
    neighborhood: str
    title: str
    price: int | None
    gross_m2: int | None
    net_m2: int | None
    rooms: str
    listing_date: str
    building_age: int | None = None
    source: str = "sahibinden-real-estate"

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
# PostgreSQL
# =========================================================

def db_configured():
    return bool(DATABASE_URL)


def db_connect():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL tanımlı değil.")
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def init_db():
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
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_pas_listings_location
                ON pas_listings (district, neighborhood)
            """)
        conn.commit()


def save_listings_to_db(listings):
    if not listings:
        return {"saved": 0, "new": 0, "updated": 0}

    init_db()
    new_count = 0
    updated_count = 0

    with db_connect() as conn:
        with conn.cursor() as cur:
            for item in listings:
                url = getattr(item, "_listing_url", "") or ""

                cur.execute("SELECT 1 FROM pas_listings WHERE id=%s", (str(item.id),))
                exists = cur.fetchone() is not None

                cur.execute("""
                    INSERT INTO pas_listings (
                        id,district,neighborhood,title,price,gross_m2,net_m2,
                        rooms,listing_date,building_age,source,url,active,
                        first_seen,last_seen,updated_at
                    )
                    VALUES (
                        %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,TRUE,
                        NOW(),NOW(),NOW()
                    )
                    ON CONFLICT (id) DO UPDATE SET
                        district=EXCLUDED.district,
                        neighborhood=EXCLUDED.neighborhood,
                        title=EXCLUDED.title,
                        price=EXCLUDED.price,
                        gross_m2=COALESCE(EXCLUDED.gross_m2,pas_listings.gross_m2),
                        net_m2=COALESCE(EXCLUDED.net_m2,pas_listings.net_m2),
                        rooms=CASE WHEN EXCLUDED.rooms<>'' THEN EXCLUDED.rooms ELSE pas_listings.rooms END,
                        listing_date=CASE WHEN EXCLUDED.listing_date<>'' THEN EXCLUDED.listing_date ELSE pas_listings.listing_date END,
                        building_age=COALESCE(EXCLUDED.building_age,pas_listings.building_age),
                        source=EXCLUDED.source,
                        url=CASE WHEN EXCLUDED.url<>'' THEN EXCLUDED.url ELSE pas_listings.url END,
                        active=TRUE,
                        last_seen=NOW(),
                        updated_at=NOW()
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

    return {"saved": len(listings), "new": new_count, "updated": updated_count}


def record_sync_state(district, neighborhood, result_count=0, error=""):
    if not db_configured():
        return

    init_db()
    key = f"{slug(district)}::{slug(neighborhood)}"

    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO pas_sync_state (
                    scope_key,district,neighborhood,last_sync,last_result_count,last_error
                )
                VALUES (%s,%s,%s,NOW(),%s,%s)
                ON CONFLICT (scope_key) DO UPDATE SET
                    district=EXCLUDED.district,
                    neighborhood=EXCLUDED.neighborhood,
                    last_sync=NOW(),
                    last_result_count=EXCLUDED.last_result_count,
                    last_error=EXCLUDED.last_error
            """, (key, district, neighborhood, result_count, error or ""))
        conn.commit()


def listing_matches_filters(row, filters):
    room = str(filters.get("rooms") or "").strip()
    if room and row.rooms != room:
        return False

    comparisons = (
        ("gross_m2", "min_m2", ">="),
        ("gross_m2", "max_m2", "<="),
        ("price", "min_price", ">="),
        ("price", "max_price", "<="),
        ("building_age", "building_age_min", ">="),
        ("building_age", "building_age_max", "<="),
    )

    for field, key, op in comparisons:
        wanted = parse_int(filters.get(key))
        if wanted is None:
            continue
        actual = getattr(row, field)
        if actual is None:
            return False
        if op == ">=" and actual < wanted:
            return False
        if op == "<=" and actual > wanted:
            return False

    for prop, lo_key, hi_key in (
        ("gross_price_m2", "gross_m2_min", "gross_m2_max"),
        ("net_price_m2", "net_m2_min", "net_m2_max"),
    ):
        actual = getattr(row, prop)
        lo = parse_int(filters.get(lo_key))
        hi = parse_int(filters.get(hi_key))
        if lo is not None and (actual is None or actual < lo):
            return False
        if hi is not None and (actual is None or actual > hi):
            return False

    return True


def load_listings_from_db(filters):
    if not db_configured():
        return []

    init_db()
    districts = filters.get("districts") or []
    selected_nbs = filters.get("neighborhoods") or {}

    if not districts:
        return []

    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id,district,neighborhood,title,price,gross_m2,net_m2,
                       rooms,listing_date,building_age,source,url
                FROM pas_listings
                WHERE active=TRUE AND district=ANY(%s)
                ORDER BY updated_at DESC
            """, (districts,))
            rows = cur.fetchall()

    requested_pairs = {
        (slug(d), slug(n))
        for d in districts
        for n in (selected_nbs.get(d) or [])
    }

    out = []
    for r in rows:
        if requested_pairs:
            if (slug(r["district"]), slug(r["neighborhood"])) not in requested_pairs:
                continue

        item = Listing(
            id=str(r["id"]),
            district=r["district"] or "",
            neighborhood=r["neighborhood"] or "",
            title=r["title"] or "İlan",
            price=parse_int(r["price"]),
            gross_m2=parse_int(r["gross_m2"]),
            net_m2=parse_int(r["net_m2"]),
            rooms=r["rooms"] or "",
            listing_date=r["listing_date"] or "",
            building_age=parse_int(r["building_age"]),
            source=r["source"] or "cache",
        )
        item._listing_url = r["url"] or ""

        if listing_matches_filters(item, filters):
            out.append(item)

    return out


# =========================================================
# Apify — Real Estate Actor
# =========================================================

class RealEstateApifyProvider:
    def __init__(self):
        self.api_token = APIFY_API_TOKEN
        self.actor_id = ACTOR_ID
        self.timeout = max(30, min(APIFY_TIMEOUT, 300))

    def configured(self):
        return bool(self.api_token)

    def _request_json(self, req):
        try:
            with urlopen(req, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", errors="ignore")[:1200]
            except Exception:
                pass
            raise RuntimeError(f"Apify HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise RuntimeError(f"Apify bağlantı hatası: {exc.reason}") from exc
        except json.JSONDecodeError as exc:
            raise RuntimeError("Apify geçerli JSON döndürmedi.") from exc

    def run_district(self, district, max_results=None):
        if not self.configured():
            raise RuntimeError("APIFY_API_TOKEN tanımlı değil.")

        limit = max(1, min(int(max_results or LIVE_DISTRICT_MAX_RESULTS), 500))

        actor_input = {
            "listingType": "Sale",
            "propertyCategory": "Residential",
            "propertyType": ["Apartment"],
            "city": "Istanbul",
            "district": [district],
            "sortBy": "Newest",
            "extractPhoneNumbers": False,
            "maxResults": limit,
            "currency": "TRY",
        }

        params = {
            "clean": "true",
            "format": "json",
            "limit": str(limit),
            "maxItems": str(limit),
            "maxTotalChargeUsd": f"{SYNC_MAX_CHARGE_USD:.2f}",
            "timeout": str(self.timeout),
        }

        url = (
            f"https://api.apify.com/v2/acts/{self.actor_id}"
            "/run-sync-get-dataset-items?"
            + urlencode(params)
        )

        req = Request(
            url,
            data=json.dumps(actor_input, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": f"Bearer {self.api_token}",
                "User-Agent": "HLF-PAS/3.4",
            },
            method="POST",
        )

        payload = self._request_json(req)

        if isinstance(payload, list):
            return payload, actor_input
        if isinstance(payload, dict):
            return (
                payload.get("items")
                or payload.get("data")
                or payload.get("results")
                or []
            ), actor_input
        return [], actor_input

    def normalize_item(self, item):
        if not isinstance(item, dict):
            return None

        listing_id = str(
            item.get("id")
            or item.get("listingId")
            or ""
        ).strip()

        url = str(
            item.get("url")
            or item.get("listingUrl")
            or ""
        ).strip()

        if not listing_id and url:
            m = re.search(r"(\d{8,})", url)
            if m:
                listing_id = m.group(1)

        price = parse_int(item.get("price") or item.get("formattedPrice"))

        if not listing_id or price is None:
            return None

        city = normalize_place(item.get("city"))
        district = normalize_place(item.get("district"))

        # Actor output örneğinde neighborhood çoğu zaman boş,
        # gerçek mahalle quarter alanında geliyor.
        quarter = normalize_place(item.get("quarter"))
        neighborhood = normalize_place(item.get("neighborhood"))
        effective_neighborhood = quarter or neighborhood

        rooms = str(item.get("rooms") or "").strip()
        gross_m2 = parse_int(item.get("grossSize"))
        net_m2 = parse_int(item.get("netSize"))
        building_age = parse_int(item.get("buildingAge"))

        listed_at = str(item.get("listedAt") or item.get("listingDate") or "").strip()
        listing_date = listed_at[:10] if listed_at else ""

        listing = Listing(
            id=listing_id,
            district=district,
            neighborhood=effective_neighborhood,
            title=str(item.get("title") or "İlan").strip(),
            price=price,
            gross_m2=gross_m2,
            net_m2=net_m2,
            rooms=rooms,
            listing_date=listing_date,
            building_age=building_age,
            source="sahibinden-real-estate",
        )

        listing._listing_url = url
        listing._city = city
        listing._quarter = quarter
        listing._raw_neighborhood = neighborhood
        listing._address = str(item.get("address") or "")

        return listing

    def is_target(self, item, district, neighborhood):
        if slug(getattr(item, "_city", "")) != "istanbul":
            return False

        if slug(item.district) != slug(district):
            return False

        candidate_names = {
            slug(item.neighborhood),
            slug(getattr(item, "_quarter", "")),
            slug(getattr(item, "_raw_neighborhood", "")),
        }
        candidate_names.discard("")

        return slug(neighborhood) in candidate_names

    def sync_district(self, district, max_results=None):
        raw_items, actor_input = self.run_district(district, max_results=max_results)

        accepted = []
        rejected = []

        for raw in raw_items:
            item = self.normalize_item(raw)
            if not item:
                rejected.append({"reason": "parse"})
                continue

            if slug(getattr(item, "_city", "")) != "istanbul":
                rejected.append({"reason": "wrong_city", "id": item.id})
                continue

            if slug(item.district) != slug(district):
                rejected.append({
                    "reason": "wrong_district",
                    "id": item.id,
                    "district": item.district,
                    "quarter": getattr(item, "_quarter", ""),
                })
                continue

            # Kritik değişiklik:
            # Mahalle burada filtrelenmez. Actor ilçe bazında çalışır.
            # İlan gerçek quarter/neighborhood değeriyle PostgreSQL'e kaydedilir.
            # PAS mahalle seçimini daha sonra tamamen PostgreSQL üzerinde uygular.
            accepted.append(item)

        return {
            "raw_count": len(raw_items),
            "accepted": accepted,
            "rejected": rejected,
            "actor_input": actor_input,
        }

    def get_json(self, url):
        req = Request(
            url,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {self.api_token}",
                "User-Agent": "HLF-PAS/3.4",
            },
            method="GET",
        )
        return self._request_json(req)

    def import_old_real_estate_history(self, district, max_items=1000):
        """
        Yeni Actor run başlatmaz.
        Sadece clearpath/sahibinden-real-estate geçmiş başarılı run datasetlerini okur.
        """
        if not self.configured():
            raise RuntimeError("APIFY_API_TOKEN tanımlı değil.")

        runs_url = (
            f"https://api.apify.com/v2/acts/{self.actor_id}/runs?"
            + urlencode({"desc": "true", "limit": "100"})
        )

        payload = self.get_json(runs_url)
        runs = (
            ((payload.get("data") or {}).get("items") or [])
            if isinstance(payload, dict)
            else []
        )

        accepted = []
        seen = set()
        inspected = 0

        for run in runs:
            if len(accepted) >= max_items:
                break

            if str(run.get("status") or "").upper() != "SUCCEEDED":
                continue

            dataset_id = run.get("defaultDatasetId")
            if not dataset_id:
                continue

            items_url = (
                f"https://api.apify.com/v2/datasets/{dataset_id}/items?"
                + urlencode({"clean": "true", "limit": "1000"})
            )

            try:
                items = self.get_json(items_url)
            except Exception:
                continue

            if not isinstance(items, list):
                continue

            for raw in items:
                if len(accepted) >= max_items:
                    break

                inspected += 1
                item = self.normalize_item(raw)
                if not item:
                    continue

                if slug(getattr(item, "_city", "")) != "istanbul":
                    continue
                if slug(item.district) != slug(district):
                    continue

                if item.id in seen:
                    continue

                seen.add(item.id)
                accepted.append(item)

        return accepted, inspected


APIFY = RealEstateApifyProvider()

try:
    init_db()
except Exception as exc:
    print("HLF PAS DB init warning:", exc, flush=True)


# =========================================================
# Analiz
# =========================================================

def analyze(listings):
    if not listings:
        return {
            "count": 0,
            "median_price": None,
            "avg_price": None,
            "median_gross_m2_price": None,
            "median_net_m2_price": None,
            "avg_building_age": None,
            "by_neighborhood": [],
        }

    prices = [x.price for x in listings if x.price]
    gross = [x.gross_price_m2 for x in listings if x.gross_price_m2]
    net = [x.net_price_m2 for x in listings if x.net_price_m2]
    ages = [x.building_age for x in listings if x.building_age is not None]

    grouped = {}
    for x in listings:
        grouped.setdefault(f"{x.district} · {x.neighborhood}", []).append(x)

    by_neighborhood = []
    for name, rows in grouped.items():
        ps = [x.price for x in rows if x.price]
        gs = [x.gross_price_m2 for x in rows if x.gross_price_m2]
        aa = [x.building_age for x in rows if x.building_age is not None]

        by_neighborhood.append({
            "name": name,
            "count": len(rows),
            "median_price": round(statistics.median(ps)) if ps else None,
            "median_gross_m2_price": round(statistics.median(gs)) if gs else None,
            "avg_building_age": round(statistics.mean(aa), 1) if aa else None,
        })

    return {
        "count": len(listings),
        "median_price": round(statistics.median(prices)) if prices else None,
        "avg_price": round(statistics.mean(prices)) if prices else None,
        "median_gross_m2_price": round(statistics.median(gross)) if gross else None,
        "median_net_m2_price": round(statistics.median(net)) if net else None,
        "avg_building_age": round(statistics.mean(ages), 1) if ages else None,
        "by_neighborhood": by_neighborhood,
    }


def opportunity_analysis(listings):
    groups = {}
    for x in listings:
        groups.setdefault((x.district, x.neighborhood), []).append(x)

    result = []

    for x in listings:
        peers = groups[(x.district, x.neighborhood)]
        gross_values = [p.gross_price_m2 for p in peers if p.gross_price_m2]
        median_gross = statistics.median(gross_values) if gross_values else None

        delta = (
            ((x.gross_price_m2 / median_gross) - 1) * 100
            if median_gross and x.gross_price_m2
            else None
        )

        score = max(0, min(100, round(50 - (delta or 0) * 2)))

        if score >= 70:
            label = "Dikkat çekici"
        elif score >= 58:
            label = "Piyasanın altında"
        elif score <= 35:
            label = "Piyasanın üstünde"
        else:
            label = "Piyasa civarı"

        result.append({
            "id": x.id,
            "opportunity_score": score,
            "opportunity_label": label,
            "gross_vs_neighborhood_pct": round(delta, 1) if delta is not None else None,
        })

    return result


# =========================================================
# UI
# =========================================================

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
.notice{background:#eef6ff;border:1px solid #cfe3ff;border-radius:10px;padding:10px;font-size:13px}
.error{background:#fff1f1;border:1px solid #f4c4c4;border-radius:10px;padding:10px;font-size:13px;white-space:pre-wrap}
.grid,.pair,.metrics,.neighborhoods{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.check{display:flex;align-items:center;gap:8px;padding:10px;border:1px solid #d9dde3;border-radius:11px;background:#fff}
.check input{width:18px;height:18px}
.favorite{background:#fffaf0;border:1px solid #eadfbe;border-radius:12px;padding:11px}
.segmented{display:grid;grid-template-columns:repeat(3,1fr);gap:7px;margin-bottom:12px}
.seg input{display:none}
.seg span{display:block;text-align:center;padding:11px;border:1px solid #d9dde3;border-radius:10px;font-weight:700}
.seg input:checked+span{background:#1f2937;color:#fff}
details{border:1px solid #d9dde3;border-radius:12px;padding:0 11px;margin-top:9px}
summary{padding:11px 0;font-weight:800}
.neighborhood-box{border:1px solid #d9dde3;border-radius:12px;margin-top:10px;overflow:hidden}
.neighborhood-head{background:#f2f3f5;padding:10px 12px;font-weight:800}
.neighborhoods{padding:9px}
.field{display:block;font-weight:800;margin:10px 0 5px}
input[type=number],select{width:100%;padding:11px;border:1px solid #d9dde3;border-radius:10px;font-size:16px}
.primary,.secondary{width:100%;margin-top:10px;padding:14px;border-radius:11px;font-size:17px;font-weight:800}
.primary{border:0;background:#181818;color:#fff}
.secondary{border:1px solid #ccd2da;background:#fff;color:#18202b}
.primary:disabled,.secondary:disabled{opacity:.55}
.hidden{display:none!important}
.metric{padding:12px;border:1px solid #e1e5ea;border-radius:12px}
.metric .k{font-size:12px;color:#6b7280}
.metric .v{font-size:20px;font-weight:800}
.table-wrap{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{padding:10px 8px;border-bottom:1px solid #eceff3;text-align:left;white-space:nowrap}
.badge{padding:5px 8px;border-radius:999px;background:#eef2f7;font-size:12px}
.listing-clickable{cursor:pointer}
@media(max-width:600px){.grid,.pair,.metrics,.neighborhoods{grid-template-columns:1fr 1fr}}
</style>
</head>
<body>
<div class="container">

<h1>HLF PAS</h1>
<div class="subtitle">Piyasa Arama Sistemi <span class="small">v3.3-realestate-safe1</span></div>

<div class="card">
<div class="notice">
<strong>Veri sağlayıcı:</strong> PostgreSQL kayıt sistemi.<br>
Normal analiz Apify çalıştırmaz. Canlı test <strong>Real Estate Scraper</strong> ile ilçe bazında sadece <strong>1 ilan</strong> çeker.
Seçili mahalleyle eşleşmeyen ilan kaydedilmez.
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
<div class="pair">
<input name="net_m2_min" type="number" placeholder="Min TL/m²">
<input name="net_m2_max" type="number" placeholder="Max TL/m²">
</div>
</details>

<details>
<summary>Brüt m² satış fiyatı</summary>
<div class="pair">
<input name="gross_m2_min" type="number" placeholder="Min TL/m²">
<input name="gross_m2_max" type="number" placeholder="Max TL/m²">
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
<button class="secondary" id="syncButton" type="button">Seçili İlçeyi Real Estate ile Güncelle</button>
<button class="secondary" id="historyButton" type="button">Eski İlçe Verilerini İçe Aktar (Yeni Ücret Yok)</button>

<div class="small" style="margin-top:10px">
Actor ilçe bazında çalışır; dönen ilanların gerçek mahalleleri PostgreSQL'e kaydedilir. PAS'taki mahalle seçimi daha sonra veritabanı üzerinde ücretsiz filtrelenir. Önce eski başarılı run'ları içe aktarmak yeni ücret oluşturmadan veri tabanını doldurur.
</div>
</div>
</form>

<div id="errorBox" class="card hidden"><div class="error" id="errorText"></div></div>
<div id="syncBox" class="card hidden"><div class="notice" id="syncText"></div></div>

<div id="resultsCard" class="card hidden">
<div class="title">Piyasa özeti <span class="badge">kayıt</span></div>

<div class="metrics">
<div class="metric"><div class="k">İlan sayısı</div><div class="v" id="mCount">-</div></div>
<div class="metric"><div class="k">Medyan fiyat</div><div class="v" id="mMedianPrice">-</div></div>
<div class="metric"><div class="k">Ort. fiyat</div><div class="v" id="mAvgPrice">-</div></div>
<div class="metric"><div class="k">Medyan brüt TL/m²</div><div class="v" id="mMedianM2">-</div></div>
<div class="metric"><div class="k">Medyan net TL/m²</div><div class="v" id="mMedianNetM2">-</div></div>
<div class="metric"><div class="k">Ort. bina yaşı</div><div class="v" id="mAvgAge">-</div></div>
</div>

<div class="title" style="margin-top:16px">İlanlar</div>
<div class="table-wrap">
<table>
<thead>
<tr>
<th>Mahalle</th><th>Oda</th><th>Yaş</th><th>Brüt</th><th>Net</th>
<th>Fiyat</th><th>Brüt TL/m²</th><th>PAS</th>
</tr>
</thead>
<tbody id="listingRows"></tbody>
</table>
</div>
</div>

</div>

<script>
const DISTRICTS={{ districts_json|safe }};
const NEIGHBORHOODS={{ neighborhoods_json|safe }};
const STATE_KEY="hlf_pas_last_state_v3";

let selectedDistricts=new Set();
let selectedNeighborhoods={};

function esc(s){
 return String(s??"").replace(/[&<>"']/g,c=>({
  "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"
 }[c]));
}

function money(n){
 return n==null?"-":new Intl.NumberFormat("tr-TR").format(n)+" ₺";
}

function sideValue(){
 return document.querySelector('input[name="side"]:checked')?.value||"all";
}

function domSlug(s){
 return s.toLocaleLowerCase("tr-TR")
  .normalize("NFD")
  .replace(/[\u0300-\u036f]/g,"")
  .replace(/[^a-z0-9]+/g,"-");
}

function districtHtml(d){
 return `<label class="check">
  <input class="districtCheck" type="checkbox" value="${esc(d.name)}"
   ${selectedDistricts.has(d.name)?"checked":""}>
  <span>${esc(d.name)}${d.favorite?" ★":""}</span>
 </label>`;
}

function renderDistricts(){
 const side=sideValue();
 const visible=DISTRICTS.filter(d=>side==="all"||d.side===side);

 document.getElementById("districts").innerHTML=
  visible.map(districtHtml).join("");

 document.getElementById("favorites").innerHTML=
  visible.filter(d=>d.favorite).map(districtHtml).join("");

 document.querySelectorAll(".districtCheck").forEach(cb=>{
  cb.onchange=()=>{
   document.querySelectorAll(".districtCheck").forEach(x=>{
    if(x.value===cb.value)x.checked=cb.checked;
   });

   if(cb.checked){
    selectedDistricts.add(cb.value);
    renderNeighborhoodBlock(cb.value);
   }else{
    selectedDistricts.delete(cb.value);
    document.getElementById("nb-"+domSlug(cb.value))?.remove();
    syncSelectedNeighborhoods();
   }

   saveState();
  };
 });
}

function renderNeighborhoodBlock(district){
 const id="nb-"+domSlug(district);
 document.getElementById(id)?.remove();

 const selected=new Set(selectedNeighborhoods[district]||[]);
 const wrap=document.createElement("div");

 wrap.id=id;
 wrap.className="neighborhood-box";
 wrap.innerHTML=`
  <div class="neighborhood-head">${esc(district)} mahalleleri</div>
  <div class="neighborhoods">
   ${(NEIGHBORHOODS[district]||[]).map(n=>`
    <label class="check">
     <input class="neighborhoodCheck" type="checkbox" value="${esc(n)}"
      ${selected.has(n)?"checked":""}>
     <span>${esc(n)}</span>
    </label>
   `).join("")}
  </div>`;

 document.getElementById("neighborhoodArea").appendChild(wrap);

 wrap.querySelectorAll(".neighborhoodCheck").forEach(cb=>{
  cb.onchange=()=>{
   syncSelectedNeighborhoods();
   saveState();
  };
 });

 syncSelectedNeighborhoods();
}

function syncSelectedNeighborhoods(){
 const fresh={};

 selectedDistricts.forEach(d=>{
  const wrap=document.getElementById("nb-"+domSlug(d));
  fresh[d]=wrap
   ? [...wrap.querySelectorAll(".neighborhoodCheck:checked")].map(x=>x.value)
   : [];
 });

 selectedNeighborhoods=fresh;
}

function getOnePair(){
 syncSelectedNeighborhoods();
 const pairs=[];

 [...selectedDistricts].forEach(d=>{
  (selectedNeighborhoods[d]||[]).forEach(n=>pairs.push([d,n]));
 });

 return pairs;
}

function postJson(path,payload){
 return new Promise((resolve,reject)=>{
  const xhr=new XMLHttpRequest();

  xhr.open("POST",window.location.origin+path,true);
  xhr.setRequestHeader("Content-Type","application/json; charset=UTF-8");
  xhr.setRequestHeader("Accept","application/json");
  xhr.timeout=360000;

  xhr.onreadystatechange=()=>{
   if(xhr.readyState!==4)return;

   let data={};

   try{
    data=xhr.responseText?JSON.parse(xhr.responseText):{};
   }catch(_e){
    reject(new Error("Sunucu geçerli JSON döndürmedi. HTTP "+xhr.status));
    return;
   }

   resolve({
    ok:xhr.status>=200&&xhr.status<300,
    status:xhr.status,
    data
   });
  };

  xhr.onerror=()=>reject(new Error("Sunucuya bağlantı kurulamadı."));
  xhr.ontimeout=()=>reject(new Error("İstek zaman aşımına uğradı."));

  xhr.send(JSON.stringify(payload));
 });
}

function showError(text){
 document.getElementById("errorText").textContent=text;
 document.getElementById("errorBox").classList.remove("hidden");
 document.getElementById("syncBox").classList.add("hidden");
}

function showSuccess(text){
 document.getElementById("syncText").textContent=text;
 document.getElementById("syncBox").classList.remove("hidden");
 document.getElementById("errorBox").classList.add("hidden");
}

document.getElementById("pasForm").addEventListener("submit",async e=>{
 e.preventDefault();

 syncSelectedNeighborhoods();

 if(selectedDistricts.size===0){
  showError("En az bir ilçe seçin.");
  return;
 }

 const fd=new FormData(e.target);

 const payload={
  districts:[...selectedDistricts],
  neighborhoods:selectedNeighborhoods,
  rooms:fd.get("rooms")||"",
  min_m2:fd.get("min_m2")||"",
  max_m2:fd.get("max_m2")||"",
  min_price:fd.get("min_price")||"",
  max_price:fd.get("max_price")||"",
  building_age_min:fd.get("building_age_min")||"",
  building_age_max:fd.get("building_age_max")||"",
  net_m2_min:fd.get("net_m2_min")||"",
  net_m2_max:fd.get("net_m2_max")||"",
  gross_m2_min:fd.get("gross_m2_min")||"",
  gross_m2_max:fd.get("gross_m2_max")||""
 };

 const button=document.getElementById("searchButton");
 button.disabled=true;

 try{
  const result=await postJson("/api/search",payload);
  const data=result.data;

  if(!result.ok||!data.ok){
   throw new Error(data.error||("Arama başarısız. HTTP "+result.status));
  }

  document.getElementById("mCount").textContent=data.analysis.count;
  document.getElementById("mMedianPrice").textContent=money(data.analysis.median_price);
  document.getElementById("mAvgPrice").textContent=money(data.analysis.avg_price);
  document.getElementById("mMedianM2").textContent=money(data.analysis.median_gross_m2_price);
  document.getElementById("mMedianNetM2").textContent=money(data.analysis.median_net_m2_price);
  document.getElementById("mAvgAge").textContent=
   data.analysis.avg_building_age==null?"-":data.analysis.avg_building_age+" yıl";

  document.getElementById("listingRows").innerHTML=
   data.listings.map(r=>`
    <tr class="${r.url?"listing-clickable":""}" data-url="${esc(r.url||"")}">
     <td>${esc(r.district)} · ${esc(r.neighborhood)}</td>
     <td>${esc(r.rooms)}</td>
     <td>${r.building_age==null?"-":r.building_age+" yıl"}</td>
     <td>${r.gross_m2==null?"-":r.gross_m2+" m²"}</td>
     <td>${r.net_m2==null?"-":r.net_m2+" m²"}</td>
     <td>${money(r.price)}</td>
     <td>${money(r.gross_price_m2)}</td>
     <td>${r.opportunity_score??"-"} <span class="small">${esc(r.opportunity_label||"")}</span></td>
    </tr>
   `).join("");

  document.querySelectorAll(".listing-clickable").forEach(tr=>{
   tr.onclick=()=>{
    if(tr.dataset.url)window.location.assign(tr.dataset.url);
   };
  });

  document.getElementById("resultsCard").classList.remove("hidden");

 }catch(err){
  showError(err.message||"Beklenmeyen hata.");
 }finally{
  button.disabled=false;
 }
});


document.getElementById("historyButton").addEventListener("click",async()=>{
 const pairs=getOnePair();

 if(pairs.length!==1){
  showError("İçe aktarma için bir ilçe ve o ilçeden bir mahalle seçin.");
  return;
 }

 const [district,neighborhood]=pairs[0];
 const button=document.getElementById("historyButton");
 const oldText=button.textContent;

 button.disabled=true;
 button.textContent="Eski ilçe datasetleri aranıyor…";

 try{
  const result=await postJson("/api/import-history",{district,neighborhood});
  const data=result.data;

  if(!result.ok||!data.ok){
   throw new Error(data.error||("İçe aktarma başarısız. HTTP "+result.status));
  }

  showSuccess(
   `${district}: ${data.received} eski ilçe ilanı bulundu ve mahalle bilgileriyle işlendi. `+
   `${data.new} yeni kayıt, ${data.updated} güncelleme. `+
   `Yeni Actor run BAŞLATILMADI.`
  );

 }catch(err){
  showError(err.message||"İçe aktarma hatası.");
 }finally{
  button.disabled=false;
  button.textContent=oldText;
 }
});


document.getElementById("syncButton").addEventListener("click",async()=>{
 const pairs=getOnePair();

 if(pairs.length!==1){
  showError("İlçe güncellemesi için bir ilçe ve o ilçeden bir mahalle seçin.");
  return;
 }

 const [district,neighborhood]=pairs[0];
 const button=document.getElementById("syncButton");
 const oldText=button.textContent;

 button.disabled=true;
 button.textContent="Real Estate ilçe verileri güncelleniyor…";

 try{
  const result=await postJson("/api/sync",{district,neighborhood});
  const data=result.data;

  if(!result.ok||!data.ok){
   throw new Error(data.error||("Canlı test başarısız. HTTP "+result.status));
  }

  showSuccess(
   `${district}: ${data.raw_received} ilan çekildi; ${data.accepted} geçerli ilçe ilanı PostgreSQL için kabul edildi. `+
   `${data.new} yeni kayıt, ${data.updated} güncelleme. `+
   `${neighborhood} için veritabanında şu anda ${data.selected_neighborhood_count} ilan var.`
  );

 }catch(err){
  showError(err.message||"Canlı test hatası.");
 }finally{
  button.disabled=false;
  button.textContent=oldText;
 }
});


function collectState(){
 syncSelectedNeighborhoods();

 const fd=new FormData(document.getElementById("pasForm"));
 const filters={};

 [
  "rooms","min_m2","max_m2","min_price","max_price",
  "building_age_min","building_age_max",
  "net_m2_min","net_m2_max","gross_m2_min","gross_m2_max"
 ].forEach(k=>filters[k]=fd.get(k)||"");

 return {
  side:sideValue(),
  districts:[...selectedDistricts],
  neighborhoods:selectedNeighborhoods,
  filters
 };
}

function saveState(){
 try{
  localStorage.setItem(STATE_KEY,JSON.stringify(collectState()));
 }catch(_e){}
}

function loadState(){
 let saved=null;

 try{
  saved=JSON.parse(localStorage.getItem(STATE_KEY)||"null");
 }catch(_e){}

 if(!saved)return;

 const sideEl=document.querySelector(
  `input[name="side"][value="${saved.side||"all"}"]`
 );

 if(sideEl)sideEl.checked=true;

 selectedDistricts=new Set(
  (saved.districts||[])
   .filter(d=>DISTRICTS.some(x=>x.name===d))
 );

 selectedNeighborhoods=saved.neighborhoods||{};

 renderDistricts();

 selectedDistricts.forEach(d=>{
  renderNeighborhoodBlock(d);
 });

 Object.entries(saved.filters||{}).forEach(([name,value])=>{
  const el=document.querySelector(`[name="${name}"]`);
  if(el)el.value=value||"";
 });
}

document.querySelectorAll('input[name="side"]').forEach(el=>{
 el.addEventListener("change",()=>{
  renderDistricts();
  saveState();
 });
});

document.getElementById("pasForm").addEventListener("change",saveState);
document.getElementById("pasForm").addEventListener("input",saveState);

renderDistricts();
loadState();

</script>
</body>
</html>
"""


# =========================================================
# Routes
# =========================================================

@app.get("/")
def home():
    return render_template_string(
        PAGE,
        districts_json=json.dumps(DISTRICTS, ensure_ascii=False),
        neighborhoods_json=json.dumps(NEIGHBORHOODS, ensure_ascii=False),
    )


def validate_pair(payload):
    district = str(payload.get("district") or "").strip()
    neighborhood = str(payload.get("neighborhood") or "").strip()

    if district not in {d["name"] for d in DISTRICTS}:
        raise ValueError("Geçersiz ilçe.")

    if neighborhood not in set(NEIGHBORHOODS.get(district, [])):
        raise ValueError("Geçersiz mahalle.")

    return district, neighborhood


@app.post("/api/search")
def api_search():
    try:
        payload = request.get_json(silent=True) or {}

        allowed_districts = {d["name"] for d in DISTRICTS}

        districts = [
            d for d in (payload.get("districts") or [])
            if d in allowed_districts
        ]

        if not districts:
            return jsonify(ok=False, error="Geçerli bir ilçe seçilmedi."), 400

        raw_neighborhoods = payload.get("neighborhoods") or {}
        neighborhoods = {}

        for district in districts:
            allowed_nbs = set(NEIGHBORHOODS.get(district, []))
            neighborhoods[district] = [
                n for n in (raw_neighborhoods.get(district) or [])
                if n in allowed_nbs
            ]

        filters = dict(payload)
        filters["districts"] = districts
        filters["neighborhoods"] = neighborhoods

        listings = load_listings_from_db(filters)

        analysis = analyze(listings)
        opportunity = {
            str(x["id"]): x
            for x in opportunity_analysis(listings)
        }

        rows = []

        for item in listings:
            row = item.to_dict()
            row.update(opportunity.get(str(item.id), {}))
            row["url"] = getattr(item, "_listing_url", "")
            rows.append(row)

        return jsonify(
            ok=True,
            provider="kayıt",
            analysis=analysis,
            listings=rows,
        )

    except Exception as exc:
        return jsonify(
            ok=False,
            error=f"Kayıtlı veri hazırlanamadı: {exc}",
        ), 500


@app.post("/api/import-history")
def api_import_history():
    payload = request.get_json(silent=True) or {}

    try:
        district, neighborhood = validate_pair(payload)

        listings, inspected = APIFY.import_old_real_estate_history(
            district,
            max_items=1000,
        )

        saved = save_listings_to_db(listings)

        record_sync_state(
            district,
            neighborhood,
            result_count=len(listings),
            error="",
        )

        return jsonify(
            ok=True,
            district=district,
            neighborhood=neighborhood,
            received=len(listings),
            inspected=inspected,
            new_actor_run=False,
            **saved,
        )

    except ValueError as exc:
        return jsonify(ok=False, error=str(exc)), 400

    except Exception as exc:
        return jsonify(
            ok=False,
            error=f"Eski Real Estate verileri içe aktarılamadı: {exc}",
        ), 502


@app.post("/api/sync")
def api_sync():
    payload = request.get_json(silent=True) or {}

    try:
        district, neighborhood = validate_pair(payload)

        result = APIFY.sync_district(
            district,
            max_results=LIVE_DISTRICT_MAX_RESULTS,
        )

        accepted = result["accepted"]
        rejected = result["rejected"]

        if not accepted:
            message = (
                f"{district} için Real Estate Actor ilçe bazında çalıştı ancak "
                "kaydedilebilir ilan üretmedi. PostgreSQL kayıtları etkilenmedi."
            )
            record_sync_state(
                district,
                neighborhood,
                result_count=0,
                error=message,
            )
            return jsonify(
                ok=False,
                error=message,
                raw_received=result["raw_count"],
                accepted=0,
                rejected=len(rejected),
                actor_input=result["actor_input"],
            ), 409

        saved = save_listings_to_db(accepted)

        # Kullanıcının seçtiği mahalle için DB'de kaç kayıt oluştuğunu ayrıca bildir.
        selected_filters = {
            "districts": [district],
            "neighborhoods": {district: [neighborhood]},
        }
        selected_count = len(load_listings_from_db(selected_filters))

        record_sync_state(
            district,
            neighborhood,
            result_count=selected_count,
            error="",
        )

        return jsonify(
            ok=True,
            district=district,
            neighborhood=neighborhood,
            raw_received=result["raw_count"],
            accepted=len(accepted),
            rejected=len(rejected),
            selected_neighborhood_count=selected_count,
            actor_input=result["actor_input"],
            sync_limit=LIVE_DISTRICT_MAX_RESULTS,
            **saved,
        )

    except ValueError as exc:
        return jsonify(ok=False, error=str(exc)), 400

    except Exception as exc:
        try:
            record_sync_state(
                str(payload.get("district") or ""),
                str(payload.get("neighborhood") or ""),
                result_count=0,
                error=str(exc)[:700],
            )
        except Exception:
            pass

        return jsonify(
            ok=False,
            error=(
                "Real Estate ilçe güncellemesi yapılamadı: "
                f"{exc}. PostgreSQL kayıtları etkilenmedi."
            ),
        ), 502


@app.get("/api/provider-status")
def api_provider_status():
    return jsonify(
        ok=True,
        database_configured=db_configured(),
        apify_configured=APIFY.configured(),
        actor_id=ACTOR_ID,
        max_results=LIVE_DISTRICT_MAX_RESULTS,
        extract_phone_numbers=False,
        max_items=1,
        max_total_charge_usd=SYNC_MAX_CHARGE_USD,
        neighborhood_input_supported=False,
        normal_search_uses_apify=False,
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)
