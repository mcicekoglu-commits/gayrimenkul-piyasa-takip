import os
import re
import json
import unicodedata
from urllib.parse import quote, urlencode

from flask import Flask, request, render_template_string

app = Flask(__name__)

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

FAVORITES = [d["name"] for d in DISTRICTS if d["favorite"]]


def slugify(text):
    text = (text or "").strip().lower()

    replacements = {
        "ı": "i",
        "ğ": "g",
        "ü": "u",
        "ş": "s",
        "ö": "o",
        "ç": "c",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    text = unicodedata.normalize("NFKD", text)
    text = "".join(
        c for c in text
        if not unicodedata.combining(c)
    )

    text = re.sub(r"[^a-z0-9]+", "-", text)

    return text.strip("-")


def sahibinden_url(
    district,
    neighborhood="",
    street="",
    min_price="",
    max_price="",
):
    base = (
        "https://www.sahibinden.com/"
        f"satilik-daire/istanbul-{slugify(district)}"
    )

    params = {}

    query_parts = [
        p.strip()
        for p in [neighborhood, street]
        if p and p.strip()
    ]

    if query_parts:
        params["query_text"] = " ".join(query_parts)

    if min_price:
        params["price_min"] = min_price

    if max_price:
        params["price_max"] = max_price

    if params:
        return (
            base
            + "?"
            + urlencode(
                params,
                quote_via=quote,
            )
        )

    return base


PAGE = r"""
<!doctype html>

<html lang="tr">

<head>

<meta charset="utf-8">

<meta
    name="viewport"
    content="width=device-width, initial-scale=1"
>

<title>PAS</title>

<link
    rel="stylesheet"
    href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
>

<style>

* {
    box-sizing: border-box;
}

body {
    margin: 0;
    padding: 16px;

    background: #f4f5f7;

    color: #191919;

    font-family:
        Arial,
        Helvetica,
        sans-serif;
}

.container {
    max-width: 850px;
    margin: 0 auto;
}

h1 {
    margin: 0;

    font-size: 46px;

    letter-spacing: -1px;
}

.subtitle {
    margin: 4px 0 18px;

    color: #6b7280;

    font-size: 17px;
}

.card {
    margin-bottom: 14px;

    padding: 16px;

    background: white;

    border-radius: 16px;

    box-shadow:
        0 4px 18px
        rgba(0, 0, 0, 0.07);
}

.section-title {
    margin: 0 0 10px;

    font-weight: 700;
}

.segmented {
    display: grid;

    grid-template-columns:
        repeat(2, 1fr);

    gap: 8px;

    margin-bottom: 14px;
}

.segmented.three {
    grid-template-columns:
        repeat(3, 1fr);
}

.seg input {
    display: none;
}

.seg span {
    display: block;

    padding: 11px 8px;

    border:
        1px solid
        #d9dde3;

    border-radius: 10px;

    text-align: center;

    background: white;

    cursor: pointer;

    font-weight: 600;
}

.seg input:checked + span {
    background: #1f2937;

    color: white;

    border-color: #1f2937;
}

.favorites {
    padding: 12px;

    margin-bottom: 12px;

    background: #faf7ef;

    border:
        1px solid
        #e6dfcd;

    border-radius: 12px;
}

.small {
    color: #6b7280;

    font-size: 13px;
}

.grid-checks {
    display: grid;

    grid-template-columns:
        repeat(2, minmax(0, 1fr));

    gap: 8px;
}

.check {
    display: flex;

    align-items: center;

    gap: 8px;

    padding: 10px;

    background: white;

    border:
        1px solid
        #d9dde3;

    border-radius: 10px;
}

.check input {
    width: 18px;
    height: 18px;
}

.district-block {
    margin-top: 10px;

    overflow: hidden;

    border:
        1px solid
        #d9dde3;

    border-radius: 12px;
}

.district-head {
    display: flex;

    justify-content: space-between;

    align-items: center;

    gap: 8px;

    padding: 11px 12px;

    background: #f0f2f5;

    font-weight: 700;
}

.neighborhoods {
    display: grid;

    grid-template-columns:
        repeat(2, minmax(0, 1fr));

    gap: 7px;

    padding: 10px;
}

.loading {
    color: #6b7280;

    font-size: 14px;
}

label.field {
    display: block;

    margin:
        12px 0 6px;

    font-weight: 700;
}

input[type="number"],
input[type="text"],
select {
    width: 100%;

    padding: 11px;

    background: white;

    border:
        1px solid
        #d9dde3;

    border-radius: 10px;

    font-size: 16px;
}

.pair {
    display: grid;

    grid-template-columns:
        1fr 1fr;

    gap: 10px;
}

.pair label.field {
    margin-top: 10px;
}

details {
    margin-top: 10px;

    padding:
        0 12px;

    background: white;

    border:
        1px solid
        #d9dde3;

    border-radius: 12px;
}

summary {
    padding:
        12px 0;

    cursor: pointer;

    font-weight: 700;
}

.details-body {
    padding-bottom: 12px;
}

button.primary {
    width: 100%;

    margin-top: 16px;

    padding: 14px;

    border: 0;

    border-radius: 11px;

    background: #181818;

    color: white;

    font-size: 17px;

    font-weight: 700;

    cursor: pointer;
}

#map {
    height: 320px;

    margin-top: 10px;

    border-radius: 12px;
}

.hidden {
    display: none !important;
}

.result {
    margin-top: 10px;

    padding: 12px;

    border:
        1px solid
        #d9dde3;

    border-radius: 12px;
}

.result a {
    display: block;

    margin-top: 8px;

    padding: 11px;

    background: #181818;

    color: white;

    border-radius: 9px;

    text-align: center;

    text-decoration: none;

    font-weight: 700;
}

.warn {
    padding: 11px;

    background: #fff8e8;

    border:
        1px solid
        #ead9a8;

    border-radius: 10px;

    font-size: 14px;

    line-height: 1.45;
}

@media (max-width: 600px) {

    body {
        padding: 12px;
    }

    h1 {
        font-size: 42px;
    }

    .grid-checks,
    .neighborhoods {
        grid-template-columns:
            1fr 1fr;
    }

    .card {
        padding: 14px;
    }
}

</style>

</head>


<body>

<div class="container">

<h1>PAS</h1>

<div class="subtitle">
    Piyasa Arama Sistemi
</div>


{% if results %}

<div class="card">

<div class="section-title">
    Sahibinden arama bağlantıları
</div>


{% for r in results %}

<div class="result">

<strong>
    {{ r.title }}
</strong>

<a
    href="{{ r.url }}"
    target="_blank"
    rel="noopener"
>
    Sahibinden'de aç
</a>

</div>

{% endfor %}


{% if local_filters %}

<div
    class="warn"
    style="margin-top:12px;"
>

<strong>
    PAS'ta seçili ek kriterler:
</strong>

<br>

{{ local_filters }}

<br><br>

Net/brüt TL/m² ve bazı gelişmiş
filtreler şu aşamada Sahibinden
URL'sine güvenilir biçimde
aktarılamadığı için PAS seçim
olarak saklar.

</div>

{% endif %}

</div>

{% endif %}



<form
    method="post"
    id="pasForm"
>


<div class="card">

<div class="section-title">
    Arama yöntemi
</div>


<div class="segmented">

<label class="seg">

<input
    type="radio"
    name="mode"
    value="list"
    checked
>

<span>
    Listeden Seç
</span>

</label>


<label class="seg">

<input
    type="radio"
    name="mode"
    value="map"
>

<span>
    Haritadan Seç
</span>

</label>

</div>



<div id="listMode">


<div class="section-title">
    İstanbul
</div>


<div class="segmented three">

<label class="seg">

<input
    type="radio"
    name="side"
    value="all"
    checked
>

<span>
    Tümü
</span>

</label>


<label class="seg">

<input
    type="radio"
    name="side"
    value="anadolu"
>

<span>
    Anadolu
</span>

</label>


<label class="seg">

<input
    type="radio"
    name="side"
    value="avrupa"
>

<span>
    Avrupa
</span>

</label>

</div>



<div class="favorites">

<strong>
    ★ Favoriler
</strong>

<div class="small">
const ISTANBUL_DISTRICTS_API =
"https://api.turkiyeapi.dev/v2/districts?provinceId=34&fields=id,name&sort=name&limit=100";
    id="favoriteDistricts"
    class="grid-checks"
    style="margin-top:9px;"
></div>

</div>



<details open>

<summary>
    11 İlçe
</summary>

<div class="details-body">

<div
    id="districts"
    class="grid-checks"
></div>

</div>

</details>



<div id="neighborhoodArea"></div>



<details>

<summary>
    Sokak / Cadde (opsiyonel)
</summary>

<div class="details-body">

<input
    type="text"
    name="street"
    id="street"
    placeholder="Örn: Bağdat Caddesi"
>

<div
    class="small"
    style="margin-top:7px;"
>

Mahalleler otomatik gelir.
Sokak/cadde şu aşamada isteğe
bağlı metin olarak kullanılmaktadır.

</div>

</div>

</details>


</div>



<div
    id="mapMode"
    class="hidden"
>

<div class="warn">

Haritada bir merkez seçin.
Koordinat ve yarıçap PAS'ta
saklanır.

</div>


<div id="map"></div>


<div class="pair">

<div>

<label class="field">
    Enlem
</label>

<input
    type="text"
    id="lat"
    name="lat"
    readonly
>

</div>


<div>

<label class="field">
    Boylam
</label>

<input
    type="text"
    id="lng"
    name="lng"
    readonly
>

</div>

</div>


<label class="field">
    Yarıçap
</label>

<select
    name="radius"
    id="radius"
>

<option value="1">
    1 km
</option>

<option
    value="3"
    selected
>
    3 km
</option>

<option value="5">
    5 km
</option>

<option value="10">
    10 km
</option>

</select>


</div>

</div>



<div class="card">

<div class="section-title">
    İlan filtreleri
</div>


<div class="pair">

<div>

<label class="field">
    Min m²
</label>

<input
    type="number"
    name="min_m2"
    id="min_m2"
    min="0"
>

</div>


<div>

<label class="field">
    Max m²
</label>

<input
    type="number"
    name="max_m2"
    id="max_m2"
    min="0"
>

</div>

</div>



<div class="pair">

<div>

<label class="field">
    Min Fiyat (TL)
</label>

<input
    type="number"
    name="min_price"
    id="min_price"
    min="0"
>

</div>


<div>

<label class="field">
    Max Fiyat (TL)
</label>

<input
    type="number"
    name="max_price"
    id="max_price"
    min="0"
>

</div>

</div>



<details>

<summary>
    Net m² satış fiyatı
    (opsiyonel)
</summary>

<div class="details-body pair">


<div>

<label class="field">
    Min TL/m²
</label>

<input
    type="number"
    name="net_m2_min"
    id="net_m2_min"
    min="0"
>

</div>


<div>

<label class="field">
    Max TL/m²
</label>

<input
    type="number"
    name="net_m2_max"
    id="net_m2_max"
    min="0"
>

</div>

</div>

</details>



<details>

<summary>
    Brüt m² satış fiyatı
    (opsiyonel)
</summary>

<div class="details-body pair">


<div>

<label class="field">
    Min TL/m²
</label>

<input
    type="number"
    name="gross_m2_min"
    id="gross_m2_min"
    min="0"
>

</div>


<div>

<label class="field">
    Max TL/m²
</label>

<input
    type="number"
    name="gross_m2_max"
    id="gross_m2_max"
    min="0"
>

</div>

</div>

</details>



<label class="field">
    Oda Sayısı
</label>

<select
    name="rooms"
    id="rooms"
>

<option value="">
    Farketmez
</option>

<option>
    1+1
</option>

<option>
    2+1
</option>

<option>
    3+1
</option>

<option>
    4+1
</option>

<option>
    5+1 ve üzeri
</option>

</select>



<button
    class="primary"
    type="submit"
>

Sahibinden Aramalarını Hazırla

</button>


</div>

</form>

</div>



<script
src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
></script>



<script>

const DISTRICTS =
    {{ districts_json|safe }};

const FAVORITES =
    {{ favorites_json|safe }};


const ISTANBUL_DISTRICTS_API =
    "https://api.turkiyeapi.dev/v2/provinces/34/districts?fields=id,name&limit=100";


const districtIdByName = {};

const stateKey =
    "PAS_STATE_V3";


let selectedDistricts =
    new Set();

let selectedNeighborhoods = {};

let map;

let marker;



function esc(s) {

    return String(s).replace(
        /[&<>"']/g,
        c => ({
            "&": "&amp;",
            "<": "&lt;",
            ">": "&gt;",
            '"': "&quot;",
            "'": "&#39;"
        }[c])
    );
}



function saveState() {

    const mode =
        document.querySelector(
            'input[name="mode"]:checked'
        )?.value || "list";

    const side =
        document.querySelector(
            'input[name="side"]:checked'
        )?.value || "all";


    const inputs = {};


    [
        "street",
        "min_m2",
        "max_m2",
        "min_price",
        "max_price",
        "net_m2_min",
        "net_m2_max",
        "gross_m2_min",
        "gross_m2_max",
        "rooms",
        "lat",
        "lng",
        "radius"
    ].forEach(id => {

        const el =
            document.getElementById(id);

        if (el) {
            inputs[id] =
                el.value;
        }

    });


    localStorage.setItem(
        stateKey,
        JSON.stringify({

            mode,

            side,

            selectedDistricts:
                [...selectedDistricts],

            selectedNeighborhoods,

            inputs
        })
    );
}



function loadState() {

    try {

        return JSON.parse(
            localStorage.getItem(
                stateKey
            ) || "{}"
        );

    }

    catch {

        return {};

    }
}



function districtVisible(
    district,
    side
) {

    return (
        side === "all"
        ||
        district.side === side
    );
}



function districtCheckbox(
    name,
    favorite = false
) {

    const checked =
        selectedDistricts.has(name)
        ? "checked"
        : "";

    const star =
        favorite
        ? " ★"
        : "";


    return `

    <label class="check">

        <input

            type="checkbox"

            class="districtCheck"

            value="${esc(name)}"

            ${checked}

        >

        <span>

            ${esc(name)}${star}

        </span>

    </label>

    `;
}



function renderDistricts() {

    const side =
        document.querySelector(
            'input[name="side"]:checked'
        )?.value || "all";


    document.getElementById(
        "districts"
    ).innerHTML =

        DISTRICTS

        .filter(
            d =>
            districtVisible(
                d,
                side
            )
        )

        .map(
            d =>
            districtCheckbox(
                d.name,
                d.favorite
            )
        )

        .join("");


    document.getElementById(
        "favoriteDistricts"
    ).innerHTML =

        DISTRICTS

        .filter(
            d =>
            d.favorite
            &&
            districtVisible(
                d,
                side
            )
        )

        .map(
            d =>
            districtCheckbox(
                d.name,
                true
            )
        )

        .join("");


    bindDistrictChecks();
}



function syncDistrictCopies(
    name,
    checked
) {

    document.querySelectorAll(
        ".districtCheck"
    ).forEach(cb => {

        if (
            cb.value === name
        ) {

            cb.checked =
                checked;

        }

    });
}



function bindDistrictChecks() {

    document.querySelectorAll(
        ".districtCheck"
    ).forEach(cb => {

        cb.onchange =
        async () => {

            syncDistrictCopies(
                cb.value,
                cb.checked
            );


            if (cb.checked) {

                selectedDistricts.add(
                    cb.value
                );

                await ensureNeighborhoodBlock(
                    cb.value
                );

            }

            else {

                selectedDistricts.delete(
                    cb.value
                );


                delete selectedNeighborhoods[
                    cb.value
                ];


                const block =
                    document.getElementById(
                        "nb-"
                        +
                        slugDom(
                            cb.value
                        )
                    );


                if (block) {
                    block.remove();
                }

            }


            saveState();

        };

    });
}



function slugDom(s) {

    return s

    .toLocaleLowerCase(
        "tr-TR"
    )

    .normalize("NFD")

    .replace(
        /[\u0300-\u036f]/g,
        ""
    )

    .replace(
        /[^a-z0-9]+/g,
        "-"
    );
}



async function loadDistrictIds() {

    const res =
        await fetch(
            ISTANBUL_DISTRICTS_API
        );


    if (!res.ok) {

        throw new Error(
            "İlçe listesi yüklenemedi"
        );

    }


    const json =
        await res.json();


    (json.data || [])
    .forEach(d => {

        districtIdByName[
            d.name
        ] = d.id;

    });
}



async function fetchNeighborhoods(
    districtName
) {

    const id =
        districtIdByName[
            districtName
        ];


    if (!id) {
        return [];
    }


    const url =
    `https://api.turkiyeapi.dev/v2/districts/${id}/neighborhoods` +
    `?fields=id,name&limit=1000`;


    const res =
        await fetch(url);


    if (!res.ok) {

        throw new Error(
            "Mahalleler yüklenemedi"
        );

    }


    const json =
        await res.json();


    return (
        json.data || []
    ).map(
        x => x.name
    );
}



async function ensureNeighborhoodBlock(
    districtName
) {

    const area =
        document.getElementById(
            "neighborhoodArea"
        );


    const blockId =
        "nb-"
        +
        slugDom(
            districtName
        );


    if (
        document.getElementById(
            blockId
        )
    ) {
        return;
    }


    const wrap =
        document.createElement(
            "div"
        );


    wrap.className =
        "district-block";

    wrap.id =
        blockId;


    wrap.innerHTML = `

        <div class="district-head">

            <span>
                ${esc(districtName)}
                mahalleleri
            </span>

            <span class="small">
                çoklu seçim
            </span>

        </div>


        <div class="neighborhoods">

            <div class="loading">
                Mahalleler yükleniyor…
            </div>

        </div>

    `;


    area.appendChild(
        wrap
    );


    try {

        const neighborhoods =
            await fetchNeighborhoods(
                districtName
            );


        const selected =
            new Set(

                selectedNeighborhoods[
                    districtName
                ]

                || []

            );


        wrap.querySelector(
            ".neighborhoods"
        ).innerHTML =

            neighborhoods

            .map(n => `

                <label class="check">

                    <input

                        type="checkbox"

                        class="neighborhoodCheck"

                        data-district="${esc(districtName)}"

                        value="${esc(n)}"

                        ${selected.has(n) ? "checked" : ""}

                    >

                    <span>
                        ${esc(n)}
                    </span>

                </label>

            `)

            .join("");


        wrap.querySelectorAll(
            ".neighborhoodCheck"
        ).forEach(cb => {


            cb.onchange =
            () => {


                const district =
                    cb.dataset.district;


                const values =

                    [
                        ...wrap.querySelectorAll(
                            ".neighborhoodCheck:checked"
                        )
                    ]

                    .map(
                        x => x.value
                    );


                selectedNeighborhoods[
                    district
                ] = values;


                saveState();

            };

        });

    }

    catch (e) {

        wrap.querySelector(
            ".neighborhoods"
        ).innerHTML = `

            <div class="warn">

                Mahalleler şu anda
                yüklenemedi.

                Sayfayı yenileyip
                tekrar deneyin.

            </div>

        `;

    }
}



function addHidden(
    name,
    value
) {

    const input =
        document.createElement(
            "input"
        );


    input.type =
        "hidden";

    input.name =
        name;

    input.value =
        value;

    input.className =
        "dynamic-hidden";


    document.getElementById(
        "pasForm"
    ).appendChild(
        input
    );
}



function setupMode() {

    const mode =
        document.querySelector(
            'input[name="mode"]:checked'
        ).value;


    document.getElementById(
        "listMode"
    ).classList.toggle(
        "hidden",
        mode !== "list"
    );


    document.getElementById(
        "mapMode"
    ).classList.toggle(
        "hidden",
        mode !== "map"
    );


    if (
        mode === "map"
        &&
        map
    ) {

        setTimeout(
            () =>
            map.invalidateSize(),
            100
        );

    }


    saveState();
}



function initMap() {

    map =
        L.map(
            "map"
        ).setView(
            [41.02, 29.05],
            11
        );


    L.tileLayer(

        "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",

        {

            maxZoom: 19,

            attribution:
                "&copy; OpenStreetMap"

        }

    ).addTo(map);


    map.on(
        "click",
        e => {


            if (marker) {
                marker.remove();
            }


            marker =
                L.marker(
                    e.latlng
                ).addTo(map);


            document.getElementById(
                "lat"
            ).value =
                e.latlng.lat
                .toFixed(6);


            document.getElementById(
                "lng"
            ).value =
                e.latlng.lng
                .toFixed(6);


            saveState();

        }
    );
}



async function restore() {

    const s =
        loadState();


    if (s.mode) {

        const el =
            document.querySelector(

                `input[name="mode"][value="${s.mode}"]`

            );


        if (el) {
            el.checked = true;
        }

    }


    if (s.side) {

        const el =
            document.querySelector(

                `input[name="side"][value="${s.side}"]`

            );


        if (el) {
            el.checked = true;
        }

    }


    selectedDistricts =
        new Set(
            s.selectedDistricts
            || []
        );


    selectedNeighborhoods =
        s.selectedNeighborhoods
        || {};


    if (s.inputs) {

        Object.entries(
            s.inputs
        ).forEach(
            ([id, value]) => {


                const el =
                    document.getElementById(
                        id
                    );


                if (
                    el
                    &&
                    value !== undefined
                    &&
                    value !== null
                ) {

                    el.value =
                        value;

                }

            }
        );

    }


    renderDistricts();


    for (
        const district
        of selectedDistricts
    ) {

        await ensureNeighborhoodBlock(
            district
        );

    }


    setupMode();


    const lat =
        parseFloat(
            document.getElementById(
                "lat"
            ).value
        );


    const lng =
        parseFloat(
            document.getElementById(
                "lng"
            ).value
        );


    if (
        !Number.isNaN(lat)
        &&
        !Number.isNaN(lng)
    ) {

        marker =
            L.marker(
                [lat, lng]
            ).addTo(map);


        map.setView(
            [lat, lng],
            14
        );

    }
}



document.querySelectorAll(
    'input[name="mode"]'
).forEach(
    el =>

    el.addEventListener(
        "change",
        setupMode
    )

);



document.querySelectorAll(
    'input[name="side"]'
).forEach(
    el =>

    el.addEventListener(
        "change",
        () => {

            renderDistricts();

            saveState();

        }
    )

);



[
    "street",
    "min_m2",
    "max_m2",
    "min_price",
    "max_price",
    "net_m2_min",
    "net_m2_max",
    "gross_m2_min",
    "gross_m2_max",
    "rooms",
    "radius"
].forEach(id => {

    const el =
        document.getElementById(
            id
        );


    if (el) {

        el.addEventListener(
            "change",
            saveState
        );

    }

});



document.getElementById(
    "pasForm"
).addEventListener(
    "submit",
    event => {


        document.querySelectorAll(
            ".dynamic-hidden"
        ).forEach(
            x => x.remove()
        );


        const mode =
            document.querySelector(
                'input[name="mode"]:checked'
            ).value;


        if (
            mode === "list"
        ) {


            if (
                selectedDistricts.size
                === 0
            ) {

                event.preventDefault();

                alert(
                    "En az bir ilçe seçin."
                );

                return;

            }


            [
                ...selectedDistricts
            ].forEach(
                district =>

                addHidden(
                    "districts",
                    district
                )

            );


            Object.entries(
                selectedNeighborhoods
            ).forEach(

                (
                    [
                        district,
                        items
                    ]
                ) => {


                    items.forEach(
                        neighborhood =>

                        addHidden(

                            "neighborhoods",

                            `${district}|||${neighborhood}`

                        )

                    );

                }

            );

        }


        saveState();

    }

);



initMap();



loadDistrictIds()

.then(
    restore
)

.catch(
    () => {


        renderDistricts();

        setupMode();


        document.getElementById(
            "neighborhoodArea"
        ).innerHTML = `

            <div class="warn">

                Adres servisine
                şu anda ulaşılamadı.

                İlçe seçimi çalışır.

                Mahalle listesi için
                daha sonra tekrar
                deneyin.

            </div>

        `;

    }
);

</script>

</body>

</html>
"""


@app.route(
    "/",
    methods=["GET", "POST"],
)
def home():

    results = []

    local_filters = ""


    if request.method == "POST":

        mode = request.form.get(
            "mode",
            "list",
        )


        min_price = request.form.get(
            "min_price",
            "",
        ).strip()


        max_price = request.form.get(
            "max_price",
            "",
        ).strip()


        min_m2 = request.form.get(
            "min_m2",
            "",
        ).strip()


        max_m2 = request.form.get(
            "max_m2",
            "",
        ).strip()


        net_m2_min = request.form.get(
            "net_m2_min",
            "",
        ).strip()


        net_m2_max = request.form.get(
            "net_m2_max",
            "",
        ).strip()


        gross_m2_min = request.form.get(
            "gross_m2_min",
            "",
        ).strip()


        gross_m2_max = request.form.get(
            "gross_m2_max",
            "",
        ).strip()


        rooms = request.form.get(
            "rooms",
            "",
        ).strip()


        street = request.form.get(
            "street",
            "",
        ).strip()


        local_parts = []


        if min_m2 or max_m2:

            local_parts.append(

                f"Alan: "
                f"{min_m2 or '-'}"
                f" – "
                f"{max_m2 or '-'} m²"

            )


        if net_m2_min or net_m2_max:

            local_parts.append(

                f"Net birim fiyat: "
                f"{net_m2_min or '-'}"
                f" – "
                f"{net_m2_max or '-'} TL/m²"

            )


        if gross_m2_min or gross_m2_max:

            local_parts.append(

                f"Brüt birim fiyat: "
                f"{gross_m2_min or '-'}"
                f" – "
                f"{gross_m2_max or '-'} TL/m²"

            )


        if rooms:

            local_parts.append(
                f"Oda: {rooms}"
            )


        local_filters = (
            " | ".join(
                local_parts
            )
        )


        if mode == "list":

            districts = (
                request.form.getlist(
                    "districts"
                )
            )


            raw_neighborhoods = (
                request.form.getlist(
                    "neighborhoods"
                )
            )


            by_district = {

                district: []

                for district
                in districts

            }


            for raw in raw_neighborhoods:

                if "|||" not in raw:

                    continue


                district, neighborhood = (
                    raw.split(
                        "|||",
                        1
                    )
                )


                if (
                    district
                    in by_district
                ):

                    by_district[
                        district
                    ].append(
                        neighborhood
                    )


            for district in districts:


                neighborhoods = (

                    by_district.get(
                        district
                    )

                    or [""]

                )


                for neighborhood in neighborhoods:


                    title = district


                    if neighborhood:

                        title += (
                            f" · "
                            f"{neighborhood}"
                        )


                    if street:

                        title += (
                            f" · "
                            f"{street}"
                        )


                    results.append({

                        "title":
                            title,

                        "url":
                            sahibinden_url(

                                district=
                                    district,

                                neighborhood=
                                    neighborhood,

                                street=
                                    street,

                                min_price=
                                    min_price,

                                max_price=
                                    max_price,

                            )

                    })


        else:

            lat = request.form.get(
                "lat",
                "",
            ).strip()


            lng = request.form.get(
                "lng",
                "",
            ).strip()


            radius = request.form.get(
                "radius",
                "3",
            ).strip()


            results.append({

                "title":

                    f"Harita seçimi: "
                    f"{lat or '-'}, "
                    f"{lng or '-'} · "
                    f"{radius} km",

                "url":

                    "https://www.sahibinden.com/"
                    "satilik-daire/istanbul"

            })


    return render_template_string(

        PAGE,

        results=
            results,

        local_filters=
            local_filters,

        districts_json=
            json.dumps(
                DISTRICTS,
                ensure_ascii=False,
            ),

        favorites_json=
            json.dumps(
                FAVORITES,
                ensure_ascii=False,
            ),

    )


if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            8080,
        )
    )

    app.run(
        host="0.0.0.0",
        port=port,
    )
