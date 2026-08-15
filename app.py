import os
import re
import json
import math
import random
import statistics
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from dataclasses import dataclass, asdict
from datetime import date, timedelta

from flask import Flask, request, render_template_string, jsonify

app = Flask(__name__)

# =========================================================
# PAS — Piyasa Arama Sistemi
# Mimari:
#   UI -> /api/search -> ListingProvider -> normalize -> analyze
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
        # Sahibinden'in doğrulanmış mahalle URL kalıbı:
        # /satilik-daire/istanbul-kadikoy-erenkoy
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
    """Sahibinden Search Scraper Pro ile mahalle hedefli canlı veri sağlayıcısı."""

    name = "apify"
    ACTOR_ID = "clearpath~sahibinden-scraper-pro"

    def __init__(self):
        self.api_token = os.environ.get("APIFY_API_TOKEN", "").strip()
        self.actor_id = self.ACTOR_ID
        self.timeout = parse_int(os.environ.get("APIFY_TIMEOUT", "300")) or 300
        # Önce ücretsiz katmanda 20 kaydı eksiksiz doğruluyoruz.
        self.max_results = 20

    def configured(self):
        return bool(self.api_token)

    def _run_actor(self, actor_input):
        url = (
            f"https://api.apify.com/v2/acts/{self.actor_id}"
            "/run-sync-get-dataset-items?clean=true"
        )
        body = json.dumps(actor_input, ensure_ascii=False).encode("utf-8")
        req = Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": f"Bearer {self.api_token}",
                "User-Agent": "PAS/1.0",
            },
            method="POST",
        )

        try:
            with urlopen(req, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if isinstance(payload, list):
                return payload
            if isinstance(payload, dict):
                return payload.get("items") or payload.get("data") or payload.get("results") or []
            return []
        except HTTPError as exc:
            try:
                detail = exc.read().decode("utf-8", errors="ignore")[:800]
            except Exception:
                detail = ""
            raise RuntimeError(f"Apify HTTP hatası: {exc.code}. {detail}") from exc
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
    def _key(value):
        text = str(value or "").casefold()
        replacements = {
            "ı": "i", "ğ": "g", "ü": "u", "ş": "s", "ö": "o", "ç": "c",
            "²": "2",
        }
        for src, dst in replacements.items():
            text = text.replace(src, dst)
        return re.sub(r"[^a-z0-9]+", "", text)

    def _attribute_value(self, item, wanted_labels):
        """Actor'ün resolved search/detail attribute alanlarından değer bulur."""
        wanted = {self._key(x) for x in wanted_labels}
        containers = [
            item.get("searchAttributes"),
            item.get("summaryAttributes"),
            item.get("attributes"),
        ]
        raw = item.get("rawSummary")
        if isinstance(raw, dict):
            containers.extend([
                raw.get("searchAttributes"),
                raw.get("summaryAttributes"),
            ])

        for container in containers:
            if isinstance(container, dict):
                for key, value in container.items():
                    if self._key(key) in wanted and value not in (None, ""):
                        return value
            elif isinstance(container, list):
                for row in container:
                    if not isinstance(row, dict):
                        continue
                    label = row.get("label") or row.get("name") or row.get("title") or row.get("key")
                    if self._key(label) in wanted:
                        value = row.get("value") or row.get("text") or row.get("displayValue")
                        if value not in (None, ""):
                            return value
        return None

    def _normalize_item(self, item, fallback_district="", fallback_neighborhood=""):
        raw = item.get("rawSummary") if isinstance(item.get("rawSummary"), dict) else {}

        listing_id = str(
            self._pick(item, "id", "listingId", "adId", "classifiedId")
            or self._pick(raw, "id", "listingId", "adId")
            or ""
        ).strip()

        listing_url = str(
            self._pick(item, "url", "listingUrl", "href")
            or self._pick(raw, "url", "listingUrl")
            or ""
        ).strip()

        if not listing_id and listing_url:
            match = re.search(r"(\d{8,})", listing_url)
            if match:
                listing_id = match.group(1)

        title = str(
            self._pick(item, "title", "listingTitle", "adTitle")
            or self._pick(raw, "title", "listingTitle")
            or "İlan"
        ).strip()

        raw_district = normalize_place_name(
            self._pick(item, "district", "districtName", "town")
            or self._pick(raw, "district", "districtName", "town")
            or ""
        )

        raw_neighborhood = normalize_place_name(
            self._pick(item, "neighborhood", "quarter", "neighborhoodName")
            or self._pick(raw, "neighborhood", "quarter", "neighborhoodName")
            or ""
        )

        district = raw_district or fallback_district
        neighborhood = raw_neighborhood or fallback_neighborhood

        price = parse_int(
            self._pick(item, "price", "salePrice", "amount", "priceValue")
            or self._pick(raw, "price", "salePrice", "amount", "priceValue")
        )

        gross_m2 = parse_int(
            self._pick(item, "grossSize", "grossM2", "grossSquareMeters", "areaGross")
            or self._pick(raw, "grossSize", "grossM2", "grossSquareMeters", "areaGross")
            or self._attribute_value(item, [
                "m² (Brüt)", "m2 (Brüt)", "Brüt m²", "Brüt m2", "Brüt",
                "Brüt Alan", "Brüt Metrekare", "Gross Size", "Gross m2", "Gross M²"
            ])
        )

        net_m2 = parse_int(
            self._pick(item, "netSize", "netM2", "netSquareMeters", "areaNet")
            or self._pick(raw, "netSize", "netM2", "netSquareMeters", "areaNet")
            or self._attribute_value(item, [
                "m² (Net)", "m2 (Net)", "Net m²", "Net m2", "Net",
                "Net Alan", "Net Metrekare", "Net Size", "Net M²"
            ])
        )

        rooms = str(
            self._pick(item, "rooms", "roomCount", "room")
            or self._pick(raw, "rooms", "roomCount", "room")
            or self._attribute_value(item, ["Oda Sayısı", "Oda", "Oda + Salon", "Rooms", "Room Count"])
            or ""
        ).strip()

        listed_at = str(
            self._pick(item, "listedAt", "listingDate", "createdAt", "date")
            or self._pick(raw, "listedAt", "listingDate", "createdAt", "date")
            or ""
        ).strip()
        listing_date = listed_at[:10] if listed_at else ""

        # searchSummary kayıtlarında m² / mahalle bazen boş gelebilir.
        # En az ilan numarası ve fiyat varsa kaydı PAS'a al.
        if not listing_id or not price:
            return None

        if not district:
            district = fallback_district
        if not neighborhood:
            neighborhood = fallback_neighborhood

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
            source=self.name,
        )
        listing._listing_url = listing_url
        listing._raw_district = raw_district
        listing._raw_neighborhood = raw_neighborhood
        listing._source_url = str(item.get("sourceUrl") or raw.get("sourceUrl") or "").strip()
        listing._input_index = parse_int(item.get("inputIndex"))
        return listing

    def search(self, filters):
        if not self.configured():
            raise RuntimeError("APIFY_API_TOKEN tanımlı değil.")

        districts = filters.get("districts") or []
        selected_neighborhoods = filters.get("neighborhoods") or {}

        targets = []
        for district in districts:
            neighborhoods = selected_neighborhoods.get(district) or []
            if neighborhoods:
                for neighborhood in neighborhoods:
                    targets.append({
                        "district": district,
                        "neighborhood": neighborhood,
                        "url": sahibinden_search_url(district, neighborhood),
                    })
            else:
                targets.append({
                    "district": district,
                    "neighborhood": "",
                    "url": sahibinden_search_url(district),
                })

        if not targets:
            return []

        actor_input = {
            "startUrls": [target["url"] for target in targets],
            "enrichment": True,
            "maxResults": 20,
        }

        raw_items = self._run_actor(actor_input)

        single_target = targets[0] if len(targets) == 1 else None
        fallback_district = single_target["district"] if single_target else ""
        fallback_neighborhood = single_target["neighborhood"] if single_target else ""

        requested_rooms = str(filters.get("rooms") or "").strip()
        min_m2 = parse_int(filters.get("min_m2"))
        max_m2 = parse_int(filters.get("max_m2"))
        min_price = parse_int(filters.get("min_price"))
        max_price = parse_int(filters.get("max_price"))
        net_m2_min = parse_int(filters.get("net_m2_min"))
        net_m2_max = parse_int(filters.get("net_m2_max"))
        gross_m2_min = parse_int(filters.get("gross_m2_min"))
        gross_m2_max = parse_int(filters.get("gross_m2_max"))

        requested_pairs = set()
        for target in targets:
            if target["neighborhood"]:
                requested_pairs.add((
                    self._key(target["district"]),
                    self._key(target["neighborhood"]),
                ))

        listings = []
        seen_ids = set()

        for item in raw_items:
            if not isinstance(item, dict):
                continue

            normalized = self._normalize_item(
                item,
                fallback_district=fallback_district,
                fallback_neighborhood=fallback_neighborhood,
            )
            if not normalized:
                continue

            # Kayıt hangi startUrl'den geldiyse hedefi onunla eşleştir.
            item_index = getattr(normalized, "_input_index", None)
            target = None
            if item_index is not None and 0 <= item_index < len(targets):
                target = targets[item_index]
            elif single_target:
                target = single_target

            if target and target["neighborhood"]:
                expected_district = self._key(target["district"])
                expected_neighborhood = self._key(target["neighborhood"])

                actual_district = self._key(
                    getattr(normalized, "_raw_district", "") or ""
                )
                actual_neighborhood = self._key(
                    getattr(normalized, "_raw_neighborhood", "") or ""
                )

                # Apify gerçek konumu döndürmüşse, yanlış bölge ilanını kesinlikle alma.
                if actual_district and actual_district != expected_district:
                    continue
                if actual_neighborhood and actual_neighborhood != expected_neighborhood:
                    continue

                # Konum alanı eksikse yalnızca ilgili startUrl'ün hedefini fallback olarak kullan.
                if not actual_district:
                    normalized.district = target["district"]
                if not actual_neighborhood:
                    normalized.neighborhood = target["neighborhood"]

            elif requested_pairs:
                current_pair = (
                    self._key(normalized.district),
                    self._key(normalized.neighborhood),
                )
                if current_pair not in requested_pairs:
                    continue

            if str(normalized.id) in seen_ids:
                continue
            seen_ids.add(str(normalized.id))

            if requested_rooms and normalized.rooms and normalized.rooms != requested_rooms:
                continue
            if min_m2 is not None:
                if normalized.gross_m2 is None or normalized.gross_m2 < min_m2:
                    continue
            if max_m2 is not None:
                if normalized.gross_m2 is None or normalized.gross_m2 > max_m2:
                    continue
            if min_price is not None and normalized.price < min_price:
                continue
            if max_price is not None and normalized.price > max_price:
                continue

            if net_m2_min is not None:
                if not normalized.net_price_m2 or normalized.net_price_m2 < net_m2_min:
                    continue
            if net_m2_max is not None:
                if not normalized.net_price_m2 or normalized.net_price_m2 > net_m2_max:
                    continue
            if gross_m2_min is not None:
                if not normalized.gross_price_m2 or normalized.gross_price_m2 < gross_m2_min:
                    continue
            if gross_m2_max is not None:
                if not normalized.gross_price_m2 or normalized.gross_price_m2 > gross_m2_max:
                    continue

            listings.append(normalized)

        return listings

def build_provider():
    mode = os.environ.get("PAS_PROVIDER", "demo").strip().lower()

    if mode == "apify":
        return ApifyListingProvider()

    if mode == "authorized_sahibinden":
        return AuthorizedSahibindenProvider()

    return DemoListingProvider()


PROVIDER = build_provider()


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
            "q1_gross_m2_price": None,
            "q3_gross_m2_price": None,
            "by_neighborhood": [],
        }

    prices = [x.price for x in listings if x.price]
    m2s = [x.gross_price_m2 for x in listings if x.gross_price_m2]
    net_m2s = [x.net_price_m2 for x in listings if x.net_price_m2]

    grouped = {}
    for x in listings:
        key = f"{x.district} · {x.neighborhood}"
        grouped.setdefault(key, []).append(x)

    by_neighborhood = []
    for key, rows in grouped.items():
        row_prices = [x.price for x in rows if x.price]
        row_m2s = [x.gross_price_m2 for x in rows if x.gross_price_m2]
        if not row_prices or not row_m2s:
            continue
        by_neighborhood.append({
            "name": key,
            "count": len(rows),
            "median_price": round(statistics.median(row_prices)),
            "median_gross_m2_price": round(statistics.median(row_m2s)),
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
    if isinstance(PROVIDER, ApifyListingProvider):
        return {
            "mode": "apify",
            "configured": PROVIDER.configured(),
            "label": "Apify · doğrulanmış mahalle URL + gerçek konum filtresi",
        }

    if isinstance(PROVIDER, AuthorizedSahibindenProvider):
        return {
            "mode": "authorized_sahibinden",
            "configured": PROVIDER.configured(),
            "label": "Sahibinden yetkili API",
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
<title>PAS</title>
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
.hidden{display:none!important}
.metrics{display:grid;grid-template-columns:repeat(2,1fr);gap:8px}
.metric{padding:12px;border:1px solid #e1e5ea;border-radius:12px}
.metric .k{font-size:12px;color:#6b7280}
.metric .v{font-size:20px;font-weight:800;margin-top:3px}
.table-wrap{overflow-x:auto}
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
<h1>PAS</h1>
<div class="subtitle">Piyasa Arama Sistemi</div>

<div class="card">
<div class="notice">
<strong>Veri sağlayıcı:</strong> {{ provider_status.label }}.
{% if provider_status.mode == "demo" %}
Şu an demo veri kullanılıyor.
{% elif provider_status.mode == "apify" and provider_status.configured %}
Apify üzerinden canlı ilan verisi modu aktif.
{% elif provider_status.mode == "apify" %}
Apify modu seçili ancak API tokenı eksik.
{% elif provider_status.configured %}
Yetkili Sahibinden API yapılandırması aktif.
{% else %}
Yetkili Sahibinden API modu seçili ancak erişim bilgileri eksik.
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

<details open>
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

<button class="primary" id="searchButton" type="submit">İlanları PAS'a Getir ve Analiz Et</button>
</div>
</form>

<div id="errorBox" class="card hidden"><div class="error" id="errorText"></div></div>

<div id="resultsCard" class="card hidden">
<div class="title">Piyasa özeti <span class="badge" id="providerBadge"></span></div>
<div class="metrics">
<div class="metric"><div class="k">İlan sayısı</div><div class="v" id="mCount">-</div></div>
<div class="metric"><div class="k">Medyan fiyat</div><div class="v" id="mMedianPrice">-</div></div>
<div class="metric"><div class="k">Ort. fiyat</div><div class="v" id="mAvgPrice">-</div></div>
<div class="metric"><div class="k">Medyan brüt TL/m²</div><div class="v" id="mMedianM2">-</div></div>
<div class="metric"><div class="k">Medyan net TL/m²</div><div class="v" id="mMedianNetM2">-</div></div>
</div>

<div class="title" style="margin-top:16px">Mahalle karşılaştırması</div>
<div class="table-wrap">
<table>
<thead><tr><th>Bölge</th><th>İlan</th><th>Medyan fiyat</th><th>Medyan TL/m²</th></tr></thead>
<tbody id="neighborhoodStats"></tbody>
</table>
</div>

<div class="title" style="margin-top:16px">İlanlar</div>
<div class="table-wrap">
<table>
<thead><tr><th>Mahalle</th><th>Oda</th><th>Brüt</th><th>Net</th><th>Fiyat</th><th>Brüt TL/m²</th><th>Net TL/m²</th><th>Mahalleye göre</th><th>PAS puanı</th><th>Tarih</th></tr></thead>
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
    delete selectedNeighborhoods[cb.value];
    document.getElementById("nb-"+slugDom(cb.value))?.remove();
   }
  };
 });
}
function renderNeighborhoodBlock(district){
 const id="nb-"+slugDom(district);
 if(document.getElementById(id))return;
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
   selectedNeighborhoods[district]=[...wrap.querySelectorAll(".neighborhoodCheck:checked")].map(x=>x.value);
  };
 });
}

document.querySelectorAll('input[name="side"]').forEach(el=>{
 el.addEventListener("change",renderDistricts);
});

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

 const formData=new FormData(e.target);
 const payload={
  districts:[...selectedDistricts],
  neighborhoods:selectedNeighborhoods,
  rooms:formData.get("rooms")||"",
  min_m2:formData.get("min_m2")||"",
  max_m2:formData.get("max_m2")||"",
  min_price:formData.get("min_price")||"",
  max_price:formData.get("max_price")||"",
  net_m2_min:formData.get("net_m2_min")||"",
  net_m2_max:formData.get("net_m2_max")||"",
  gross_m2_min:formData.get("gross_m2_min")||"",
  gross_m2_max:formData.get("gross_m2_max")||""
 };

 try{
  const response=await fetch("/api/search",{
   method:"POST",
   headers:{"Content-Type":"application/json"},
   body:JSON.stringify(payload)
  });
  const data=await response.json();
  if(!response.ok||!data.ok)throw new Error(data.error||"Arama başarısız.");

  document.getElementById("providerBadge").textContent=data.provider;
  document.getElementById("mCount").textContent=data.analysis.count;
  document.getElementById("mMedianPrice").textContent=fmtMoney(data.analysis.median_price);
  document.getElementById("mAvgPrice").textContent=fmtMoney(data.analysis.avg_price);
  document.getElementById("mMedianM2").textContent=fmtMoney(data.analysis.median_gross_m2_price);
  document.getElementById("mMedianNetM2").textContent=fmtMoney(data.analysis.median_net_m2_price);

  document.getElementById("neighborhoodStats").innerHTML=
   data.analysis.by_neighborhood.map(r=>`
    <tr>
     <td>${esc(r.name)}</td>
     <td>${r.count}</td>
     <td>${fmtMoney(r.median_price)}</td>
     <td>${fmtMoney(r.median_gross_m2_price)}</td>
    </tr>
   `).join("");

  document.getElementById("listingRows").innerHTML=
   data.listings.map(r=>`
    <tr>
     <td>${esc(r.district)} · ${esc(r.neighborhood)}</td>
     <td>${esc(r.rooms)}</td>
     <td>${r.gross_m2==null?"-":r.gross_m2+" m²"}</td>
     <td>${r.net_m2==null?"-":r.net_m2+" m²"}</td>
     <td>${fmtMoney(r.price)}</td>
     <td>${fmtMoney(r.gross_price_m2)}</td>
     <td>${fmtMoney(r.net_price_m2)}</td>
     <td>${r.net_vs_neighborhood_pct==null?"-":(r.net_vs_neighborhood_pct>0?"+":"")+r.net_vs_neighborhood_pct+"%"}</td>
     <td><strong>${r.opportunity_score ?? "-"}</strong><div class="small">${esc(r.opportunity_label||"")}</div></td>
     <td>${esc(r.listing_date)}</td>
    </tr>
   `).join("");

  resultsCard.classList.remove("hidden");
 }catch(err){
  document.getElementById("errorText").textContent=err.message||"Beklenmeyen hata.";
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
            return jsonify({"ok": False, "error": "Geçerli bir ilçe seçilmedi."}), 400

        raw_neighborhoods = payload.get("neighborhoods") or {}
        neighborhoods = {}

        for district in districts:
            allowed_nbs = set(NEIGHBORHOODS.get(district, []))
            requested = raw_neighborhoods.get(district) or []
            neighborhoods[district] = [n for n in requested if n in allowed_nbs]

        filters = {
            "districts": districts,
            "neighborhoods": neighborhoods,
            "rooms": payload.get("rooms", ""),
            "min_m2": payload.get("min_m2", ""),
            "max_m2": payload.get("max_m2", ""),
            "min_price": payload.get("min_price", ""),
            "max_price": payload.get("max_price", ""),
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
            key=lambda x: (x.get("opportunity_score") or 0),
            reverse=True,
        )

        return jsonify({
            "ok": True,
            "provider": PROVIDER.name,
            "analysis": analysis,
            "listings": listing_rows,
        })

    except Exception as exc:
        return jsonify({
            "ok": False,
            "error": f"Veri hazırlanırken hata oluştu: {exc}"
        }), 500


@app.get("/api/provider-status")
def api_provider_status():
    data = {
        "ok": True,
        **provider_status(),
    }

    if isinstance(PROVIDER, ApifyListingProvider):
        data.update({
            "actor_id": PROVIDER.actor_id,
            "requested_max_results": PROVIDER.max_results,
            "url_targeted": True,
            "include_details": True,
        })

    return jsonify(data)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
