import os
import re
import json
import statistics
import unicodedata
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from dataclasses import dataclass, asdict

from flask import Flask, request, render_template_string, jsonify
import psycopg
from psycopg.rows import dict_row

app = Flask(__name__)

# =========================================================
# HLF PAS v4.5
#
# ANA PRENSİPLER
# 1) Normal analiz sadece PostgreSQL -> Apify maliyeti yok.
# 2) Canlı güncelleme seçili mahalle için yapılır.
# 3) Telefon/detay enrichment kapalı.
# 4) Aynı mahalle kısa süre içinde yeniden ücretli çalıştırılmaz.
# 5) Sahibinden ilan URL / ilan ID doğrulaması yapılır.
# 6) Eski bozuk/geçersiz URL'li kayıtlar analizden çıkarılır.
# 7) Fiyat için piyasa eşiği kullanılmaz.
#    Gerçekten ucuz/pahalı ilan yanlışlıkla silinmez.
# 8) Mobil tabloda yalnızca mahalle adı gösterilir.
# =========================================================

VERSION = "v4.5-valid-listing-mobile"

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


LIVE_NEIGHBORHOOD_MAX_RESULTS = max(
    1, min(env_int("PAS_SYNC_MAX_RESULTS", 20), 200)
)

SYNC_CACHE_HOURS = max(
    1, min(env_int("PAS_SYNC_CACHE_HOURS", 6), 72)
)


# =========================================================
# NORMALIZATION
# =========================================================

def parse_int(value):
    if value in (None, ""):
        return None

    if isinstance(value, bool):
        return int(value)

    if isinstance(value, int):
        return value

    if isinstance(value, float):
        return int(value)

    raw = str(value).strip()

    # Fiyat/metrekare alanından sayı dışı karakterleri çıkar.
    text = re.sub(r"[^\d,.\-]", "", raw)

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

            if (
                len(parts) > 1
                and all(p.isdigit() for p in parts)
                and len(parts[-1]) == 3
            ):
                text = "".join(parts)
            else:
                text = text.replace(",", ".")

        elif "." in text:
            parts = text.split(".")

            if (
                len(parts) > 1
                and all(p.isdigit() for p in parts)
                and len(parts[-1]) == 3
            ):
                text = "".join(parts)

        return int(float(text))

    except Exception:
        return None


def normalize_place(value):
    text = str(value or "").strip()

    text = re.sub(
        r"\s+(Mahallesi|Mah\.|Mh\.|Mah|Mh)$",
        "",
        text,
        flags=re.I
    )

    return text.strip()


def slug(value):
    text = normalize_place(value).strip().casefold()

    text = unicodedata.normalize("NFKD", text)
    text = "".join(
        ch for ch in text
        if not unicodedata.combining(ch)
    )

    for a, b in {
        "ı": "i",
        "ğ": "g",
        "ü": "u",
        "ş": "s",
        "ö": "o",
        "ç": "c",
    }.items():
        text = text.replace(a, b)

    return re.sub(
        r"[^a-z0-9]+",
        "-",
        text
    ).strip("-")


def sahibinden_neighborhood_url(district, neighborhood):
    d = slug(district)
    n = slug(neighborhood)

    return (
        "https://www.sahibinden.com/satilik-daire/"
        f"istanbul-{d}-{n}-{n}-mh.?sorting=date_desc"
    )


def normalize_listing_date(value):
    from datetime import date

    raw = str(value or "").strip()

    if not raw:
        return ""

    m = re.match(
        r"(\d{4})-(\d{2})-(\d{2})",
        raw
    )

    if m:
        return (
            f"{m.group(1)}-"
            f"{m.group(2)}-"
            f"{m.group(3)}"
        )

    months = {
        "ocak": 1,
        "şubat": 2,
        "subat": 2,
        "mart": 3,
        "nisan": 4,
        "mayıs": 5,
        "mayis": 5,
        "haziran": 6,
        "temmuz": 7,
        "ağustos": 8,
        "agustos": 8,
        "eylül": 9,
        "eylul": 9,
        "ekim": 10,
        "kasım": 11,
        "kasim": 11,
        "aralık": 12,
        "aralik": 12,
    }

    cleaned = raw.casefold().replace(".", " ")
    parts = re.split(r"\s+", cleaned)

    if len(parts) >= 2:
        try:
            day = int(
                re.sub(r"\D", "", parts[0])
            )
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
                return date(
                    year,
                    month,
                    day
                ).isoformat()
            except Exception:
                pass

    return ""


# =========================================================
# SAHIBINDEN URL / ID VALIDATION
# =========================================================

def extract_listing_id_from_url(url):
    """
    Sahibinden ilan detay URL'sinden güçlü biçimde ilan ID'si çıkarmaya çalışır.

    Örnek:
    .../ilan/emlak-konut-satilik-....-1234567890/detay
    """

    value = str(url or "").strip()

    if not value:
        return ""

    try:
        parsed = urlparse(value)

        host = (parsed.hostname or "").lower()

        if host not in {
            "sahibinden.com",
            "www.sahibinden.com"
        }:
            return ""

        path = parsed.path or ""

    except Exception:
        return ""

    # İlan numaraları uzun numerik ID'lerdir.
    matches = re.findall(
        r"(?<!\d)(\d{8,})(?!\d)",
        path
    )

    if not matches:
        return ""

    # Detay URL'sinde en sondaki uzun sayı genellikle ilan ID'sidir.
    return matches[-1]


def valid_listing_url(url, expected_id=None):
    """
    Arama/category URL'sini ilan URL'si sanmayı önler.

    expected_id verilmişse URL'deki ilan ID'si ile eşleşmesi gerekir.
    """

    value = str(url or "").strip()

    if not value:
        return False

    if value.startswith("/"):
        value = "https://www.sahibinden.com" + value

    try:
        parsed = urlparse(value)
        host = (parsed.hostname or "").lower()

        if host not in {
            "sahibinden.com",
            "www.sahibinden.com"
        }:
            return False

    except Exception:
        return False

    url_id = extract_listing_id_from_url(value)

    if not url_id:
        return False

    if expected_id:
        expected = str(expected_id).strip()

        if expected and expected != url_id:
            return False

    return True


# =========================================================
# LISTING MODEL
# =========================================================

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
    source: str = "sahibinden-scraper-pro"

    @property
    def gross_price_m2(self):
        if self.price and self.gross_m2:
            return round(
                self.price / self.gross_m2
            )

        return None

    @property
    def net_price_m2(self):
        if self.price and self.net_m2:
            return round(
                self.price / self.net_m2
            )

        return None

    def to_dict(self):
        d = asdict(self)

        d["gross_price_m2"] = (
            self.gross_price_m2
        )

        d["net_price_m2"] = (
            self.net_price_m2
        )

        return d


# =========================================================
# POSTGRESQL
# =========================================================

def db_configured():
    return bool(DATABASE_URL)


def db_connect():
    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL tanımlı değil."
        )

    return psycopg.connect(
        DATABASE_URL,
        row_factory=dict_row
    )


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
                   
