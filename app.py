import os
from flask import Flask, request, render_template_string

app = Flask(__name__)

PAGE = """
<!doctype html>
<html lang="tr">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>PAS</title>

    <style>
        body {
            font-family: Arial, sans-serif;
            background: #f5f6f8;
            margin: 0;
            padding: 20px;
            color: #222;
        }

        .container {
            max-width: 760px;
            margin: 0 auto;
        }

        h1 {
            font-size: 48px;
            margin-bottom: 6px;
        }

        .subtitle {
            color: #666;
            font-size: 20px;
            margin-bottom: 24px;
        }

        .card {
            background: white;
            border-radius: 16px;
            padding: 20px;
            box-shadow: 0 4px 18px rgba(0,0,0,0.08);
        }

        label {
            display: block;
            font-weight: bold;
            margin-top: 14px;
            margin-bottom: 6px;
        }

        input, select {
            width: 100%;
            box-sizing: border-box;
            padding: 12px;
            border: 1px solid #ccc;
            border-radius: 10px;
            font-size: 16px;
            background: white;
        }

        .row {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 12px;
        }

        button {
            width: 100%;
            margin-top: 22px;
            padding: 14px;
            background: #222;
            color: white;
            border: none;
            border-radius: 10px;
            font-size: 18px;
            font-weight: bold;
        }

        .note {
            margin-top: 20px;
            background: #eef1f5;
            border-radius: 12px;
            padding: 16px;
            line-height: 1.6;
        }

        @media (max-width: 600px) {
            .row {
                grid-template-columns: 1fr;
            }

            h1 {
                font-size: 42px;
            }
        }
    </style>
</head>

<body>

<div class="container">

    <h1>PAS</h1>
    <div class="subtitle">Bölge ve ilan kriterlerinizi seçin.</div>

    <div class="card">

        <form method="post">

            <label>İl</label>
            <select id="il" name="il" data-selected="{{ kriterler.il }}">
                <option value="">İl seçin</option>
            </select>

            <label>İlçe</label>
            <select id="ilce" name="ilce" data-selected="{{ kriterler.ilce }}">
                <option value="">Önce il seçin</option>
            </select>

            <label>Mahalle / Bölge</label>
            <select id="mahalle" name="mahalle" data-selected="{{ kriterler.mahalle }}">
                <option value="">Önce ilçe seçin</option>
            </select>

            <label>Sokak / Cadde (opsiyonel)</label>
            <select id="sokak" name="sokak" data-selected="{{ kriterler.sokak }}">
                <option value="">Önce mahalle seçin</option>
            </select>

            <div class="row">
                <div>
                    <label>Min m²</label>
                    <input
                        name="min_m2"
                        type="number"
                        value="{{ kriterler.min_m2 }}"
                    >
                </div>

                <div>
                    <label>Max m²</label>
                    <input
                        name="max_m2"
                        type="number"
                        value="{{ kriterler.max_m2 }}"
                    >
                </div>
            </div>

            <div class="row">
                <div>
                    <label>Min Fiyat</label>
                    <input
                        name="min_fiyat"
                        type="number"
                        value="{{ kriterler.min_fiyat }}"
                    >
                </div>

                <div>
                    <label>Max Fiyat</label>
                    <input
                        name="max_fiyat"
                        type="number"
                        value="{{ kriterler.max_fiyat }}"
                    >
                </div>
            </div>

            <label>Oda Sayısı</label>
            <select name="oda">
                <option value="" {% if not kriterler.oda %}selected{% endif %}>
                    Farketmez
                </option>

                <option value="1+1" {% if kriterler.oda == "1+1" %}selected{% endif %}>
                    1+1
                </option>

                <option value="2+1" {% if kriterler.oda == "2+1" %}selected{% endif %}>
                    2+1
                </option>

                <option value="3+1" {% if kriterler.oda == "3+1" %}selected{% endif %}>
                    3+1
                </option>

                <option value="4+1" {% if kriterler.oda == "4+1" %}selected{% endif %}>
                    4+1
                </option>

                <option value="5+1" {% if kriterler.oda == "5+1" %}selected{% endif %}>
                    5+1
                </option>
            </select>

            <button type="submit">Ara</button>

        </form>

        {% if searched %}
        <div class="note">
            <strong>Arama kriterleri:</strong><br><br>

            İl: {{ kriterler.il or "-" }}<br>
            İlçe: {{ kriterler.ilce or "-" }}<br>
            Mahalle: {{ kriterler.mahalle or "-" }}<br>
            Sokak: {{ kriterler.sokak or "Belirtilmedi" }}<br>

            m²:
            {{ kriterler.min_m2 or "-" }}
            -
            {{ kriterler.max_m2 or "-" }}
            <br>

            Fiyat:
            {{ kriterler.min_fiyat or "-" }}
            -
            {{ kriterler.max_fiyat or "-" }}
            <br>

            Oda: {{ kriterler.oda or "Farketmez" }}
        </div>
        {% endif %}

    </div>
</div>

<script>

const konumlar = {

    "İstanbul": {

        "Kadıköy": {

            "Merdivenköy": [
                "Şair Arşi Caddesi",
                "Ressam Salih Ermez Caddesi",
                "Merdivenköy Yolu"
            ],

            "Kozyatağı": [
                "Bayar Caddesi",
                "Kaya Sultan Sokak",
                "Değirmen Sokak"
            ],

            "Göztepe": [
                "Tütüncü Mehmet Efendi Caddesi",
                "Bağdat Caddesi",
                "Fahrettin Kerim Gökay Caddesi"
            ],

            "Fenerbahçe": [
                "Bağdat Caddesi",
                "Dr. Faruk Ayanoğlu Caddesi",
                "Fener Kalamış Caddesi"
            ]
        },

        "Beykoz": {

            "Çavuşbaşı": [
                "Çavuşbaşı Caddesi",
                "Fatih Caddesi",
                "Cumhuriyet Caddesi"
            ],

            "Acarkent": [
                "Acarlar Mahallesi",
                "Acarkent Caddesi",
                "Çamlıca Yolu"
            ],

            "Kanlıca": [
                "Mihrabat Caddesi",
                "Barış Manço Caddesi",
                "İskenderpaşa Caddesi"
            ],

            "Paşabahçe": [
                "Paşabahçe Caddesi",
                "Çubuklu Caddesi",
                "Şişecam Yolu"
            ]
        }
    }
};


const ilSelect = document.getElementById("il");
const ilceSelect = document.getElementById("ilce");
const mahalleSelect = document.getElementById("mahalle");
const sokakSelect = document.getElementById("sokak");


function optionEkle(select, value, text) {

    const option = document.createElement("option");

    option.value = value;
    option.textContent = text;

    select.appendChild(option);
}


function illeriDoldur() {

    Object.keys(konumlar).forEach(il => {
        optionEkle(ilSelect, il, il);
    });

    const seciliIl = ilSelect.dataset.selected;

    if (seciliIl) {
        ilSelect.value = seciliIl;
        ilceleriDoldur(true);
    }
}


function ilceleriDoldur(ilkYukleme = false) {

    ilceSelect.innerHTML =
        '<option value="">İlçe seçin</option>';

    mahalleSelect.innerHTML =
        '<option value="">Önce ilçe seçin</option>';

    sokakSelect.innerHTML =
        '<option value="">Önce mahalle seçin</option>';

    const il = ilSelect.value;

    if (!il || !konumlar[il]) {
        return;
    }

    Object.keys(konumlar[il]).forEach(ilce => {
        optionEkle(ilceSelect, ilce, ilce);
    });

    if (ilkYukleme) {

        const seciliIlce = ilceSelect.dataset.selected;

        if (seciliIlce) {
            ilceSelect.value = seciliIlce;
            mahalleleriDoldur(true);
        }
    }
}


function mahalleleriDoldur(ilkYukleme = false) {

    mahalleSelect.innerHTML =
        '<option value="">Mahalle seçin</option>';

    sokakSelect.innerHTML =
        '<option value="">Önce mahalle seçin</option>';

    const il = ilSelect.value;
    const ilce = ilceSelect.value;

    if (
        !il ||
        !ilce ||
        !konumlar[il] ||
        !konumlar[il][ilce]
    ) {
        return;
    }

    Object.keys(konumlar[il][ilce]).forEach(mahalle => {
        optionEkle(mahalleSelect, mahalle, mahalle);
    });

    if (ilkYukleme) {

        const seciliMahalle =
            mahalleSelect.dataset.selected;

        if (seciliMahalle) {
            mahalleSelect.value = seciliMahalle;
            sokaklariDoldur(true);
        }
    }
}


function sokaklariDoldur(ilkYukleme = false) {

    sokakSelect.innerHTML =
        '<option value="">Sokak seçmek istemiyorum</option>';

    const il = ilSelect.value;
    const ilce = ilceSelect.value;
    const mahalle = mahalleSelect.value;

    if (
        !il ||
        !ilce ||
        !mahalle ||
        !konumlar[il] ||
        !konumlar[il][ilce] ||
        !konumlar[il][ilce][mahalle]
    ) {
        return;
    }

    konumlar[il][ilce][mahalle].forEach(sokak => {
        optionEkle(sokakSelect, sokak, sokak);
    });

    if (ilkYukleme) {

        const seciliSokak =
            sokakSelect.dataset.selected;

        if (seciliSokak) {
            sokakSelect.value = seciliSokak;
        }
    }
}


ilSelect.addEventListener(
    "change",
    () => ilceleriDoldur(false)
);

ilceSelect.addEventListener(
    "change",
    () => mahalleleriDoldur(false)
);

mahalleSelect.addEventListener(
    "change",
    () => sokaklariDoldur(false)
);


illeriDoldur();

</script>

</body>
</html>
"""


@app.route("/", methods=["GET", "POST"])
def home():

    searched = request.method == "POST"

    kriterler = {
        "il": request.form.get("il", ""),
        "ilce": request.form.get("ilce", ""),
        "mahalle": request.form.get("mahalle", ""),
        "sokak": request.form.get("sokak", ""),
        "min_m2": request.form.get("min_m2", ""),
        "max_m2": request.form.get("max_m2", ""),
        "min_fiyat": request.form.get("min_fiyat", ""),
        "max_fiyat": request.form.get("max_fiyat", ""),
        "oda": request.form.get("oda", "")
    }

    return render_template_string(
        PAGE,
        searched=searched,
        kriterler=kriterler
    )


if __name__ == "__main__":

    port = int(
        os.environ.get("PORT", 8080)
    )

    app.run(
        host="0.0.0.0",
        port=port
    )
