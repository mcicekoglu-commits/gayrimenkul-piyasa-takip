import os
import re
import json
import statistics
import unicodedata
import xml.etree.ElementTree as ET
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from dataclasses import dataclass, asdict
from datetime import date, datetime, timezone, timedelta
from threading import Lock

from flask import Flask, request, render_template_string, jsonify
import psycopg
from psycopg.rows import dict_row

app = Flask(__name__)

# =========================================================
# HLF PAS v4.6
#
# ANA PRENSİPLER
# 1) Normal analiz yalnız PostgreSQL kullanır -> Apify maliyeti yok.
# 2) Canlı güncelleme yalnız seçili mahalle için yapılır.
# 3) Telefon/detay enrichment kapalıdır.
# 4) Aynı mahalle + aynı sorgu kısa sürede yeniden ücretli çalıştırılmaz.
# 5) Sahibinden ilan URL + ilan ID doğrulaması yapılır.
# 6) Geçersiz/eski kategori URL'leri analizden çıkarılır.
# 7) Fiyat ve m² fiyatı piyasa eşiğiyle "düzeltilmez".
# 8) Fiyat/m² DAİMA PAS içinde hesaplanır:
#       net TL/m²  = gerçek ilan fiyatı / net m²
#       brüt TL/m² = gerçek ilan fiyatı / brüt m²
# 9) Kaynaktan gelen hazır TL/m² alanı kullanılmaz.
# 10) Mobil arayüz kompakt, favori ilçe/mahalle yıldızlıdır.
# =========================================================

VERSION = "v4.28-compact-favorite-filters"

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
ACTOR_ID = "clearpath~sahibinden-real-estate"


# =========================================================
# USD / TRY — TCMB
# =========================================================

TCMB_TODAY_XML = "https://www.tcmb.gov.tr/kurlar/today.xml"

_usd_try_cache = {
    "rate": None,
    "fetched_at": None,
    "source": "TCMB",
}
_usd_try_lock = Lock()


def env_int(name, default):
    try:
        return int(os.environ.get(name, str(default)) or default)
    except Exception:
        return default


USD_TRY_CACHE_MINUTES = max(
    15, min(env_int("PAS_USD_TRY_CACHE_MINUTES", 180), 1440)
)


def env_float(name, default):
    try:
        return float(os.environ.get(name, str(default)) or default)
    except Exception:
        return default


LIVE_NEIGHBORHOOD_MAX_RESULTS = max(1, min(env_int("PAS_SYNC_MAX_RESULTS", 100), 100))
SYNC_CACHE_HOURS = max(
    1, min(env_int("PAS_SYNC_CACHE_HOURS", 6), 72)
)


# Bir canlı güncellemenin toplam Apify maliyetine üst sınır.
# Sahibinden Real Estate Scraper 20 özet ilan için normalde bunun çok altında kalmalıdır.
APIFY_MAX_TOTAL_CHARGE_USD = max(0.10, min(env_float("PAS_APIFY_MAX_TOTAL_CHARGE_USD", 1.25), 1.25))



def get_usd_try_rate(force=False):
    """
    TCMB günlük USD döviz satış kurunu alır.
    Kur uygulama belleğinde cache'lenir; her ilan için internete çıkılmaz.
    İnternet geçici olarak erişilemezse son başarılı kur kullanılır.
    İsteğe bağlı acil fallback:
      PAS_USD_TRY_FALLBACK=...
    """
    now = datetime.now(timezone.utc)

    with _usd_try_lock:
        cached_rate = _usd_try_cache.get("rate")
        fetched_at = _usd_try_cache.get("fetched_at")

        if (
            not force
            and cached_rate
            and fetched_at
            and (now - fetched_at).total_seconds() < USD_TRY_CACHE_MINUTES * 60
        ):
            return float(cached_rate)

        try:
            req = Request(
                TCMB_TODAY_XML,
                headers={
                    "Accept": "application/xml,text/xml,*/*",
                    "User-Agent": f"HLF-PAS/{VERSION}",
                },
                method="GET",
            )
            with urlopen(req, timeout=12) as response:
                xml_data = response.read()

            root = ET.fromstring(xml_data)
            usd = None

            for currency in root.findall("Currency"):
                if str(currency.attrib.get("CurrencyCode") or "").upper() == "USD":
                    usd = currency
                    break

            if usd is None:
                raise RuntimeError("TCMB XML içinde USD bulunamadı.")

            # Kullanıcıya gösterilecek TL->USD çevrimi için Döviz Satış kurunu kullan.
            text = (usd.findtext("ForexSelling") or "").strip().replace(",", ".")
            rate = float(text)

            if rate <= 0:
                raise RuntimeError("TCMB USD kuru geçersiz.")

            _usd_try_cache["rate"] = rate
            _usd_try_cache["fetched_at"] = now
            _usd_try_cache["source"] = "TCMB ForexSelling"
            return rate

        except Exception as exc:
            if cached_rate:
                return float(cached_rate)

            fallback = os.environ.get("PAS_USD_TRY_FALLBACK", "").strip()
            if fallback:
                try:
                    rate = float(fallback.replace(",", "."))
                    if rate > 0:
                        _usd_try_cache["rate"] = rate
                        _usd_try_cache["fetched_at"] = now
                        _usd_try_cache["source"] = "ENV fallback"
                        return rate
                except Exception:
                    pass

            print("HLF PAS USD/TRY warning:", exc, flush=True)
            return None


def try_to_usd(tl_value, usd_try_rate):
    if tl_value in (None, "") or not usd_try_rate:
        return None
    try:
        return round(float(tl_value) / float(usd_try_rate))
    except Exception:
        return None


# =========================================================
# NORMALIZATION
# =========================================================

def parse_int(value):
    """Türkçe/uluslararası sayı formatlarını güvenli biçimde integer'a çevirir."""
    if value in (None, ""):
        return None

    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)

    # Bazı API'ler price={"value": 123, "currency":"TRY"} döndürebilir.
    if isinstance(value, dict):
        for key in ("value", "amount", "price", "rawValue"):
            if value.get(key) not in (None, ""):
                return parse_int(value.get(key))
        return None

    raw = str(value).strip()
    text = re.sub(r"[^\d,.\-]", "", raw)
    if not text:
        return None

    try:
        if "," in text and "." in text:
            # 12.500.000,00 veya 12,500,000.00
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
            # 12.500.000 -> binlik ayırıcı
            if len(parts) > 1 and all(p.isdigit() for p in parts) and all(len(p) == 3 for p in parts[1:]):
                text = "".join(parts)

        return int(float(text))
    except Exception:
        return None


def normalize_place(value):
    text = str(value or "").strip()
    text = re.sub(r"\s+(Mahallesi|Mah\.|Mh\.|Mah|Mh)$", "", text, flags=re.I)
    return text.strip()


def slug(value):
    text = normalize_place(value).strip().casefold()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    for a, b in {
        "ı": "i", "ğ": "g", "ü": "u",
        "ş": "s", "ö": "o", "ç": "c",
    }.items():
        text = text.replace(a, b)
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def sahibinden_neighborhood_url(district, neighborhood, filters=None):
    """
    HLF PAS v4.10:
    Sahibinden'in gerçek mahalle SEO URL'sini üretir.

    ÖNEMLİ:
    Tarih/fiyat gibi doğrulanmamış query parametrelerini URL'ye eklemiyoruz.
    Bunlar Actor'ın mahalle sayfasını geniş kategori gibi yorumlamasına yol açabiliyor.
    Filtreleme PostgreSQL/PAS tarafında yapılır.
    """
    path_overrides = {
        "Sahrayıcedit": "sahrayi-cedit",
        "Küçükyalı Merkez": "kucukyali-merkez",
        "Yeni Mahalle": "yeni-mahalle",
        "Beykoz Merkez": "beykoz-merkez",
        "Şişli Merkez": "sisli-merkez",
        "Kocasinan Merkez": "kocasinan-merkez",
        "Yenibosna Merkez": "yenibosna-merkez",
        "Mahmut Şevket Paşa": "mahmut-sevket-pasa",
        "Mehmet Akif Ersoy": "mehmet-akif-ersoy",
        "Aziz Mahmut Hüdayi": "aziz-mahmut-hudayi",
        "Küçük Çamlıca": "kucuk-camlica",
        "Fevzi Çakmak": "fevzi-cakmak",
        "Petrol İş": "petrol-is",
    }

    # "(Bölge)" kayıtları mahalle değildir; yanlış/geniş aramaya gitmesin.
    if "(Bölge)" in str(neighborhood):
        raise ValueError(
            f"{neighborhood} bir mahalle değil, bölge kaydıdır. "
            "Canlı güncelleme için gerçek bir mahalle seçin."
        )

    d = slug(district)
    n = path_overrides.get(neighborhood, slug(neighborhood))

    if not d or not n:
        raise ValueError("İlçe/mahalle URL'si üretilemedi.")

    return (
        "https://www.sahibinden.com/satilik-daire/"
        f"istanbul-{d}-{n}-{n}-mh.?sorting=date_desc"
    )


def validate_live_start_url(url, district, neighborhood):
    """
    Apify çağrısından ÖNCE URL'nin gerçekten seçilen ilçe+mahalleyi
    hedeflediğini kontrol eder. Uyuşmazsa ücretli Actor hiç çalışmaz.
    """
    value = str(url or "").strip()
    parsed = urlparse(value)

    if (parsed.hostname or "").lower() not in {"www.sahibinden.com", "sahibinden.com"}:
        raise ValueError("Canlı güncelleme URL alan adı geçersiz.")

    if not parsed.path.startswith("/satilik-daire/"):
        raise ValueError("Canlı güncelleme URL'si satılık daire sayfası değil.")

    path = parsed.path.strip("/").casefold()
    d = slug(district)
    n = slug(neighborhood)

    # path_overrides ile üretilmiş mahalle slug'ını URL'nin kendisinden çıkarıp
    # district + '-...-...-mh.' yapısını kontrol ediyoruz.
    if f"istanbul-{d}-" not in path or not path.endswith("-mh."):
        raise ValueError(
            "Mahalle URL doğrulaması başarısız. Apify çalıştırılmadı; ücret oluşmadı."
        )

    # URL'de mahalle segmenti iki kez yer almalı (Sahibinden SEO formatı).
    tail = path.split(f"istanbul-{d}-", 1)[1]
    if not re.match(r"^.+-.+-mh\.$", tail):
        raise ValueError(
            "Mahalle URL kapsamı yeterince dar değil. Apify çalıştırılmadı."
        )

    return True

def normalize_listing_date(value):
    raw = str(value or "").strip()
    if not raw:
        return ""

    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", raw)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"

    months = {
        "ocak": 1, "şubat": 2, "subat": 2, "mart": 3, "nisan": 4,
        "mayıs": 5, "mayis": 5, "haziran": 6, "temmuz": 7,
        "ağustos": 8, "agustos": 8, "eylül": 9, "eylul": 9,
        "ekim": 10, "kasım": 11, "kasim": 11, "aralık": 12, "aralik": 12,
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


# =========================================================
# SAHIBINDEN URL / ID VALIDATION
# =========================================================

def extract_listing_id_from_url(url):
    value = str(url or "").strip()
    if not value:
        return ""

    if value.startswith("/"):
        value = "https://www.sahibinden.com" + value

    try:
        parsed = urlparse(value)
        host = (parsed.hostname or "").lower()
        if host not in {"sahibinden.com", "www.sahibinden.com"}:
            return ""
        path = parsed.path or ""
    except Exception:
        return ""

    matches = re.findall(r"(?<!\d)(\d{8,})(?!\d)", path)
    return matches[-1] if matches else ""


def valid_listing_url(url, expected_id=None):
    value = str(url or "").strip()
    if not value:
        return False

    if value.startswith("/"):
        value = "https://www.sahibinden.com" + value

    try:
        parsed = urlparse(value)
        host = (parsed.hostname or "").lower()
        if host not in {"sahibinden.com", "www.sahibinden.com"}:
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



def normalize_compare(value):
    return slug(value or "")


def item_matches_requested_location(item, raw, district, neighborhood):
    """
    Sahibinden Real Estate Scraper sonucunun hedef konumla uyuşup uyuşmadığını denetler.

    Açık district / neighborhood alanları varsa bunlar hedef ile eşleşmek zorundadır.
    Açık city alanı varsa İstanbul olmak zorundadır.
    Adres tek başına kullanıldığında eksik yazılabileceği için sadece ek doğrulama olarak
    değerlendirilir; yanlış pozitif üretmemek için adres zorunlu eşleşme değildir.
    """
    sources = [x for x in (item, raw) if isinstance(x, dict)]

    district_values = []
    neighborhood_values = []
    city_values = []
    address_values = []

    for source in sources:
        for key in ("district", "districtName"):
            if source.get(key) not in (None, ""):
                district_values.append(str(source.get(key)))

        for key in ("neighborhood", "neighbourhood", "neighborhoodName", "quarter"):
            if source.get(key) not in (None, ""):
                neighborhood_values.append(str(source.get(key)))

        for key in ("city", "cityName"):
            if source.get(key) not in (None, ""):
                city_values.append(str(source.get(key)))

        for key in ("address", "location", "locationText", "addressNormalized"):
            if source.get(key) not in (None, ""):
                address_values.append(str(source.get(key)))

    wanted_d = slug(district)
    wanted_n = slug(neighborhood)

    if city_values:
        if not any(slug(v) == "istanbul" for v in city_values):
            return False

    if district_values:
        if not any(slug(v) == wanted_d for v in district_values):
            return False

    if neighborhood_values:
        if not any(slug(v) == wanted_n for v in neighborhood_values):
            return False

    # Eğer açık district/neighborhood alanı yok ama adres hedef ilçe/mahalle dışında
    # açıkça başka bir konum gösteriyorsa reddet. Adres eksikse reddetme.
    if not district_values and not neighborhood_values and address_values:
        normalized_addresses = [slug(v) for v in address_values]
        has_target_hint = any(
            wanted_d in a or wanted_n in a or "istanbul" in a
            for a in normalized_addresses
        )
        if not has_target_hint:
            return False

    return True


# =========================================================
# PRICE EXTRACTION / VALIDATION
# =========================================================

def _price_candidate(mapping, *keys):
    if not isinstance(mapping, dict):
        return None
    for key in keys:
        value = mapping.get(key)
        if value not in (None, ""):
            parsed = parse_int(value)
            if parsed is not None and parsed > 0:
                return parsed
    return None


def extract_real_price(item, raw):
    """
    v4.24 PRICE LOCK

    A listing is accepted only if:
    - a positive numeric `price` exists in item or rawSummary,
    - formattedPrice exists,
    - every numeric price source agrees,
    - every formatted price agrees with the numeric price,
    - currency is TRY/TL when provided.

    No guessing, no market threshold, no correcting a price.
    If sources disagree, the listing is rejected.
    """
    sources = [x for x in (item, raw) if isinstance(x, dict)]

    numeric_prices = []
    formatted_prices = []
    currencies = []

    for source in sources:
        if source.get("price") not in (None, ""):
            p = parse_int(source.get("price"))
            if p is not None and p > 0:
                numeric_prices.append(p)

        if source.get("formattedPrice") not in (None, ""):
            fp = parse_int(source.get("formattedPrice"))
            if fp is not None and fp > 0:
                formatted_prices.append(fp)

        if source.get("currency") not in (None, ""):
            currencies.append(str(source.get("currency")).strip().upper())

    # Numeric and formatted values are both mandatory.
    if not numeric_prices or not formatted_prices:
        return None

    if len(set(numeric_prices)) != 1:
        return None

    price = numeric_prices[0]

    if any(fp != price for fp in formatted_prices):
        return None

    if currencies and any(c not in ("TRY", "TL", "₺") for c in currencies):
        return None

    return price


def parse_building_age(value):
    """
    '11-15 arası' gibi aralıkları yanlışlıkla 1115 olarak okumaz.
    Kesin sayı varsa sayı, aralık varsa alt sınır döndürür.
    """
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return int(value)

    text = str(value).strip().casefold()

    m = re.search(r"(\d+)\s*[-–]\s*(\d+)", text)
    if m:
        return int(m.group(1))

    m = re.search(r"\d+", text)
    if m:
        return int(m.group(0))

    if "0-4" in text or "0 - 4" in text:
        return 0

    return None


def valid_area(gross_m2, net_m2):
    """
    Burada piyasa fiyat eşiği YOKTUR.
    Sadece fiziksel olarak anlamsız m² eşleşmelerini engeller.
    """
    if gross_m2 is not None and gross_m2 <= 0:
        gross_m2 = None
    if net_m2 is not None and net_m2 <= 0:
        net_m2 = None

    # Net > brüt olamaz; yanlış alan eşleşmesini boş bırak.
    if gross_m2 and net_m2 and net_m2 > gross_m2:
        net_m2 = None

    return gross_m2, net_m2


def resolve_known_neighborhood(item, raw, district):
    """
    v4.23 strict location verification.

    Rules:
    1) Explicit quarter/neighborhood fields have priority.
    2) If an explicit neighborhood value exists, it MUST exactly map to one
       known neighborhood of the selected district.
    3) Address is used only when explicit neighborhood fields are absent.
    4) Address must identify exactly ONE known neighborhood.
    5) We NEVER replace an unknown location with the user's selected neighborhood.
    """
    known = NEIGHBORHOODS.get(district, [])
    if not known:
        return ""

    known_by_slug = {slug(nb): nb for nb in known if slug(nb)}

    explicit_values = []
    address_values = []

    for source in (item, raw):
        if not isinstance(source, dict):
            continue

        for key in ("quarter", "neighborhood", "neighbourhood", "neighborhoodName"):
            value = source.get(key)
            if value not in (None, ""):
                explicit_values.append(str(value))

        for key in (
            "address", "location", "locationText",
            "fullAddress", "addressNormalized"
        ):
            value = source.get(key)
            if value not in (None, ""):
                address_values.append(str(value))

    # Strong path: explicit neighborhood fields.
    if explicit_values:
        matches = set()
        for value in explicit_values:
            value_slug = slug(normalize_place(value))

            # Exact normalized match.
            if value_slug in known_by_slug:
                matches.add(known_by_slug[value_slug])
                continue

            # Some providers return "X Mahallesi, Kadıköy" or similar.
            for nb_slug, nb_name in known_by_slug.items():
                if re.search(rf"(?:^|-){re.escape(nb_slug)}(?:-|$)", value_slug):
                    matches.add(nb_name)

        return next(iter(matches)) if len(matches) == 1 else ""

    # Fallback path: no explicit neighborhood. Use address only if unambiguous.
    if address_values:
        address_slug = slug(" | ".join(address_values))
        matches = set()

        for nb_slug, nb_name in known_by_slug.items():
            if re.search(rf"(?:^|-){re.escape(nb_slug)}(?:-|$)", address_slug):
                matches.add(nb_name)

        return next(iter(matches)) if len(matches) == 1 else ""

    return ""


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
    property_group: str = "residential"
    location_verified: bool = False
    price_verified: bool = False
    verification_version: int = 0
    source: str = "sahibinden-scraper-pro"

    @property
    def gross_price_m2(self):
        if self.price and self.gross_m2 and self.gross_m2 > 0:
            return round(self.price / self.gross_m2)
        return None

    @property
    def net_price_m2(self):
        if self.price and self.net_m2 and self.net_m2 > 0:
            return round(self.price / self.net_m2)
        return None

    def to_dict(self):
        d = asdict(self)
        d["gross_price_m2"] = self.gross_price_m2
        d["net_price_m2"] = self.net_price_m2
        return d


# =========================================================
# POSTGRESQL
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
                    property_group TEXT NOT NULL DEFAULT 'residential',
                    location_verified BOOLEAN NOT NULL DEFAULT FALSE,
                    price_verified BOOLEAN NOT NULL DEFAULT FALSE,
                    verification_version INTEGER NOT NULL DEFAULT 0,
                    source TEXT NOT NULL DEFAULT '',
                    url TEXT NOT NULL DEFAULT '',
                    active BOOLEAN NOT NULL DEFAULT TRUE,
                    first_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    last_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
            cur.execute("""
                ALTER TABLE pas_listings
                ADD COLUMN IF NOT EXISTS property_group TEXT NOT NULL DEFAULT 'residential'
            """)
            cur.execute("""
                ALTER TABLE pas_listings
                ADD COLUMN IF NOT EXISTS location_verified BOOLEAN NOT NULL DEFAULT FALSE
            """)
            cur.execute("""
                ALTER TABLE pas_listings
                ADD COLUMN IF NOT EXISTS price_verified BOOLEAN NOT NULL DEFAULT FALSE
            """)
            cur.execute("""
                ALTER TABLE pas_listings
                ADD COLUMN IF NOT EXISTS verification_version INTEGER NOT NULL DEFAULT 0
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
            cur.execute("""
                CREATE TABLE IF NOT EXISTS pas_query_cache (
                    query_key TEXT PRIMARY KEY,
                    district TEXT NOT NULL,
                    neighborhood TEXT NOT NULL,
                    last_sync TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    last_received INTEGER NOT NULL DEFAULT 0
                )
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

                # Yalnız gerçek ilan URL'si kaydedilir.
                if not valid_listing_url(url, item.id):
                    continue

                cur.execute("SELECT 1 FROM pas_listings WHERE id=%s", (str(item.id),))
                exists = cur.fetchone() is not None

                cur.execute("""
                    INSERT INTO pas_listings (
                        id,district,neighborhood,title,price,gross_m2,net_m2,
                        rooms,listing_date,building_age,property_group,
                        location_verified,price_verified,verification_version,
                        source,url,active,
                        first_seen,last_seen,updated_at
                    )
                    VALUES (
                        %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                        %s,%s,%s,%s,%s,TRUE,
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
                        property_group=EXCLUDED.property_group,
                        location_verified=EXCLUDED.location_verified,
                        price_verified=EXCLUDED.price_verified,
                        verification_version=EXCLUDED.verification_version,
                        source=EXCLUDED.source,
                        url=EXCLUDED.url,
                        active=TRUE,
                        last_seen=NOW(),
                        updated_at=NOW()
                """, (
                    str(item.id), item.district, item.neighborhood, item.title or "",
                    item.price, item.gross_m2, item.net_m2, item.rooms or "",
                    item.listing_date or "", item.building_age,
                    item.property_group or "residential",
                    bool(item.location_verified),
                    bool(item.price_verified),
                    int(item.verification_version or 0),
                    item.source or "", url
                ))

                if exists:
                    updated_count += 1
                else:
                    new_count += 1

        conn.commit()

    return {"saved": new_count + updated_count, "new": new_count, "updated": updated_count}



def retire_legacy_scope_records(district, neighborhood):
    """
    Eski Search Scraper sürümlerinden kalan kayıtları silmez;
    yalnız sonuç ekranından çıkarılmaları için pasif yapar.
    Yeni Real Estate Actor kayıtlarına dokunmaz.
    """
    if not db_configured():
        return 0
    init_db()
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE pas_listings
                SET active=FALSE, updated_at=NOW()
                WHERE district=%s
                  AND neighborhood=%s
                  AND source<>'sahibinden-real-estate'
                  AND active=TRUE
            """, (district, neighborhood))
            count = cur.rowcount or 0
        conn.commit()
    return count

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


def make_query_key(district, neighborhood, filters):
    """
    v4.22: Actor mahalle filtresi desteklemiyor; ücretli sorgunun gerçek kapsamı
    ilçe + tarih + kaynakta uygulanabilen filtrelerdir. Bu nedenle aynı ilçe için
    farklı mahalle seçmek yeni bir ücretli sorgu başlatmamalı.
    """
    relevant = {
        "engine_version": VERSION,
        "scope": "district",
        "district": district,
        "property_group": str(filters.get("property_group") or "residential_all"),
        "rooms": str(filters.get("rooms") or ""),
        "min_m2": str(filters.get("min_m2") or ""),
        "max_m2": str(filters.get("max_m2") or ""),
        "min_price": str(filters.get("min_price") or ""),
        "max_price": str(filters.get("max_price") or ""),
        "building_age_min": str(filters.get("building_age_min") or ""),
        "building_age_max": str(filters.get("building_age_max") or ""),
        "date_filter": str(filters.get("date_filter") or "current"),
        "hard_max_results": LIVE_NEIGHBORHOOD_MAX_RESULTS,
    }
    return json.dumps(relevant, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def recently_synced_query(query_key, hours=SYNC_CACHE_HOURS):
    if not db_configured():
        return False

    init_db()
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT last_sync
                FROM pas_query_cache
                WHERE query_key = %s
            """, (query_key,))
            row = cur.fetchone()

    if not row or not row["last_sync"]:
        return False

    now = datetime.now(timezone.utc)
    age_seconds = (now - row["last_sync"]).total_seconds()
    return age_seconds < (hours * 3600)


def save_query_sync(query_key, district, neighborhood, received):
    if not db_configured():
        return

    init_db()
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO pas_query_cache (
                    query_key, district, neighborhood, last_sync, last_received
                )
                VALUES (%s, %s, %s, NOW(), %s)
                ON CONFLICT (query_key) DO UPDATE SET
                    district = EXCLUDED.district,
                    neighborhood = EXCLUDED.neighborhood,
                    last_sync = NOW(),
                    last_received = EXCLUDED.last_received
            """, (query_key, district, neighborhood, int(received or 0)))
        conn.commit()


def listing_date_is_allowed(listing_date, date_filter):
    date_filter = str(date_filter or "current").strip()
    if date_filter == "current":
        return True

    days_map = {"7d": 7, "30d": 30, "90d": 90}
    days = days_map.get(date_filter)
    if not days:
        return True

    text = str(listing_date or "").strip()
    if not text:
        return False

    try:
        d = date.fromisoformat(text[:10])
    except Exception:
        return False

    return d >= (date.today() - timedelta(days=days))


def listing_matches_filters(row, filters):
    if not listing_date_is_allowed(row.listing_date, filters.get("date_filter")):
        return False

    wanted_property_group = str(
        filters.get("property_group") or "residential_all"
    ).strip()
    actual_property_group = str(
        getattr(row, "property_group", "") or ""
    ).strip()

    if wanted_property_group == "apartment" and actual_property_group != "apartment":
        return False
    if wanted_property_group == "villa" and actual_property_group != "villa":
        return False
    if wanted_property_group == "commercial" and actual_property_group != "commercial":
        return False
    if wanted_property_group == "residential_all" and actual_property_group not in (
        "apartment", "villa", "residential"
    ):
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
                       rooms,listing_date,building_age,property_group,
                       location_verified,price_verified,verification_version,source,url
                FROM pas_listings
                WHERE active=TRUE
                  AND location_verified=TRUE
                  AND price_verified=TRUE
                  AND verification_version>=24
                  AND source='sahibinden-real-estate'
                  AND district=ANY(%s)
                ORDER BY listing_date DESC, updated_at DESC
            """, (districts,))
            rows = cur.fetchall()

    requested_pairs = {
        (slug(d), slug(n))
        for d in districts
        for n in (selected_nbs.get(d) or [])
    }

    out = []
    for r in rows:
        if requested_pairs and (slug(r["district"]), slug(r["neighborhood"])) not in requested_pairs:
            continue

        # Eski bozuk kategori URL'leri artık sonuçlara girmez.
        if not valid_listing_url(r["url"], r["id"]):
            continue

        gross_m2, net_m2 = valid_area(
            parse_int(r["gross_m2"]),
            parse_int(r["net_m2"])
        )

        item = Listing(
            id=str(r["id"]),
            district=r["district"] or "",
            neighborhood=r["neighborhood"] or "",
            title=r["title"] or "İlan",
            price=parse_int(r["price"]),
            gross_m2=gross_m2,
            net_m2=net_m2,
            rooms=r["rooms"] or "",
            listing_date=normalize_listing_date(r["listing_date"]),
            building_age=parse_int(r["building_age"]),
            property_group=r["property_group"] or "residential",
            location_verified=bool(r["location_verified"]),
            price_verified=bool(r["price_verified"]),
            verification_version=parse_int(r["verification_version"]) or 0,
            source=r["source"] or "cache",
        )
        item._listing_url = r["url"] or ""

        if listing_matches_filters(item, filters):
            out.append(item)

    return out


# =========================================================
# APIFY — SEARCH SCRAPER PRO / MAHALLE
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

            low = detail.casefold()
            if "maximum cost" in low or "usage limit" in low or "aborted" in low:
                raise RuntimeError(
                    "Apify çalışma limiti nedeniyle Actor durduruldu. "
                    f"PAS bu run için enrichment kapalı ve maksimum maliyet "
                    f"${APIFY_MAX_TOTAL_CHARGE_USD:.2f} olarak ayarlı. "
                    "Apify aylık kullanım limiti bu tutarın altındaysa Canlı Güncelle çalışmaz. "
                    f"Teknik ayrıntı: HTTP {exc.code}: {detail}"
                ) from exc

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

    @staticmethod
    def _named_attribute(item, *names):
        if not isinstance(item, dict):
            return None
        raw = item.get("rawSummary") if isinstance(item.get("rawSummary"), dict) else {}

        containers = [item, raw]
        wanted = {slug(x) for x in names}

        for container in containers:
            for bucket_name in ("attributes", "searchAttributes", "summaryAttributes"):
                bucket = container.get(bucket_name)
                if isinstance(bucket, dict):
                    for k, v in bucket.items():
                        if slug(k) in wanted and v not in (None, ""):
                            return v
        return None

    def run_neighborhood(self, district, neighborhood, filters=None, max_results=None):
        if not self.configured():
            raise RuntimeError("APIFY_API_TOKEN tanımlı değil.")

        filters = filters or {}

        property_group = str(
            filters.get("property_group") or "residential_all"
        ).strip()

        limit = max(
            1,
            min(int(max_results or LIVE_NEIGHBORHOOD_MAX_RESULTS), 100)
        )

        actor_input = {
            "listingType": "Sale",
            "city": "Istanbul",
            "district": [district],
            "sortBy": "Newest",
            "extractPhoneNumbers": False,
            # KRİTİK MALİYET KORUMASI:
            # 0 = sınırsızdı ve 496 gibi pahalı taramalara yol açıyordu.
            "maxResults": limit,
        }

        if property_group == "commercial":
            actor_input["propertyCategory"] = "Commercial"
        else:
            # v4.20:
            # Daire / Villa alt tipini Actor'a göndermiyoruz.
            # Actor bazı ilçe+tarih+çoklu propertyType kombinasyonlarında
            # 0 ham sonuç döndürebiliyor. Bunun yerine Residential kapsamın
            # tamamını çekip propertyType sınıflamasını PAS içinde yapıyoruz.
            actor_input["propertyCategory"] = "Residential"

        # Actor native tarih seçenekleri: 24 saat, 3/7/15/30 gün.
        # 7d ve 30d doğrudan kaynağa gönderilir.
        # 90d Actor tarafından native desteklenmediği için 30 günlük canlı
        # pencere + PostgreSQL geçmişi yaklaşımıyla yürütülür.
        date_map = {
            "current": "Last 24 hours",
            "7d": "Last 7 days",
            "30d": "Last 30 days",
            "90d": "Last 30 days",
        }
        actor_input["listingDate"] = date_map.get(
            str(filters.get("date_filter") or "current"),
            "Last 24 hours"
        )

        min_price = parse_int(filters.get("min_price"))
        max_price = parse_int(filters.get("max_price"))
        min_size = parse_int(filters.get("min_m2"))
        max_size = parse_int(filters.get("max_m2"))

        if min_price is not None:
            actor_input["minPrice"] = min_price
            actor_input["currency"] = "TRY"
        if max_price is not None:
            actor_input["maxPrice"] = max_price
            actor_input["currency"] = "TRY"
        if min_size is not None:
            actor_input["minSize"] = min_size
        if max_size is not None:
            actor_input["maxSize"] = max_size

        room = str(filters.get("rooms") or "").strip()
        if room and room != "5+1 ve üzeri":
            actor_input["rooms"] = [room]

        age_min = parse_int(filters.get("building_age_min"))
        age_max = parse_int(filters.get("building_age_max"))
        if age_min is not None and age_max is not None and 0 <= age_min <= age_max <= 31:
            ages = []
            for age in range(age_min, age_max + 1):
                ages.append("0 (Ready)" if age == 0 else str(age))
            if ages:
                actor_input["buildingAge"] = ages

        params = {
            "clean": "true",
            "format": "json",
            "limit": str(limit),
            "maxItems": str(limit),
            "maxTotalChargeUsd": f"{APIFY_MAX_TOTAL_CHARGE_USD:.2f}",
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
            method="POST"
        )

        payload = self._request_json(req)

        if isinstance(payload, list):
            rows = payload
        elif isinstance(payload, dict):
            rows = payload.get("items") or payload.get("data") or payload.get("results") or []
            if not isinstance(rows, list):
                rows = []
        else:
            rows = []

        return rows, actor_input, f"actor://{self.actor_id}/Istanbul/{district}/{neighborhood}"

    def normalize_item(self, item, fallback_district, fallback_neighborhood):
        if not isinstance(item, dict):
            return None
        raw = item.get("rawSummary") if isinstance(item.get("rawSummary"), dict) else {}

        city = normalize_place(self._pick(item, "city", "cityName") or self._pick(raw, "city", "cityName") or "")
        district = normalize_place(self._pick(item, "district", "districtName") or self._pick(raw, "district", "districtName") or "")
        # Actor'ın gerçek ücretli kapsamı ilçe. O yüzden gelen 100 kaydın
        # tümünü doğru mahalleleriyle DB'ye yazıyoruz; seçilen mahalle sonra DB'de süzülür.
        if slug(city) not in ("istanbul", ""):
            return None
        if district and slug(district) != slug(fallback_district):
            return None

        neighborhood = resolve_known_neighborhood(
            item, raw, fallback_district
        )
        if not neighborhood:
            # Konum açıkça doğrulanamıyorsa ilanı kaydetme.
            return None

        city = "İstanbul"
        district = fallback_district

        listing_url = str(
            self._pick(item, "url", "listingUrl", "href", "sourceUrl")
            or self._pick(raw, "url", "listingUrl", "href", "sourceUrl") or ""
        ).strip()
        if listing_url.startswith("/"):
            listing_url = "https://www.sahibinden.com" + listing_url

        listing_id = str(
            self._pick(item, "id", "listingId", "adId", "classifiedId")
            or self._pick(raw, "id", "listingId", "adId", "classifiedId") or ""
        ).strip()
        if not listing_id:
            listing_id = extract_listing_id_from_url(listing_url)
        if not listing_id or not valid_listing_url(listing_url, listing_id):
            return None

        status = str(item.get("status") or "active").strip().casefold()
        if status and status not in ("active", "aktif"):
            return None

        price = extract_real_price(item, raw)
        if price is None:
            return None

        gross_m2 = parse_int(
            self._pick(item, "grossSize", "grossM2", "gross_m2", "size", "m2")
            or self._pick(raw, "grossSize", "grossM2", "gross_m2", "size", "m2")
        )
        net_m2 = parse_int(
            self._pick(item, "netSize", "netM2", "net_m2")
            or self._pick(raw, "netSize", "netM2", "net_m2")
        )
        gross_m2, net_m2 = valid_area(gross_m2, net_m2)
        if gross_m2 is None and net_m2 is None:
            return None

        rooms = str(
            self._pick(item, "rooms", "roomCount", "room")
            or self._pick(raw, "rooms", "roomCount", "room") or ""
        ).strip()
        building_age = parse_building_age(
            self._pick(item, "buildingAge", "building_age", "buildingAgeYears")
            or self._pick(raw, "buildingAge", "building_age", "buildingAgeYears")
        )
        listed_at = (
            self._pick(item, "listingDate", "listedAt", "createdAt", "date", "dateCreated")
            or self._pick(raw, "listingDate", "listedAt", "createdAt", "date", "dateCreated") or ""
        )
        title = str(
            self._pick(item, "title", "listingTitle", "adTitle")
            or self._pick(raw, "title", "listingTitle", "adTitle") or "İlan"
        ).strip()

        raw_category = str(
            self._pick(item, "propertyCategory", "category")
            or self._pick(raw, "propertyCategory", "category")
            or ""
        ).strip()
        raw_type = str(
            self._pick(item, "propertyType", "type")
            or self._pick(raw, "propertyType", "type")
            or ""
        ).strip()

        category_path = self._pick(item, "categoryPath") or self._pick(raw, "categoryPath") or ""
        if isinstance(category_path, list):
            category_path_text = " ".join(str(x) for x in category_path)
        else:
            category_path_text = str(category_path)

        classify_text = " ".join([
            raw_type,
            raw_category,
            category_path_text,
            title,
        ])
        classify_slug = slug(classify_text)

        villa_keywords = (
            "villa", "mustakil", "detached-house", "summer-house",
            "yazlik", "farm-house", "ciftlik-evi", "mansion",
            "kosk", "waterfront-villa", "yali"
        )
        apartment_keywords = (
            "apartment", "daire", "residence", "rezidans",
            "waterfront-apartment"
        )
        commercial_keywords = (
            "commercial", "isyeri", "is-yeri", "ofis", "dukkan",
            "magaza", "depo", "atolye"
        )

        if any(k in classify_slug for k in commercial_keywords):
            property_group = "commercial"
        elif any(k in classify_slug for k in villa_keywords):
            property_group = "villa"
        elif any(k in classify_slug for k in apartment_keywords):
            property_group = "apartment"
        else:
            property_group = "residential"

        listing = Listing(
            id=listing_id,
            district=fallback_district,
            neighborhood=neighborhood,
            title=title,
            price=price,
            gross_m2=gross_m2,
            net_m2=net_m2,
            rooms=rooms,
            listing_date=normalize_listing_date(listed_at),
            building_age=building_age,
            property_group=property_group,
            location_verified=True,
            price_verified=True,
            verification_version=24,
            source="sahibinden-real-estate"
        )
        listing._listing_url = listing_url
        listing._city = city
        return listing

    def sync_neighborhood(self, district, neighborhood, filters=None, max_results=None):
        self._active_property_group = str(
            (filters or {}).get("property_group") or "residential_all"
        ).strip()

        raw_items, actor_input, start_url = self.run_neighborhood(
            district,
            neighborhood,
            filters=filters,
            max_results=max_results,
        )

        accepted_all = []
        rejected = {
            "strict_validation": 0,
            "outside_date_range": 0,
            "duplicate_id": 0,
        }
        seen = set()

        for raw in raw_items:
            item = self.normalize_item(raw, district, neighborhood)
            if not item:
                rejected["strict_validation"] += 1
                continue

            if not listing_date_is_allowed(
                item.listing_date, (filters or {}).get("date_filter")
            ):
                rejected["outside_date_range"] += 1
                continue

            if item.id in seen:
                rejected["duplicate_id"] += 1
                continue

            seen.add(item.id)
            accepted_all.append(item)

        # Kullanıcının seçtiği mülk tipi/oda vb. filtreler hedef sonuç için uygulanır.
        target_items = [
            item for item in accepted_all
            if slug(item.neighborhood) == slug(neighborhood)
            and listing_matches_filters(item, filters or {})
        ]

        return {
            "raw_count": len(raw_items),
            "accepted_all": accepted_all,
            "accepted": target_items,
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
# ANALİZ
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
            "avg_net_m2": None,
            "avg_rooms": None,
        }

    prices = [x.price for x in listings if x.price]
    gross = [x.gross_price_m2 for x in listings if x.gross_price_m2]
    net = [x.net_price_m2 for x in listings if x.net_price_m2]
    ages = [x.building_age for x in listings if x.building_age is not None]
    net_sizes = [x.net_m2 for x in listings if x.net_m2 and x.net_m2 > 0]

    # Oda ortalaması: 3+1 -> 3, 2+1 -> 2.
    # Sonuç kullanıcıya örn. "2.8+1" şeklinde gösterilir.
    room_values = []
    for x in listings:
        room_text = str(x.rooms or "").strip()
        m = re.match(r"^(\d+)\s*\+", room_text)
        if m:
            room_values.append(int(m.group(1)))
        elif re.fullmatch(r"\d+", room_text):
            room_values.append(int(room_text))

    avg_rooms = round(statistics.mean(room_values), 1) if room_values else None

    return {
        "count": len(listings),
        "median_price": round(statistics.median(prices)) if prices else None,
        "avg_price": round(statistics.mean(prices)) if prices else None,
        "avg_gross_m2_price": round(statistics.mean(gross)) if gross else None,
        "avg_net_m2_price": round(statistics.mean(net)) if net else None,
        "avg_building_age": round(statistics.mean(ages), 1) if ages else None,
        "avg_net_m2": round(statistics.mean(net_sizes), 1) if net_sizes else None,
        "avg_rooms": avg_rooms,
    }


def opportunity_analysis(listings):
    groups = {}
    for x in listings:
        groups.setdefault((x.district, x.neighborhood), []).append(x)

    result = []
    for x in listings:
        peers = groups[(x.district, x.neighborhood)]

        # Fırsat hesabında öncelik NET m² fiyatıdır.
        peer_values = [p.net_price_m2 for p in peers if p.net_price_m2]
        current = x.net_price_m2

        # Net yoksa brüt yedeği.
        if not peer_values or not current:
            peer_values = [p.gross_price_m2 for p in peers if p.gross_price_m2]
            current = x.gross_price_m2

        median_m2 = statistics.median(peer_values) if peer_values else None
        delta = (
            ((current / median_m2) - 1) * 100
            if median_m2 and current
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
            "m2_vs_neighborhood_pct": round(delta, 1) if delta is not None else None,
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
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>HLF PAS</title>
<style>
*{box-sizing:border-box}
:root{--ink:#18202b;--muted:#6b7280;--line:#d9dde3;--bg:#f4f5f7;--card:#fff;--accent:#1f2937}
body{margin:0;padding:10px;background:var(--bg);color:var(--ink);font-family:Arial,Helvetica,sans-serif}
.container{max-width:920px;margin:auto;padding-bottom:90px}
.header{display:flex;align-items:baseline;gap:10px;margin:2px 2px 8px}
h1{font-size:31px;line-height:1;margin:0;font-weight:850;letter-spacing:-.5px}
.subtitle{font-size:13px;color:var(--muted);white-space:nowrap}
.card{background:var(--card);border-radius:15px;padding:11px;margin-bottom:9px;box-shadow:0 3px 14px rgba(0,0,0,.055)}
.title{font-size:17px;font-weight:800;margin:0}
.small{font-size:12px;color:var(--muted)}
.topline{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:8px}
.segmented{display:flex;gap:4px}
.seg input{display:none}
.seg span{display:block;padding:6px 8px;border:1px solid var(--line);border-radius:9px;font-size:12px;font-weight:750;white-space:nowrap}
.seg input:checked+span{background:var(--accent);color:#fff;border-color:var(--accent)}
.favorite{background:#fffaf0;border:1px solid #eadfbe;border-radius:11px;padding:8px;margin-bottom:8px}
.favorite-title{font-size:14px;font-weight:800;margin-bottom:5px}
.favorite-section{display:flex;gap:5px;flex-wrap:wrap}
.favorite-label{font-size:11px;color:var(--muted);width:100%;margin-top:3px}
.chip{display:flex;align-items:center;gap:4px;border:1px solid var(--line);border-radius:9px;padding:5px 6px;background:#fff;font-size:13px}
.chip input{width:16px;height:16px;margin:0}
.star{border:0;background:transparent;padding:0 2px;font-size:19px;line-height:1;color:#c6cbd2;cursor:pointer}
.star.on{color:#e6ad00}
details{border:1px solid var(--line);border-radius:11px;margin-top:7px;background:#fff;overflow:hidden}
summary{padding:9px 10px;font-weight:800;font-size:14px;cursor:pointer;list-style:none}
summary::-webkit-details-marker{display:none}
summary::before{content:"▸";display:inline-block;margin-right:7px;transition:.15s}
details[open]>summary::before{transform:rotate(90deg)}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:6px;padding:0 7px 8px}
.rowitem{display:flex;align-items:center;gap:5px;padding:7px;border:1px solid var(--line);border-radius:9px;background:#fff;min-width:0}
.rowitem input{width:17px;height:17px;margin:0;flex:0 0 auto}
.rowname{flex:1;min-width:0;font-size:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.district-line{display:flex;align-items:center;gap:5px}
.district-line .rowitem{flex:1}
.nb-list{padding:0 7px 8px}
.nb-grid{display:grid;grid-template-columns:1fr 1fr;gap:6px}
.filter-grid{display:grid;grid-template-columns:1fr 1fr;gap:6px}
.field{display:block;font-size:11px;font-weight:700;color:var(--muted);margin:0 0 3px}
input[type=number],select{width:100%;padding:8px;border:1px solid var(--line);border-radius:9px;font-size:14px;background:#fff;color:var(--ink)}
.quickbar{display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:7px}.quickbar-three{grid-template-columns:1.05fr 1.05fr .9fr}
.primary,.secondary{width:100%;padding:11px;border-radius:10px;font-size:14px;font-weight:800}
.primary{border:0;background:#181818;color:#fff}
.secondary{border:1px solid #ccd2da;background:#fff;color:var(--ink)}
.primary:disabled,.secondary:disabled{opacity:.55}
.hidden{display:none!important}
.notice{background:#eef6ff;border:1px solid #cfe3ff;border-radius:10px;padding:9px;font-size:12px;white-space:pre-wrap}
.error{background:#fff1f1;border:1px solid #f4c4c4;border-radius:10px;padding:9px;font-size:12px;white-space:pre-wrap}
.metrics{display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px}
.metric{padding:8px;border:1px solid #e1e5ea;border-radius:10px}
.metric .k{font-size:10px;color:var(--muted)}
.metric .v{font-size:15px;font-weight:800}
.table-wrap{overflow-x:auto;-webkit-overflow-scrolling:touch}
table{width:100%;border-collapse:collapse;font-size:12px}
th,td{padding:8px 6px;border-bottom:1px solid #eceff3;text-align:left;white-space:nowrap}
th{font-size:11px}
.badge{padding:4px 7px;border-radius:999px;background:#eef2f7;font-size:11px}
.usd-value{color:#159447;font-weight:800}
.usd-rate{color:#159447;font-weight:700}
.listing-clickable{cursor:pointer}
.info-bottom{margin-top:12px}
.actions-sticky{position:sticky;bottom:8px;z-index:20;background:rgba(244,245,247,.92);backdrop-filter:blur(8px);padding:5px;border-radius:12px;display:grid;grid-template-columns:1.2fr .8fr;gap:6px}
@media(max-width:600px){
 body{padding:8px}
 h1{font-size:28px}
 .subtitle{font-size:11px}
 .header{margin-bottom:6px}
 .card{padding:9px;border-radius:13px}
 .metrics{grid-template-columns:repeat(3,minmax(0,1fr));gap:4px}
 .grid,.nb-grid{grid-template-columns:1fr 1fr}
}

/* ===== HLF PAS v4.9 compact mobile layout ===== */
body{padding:7px}
.container{max-width:920px}
.header{margin:1px 2px 5px;gap:8px}
h1{font-size:28px}
.subtitle{font-size:11px}
.card{padding:8px;margin-bottom:7px;border-radius:13px}
.topline{margin-bottom:6px}
.title{font-size:16px}
.segmented{gap:3px}
.seg span{padding:5px 7px;font-size:11px;border-radius:8px}

.favorite{
  background:transparent;
  border:0;
  padding:0;
  margin:0 0 6px;
  display:block;
}
#favoriteDistrictLabel,#favoriteNeighborhoodLabel{display:none!important}
#favoriteDistricts{
  background:#f6fbff;
  border:1px solid #e8f2fb;
  border-radius:11px;
  padding:5px;
  margin-bottom:5px;
}
#favoriteNeighborhoods{
  background:#fffdf8;
  border:1px solid #f4ecd8;
  border-radius:11px;
  padding:5px;
  position:relative;
}
#favoriteNeighborhoods:has(.chip){
  min-height:39px;
  display:grid!important;
}
.favorite-section{
  display:grid!important;
  grid-template-columns:repeat(3,minmax(0,1fr))!important;
  gap:3px!important;
}
.chip{
  padding:3px 4px!important;
  gap:2px!important;
  border-radius:8px!important;
  font-size:11.5px!important;
  min-height:29px;
}
.chip input{width:14px!important;height:14px!important}
.star{font-size:16px!important}

.chip:has(input:checked),
.rowitem:has(input:checked){
  background:#effaf1!important;
  border-color:#76c98d!important;
}
.chip:has(input:checked) input,
.rowitem:has(input:checked) input{accent-color:#20aa50}

#districtDetails{margin-top:5px}
details{margin-top:5px;border-radius:10px}
summary{padding:6px 8px;font-size:12.5px}

.nb-list{padding:0 4px 5px!important}
.nb-grid{
  grid-template-columns:repeat(3,minmax(0,1fr))!important;
  gap:2px!important;
}
.nb-grid .rowitem{
  gap:1px!important;
  padding:2px 3px!important;
  min-height:27px!important;
  border-radius:7px!important;
}
.nb-grid .rowitem input{width:13px!important;height:13px!important}
.nb-grid .rowname{font-size:10.7px!important;line-height:1!important}
.nb-grid .star{font-size:14px!important}

.grid{gap:3px;padding:0 4px 5px}
.grid .rowitem{padding:4px;min-height:29px}
.grid .rowname{font-size:11.5px}

.quickbar{gap:4px;margin-bottom:4px}.quickbar-three{grid-template-columns:1.05fr 1.05fr .9fr}
.field{font-size:10px;margin-bottom:2px}
input[type=number],select{padding:7px;font-size:13px;border-radius:8px}
.filter-grid{gap:4px}
.primary,.secondary{padding:10px;font-size:13px}
.actions-sticky{bottom:6px;padding:3px;gap:4px;border-radius:10px}
.info-bottom{margin-top:7px}

@media(max-width:600px){
  body{padding:6px}
  h1{font-size:27px}
  .header{margin-bottom:4px}
  .card{padding:7px}
  .favorite-section{grid-template-columns:repeat(3,minmax(0,1fr))!important}
  .nb-grid{grid-template-columns:repeat(3,minmax(0,1fr))!important}
}


@media(max-width:600px){
  .metrics .metric{padding:6px 5px;min-width:0}
  .metrics .metric .k{font-size:9px;line-height:1.05}
  .metrics .metric .v{font-size:12px;line-height:1.1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
}


/* ===== v4.28 compact + favorite filters ===== */
.quickbar-four{
  grid-template-columns:1fr 1fr 1fr 1fr!important;
  gap:4px!important;
}
.compact-age{display:grid;grid-template-columns:1fr 1fr;gap:3px}
.compact-age input{min-width:0}
.filter-fav-wrap{
  background:#f8fbff;border:1px solid #e5edf6;border-radius:9px;
  padding:4px;margin:4px 0;
}
.filter-fav-grid,.filter-grid-v428{
  display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:4px;
}
.filter-box{
  position:relative;min-width:0;border:1px solid var(--line);
  border-radius:8px;padding:4px;background:#fff;
}
.filter-box .field{padding-right:17px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.filter-star{
  position:absolute;right:3px;top:2px;border:0;background:transparent;
  color:#c6cbd2;font-size:15px;line-height:1;cursor:pointer;padding:0;
}
.filter-star.on{color:#e6ad00}
.filter-box input,.filter-box select{padding:5px!important;font-size:11.5px!important;border-radius:6px!important}
#filterDetails[open]>summary{padding-bottom:4px}
#filterDetails .filter-inner{padding:0 5px 6px}
@media(max-width:600px){
  .quickbar-four{grid-template-columns:repeat(4,minmax(0,1fr))!important}
  .quickbar-four .field{font-size:8.5px!important}
  .quickbar-four select,.quickbar-four input{padding:5px 3px!important;font-size:10.5px!important}
  .filter-fav-grid,.filter-grid-v428{grid-template-columns:repeat(4,minmax(0,1fr))!important}
  .filter-box{padding:3px}
  .filter-box .field{font-size:8.5px!important}
  .filter-box input,.filter-box select{padding:4px 3px!important;font-size:10.5px!important}
}

</style>
</head>
<body>
<div class="container">

<div class="header">
  <h1>HLF PAS</h1>
  <div class="subtitle">Piyasa Arama Sistemi · {{ version }}</div>
</div>

<form id="pasForm">

<div class="card">
  <div class="topline">
    <div class="title">Bölge seçimi</div>
    <div class="segmented">
      <label class="seg"><input type="radio" name="side" value="all" checked><span>Tümü</span></label>
      <label class="seg"><input type="radio" name="side" value="anadolu"><span>Anadolu</span></label>
      <label class="seg"><input type="radio" name="side" value="avrupa"><span>Avrupa</span></label>
    </div>
  </div>

  <div class="favorite">
        <div id="favoriteDistrictLabel" class="favorite-label">İlçeler</div>
    <div id="favoriteDistricts" class="favorite-section"></div>
    <div id="favoriteNeighborhoodLabel" class="favorite-label">Mahalleler</div>
    <div id="favoriteNeighborhoods" class="favorite-section"></div>
  </div>

  <details id="districtDetails">
    <summary>11 İlçe</summary>
    <div id="districts" class="grid"></div>
  </details>

  <div id="neighborhoodArea"></div>
</div>

<div class="card">
  <div class="quickbar quickbar-four">
    <div>
      <label class="field">İlan Tarihi</label>
      <select name="date_filter">
        <option value="current">Güncel</option>
        <option value="7d">Son 1 hafta</option>
        <option value="30d">Son 1 ay</option>
        <option value="90d">Son 3 ay</option>
      </select>
    </div>
    <div>
      <label class="field">Mülk Tipi</label>
      <select name="property_group">
        <option value="residential_all">Konut Tümü</option>
        <option value="apartment">Apartman / Daire</option>
        <option value="villa">Villa / Müstakil</option>
        <option value="commercial">İşyeri</option>
      </select>
    </div>
    <div>
      <label class="field">Oda</label>
      <select name="rooms">
        <option value="">Farketmez</option>
        <option>1+1</option><option>2+1</option><option>3+1</option>
        <option>4+1</option><option>5+1 ve üzeri</option>
      </select>
    </div>
    <div>
      <label class="field">Bina Yaşı</label>
      <div class="compact-age">
        <input name="building_age_min" type="number" min="0" value="0" placeholder="Min">
        <input name="building_age_max" type="number" min="0" value="2" placeholder="Max">
      </div>
    </div>
  </div>

  <div id="favoriteFiltersWrap" class="filter-fav-wrap hidden">
    <div id="favoriteFilters" class="filter-fav-grid"></div>
  </div>

  <details id="filterDetails" open>
    <summary>Filtreler</summary>
    <div class="filter-inner">
      <div id="otherFilters" class="filter-grid-v428"></div>
    </div>
  </details>
</div>

<div class="actions-sticky">
  <button class="primary" id="searchButton" type="submit">Kayıtlı İlanları Ara</button>
  <button class="secondary" id="syncButton" type="button">Canlı Güncelle</button>
</div>

</form>

<div id="errorBox" class="card hidden"><div class="error" id="errorText"></div></div>
<div id="syncBox" class="card hidden"><div class="notice" id="syncText"></div></div>

<div id="resultsCard" class="card hidden">
  <div class="topline">
    <div class="title">Piyasa özeti</div><span class="badge">PostgreSQL</span>
  </div>

  <div class="metrics">
    <div class="metric"><div class="k">İlan</div><div class="v" id="mCount">-</div></div>
    <div class="metric"><div class="k">Medyan Fiyat</div><div class="v" id="mMedianPrice">-</div></div>
    <div class="metric"><div class="k">Ort. Fiyat</div><div class="v" id="mAvgPrice">-</div></div>
    <div class="metric"><div class="k">Ort. Net $/m²</div><div class="v usd-value" id="mAvgNetUsdM2">-</div></div>
    <div class="metric"><div class="k">Ort. Net TL/m²</div><div class="v" id="mMedianNetM2">-</div></div>
    <div class="metric"><div class="k">Ort. Brüt TL/m²</div><div class="v" id="mMedianM2">-</div></div>
    <div class="metric"><div class="k">Ort. Yaş</div><div class="v" id="mAvgAge">-</div></div>
    <div class="metric"><div class="k">Ort. Net m²</div><div class="v" id="mAvgNetM2">-</div></div>
    <div class="metric"><div class="k">Ort. Oda</div><div class="v" id="mAvgRooms">-</div></div>
  </div>

  <div class="title" style="margin-top:13px">İlanlar</div>
  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>Mahalle</th><th>Oda</th><th>Yaş</th>
          <th>Net m²</th><th class="usd-value">Net $/m²</th><th>Net TL/m²</th><th>Fiyat</th>
          <th>Brüt TL/m²</th><th>Brüt m²</th>
          <th>İlan Tarihi</th><th>İlan ID</th><th>PAS</th>
        </tr>
      </thead>
      <tbody id="listingRows"></tbody>
    </table>
  </div>
</div>

<div class="card info-bottom">
  <details>
    <summary>Veri sağlayıcı ve çalışma bilgisi</summary>
    <div class="notice" style="margin:0 8px 9px"><strong>Veri sağlayıcı:</strong> PostgreSQL + Sahibinden Real Estate Scraper.
Normal analiz Apify çalıştırmaz ve ücret oluşturmaz.
Canlı güncelleme yalnız doğrulanmış seçili mahalle URL’sini çalıştırır; enrichment/telefon/detay kapalıdır.
Aynı mahalle + aynı filtre {{ cache_hours }} saat içinde yeniden ücretli çalıştırılmaz.
Canlı güncellemede bu Actor mahalle filtresi desteklemediği için ilçe taranır; ancak ücretli tarama kesin olarak en fazla 100 ilanla sınırlandırılır. Aynı ilçe + aynı filtre cache süresi içinde farklı mahalleler için yeniden ücretli çalıştırılmaz. Mahalle, Actor'ın açık konum alanlarından kesin doğrulanmadan ilan gösterilmez. Fiyat, numeric price ile formattedPrice birebir uyuşmadan ilan gösterilmez. v4.24 öncesi konum/fiyat doğrulaması olmayan kayıtlar sonuçlardan tamamen gizlenir. Favori ilçe, favori mahalle ve son seçimler sürümden bağımsız kalıcı tarayıcı kaydında saklanır. Favori mahalleler yıldızdan çıkarılana kadar kaydedilir; ana ekranda yalnız seçili ilçeye ait favori mahalleler sabit görünür.
Yalnız yeni Real Estate Actor tarafından doğrulanmış aktif ilanlar gösterilir. Fiyat yalnız numeric price alanından alınır ve formattedPrice ile çapraz doğrulanır. Net TL/m² = price / netSize; Brüt TL/m² = price / grossSize. Net $/m², TCMB USD döviz satış kuru kullanılarak hesaplanır ve kur bellekte cache'lenir.</div>
  </details>
</div>

</div>

<script>
const DISTRICTS={{ districts_json|safe }};
const NEIGHBORHOODS={{ neighborhoods_json|safe }};
const STATE_KEY="hlf_pas_state";
const LEGACY_STATE_KEYS=[
  "hlf_pas_state_v424",
  "hlf_pas_state_v423",
  "hlf_pas_state_v422",
  "hlf_pas_state_v421",
  "hlf_pas_state_v420",
  "hlf_pas_state_v419",
  "hlf_pas_state_v418",
  "hlf_pas_state_v417",
  "hlf_pas_state_v416",
  "hlf_pas_state_v415",
  "hlf_pas_state_v414",
  "hlf_pas_state_v49"
];

let selectedDistricts=new Set();
let selectedNeighborhoods={};
let openDistricts=new Set();

const defaultFavoriteDistricts=DISTRICTS.filter(d=>d.favorite).map(d=>d.name);
let favoriteDistricts=new Set(defaultFavoriteDistricts);
let favoriteNeighborhoods={};

function esc(s){
  return String(s??"").replace(/[&<>"']/g,c=>({
    "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"
  }[c]));
}
function money(n){
  return n==null?"-":new Intl.NumberFormat("tr-TR").format(n)+" ₺";
}
function usdMoney(n){
  return n==null?"-":"$"+new Intl.NumberFormat("tr-TR",{maximumFractionDigits:0}).format(n);
}
function sideValue(){
  return document.querySelector('input[name="side"]:checked')?.value||"all";
}
function domSlug(s){
  return s.toLocaleLowerCase("tr-TR").normalize("NFD")
    .replace(/[\u0300-\u036f]/g,"").replace(/[^a-z0-9]+/g,"-");
}
function sideVisible(d){
  const side=sideValue();
  return side==="all"||d.side===side;
}
function districtData(name){
  return DISTRICTS.find(d=>d.name===name);
}
function isFavNb(d,n){
  return new Set(favoriteNeighborhoods[d]||[]).has(n);
}
function toggleFavDistrict(name){
  if(favoriteDistricts.has(name)) favoriteDistricts.delete(name);
  else favoriteDistricts.add(name);
  renderAll();
  saveState();
}
function toggleFavNeighborhood(d,n){
  const set=new Set(favoriteNeighborhoods[d]||[]);
  if(set.has(n)) set.delete(n); else set.add(n);
  favoriteNeighborhoods[d]=[...set];
  renderAll();
  saveState();
}
function setDistrictSelected(name,checked){
  if(checked){
    selectedDistricts.add(name);
  }else{
    selectedDistricts.delete(name);
    selectedNeighborhoods[name]=[];
    openDistricts.delete(name);
  }
  renderAll();
  saveState();
}
function setNeighborhoodSelected(d,n,checked){
  const set=new Set(selectedNeighborhoods[d]||[]);
  if(checked)set.add(n);else set.delete(n);
  selectedNeighborhoods[d]=[...set];
  if(checked)selectedDistricts.add(d);
  renderAll();
  saveState();
}
function toggleDistrictOpen(d){
  if(openDistricts.has(d))openDistricts.delete(d);else openDistricts.add(d);
  renderNeighborhoodArea();
  saveState();
}

function districtRowHtml(d){
  const fav=favoriteDistricts.has(d.name);
  return `<div class="rowitem">
    <input type="checkbox" ${selectedDistricts.has(d.name)?"checked":""}
      onchange="setDistrictSelected('${esc(d.name)}',this.checked)">
    <span class="rowname">${esc(d.name)}</span>
    <button class="star ${fav?"on":""}" type="button"
      onclick="toggleFavDistrict('${esc(d.name)}')" aria-label="Favori">${fav?"★":"☆"}</button>
  </div>`;
}

function neighborhoodRowHtml(d,n){
  const selected=new Set(selectedNeighborhoods[d]||[]).has(n);
  const fav=isFavNb(d,n);
  const jd=JSON.stringify(d), jn=JSON.stringify(n);
  return `<div class="rowitem">
    <input type="checkbox" ${selected?"checked":""}
      onchange='setNeighborhoodSelected(${jd},${jn},this.checked)'>
    <span class="rowname">${esc(n)}</span>
    <button class="star ${fav?"on":""}" type="button"
      onclick='toggleFavNeighborhood(${jd},${jn})' aria-label="Favori">${fav?"★":"☆"}</button>
  </div>`;
}

function renderDistricts(){
  const visible=DISTRICTS.filter(sideVisible);
  document.getElementById("districts").innerHTML=visible.map(districtRowHtml).join("");
}

function renderFavorites(){
  const visibleFavDistricts=DISTRICTS.filter(
    d=>sideVisible(d)&&favoriteDistricts.has(d.name)
  );

  const fd=document.getElementById("favoriteDistricts");
  fd.innerHTML=visibleFavDistricts.length
    ? visibleFavDistricts.map(d=>{
        return `<div class="chip">
          <input type="checkbox" ${selectedDistricts.has(d.name)?"checked":""}
           onchange="setDistrictSelected('${esc(d.name)}',this.checked)">
          <span>${esc(d.name)}</span>
          <button class="star on" type="button"
            onclick="toggleFavDistrict('${esc(d.name)}')">★</button>
        </div>`;
      }).join("")
    : `<span class="small">Favori ilçe yok</span>`;

  const nbRows=[];

  // v4.27:
  // Üstte yalnız SEÇİLİ ilçelerin favori mahalleleri sabit görünür.
  // Örn. Kadıköy seçiliyse sadece Kadıköy favori mahalleleri görünür.
  // İlçe değişince bu alan otomatik o ilçenin favorilerine döner.
  for(const d of DISTRICTS.filter(
    x=>sideVisible(x)&&selectedDistricts.has(x.name)
  )){
    const favs=Array.isArray(favoriteNeighborhoods[d.name])
      ? favoriteNeighborhoods[d.name]
      : [];

    for(const n of favs){
      if(!(NEIGHBORHOODS[d.name]||[]).includes(n))continue;

      const checked=new Set(
        selectedNeighborhoods[d.name]||[]
      ).has(n);

      const jd=JSON.stringify(d.name);
      const jn=JSON.stringify(n);

      nbRows.push(`<div class="chip favorite-nb-chip"
        title="${esc(d.name)} · ${esc(n)}">
        <input type="checkbox" ${checked?"checked":""}
          onchange='setNeighborhoodSelected(${jd},${jn},this.checked)'>
        <span>${esc(n)}</span>
        <button class="star on" type="button"
          onclick='toggleFavNeighborhood(${jd},${jn})'
          aria-label="${esc(d.name)} ${esc(n)} favoriden çıkar">★</button>
      </div>`);
    }
  }

  document.getElementById("favoriteNeighborhoods").innerHTML=
    nbRows.length
      ? nbRows.join("")
      : `<span class="small">Seçili ilçelerde favori mahalle yok</span>`;
}

function renderNeighborhoodArea(){
  const area=document.getElementById("neighborhoodArea");
  const active=[...selectedDistricts].filter(d=>{
    const data=districtData(d);
    return data&&sideVisible(data);
  });

  if(!active.length){
    area.innerHTML="";
    return;
  }

  area.innerHTML=active.map(d=>{
    const isOpen=openDistricts.has(d);
    const selectedCount=(selectedNeighborhoods[d]||[]).length;
    return `<details ${isOpen?"open":""} data-d="${esc(d)}">
      <summary onclick='event.preventDefault();toggleDistrictOpen(${JSON.stringify(d)})'>
        ${esc(d)} mahalleleri${selectedCount?` · ${selectedCount} seçili`:""}
      </summary>
      <div class="nb-list">
        <div class="nb-grid">
          ${(NEIGHBORHOODS[d]||[]).map(n=>neighborhoodRowHtml(d,n)).join("")}
        </div>
      </div>
    </details>`;
  }).join("");
}

function renderAll(){
  renderDistricts();
  renderFavorites();
  renderNeighborhoodArea();
}

function getOnePair(){
  const pairs=[];
  [...selectedDistricts].forEach(d=>
    (selectedNeighborhoods[d]||[]).forEach(n=>pairs.push([d,n]))
  );
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

function formPayload(){
  const fd=new FormData(document.getElementById("pasForm"));
  return {
    districts:[...selectedDistricts],
    neighborhoods:selectedNeighborhoods,
    date_filter:fd.get("date_filter")||"current",
    property_group:fd.get("property_group")||"residential_all",
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
}

document.getElementById("pasForm").addEventListener("submit",async e=>{
  e.preventDefault();
  if(selectedDistricts.size===0){showError("En az bir ilçe seçin.");return;}

  const payload=formPayload();
  const button=document.getElementById("searchButton");
  button.disabled=true;

  try{
    const result=await postJson("/api/search",payload), data=result.data;
    if(!result.ok||!data.ok)throw new Error(data.error||("Arama başarısız. HTTP "+result.status));

    document.getElementById("mCount").textContent=data.analysis.count;
    document.getElementById("mMedianPrice").textContent=money(data.analysis.median_price);
    document.getElementById("mAvgPrice").textContent=money(data.analysis.avg_price);
    document.getElementById("mMedianM2").textContent=money(data.analysis.avg_gross_m2_price);
    document.getElementById("mAvgNetUsdM2").textContent=usdMoney(data.analysis.avg_net_usd_m2);
    document.getElementById("mMedianNetM2").textContent=money(data.analysis.avg_net_m2_price);
    document.getElementById("mAvgAge").textContent=
      data.analysis.avg_building_age==null?"-":data.analysis.avg_building_age+" yıl";
    document.getElementById("mAvgNetM2").textContent=
      data.analysis.avg_net_m2==null?"-":data.analysis.avg_net_m2+" m²";
    document.getElementById("mAvgRooms").textContent=
      data.analysis.avg_rooms==null?"-":data.analysis.avg_rooms+"+1";

    document.getElementById("listingRows").innerHTML=data.listings.map(r=>`
      <tr class="${r.url?"listing-clickable":""}" data-url="${esc(r.url||"")}">
        <td>${esc(r.neighborhood||"-")}</td>
        <td>${esc(r.rooms||"-")}</td>
        <td>${r.building_age==null?"-":r.building_age}</td>
        <td>${r.net_m2==null?"-":r.net_m2}</td>
        <td class="usd-value">${usdMoney(r.net_usd_m2)}</td>
        <td>${money(r.net_price_m2)}</td>
        <td>${money(r.price)}</td>
        <td>${money(r.gross_price_m2)}</td>
        <td>${r.gross_m2==null?"-":r.gross_m2}</td>
        <td>${esc(r.listing_date||"-")}</td>
        <td>${esc(r.id||"-")}</td>
        <td>${r.opportunity_score??"-"} <span class="small">${esc(r.opportunity_label||"")}</span></td>
      </tr>`).join("");

    document.querySelectorAll(".listing-clickable").forEach(tr=>{
      tr.onclick=()=>{if(tr.dataset.url)window.location.assign(tr.dataset.url);};
    });

    document.getElementById("resultsCard").classList.remove("hidden");
    document.getElementById("errorBox").classList.add("hidden");
  }catch(err){
    showError(err.message||"Beklenmeyen hata.");
  }finally{
    button.disabled=false;
  }
});

document.getElementById("syncButton").addEventListener("click",async()=>{
  const pairs=getOnePair();
  if(pairs.length!==1){
    showError("Canlı güncelleme için tam olarak 1 ilçe ve o ilçeden 1 mahalle seçin.");
    return;
  }

  const [district,neighborhood]=pairs[0];
  const button=document.getElementById("syncButton"), oldText=button.textContent;
  button.disabled=true;
  button.textContent="Güncelleniyor…";

  try{
    const base=formPayload();
    const syncPayload={...base,district,neighborhood};
    const result=await postJson("/api/sync",syncPayload), data=result.data;
    if(!result.ok||!data.ok)throw new Error(data.error||("Güncelleme başarısız. HTTP "+result.status));

    showSuccess(
      `${district}: en fazla ${data.hard_limit||100} ilan sınırıyla ${data.raw_received} ilan tarandı; `+
      `${neighborhood} için ${data.accepted} doğrulanmış ilan bulundu. `+
      `${data.new} yeni, ${data.updated} güncellendi. `+
      `${data.retired_legacy||0} eski doğrulanmamış kayıt sonuçlardan çıkarıldı.`
    );

    document.getElementById("pasForm").requestSubmit();
  }catch(err){
    showError(err.message||"Canlı güncelleme hatası.");
  }finally{
    button.disabled=false;
    button.textContent=oldText;
  }
});


const EXTRA_FILTER_DEFS=[
  ["min_m2","Min Brüt m²","number"],
  ["max_m2","Max Brüt m²","number"],
  ["min_price","Min Fiyat","number"],
  ["max_price","Max Fiyat","number"],
  ["net_m2_min","Min Net TL/m²","number"],
  ["net_m2_max","Max Net TL/m²","number"],
  ["gross_m2_min","Min Brüt TL/m²","number"],
  ["gross_m2_max","Max Brüt TL/m²","number"]
];
let favoriteFilters=new Set();

function filterBoxHtml(def,isFav){
  const [name,label,type]=def;
  return `<div class="filter-box" data-filter="${esc(name)}">
    <label class="field">${esc(label)}</label>
    <button class="filter-star ${isFav?"on":""}" type="button"
      onclick='toggleFavoriteFilter(${JSON.stringify(name)})'>★</button>
    <input name="${esc(name)}" type="${type}" min="0">
  </div>`;
}
function currentExtraFilterValues(){
  const vals={};
  for(const [name] of EXTRA_FILTER_DEFS){
    const el=document.querySelector(`[name="${name}"]`);
    vals[name]=el?el.value:"";
  }
  return vals;
}
function renderFilterFavorites(values=null){
  const vals=values||currentExtraFilterValues();
  const fav=document.getElementById("favoriteFilters");
  const other=document.getElementById("otherFilters");
  const wrap=document.getElementById("favoriteFiltersWrap");

  const favDefs=EXTRA_FILTER_DEFS.filter(d=>favoriteFilters.has(d[0]));
  const otherDefs=EXTRA_FILTER_DEFS.filter(d=>!favoriteFilters.has(d[0]));

  fav.innerHTML=favDefs.map(d=>filterBoxHtml(d,true)).join("");
  other.innerHTML=otherDefs.map(d=>filterBoxHtml(d,false)).join("");
  wrap.classList.toggle("hidden",favDefs.length===0);

  for(const [name] of EXTRA_FILTER_DEFS){
    const el=document.querySelector(`[name="${name}"]`);
    if(el && Object.prototype.hasOwnProperty.call(vals,name))el.value=vals[name]??"";
  }
}
function toggleFavoriteFilter(name){
  const vals=currentExtraFilterValues();
  if(favoriteFilters.has(name))favoriteFilters.delete(name);
  else favoriteFilters.add(name);
  renderFilterFavorites(vals);
  saveState();
}

function collectState(){
  const fd=new FormData(document.getElementById("pasForm")), filters={};
  [
    "date_filter","property_group","rooms","min_m2","max_m2","min_price","max_price",
    "building_age_min","building_age_max",
    "net_m2_min","net_m2_max","gross_m2_min","gross_m2_max"
  ].forEach(k=>filters[k]=fd.get(k)||"");

  return {
    side:sideValue(),
    districts:[...selectedDistricts],
    neighborhoods:selectedNeighborhoods,
    favoriteDistricts:[...favoriteDistricts],
    favoriteNeighborhoods,
    favoriteFilters:[...favoriteFilters],
    openDistricts:[...openDistricts],
    filters
  };
}

function saveState(){
  try{localStorage.setItem(STATE_KEY,JSON.stringify(collectState()));}catch(_e){}
}

function loadState(){
  const states=[];

  // Kalıcı anahtar + eski sürümler: bulunanların hepsini oku.
  for(const key of [STATE_KEY,...LEGACY_STATE_KEYS]){
    try{
      const raw=localStorage.getItem(key);
      if(!raw)continue;
      const parsed=JSON.parse(raw);
      if(parsed&&typeof parsed==="object"){
        states.push({key,data:parsed});
      }
    }catch(_e){}
  }

  if(!states.length){
    renderFilterFavorites({});
    renderAll();
    return;
  }

  // Seçimler/filtreler için en güncel bulunan state'i kullan.
  // Liste sırası STATE_KEY, sonra yeni -> eski legacy şeklindedir.
  const saved=states[0].data;

  favoriteFilters=new Set(
    (saved.favoriteFilters||[]).filter(
      n=>EXTRA_FILTER_DEFS.some(d=>d[0]===n)
    )
  );
  renderFilterFavorites(saved.filters||{});

  const sideEl=document.querySelector(
    `input[name="side"][value="${saved.side||"all"}"]`
  );
  if(sideEl)sideEl.checked=true;

  selectedDistricts=new Set(
    (saved.districts||[]).filter(
      d=>DISTRICTS.some(x=>x.name===d)
    )
  );

  selectedNeighborhoods=
    saved.neighborhoods&&typeof saved.neighborhoods==="object"
      ? saved.neighborhoods
      : {};

  openDistricts=new Set(
    (saved.openDistricts||[]).filter(
      d=>DISTRICTS.some(x=>x.name===d)
    )
  );

  Object.entries(saved.filters||{}).forEach(([name,value])=>{
    const el=document.querySelector(`[name="${name}"]`);
    if(el)el.value=value||"";
  });

  // FAVORİLER için ilk bulunan state'e güvenme:
  // Tüm eski sürümlerdeki favorileri birleştir.
  const mergedFavDistricts=new Set(defaultFavoriteDistricts);
  const mergedFavNeighborhoods={};

  for(const d of DISTRICTS){
    mergedFavNeighborhoods[d.name]=new Set();
  }

  for(const entry of states){
    const st=entry.data||{};

    if(Array.isArray(st.favoriteDistricts)){
      for(const d of st.favoriteDistricts){
        if(DISTRICTS.some(x=>x.name===d)){
          mergedFavDistricts.add(d);
        }
      }
    }

    const fns=
      st.favoriteNeighborhoods&&typeof st.favoriteNeighborhoods==="object"
        ? st.favoriteNeighborhoods
        : {};

    for(const d of DISTRICTS){
      const allowed=new Set(NEIGHBORHOODS[d.name]||[]);
      const vals=Array.isArray(fns[d.name])?fns[d.name]:[];

      for(const n of vals){
        if(allowed.has(n)){
          mergedFavNeighborhoods[d.name].add(n);
        }
      }
    }
  }

  favoriteDistricts=mergedFavDistricts;
  favoriteNeighborhoods={};

  for(const d of DISTRICTS){
    favoriteNeighborhoods[d.name]=[
      ...mergedFavNeighborhoods[d.name]
    ];
  }

  renderAll();

  // Birleştirilmiş son hali kalıcı anahtara yaz.
  // Bundan sonraki sürümlerde aynı favoriler korunur.
  try{
    localStorage.setItem(
      STATE_KEY,
      JSON.stringify(collectState())
    );
  }catch(_e){}
}

document.querySelectorAll('input[name="side"]').forEach(el=>{
  el.addEventListener("change",()=>{renderAll();saveState();});
});
document.getElementById("pasForm").addEventListener("change",saveState);
document.getElementById("pasForm").addEventListener("input",saveState);

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
        opportunity = {str(x["id"]): x for x in opportunity_analysis(listings)}

        usd_try_rate = get_usd_try_rate()

        rows = []
        for item in listings:
            row = item.to_dict()
            row.update(opportunity.get(str(item.id), {}))
            row["url"] = getattr(item, "_listing_url", "")
            row["net_usd_m2"] = try_to_usd(item.net_price_m2, usd_try_rate)
            rows.append(row)

        analysis["avg_net_usd_m2"] = try_to_usd(
            analysis.get("avg_net_m2_price"),
            usd_try_rate
        )

        return jsonify(
            ok=True,
            provider="PostgreSQL",
            version=VERSION,
            usd_try_rate=usd_try_rate,
            usd_try_source=_usd_try_cache.get("source"),
            analysis=analysis,
            listings=rows
        )

    except Exception as exc:
        return jsonify(ok=False, error=f"Kayıtlı veri hazırlanamadı: {exc}"), 500


@app.post("/api/sync")
def api_sync():
    payload = request.get_json(silent=True) or {}

    try:
        district, neighborhood = validate_pair(payload)

        filters = {
            "date_filter": payload.get("date_filter", "current"),
            "property_group": payload.get("property_group", "residential_all"),
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

        query_key = make_query_key(district, neighborhood, filters)

        if recently_synced_query(query_key, hours=SYNC_CACHE_HOURS):
            selected_filters = {
                **filters,
                "districts": [district],
                "neighborhoods": {district: [neighborhood]},
            }
            selected_count = len(load_listings_from_db(selected_filters))

            return jsonify(
                ok=True,
                district=district,
                neighborhood=neighborhood,
                raw_received=0,
                accepted=0,
                new=0,
                updated=0,
                selected_neighborhood_count=selected_count,
                cached=True,
                message=f"Aynı sorgu son {SYNC_CACHE_HOURS} saat içinde güncellendi; yeni Apify ücreti oluşturulmadı.",
            )

        result = APIFY.sync_neighborhood(
            district,
            neighborhood,
            filters=filters,
            max_results=LIVE_NEIGHBORHOOD_MAX_RESULTS,
        )

        accepted = result["accepted"]
        accepted_all = result.get("accepted_all") or []

        if not accepted:
            # Ücret zaten oluştuğu için doğrulanmış ilçe kayıtlarını boşa atma.
            saved_all = save_listings_to_db(accepted_all) if accepted_all else {
                "saved": 0, "new": 0, "updated": 0
            }
            save_query_sync(query_key, district, neighborhood, result["raw_count"])

            period_label = {
                "current": "Son 24 saat",
                "7d": "Son 7 gün",
                "30d": "Son 30 gün",
                "90d": "Son 90 gün",
            }.get(str(filters.get("date_filter") or "current"), "Seçili dönem")

            message = (
                f"{district}: {period_label} için en fazla "
                f"{LIVE_NEIGHBORHOOD_MAX_RESULTS} ilan tarandı; "
                f"{neighborhood} için uygun ilan ilk {LIVE_NEIGHBORHOOD_MAX_RESULTS} "
                "kayıt içinde bulunamadı. Aynı ilçe bu cache süresinde tekrar ücretli taranmayacak."
            )
            record_sync_state(district, neighborhood, 0, message)

            return jsonify(
                ok=False,
                error=message,
                raw_received=result["raw_count"],
                district_verified=len(accepted_all),
                rejected=result["rejected"],
                start_url=result["start_url"],
                hard_limit=LIVE_NEIGHBORHOOD_MAX_RESULTS,
                cached_district=True,
                **saved_all,
            ), 409

        retired_legacy = retire_legacy_scope_records(district, neighborhood)
        saved = save_listings_to_db(accepted_all)
        save_query_sync(query_key, district, neighborhood, result["raw_count"])

        selected_filters = {
            **filters,
            "districts": [district],
            "neighborhoods": {district: [neighborhood]},
        }
        selected_count = len(load_listings_from_db(selected_filters))

        record_sync_state(district, neighborhood, selected_count, "")

        return jsonify(
            ok=True,
            district=district,
            neighborhood=neighborhood,
            raw_received=result["raw_count"],
            accepted=len(accepted),
            district_verified=len(accepted_all),
            rejected=result["rejected"],
            selected_neighborhood_count=selected_count,
            start_url=result["start_url"],
            sync_limit=LIVE_NEIGHBORHOOD_MAX_RESULTS,
            hard_limit=LIVE_NEIGHBORHOOD_MAX_RESULTS,
            cached=False,
            retired_legacy=retired_legacy,
            **saved,
        )

    except ValueError as exc:
        return jsonify(ok=False, error=str(exc)), 400

    except Exception as exc:
        try:
            record_sync_state(
                str(payload.get("district") or ""),
                str(payload.get("neighborhood") or ""),
                0,
                str(exc)[:700],
            )
        except Exception:
            pass

        return jsonify(
            ok=False,
            error=f"Mahalle güncellemesi yapılamadı: {exc}. PostgreSQL kayıtları etkilenmedi.",
        ), 502


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
        normal_search_uses_apify=False,
        neighborhood_direct_url=True,
        repeat_query_guard_hours=SYNC_CACHE_HOURS,
        apify_enrichment=False,
        apify_max_total_charge_usd=APIFY_MAX_TOTAL_CHARGE_USD,
        strict_neighborhood_url_guard=True,
        strict_output_location_guard=True,
        price_source="formattedPrice -> verified listing sale price",
        net_m2_price_formula="price / net_m2",
        gross_m2_price_formula="price / gross_m2",
        listing_url_id_validation=True,
        usd_try_source="TCMB ForexSelling",
        usd_try_cache_minutes=USD_TRY_CACHE_MINUTES,
        property_filter_strategy="broad-category-fetch + PAS local classification",
        actor_scope="district",
        neighborhood_filter_supported_by_actor=False,
        hard_paid_result_limit=LIVE_NEIGHBORHOOD_MAX_RESULTS,
        district_shared_cache=True,
        max_total_charge_usd=APIFY_MAX_TOTAL_CHARGE_USD,
        strict_location_verification=True,
        strict_price_cross_validation=True,
        verification_version=24,
        legacy_location_rows_quarantined=True,
        legacy_price_rows_quarantined=True,
        search_requires_location_verified=True,
        search_requires_price_verified=True,
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)
