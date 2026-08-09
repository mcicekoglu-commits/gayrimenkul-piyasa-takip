import os
from flask import Flask, request, render_template_string

app = Flask(__name__)

PAGE = """
<!doctype html>
<html lang="tr">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Gayrimenkul Piyasa Takip</title>
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
            margin-bottom: 6px;
        }

        .subtitle {
            color: #666;
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
            border: 0;
            border-radius: 10px;
            background: #222;
            color: white;
            font-size: 17px;
            font-weight: bold;
        }

        .note {
            margin-top: 18px;
            padding: 14px;
            background: #f0f2f5;
            border-radius: 10px;
            color: #555;
        }

        @media (max-width: 600px) {
            .row {
                grid-template-columns: 1fr;
            }
        }
    </style>
</head>

<body>
<div class="container">

    <h1>Gayrimenkul Piyasa Takip</h1>
    <div class="subtitle">Bölge ve ilan kriterlerinizi girin.</div>

    <div class="card">
        <form method="post">

            <label>İl</label>
            <input name="il" placeholder="Örn: İstanbul">

            <label>İlçe</label>
            <input name="ilce" placeholder="Örn: Beykoz">

            <label>Mahalle</label>
            <input name="mahalle" placeholder="Örn: Çavuşbaşı">

            <label>Sokak (opsiyonel)</label>
            <input name="sokak" placeholder="Örn: Çiçek Sokak">

            <div class="row">
                <div>
                    <label>Min m²</label>
                    <input name="min_m2" type="number">
                </div>

                <div>
                    <label>Max m²</label>
                    <input name="max_m2" type="number">
                </div>
            </div>

            <div class="row">
                <div>
                    <label>Min Fiyat</label>
                    <input name="min_fiyat" type="number">
                </div>

                <div>
                    <label>Max Fiyat</label>
                    <input name="max_fiyat" type="number">
                </div>
            </div>

            <label>Oda Sayısı</label>
            <select name="oda">
                <option value="">Farketmez</option>
                <option>1+1</option>
                <option>2+1</option>
                <option>3+1</option>
                <option>4+1</option>
                <option>5+1 ve üzeri</option>
            </select>

            <button type="submit">Ara</button>

        </form>

        {% if searched %}
        <div class="note">
            Arama ekranı çalışıyor. Bir sonraki aşamada gerçek ilan verilerini
            ve yakın ilan mesafelerini buraya bağlayacağız.
        </div>
        {% endif %}

    </div>
</div>
</body>
</html>
"""

@app.route("/", methods=["GET", "POST"])
def home():
    searched = request.method == "POST"
    return render_template_string(PAGE, searched=searched)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
