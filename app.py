import os
import re
import json
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
# HLF PAS v3.7 — Çalışan Real Estate akışına dönüş
#
# Amaç:
#   1) Normal analiz = sadece PostgreSQL (Apify maliyeti yok)
#   2) Canlı güncelleme = Real Estate Actor ile seçili İLÇEDE
#      kontrollü sayıda ilan çek
#   3) Dönen sonuçların gerçek quarter/neighborhood alanından
#      mahalleyi belirle ve PostgreSQL'e kaydet
#   4) Kullanıcı mahalle seçimini PostgreSQL üzerinde ücretsiz filtrele
#
# Railway Variables:
#   DATABASE_URL=...
#   APIFY_API_TOKEN=...
#   APIFY_TIMEOUT=300                (opsiyonel)
#   PAS_SYNC_MAX_RESULTS=50          (önerilen başlangıç)
#   PAS_SYNC_MAX_CHARGE_USD=0.75     (tek run güvenlik tavanı)
#
# NOT:
#   clearpath/sahibinden-real-estate Actor'ında mahalle input filtresi yok.
#   Bu nedenle Actor ilçe bazında çalışır. Mahalle doğrulaması çıktıdan yapılır.
# =========================================================

VERSION = "v4.4-stable-neighborhood"

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

ACTOR_ID = "clearpath~sahibinden-scraper-pro"

def env_int(name, default):
    try:
        return int(os.environ.get(name, str(default)) or default)
    except Exception:
        return default

def env_float(name, default):
    try:
        return float(os.environ.get(name, str(default)) or default)
    except Exception:
        return default

LIVE_NEIGHBORHOOD_MAX_RESULTS = max(1, min(env_int("PAS_SYNC_MAX_RESULTS", 20), 200))
SYNC_CACHE_HOURS = max(1, min(env_int("PAS_SYNC_CACHE_HOURS", 6), 72))


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
    # Türkçe yer adlarını API çıktılarıyla güvenli biçimde karşılaştır.
    # Özellikle "İstanbul".casefold() -> "i̇stanbul" (i + combining dot)
    # ürettiği için önce Unicode combining işaretlerini temizliyoruz.
    import unicodedata

    text = normalize_place(value).strip().casefold()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))

    for a, b in {
        "ı": "i",
        "ğ": "g",
        "ü": "u",
        "ş": "s",
        "ö": "o",
        "ç": "c",
    }.items():
        text = text.replace(a, b)

    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def sahibinden_neighborhood_url(district, neighborhood):
    """Sahibinden'in gerçek mahalle SEO URL biçimi."""
    d = slug(district)
    n = slug(neighborhood)
    return (
        "https://www.sahibinden.com/satilik-daire/"
        f"istanbul-{d}-{n}-{n}-mh.?sorting=date_desc"
    )


def normalize_listing_date(value):
    """ISO veya Türkçe Sahibinden tarihini YYYY-MM-DD biçimine çevirir."""
    from datetime import date

    raw = str(value or "").strip()
    if not raw:
        return ""

    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", raw)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"

    months = {
        "ocak":1,"şubat":2,"subat":2,"mart":3,"nisan":4,"mayıs":5,"mayis":5,
        "haziran":6,"temmuz":7,"ağustos":8,"agustos":8,"eylül":9,"eylul":9,
        "ekim":10,"kasım":11,"kasim":11,"aralık":12,"aralik":12,
    }
    cleaned = raw.casefold().replace(".", " ")
    parts = re.split(r"\s+", cleaned)
    if len(parts) >= 2:
        try:
            day = int(re.sub(r"\D", "", parts[0]))
        except Exception:
            day = None
        month = months.get(parts[1])
        year = None
        for p in parts[2:]:
            if re.fullmatch(r"\d{4}", p):
                year = int(p)
                break
        if day and month:
            if not year:
                year = date.today().year
            try:
                return date(year, month, day).isoformat()
            except Exception:
                pass
    return ""


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
                    str(item.id), item.district, item.neighborhood, item.title or "",
                    item.price, item.gross_m2, item.net_m2, item.rooms or "",
                    item.listing_date or "", item.building_age, item.source or "", url
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



def neighborhood_recently_synced(district, neighborhood):
    if not db_configured():
        return False
    init_db()
    key = f"{slug(district)}::{slug(neighborhood)}"
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT last_sync FROM pas_sync_state WHERE scope_key=%s", (key,))
            row = cur.fetchone()
    if not row or not row["last_sync"]:
        return False
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    return (now - row["last_sync"]).total_seconds() < SYNC_CACHE_HOURS * 3600


def listing_date_is_allowed(listing_date, date_filter):
    value = str(date_filter or "current")
    if value == "current":
        return True
    days = {"7d": 7, "30d": 30, "90d": 90}.get(value)
    if not days:
        return True
    if not listing_date:
        return False
    from datetime import date, timedelta
    try:
        d = date.fromisoformat(str(listing_date)[:10])
    except Exception:
        return False
    return d >= date.today() - timedelta(days=days-1)


def listing_matches_filters(row, filters):
    if not listing_date_is_allowed(row.listing_date, filters.get("date_filter")):
        return False
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
# Apify — Search Scraper Pro / doğrudan mahalle araması
# =========================================================

class NeighborhoodApifyProvider:
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
                detail = exc.read().decode("utf-8", errors="ignore")[:1500]
            except Exception:
                pass
            raise RuntimeError(f"Apify HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise RuntimeError(f"Apify bağlantı hatası: {exc.reason}") from exc
        except json.JSONDecodeError as exc:
            raise RuntimeError("Apify geçerli JSON döndürmedi.") from exc

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
    def _coded_attribute(item, code):
        """Search-summary çıktısındaki aXX kodlu alanı okur."""
        if not isinstance(item, dict):
            return None

        containers = [item]
        raw = item.get("rawSummary")
        if isinstance(raw, dict):
            containers.append(raw)

        for container in containers:
            for bucket_name in ("searchAttributes", "attributes", "summaryAttributes"):
                bucket = container.get(bucket_name)
                if isinstance(bucket, dict) and bucket.get(code) not in (None, ""):
                    return bucket.get(code)

        return None

    def run_neighborhood(self, district, neighborhood, max_results=None):
        if not self.configured():
            raise RuntimeError("APIFY_API_TOKEN tanımlı değil.")

        limit = max(1, min(int(max_results or LIVE_NEIGHBORHOOD_MAX_RESULTS), 5000))
        start_url = sahibinden_neighborhood_url(district, neighborhood)

        # Maliyet güvenliği:
        # - URL doğrudan seçili mahalleye gider.
        # - enrichment kapalıdır: telefon/detay ek ücreti yoktur.
        # - maxResults yalnızca bu mahallenin sonuçlarına uygulanır.
        actor_input = {
            "startUrls": [start_url],
            "enrichment": False,
            "maxResults": limit,
        }

        # Actor'ın kendi maxResults girdisi maliyet/sonuç sınırıdır.
        # API seviyesindeki maxItems/maxTotalChargeUsd önceki sürümlerde
        # run'ı erken keserek eksik veya 0 sonuç üretebildiği için kullanılmıyor.
        params = {
            "clean": "true",
            "format": "json",
            "limit": str(limit),
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
                "User-Agent": f"HLF-PAS/{VERSION}",
            },
            method="POST",
        )

        payload = self._request_json(req)

        if isinstance(payload, list):
            return payload, actor_input, start_url
        if isinstance(payload, dict):
            rows = payload.get("items") or payload.get("data") or payload.get("results") or []
            return (rows if isinstance(rows, list) else []), actor_input, start_url

        return [], actor_input, start_url

    def normalize_item(self, item, fallback_district, fallback_neighborhood):
        if not isinstance(item, dict):
            return None

        raw = item.get("rawSummary") if isinstance(item.get("rawSummary"), dict) else {}

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

        price = parse_int(
            self._pick(item, "price", "formattedPrice", "salePrice", "amount", "priceValue")
            or self._pick(raw, "price", "formattedPrice", "salePrice", "amount", "priceValue")
        )

        if not listing_id or price is None:
            return None

        title = str(
            self._pick(item, "title", "listingTitle", "adTitle")
            or self._pick(raw, "title", "listingTitle", "adTitle")
            or "İlan"
        ).strip()

        # Tam mahalle SEO URL'si hedefi zaten belirlediği için eksik summary
        # location alanlarına güvenip doğru ilanları reddetmiyoruz.
        city = "İstanbul"
        district = normalize_place(fallback_district)
        neighborhood = normalize_place(fallback_neighborhood)

        # Search Scraper Pro searchSummary'de daha önce doğruladığımız alanlar:
        # a24 = brüt m², a107889 = net m², a20 = oda, a812 = bina yaşı.
        gross_m2 = parse_int(
            self._pick(item, "grossSize", "grossM2", "gross_m2", "areaGross", "size", "m2")
            or self._pick(raw, "grossSize", "grossM2", "gross_m2", "areaGross", "size", "m2")
            or self._coded_attribute(item, "a24")
        )

        net_m2 = parse_int(
            self._pick(item, "netSize", "netM2", "net_m2", "areaNet")
            or self._pick(raw, "netSize", "netM2", "net_m2", "areaNet")
            or self._coded_attribute(item, "a107889")
        )

        if gross_m2 and net_m2 and net_m2 > gross_m2:
            net_m2 = None

        rooms = str(
            self._pick(item, "rooms", "roomCount", "room", "roomInfo")
            or self._pick(raw, "rooms", "roomCount", "room", "roomInfo")
            or self._coded_attribute(item, "a20")
            or ""
        ).strip()

        building_age = parse_int(
            self._pick(item, "buildingAge", "building_age", "buildingAgeYears", "ageOfBuilding")
            or self._pick(raw, "buildingAge", "building_age", "buildingAgeYears", "ageOfBuilding")
            or self._coded_attribute(item, "a812")
        )

        listed_at = str(
            self._pick(item, "listingDate", "listedAt", "createdAt", "date", "dateCreated")
            or self._pick(raw, "listingDate", "listedAt", "createdAt", "date", "dateCreated")
            or ""
        ).strip()
        listing_date = normalize_listing_date(listed_at)

        listing = Listing(
            id=listing_id,
            district=district,
            neighborhood=neighborhood,
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
        listing._city = city
        return listing

    def sync_neighborhood(self, district, neighborhood, max_results=None):
        raw_items, actor_input, start_url = self.run_neighborhood(
            district, neighborhood, max_results=max_results
        )
        accepted = []
        rejected = {"parse": 0}
        seen = set()
        for raw in raw_items:
            item = self.normalize_item(raw, district, neighborhood)
            if not item:
                rejected["parse"] += 1
                continue
            if item.id in seen:
                continue
            seen.add(item.id)
            accepted.append(item)
        return {
            "raw_count": len(raw_items),
            "accepted": accepted,
            "rejected": rejected,
            "actor_input": actor_input,
            "start_url": start_url,
        }


APIFY = NeighborhoodApifyProvider()

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
            "avg_gross_m2_price": None,
            "avg_net_m2_price": None,
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
        "avg_gross_m2_price": round(statistics.mean(gross)) if gross else None,
        "avg_net_m2_price": round(statistics.mean(net)) if net else None,
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
.notice{background:#eef6ff;border:1px solid #cfe3ff;border-radius:10px;padding:10px;font-size:13px;white-space:pre-wrap}
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
</style>
</head>
<body>
<div class="container">

<h1>HLF PAS</h1>
<div class="subtitle">Piyasa Arama Sistemi <span class="small">{{ version }}</span></div>

<div class="card">
<div class="notice"><strong>Veri sağlayıcı:</strong> PostgreSQL + Search Scraper Pro.
Normal analiz Apify çalıştırmaz ve ücret oluşturmaz.
Canlı güncelleme seçilen mahallenin gerçek Sahibinden SEO arama sayfasından en fazla {{ live_limit }} en yeni ilanı alır.
Aynı mahalle {{ cache_hours }} saat içinde yeniden ücretli çalıştırılmaz. Telefon/detay zenginleştirmesi kapalıdır.</div>
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

<label class="field">İlan Tarihi</label>
<select name="date_filter">
<option value="current">Tümü / kayıtlı güncel veri</option>
<option value="7d">Son 1 hafta</option>
<option value="30d">Son 1 ay</option>
<option value="90d">Son 3 ay</option>
</select>

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
<button class="secondary" id="syncButton" type="button">Seçili Mahalleyi Güncelle (Apify)</button>

<div class="small" style="margin-top:10px">
Filtreleri değiştirmek için yeniden Apify çalıştırmanız gerekmez; mahalleyi bir kez güncelleyin, sonra kayıtlı ilanları ücretsiz filtreleyin.
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
<div class="metric"><div class="k">Ortalama brüt TL/m²</div><div class="v" id="mMedianM2">-</div></div>
<div class="metric"><div class="k">Ortalama net TL/m²</div><div class="v" id="mMedianNetM2">-</div></div>
<div class="metric"><div class="k">Ort. bina yaşı</div><div class="v" id="mAvgAge">-</div></div>
</div>

<div class="title" style="margin-top:16px">İlanlar</div>
<div class="table-wrap">
<table>
<thead>
<tr>
<th>Mahalle</th><th>Oda</th><th>Yaş</th><th>Brüt</th><th>Net</th>
<th>Fiyat</th><th>Brüt TL/m²</th><th>Net TL/m²</th><th>İlan Tarihi</th><th>İlan ID</th><th>PAS</th>
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
const STATE_KEY="hlf_pas_last_state_v35";

let selectedDistricts=new Set();
let selectedNeighborhoods={};

function esc(s){
 return String(s??"").replace(/[&<>"']/g,c=>({
  "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"
 }[c]));
}
function money(n){ return n==null?"-":new Intl.NumberFormat("tr-TR").format(n)+" ₺"; }
function sideValue(){ return document.querySelector('input[name="side"]:checked')?.value||"all"; }
function domSlug(s){
 return s.toLocaleLowerCase("tr-TR").normalize("NFD")
  .replace(/[\u0300-\u036f]/g,"").replace(/[^a-z0-9]+/g,"-");
}
function districtHtml(d){
 return `<label class="check"><input class="districtCheck" type="checkbox" value="${esc(d.name)}"
 ${selectedDistricts.has(d.name)?"checked":""}><span>${esc(d.name)}${d.favorite?" ★":""}</span></label>`;
}
function renderDistricts(){
 const side=sideValue();
 const visible=DISTRICTS.filter(d=>side==="all"||d.side===side);
 document.getElementById("districts").innerHTML=visible.map(districtHtml).join("");
 document.getElementById("favorites").innerHTML=visible.filter(d=>d.favorite).map(districtHtml).join("");

 document.querySelectorAll(".districtCheck").forEach(cb=>{
  cb.onchange=()=>{
   document.querySelectorAll(".districtCheck").forEach(x=>{if(x.value===cb.value)x.checked=cb.checked;});
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
 wrap.id=id; wrap.className="neighborhood-box";
 wrap.innerHTML=`<div class="neighborhood-head">${esc(district)} mahalleleri</div>
 <div class="neighborhoods">${(NEIGHBORHOODS[district]||[]).map(n=>`
 <label class="check"><input class="neighborhoodCheck" type="checkbox" value="${esc(n)}"
 ${selected.has(n)?"checked":""}><span>${esc(n)}</span></label>`).join("")}</div>`;
 document.getElementById("neighborhoodArea").appendChild(wrap);
 wrap.querySelectorAll(".neighborhoodCheck").forEach(cb=>{
  cb.onchange=()=>{syncSelectedNeighborhoods();saveState();};
 });
 syncSelectedNeighborhoods();
}
function syncSelectedNeighborhoods(){
 const fresh={};
 selectedDistricts.forEach(d=>{
  const wrap=document.getElementById("nb-"+domSlug(d));
  fresh[d]=wrap?[...wrap.querySelectorAll(".neighborhoodCheck:checked")].map(x=>x.value):[];
 });
 selectedNeighborhoods=fresh;
}
function getOnePair(){
 syncSelectedNeighborhoods();
 const pairs=[];
 [...selectedDistricts].forEach(d=>(selectedNeighborhoods[d]||[]).forEach(n=>pairs.push([d,n])));
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
   try{data=xhr.responseText?JSON.parse(xhr.responseText):{};}
   catch(_e){reject(new Error("Sunucu geçerli JSON döndürmedi. HTTP "+xhr.status));return;}
   resolve({ok:xhr.status>=200&&xhr.status<300,status:xhr.status,data});
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
 if(selectedDistricts.size===0){showError("En az bir ilçe seçin.");return;}

 const fd=new FormData(e.target);
 const payload={
  districts:[...selectedDistricts], neighborhoods:selectedNeighborhoods,
  date_filter:fd.get("date_filter")||"current",
  rooms:fd.get("rooms")||"", min_m2:fd.get("min_m2")||"", max_m2:fd.get("max_m2")||"",
  min_price:fd.get("min_price")||"", max_price:fd.get("max_price")||"",
  building_age_min:fd.get("building_age_min")||"", building_age_max:fd.get("building_age_max")||"",
  net_m2_min:fd.get("net_m2_min")||"", net_m2_max:fd.get("net_m2_max")||"",
  gross_m2_min:fd.get("gross_m2_min")||"", gross_m2_max:fd.get("gross_m2_max")||""
 };

 const button=document.getElementById("searchButton"); button.disabled=true;
 try{
  const result=await postJson("/api/search",payload), data=result.data;
  if(!result.ok||!data.ok)throw new Error(data.error||("Arama başarısız. HTTP "+result.status));

  document.getElementById("mCount").textContent=data.analysis.count;
  document.getElementById("mMedianPrice").textContent=money(data.analysis.median_price);
  document.getElementById("mAvgPrice").textContent=money(data.analysis.avg_price);
  document.getElementById("mMedianM2").textContent=money(data.analysis.avg_gross_m2_price);
  document.getElementById("mMedianNetM2").textContent=money(data.analysis.avg_net_m2_price);
  document.getElementById("mAvgAge").textContent=data.analysis.avg_building_age==null?"-":data.analysis.avg_building_age+" yıl";

  document.getElementById("listingRows").innerHTML=data.listings.map(r=>`
    <tr class="${r.url?"listing-clickable":""}" data-url="${esc(r.url||"")}">
     <td>${esc(r.district)} · ${esc(r.neighborhood)}</td>
     <td>${esc(r.rooms)}</td><td>${r.building_age==null?"-":r.building_age+" yıl"}</td>
     <td>${r.gross_m2==null?"-":r.gross_m2+" m²"}</td><td>${r.net_m2==null?"-":r.net_m2+" m²"}</td>
     <td>${money(r.price)}</td>
     <td>${money(r.gross_price_m2)}</td>
     <td>${money(r.net_price_m2)}</td>
     <td>${esc(r.listing_date||"-")}</td>
     <td>${esc(r.id||"-")}</td>
     <td>${r.opportunity_score??"-"} <span class="small">${esc(r.opportunity_label||"")}</span></td>
    </tr>`).join("");

  document.querySelectorAll(".listing-clickable").forEach(tr=>{
   tr.onclick=()=>{if(tr.dataset.url)window.location.assign(tr.dataset.url);};
  });
  document.getElementById("resultsCard").classList.remove("hidden");
 }catch(err){showError(err.message||"Beklenmeyen hata.");}
 finally{button.disabled=false;}
});

document.getElementById("syncButton").addEventListener("click",async()=>{
 const pairs=getOnePair();
 if(pairs.length!==1){showError("Güncelleme için tam olarak 1 ilçe ve o ilçeden 1 mahalle seçin.");return;}

 const [district,neighborhood]=pairs[0];
 const button=document.getElementById("syncButton"), oldText=button.textContent;
 button.disabled=true; button.textContent="Mahalle ilanları çekiliyor…";

 try{
  const result=await postJson("/api/sync",{district,neighborhood}), data=result.data;
  if(!result.ok||!data.ok)throw new Error(data.error||("Güncelleme başarısız. HTTP "+result.status));

  if(data.cached){
   showSuccess(`${district} · ${neighborhood}: yakın zamanda zaten güncellendi. Yeni Apify ücreti oluşmadı. Kayıtlı ilan: ${data.selected_neighborhood_count}.`);
  }else{
   showSuccess(`${district} · ${neighborhood}: ${data.raw_received} ilan geldi; ${data.accepted} ilan kaydedildi. ${data.new} yeni, ${data.updated} güncellendi. PostgreSQL toplamı: ${data.selected_neighborhood_count}.`);
  }

  // Güncelleme başarılı olunca aynı seçim ve filtrelerle
  // PostgreSQL sonuçlarını otomatik olarak ekrana getir.
  document.getElementById("pasForm").requestSubmit();

 }catch(err){showError(err.message||"Canlı güncelleme hatası.");}
 finally{button.disabled=false;button.textContent=oldText;}
});

function collectState(){
 syncSelectedNeighborhoods();
 const fd=new FormData(document.getElementById("pasForm")), filters={};
 ["date_filter","rooms","min_m2","max_m2","min_price","max_price","building_age_min","building_age_max",
  "net_m2_min","net_m2_max","gross_m2_min","gross_m2_max"].forEach(k=>filters[k]=fd.get(k)||"");
 return {side:sideValue(),districts:[...selectedDistricts],neighborhoods:selectedNeighborhoods,filters};
}
function saveState(){try{localStorage.setItem(STATE_KEY,JSON.stringify(collectState()));}catch(_e){}}
function loadState(){
 let saved=null; try{saved=JSON.parse(localStorage.getItem(STATE_KEY)||"null");}catch(_e){}
 if(!saved)return;
 const sideEl=document.querySelector(`input[name="side"][value="${saved.side||"all"}"]`);
 if(sideEl)sideEl.checked=true;
 selectedDistricts=new Set((saved.districts||[]).filter(d=>DISTRICTS.some(x=>x.name===d)));
 selectedNeighborhoods=saved.neighborhoods||{};
 renderDistricts();
 selectedDistricts.forEach(d=>renderNeighborhoodBlock(d));
 Object.entries(saved.filters||{}).forEach(([name,value])=>{
  const el=document.querySelector(`[name="${name}"]`); if(el)el.value=value||"";
 });
}
document.querySelectorAll('input[name="side"]').forEach(el=>{
 el.addEventListener("change",()=>{renderDistricts();saveState();});
});
document.getElementById("pasForm").addEventListener("change",saveState);
document.getElementById("pasForm").addEventListener("input",saveState);

renderDistricts();
loadState();
</script>
</body>
</html>
"""


@app.get("/")
def home():
    return render_template_string(
        PAGE,
        districts_json=json.dumps(DISTRICTS, ensure_ascii=False),
        neighborhoods_json=json.dumps(NEIGHBORHOODS, ensure_ascii=False),
        version=VERSION,
        live_limit=LIVE_NEIGHBORHOOD_MAX_RESULTS,
        cache_hours=SYNC_CACHE_HOURS,
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

        districts = [d for d in (payload.get("districts") or []) if d in allowed_districts]
        if not districts:
            return jsonify(ok=False, error="Geçerli bir ilçe seçilmedi."), 400

        raw_neighborhoods = payload.get("neighborhoods") or {}
        neighborhoods = {}
        for district in districts:
            allowed_nbs = set(NEIGHBORHOODS.get(district, []))
            neighborhoods[district] = [
                n for n in (raw_neighborhoods.get(district) or []) if n in allowed_nbs
            ]

        filters = dict(payload)
        filters["districts"] = districts
        filters["neighborhoods"] = neighborhoods

        listings = load_listings_from_db(filters)
        analysis = analyze(listings)
        opportunity = {str(x["id"]): x for x in opportunity_analysis(listings)}

        rows = []
        for item in listings:
            row = item.to_dict()
            row.update(opportunity.get(str(item.id), {}))
            row["url"] = getattr(item, "_listing_url", "")
            rows.append(row)

        return jsonify(ok=True, provider="kayıt", analysis=analysis, listings=rows)

    except Exception as exc:
        return jsonify(ok=False, error=f"Kayıtlı veri hazırlanamadı: {exc}"), 500


@app.post("/api/sync")
def api_sync():
    payload = request.get_json(silent=True) or {}
    try:
        district, neighborhood = validate_pair(payload)
        if neighborhood_recently_synced(district, neighborhood):
            selected_count = len(load_listings_from_db({
                "districts": [district],
                "neighborhoods": {district: [neighborhood]},
            }))
            return jsonify(ok=True, cached=True, district=district, neighborhood=neighborhood,
                           raw_received=0, accepted=0, new=0, updated=0,
                           selected_neighborhood_count=selected_count)

        result = APIFY.sync_neighborhood(district, neighborhood, max_results=LIVE_NEIGHBORHOOD_MAX_RESULTS)
        accepted = result["accepted"]
        if not accepted:
            message = (f"{district} / {neighborhood}: Actor kaydedilebilir ilan döndürmedi. "
                       "Bu, Sahibinden'de ilan olmadığı anlamına gelmez. Aynı sorguyu tekrar ücretli çalıştırmayın.")
            record_sync_state(district, neighborhood, 0, message)
            return jsonify(ok=False, error=message, raw_received=result["raw_count"],
                           rejected=result["rejected"], actor_input=result["actor_input"],
                           start_url=result["start_url"]), 409

        saved = save_listings_to_db(accepted)
        selected_count = len(load_listings_from_db({
            "districts": [district],
            "neighborhoods": {district: [neighborhood]},
        }))
        record_sync_state(district, neighborhood, selected_count, "")
        return jsonify(ok=True, cached=False, district=district, neighborhood=neighborhood,
                       raw_received=result["raw_count"], accepted=len(accepted),
                       selected_neighborhood_count=selected_count, actor_input=result["actor_input"],
                       start_url=result["start_url"], sync_limit=LIVE_NEIGHBORHOOD_MAX_RESULTS, **saved)
    except ValueError as exc:
        return jsonify(ok=False, error=str(exc)), 400
    except Exception as exc:
        return jsonify(ok=False, error=f"Mahalle güncellemesi yapılamadı: {exc}"), 502


@app.get("/api/provider-status")
def api_provider_status():
    return jsonify(
        ok=True,
        version=VERSION,
        database_configured=db_configured(),
        apify_configured=APIFY.configured(),
        actor_id=ACTOR_ID,
        max_results=LIVE_NEIGHBORHOOD_MAX_RESULTS,
        enrichment=False,
        cache_hours=SYNC_CACHE_HOURS,
        normal_search_uses_apify=False,
        neighborhood_direct_url=True,
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)
