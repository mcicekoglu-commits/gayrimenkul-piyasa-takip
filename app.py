import os
import re
import json
import unicodedata
from urllib.parse import urlencode, quote

from flask import Flask, request, render_template_string, jsonify

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

def slugify(text):
    text = (text or "").strip().lower()
    table = str.maketrans({
        "ı": "i", "ğ": "g", "ü": "u",
        "ş": "s", "ö": "o", "ç": "c",
    })
    text = text.translate(table)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")

def sahibinden_url(district, neighborhood="", street="", min_price="", max_price=""):
    base = "https://www.sahibinden.com/satilik-daire/istanbul-" + slugify(district)
    params = {}

    search_parts = [x.strip() for x in (neighborhood, street) if x and x.strip()]
    if search_parts:
        params["query_text"] = " ".join(search_parts)
    if min_price:
        params["price_min"] = min_price
    if max_price:
        params["price_max"] = max_price

    return base if not params else base + "?" + urlencode(params, quote_via=quote)

PAGE = r"""
<!doctype html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PAS</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<style>
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;padding:14px;background:#f4f5f7;color:#1f2937;font-family:Arial,Helvetica,sans-serif}
.container{max-width:850px;margin:auto}
h1{font-size:44px;margin:0}
.subtitle{color:#6b7280;margin:4px 0 18px}
.card{background:#fff;border-radius:16px;padding:15px;margin-bottom:14px;box-shadow:0 4px 18px rgba(0,0,0,.07)}
.title{font-weight:700;margin-bottom:10px}
.small{font-size:13px;color:#6b7280}
.segmented{display:grid;grid-template-columns:repeat(3,1fr);gap:7px;margin-bottom:12px}
.segmented.two{grid-template-columns:repeat(2,1fr)}
.seg input{display:none}
.seg span{display:block;text-align:center;padding:10px 6px;border:1px solid #d9dde3;border-radius:10px;font-weight:600}
.seg input:checked+span{background:#1f2937;color:#fff;border-color:#1f2937}
.favorite-box{background:#fffaf0;border:1px solid #eadfbe;border-radius:12px;padding:11px;margin-bottom:10px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:7px}
.check{display:flex;gap:8px;align-items:center;padding:9px;border:1px solid #d9dde3;border-radius:10px;background:#fff}
.check input{width:18px;height:18px}
.district-block{border:1px solid #d9dde3;border-radius:12px;margin-top:10px;overflow:hidden}
.district-head{background:#f2f3f5;padding:10px 12px;font-weight:700;display:flex;justify-content:space-between;gap:8px}
.neighborhoods{padding:9px;display:grid;grid-template-columns:1fr 1fr;gap:7px}
label.field{display:block;font-weight:700;margin:10px 0 5px}
input[type=number],input[type=text],select{width:100%;padding:10px;border:1px solid #d9dde3;border-radius:10px;font-size:16px}
.pair{display:grid;grid-template-columns:1fr 1fr;gap:9px}
details{border:1px solid #d9dde3;border-radius:12px;padding:0 11px;margin-top:9px}
summary{padding:11px 0;font-weight:700}
.details-body{padding-bottom:11px}
.primary{width:100%;margin-top:14px;padding:14px;border:0;border-radius:10px;background:#181818;color:#fff;font-size:17px;font-weight:700}
.hidden{display:none!important}
#map{height:300px;border-radius:12px;margin-top:10px}
.warn{background:#fff8e8;border:1px solid #ead9a8;border-radius:10px;padding:10px;font-size:14px}
.result{padding:10px;border:1px solid #d9dde3;border-radius:10px;margin-top:8px}
.result-links{display:flex;flex-wrap:wrap;gap:7px;margin-top:8px}
.result-links a{display:inline-block;padding:10px;border-radius:8px;background:#181818;color:#fff;text-align:center;text-decoration:none;font-weight:700}
.compact-links{margin-top:6px;font-size:14px;line-height:1.7}
.compact-links a{color:#4b5563;text-decoration:none;font-weight:600}
.compact-links span{color:#9ca3af}

.count{font-size:12px;color:#6b7280;font-weight:400}
@media(max-width:600px){
  .grid,.neighborhoods,.pair{grid-template-columns:1fr 1fr}
  .result-links a{width:100%}
}
</style>
</head>
<body>
<div class="container">
<h1>PAS</h1>
<div class="subtitle">Piyasa Arama Sistemi</div>

<form method="post" action="/" id="pasForm">
<div class="card">
<div class="title">Arama yöntemi</div>
<div class="segmented two">
<label class="seg"><input type="radio" name="mode" value="list" checked><span>Listeden Seç</span></label>
<label class="seg"><input type="radio" name="mode" value="map"><span>Haritadan Seç</span></label>
</div>

<div id="listMode">
<div class="title">İstanbul</div>
<div class="segmented">
<label class="seg"><input type="radio" name="side" value="all" checked><span>Tümü</span></label>
<label class="seg"><input type="radio" name="side" value="anadolu"><span>Anadolu</span></label>
<label class="seg"><input type="radio" name="side" value="avrupa"><span>Avrupa</span></label>
</div>

<div class="favorite-box">
<strong>★ Favoriler</strong>
<div class="small">Kadıköy · Beykoz · Üsküdar</div>
<div id="favorites" class="grid" style="margin-top:8px"></div>
</div>

<details open>
<summary>11 İlçe</summary>
<div class="details-body"><div id="districts" class="grid"></div></div>
</details>

<div id="neighborhoodArea"></div>

<details>
<summary>Sokak / Cadde (opsiyonel)</summary>
<div class="details-body">
<input id="street" name="street" type="text" placeholder="Örn: Bağdat Caddesi">
</div>
</details>
</div>

<div id="mapMode" class="hidden">
<div class="warn">Haritada bir merkez seçebilirsiniz. Konum ve yarıçap PAS'ta saklanır.</div>
<div id="map"></div>
<div class="pair">
<div><label class="field">Enlem</label><input id="lat" name="lat" type="text" readonly></div>
<div><label class="field">Boylam</label><input id="lng" name="lng" type="text" readonly></div>
</div>
<label class="field">Yarıçap</label>
<select id="radius" name="radius">
<option value="1">1 km</option>
<option value="3" selected>3 km</option>
<option value="5">5 km</option>
<option value="10">10 km</option>
</select>
</div>
</div>

<div class="card">
<div class="title">İlan filtreleri</div>
<div class="pair">
<div><label class="field">Min m²</label><input id="min_m2" name="min_m2" type="number" min="0"></div>
<div><label class="field">Max m²</label><input id="max_m2" name="max_m2" type="number" min="0"></div>
</div>
<div class="pair">
<div><label class="field">Min Fiyat</label><input id="min_price" name="min_price" type="number" min="0"></div>
<div><label class="field">Max Fiyat</label><input id="max_price" name="max_price" type="number" min="0"></div>
</div>
<details>
<summary>Net m² satış fiyatı (opsiyonel)</summary>
<div class="details-body pair">
<div><label class="field">Min TL/m²</label><input id="net_m2_min" name="net_m2_min" type="number" min="0"></div>
<div><label class="field">Max TL/m²</label><input id="net_m2_max" name="net_m2_max" type="number" min="0"></div>
</div>
</details>
<details>
<summary>Brüt m² satış fiyatı (opsiyonel)</summary>
<div class="details-body pair">
<div><label class="field">Min TL/m²</label><input id="gross_m2_min" name="gross_m2_min" type="number" min="0"></div>
<div><label class="field">Max TL/m²</label><input id="gross_m2_max" name="gross_m2_max" type="number" min="0"></div>
</div>
</details>
<label class="field">Oda Sayısı</label>
<select id="rooms" name="rooms">
<option value="">Farketmez</option><option>1+1</option><option>2+1</option><option>3+1</option><option>4+1</option><option>5+1 ve üzeri</option>
</select>
<button class="primary" type="submit">Sahibinden Aramalarını Hazırla</button>
</div>
</form>

<div class="card{% if not results %} hidden{% endif %}" id="results">
<div class="title">Sahibinden arama bağlantıları</div>
<div id="resultsBody">
{% for r in results %}
<div class="result">
    <strong>{{ r.district }}</strong>
    <div class="compact-links">
    {% for link in r.links %}
        <a href="{{ link.url }}" target="_blank" rel="noopener">{{ link.name }}</a>{% if not loop.last %}<span> · </span>{% endif %}
    {% endfor %}
    </div>
</div>
{% endfor %}
{% if local_filters %}
<div class="warn" style="margin-top:10px"><strong>PAS ek filtreleri:</strong><br>{{ local_filters }}</div>
{% endif %}
</div>
</div>

</div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const DISTRICTS={{ districts_json|safe }};
const NEIGHBORHOODS={{ neighborhoods_json|safe }};
const STATE_KEY="PAS_STATE_STATIC_V1";
let selectedDistricts=new Set();
let selectedNeighborhoods={};
let map=null,marker=null;

function esc(s){return String(s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]))}
function slugDom(s){return s.toLocaleLowerCase("tr-TR").normalize("NFD").replace(/[\u0300-\u036f]/g,"").replace(/[^a-z0-9]+/g,"-")}
function sideValue(){return document.querySelector('input[name="side"]:checked')?.value||"all"}
function districtHtml(d){const checked=selectedDistricts.has(d.name)?"checked":"";return `<label class="check"><input class="districtCheck" type="checkbox" value="${esc(d.name)}" ${checked}><span>${esc(d.name)}${d.favorite?" ★":""}</span></label>`}

function renderDistricts(){
 const side=sideValue();
 const visible=DISTRICTS.filter(d=>side==="all"||d.side===side);
 document.getElementById("districts").innerHTML=visible.map(districtHtml).join("");
 document.getElementById("favorites").innerHTML=visible.filter(d=>d.favorite).map(districtHtml).join("");
 bindDistricts();
}
function syncCopies(name,checked){document.querySelectorAll(".districtCheck").forEach(cb=>{if(cb.value===name)cb.checked=checked})}
function bindDistricts(){
 document.querySelectorAll(".districtCheck").forEach(cb=>{
  cb.onchange=()=>{
   syncCopies(cb.value,cb.checked);
   if(cb.checked){
     selectedDistricts.add(cb.value);
     ensureNeighborhoodBlock(cb.value);
   }else{
     selectedDistricts.delete(cb.value);
     delete selectedNeighborhoods[cb.value];
     document.getElementById("nb-"+slugDom(cb.value))?.remove();
   }
   saveState();
  };
 });
}

function ensureNeighborhoodBlock(district){
 const id="nb-"+slugDom(district);
 if(document.getElementById(id))return;

 const list=NEIGHBORHOODS[district]||[];
 const selected=new Set(selectedNeighborhoods[district]||[]);

 const wrap=document.createElement("div");
 wrap.className="district-block";
 wrap.id=id;
 wrap.innerHTML=`
   <div class="district-head">
      <span>${esc(district)} mahalleleri</span>
      <span class="count">${list.length} seçenek</span>
   </div>
   <div class="neighborhoods">
      ${list.map(n=>`<label class="check"><input class="neighborhoodCheck" type="checkbox" data-district="${esc(district)}" value="${esc(n)}" ${selected.has(n)?"checked":""}><span>${esc(n)}</span></label>`).join("")}
   </div>
 `;
 document.getElementById("neighborhoodArea").appendChild(wrap);

 wrap.querySelectorAll(".neighborhoodCheck").forEach(cb=>{
   cb.onchange=()=>{
     selectedNeighborhoods[district]=[...wrap.querySelectorAll(".neighborhoodCheck:checked")].map(x=>x.value);
     saveState();
   };
 });
}

function saveState(){
 const inputs={};
 ["street","min_m2","max_m2","min_price","max_price","net_m2_min","net_m2_max","gross_m2_min","gross_m2_max","rooms","lat","lng","radius"].forEach(id=>{const el=document.getElementById(id);if(el)inputs[id]=el.value});
 localStorage.setItem(STATE_KEY,JSON.stringify({mode:document.querySelector('input[name="mode"]:checked')?.value||"list",side:sideValue(),selectedDistricts:[...selectedDistricts],selectedNeighborhoods,inputs}));
}
function loadState(){try{return JSON.parse(localStorage.getItem(STATE_KEY)||"{}")}catch{return{}}}
function setupMode(){
 const mode=document.querySelector('input[name="mode"]:checked')?.value||"list";
 document.getElementById("listMode").classList.toggle("hidden",mode!=="list");
 document.getElementById("mapMode").classList.toggle("hidden",mode!=="map");
 if(mode==="map"&&map)setTimeout(()=>map.invalidateSize(),100);
 saveState();
}
function restoreState(){
 const s=loadState();
 if(s.mode){const el=document.querySelector(`input[name="mode"][value="${s.mode}"]`);if(el)el.checked=true}
 if(s.side){const el=document.querySelector(`input[name="side"][value="${s.side}"]`);if(el)el.checked=true}
 selectedDistricts=new Set(s.selectedDistricts||[]);
 selectedNeighborhoods=s.selectedNeighborhoods||{};
 if(s.inputs)Object.entries(s.inputs).forEach(([id,value])=>{const el=document.getElementById(id);if(el&&value!=null)el.value=value});
 renderDistricts();
 [...selectedDistricts].forEach(ensureNeighborhoodBlock);
 setupMode();

 const lat=parseFloat(document.getElementById("lat").value),lng=parseFloat(document.getElementById("lng").value);
 if(!Number.isNaN(lat)&&!Number.isNaN(lng)&&map){
   marker=L.marker([lat,lng]).addTo(map);
   map.setView([lat,lng],14);
 }
}
function initMap(){
 if(typeof L==="undefined")return;
 map=L.map("map").setView([41.02,29.05],11);
 L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",{maxZoom:19,attribution:"&copy; OpenStreetMap"}).addTo(map);
 map.on("click",e=>{
  if(marker)marker.remove();
  marker=L.marker(e.latlng).addTo(map);
  document.getElementById("lat").value=e.latlng.lat.toFixed(6);
  document.getElementById("lng").value=e.latlng.lng.toFixed(6);
  saveState();
 });
}
function addHidden(name,value){
 const input=document.createElement("input");
 input.type="hidden";
 input.name=name;
 input.value=value;
 input.className="dynamic-hidden";
 document.getElementById("pasForm").appendChild(input);
}

document.querySelectorAll('input[name="mode"]').forEach(el=>el.addEventListener("change",setupMode));
document.querySelectorAll('input[name="side"]').forEach(el=>el.addEventListener("change",()=>{renderDistricts();saveState()}));
["street","min_m2","max_m2","min_price","max_price","net_m2_min","net_m2_max","gross_m2_min","gross_m2_max","rooms","radius"].forEach(id=>document.getElementById(id)?.addEventListener("change",saveState));

document.getElementById("pasForm").addEventListener("submit",async event=>{
 event.preventDefault();

 document.querySelectorAll(".dynamic-hidden").forEach(x=>x.remove());
 const mode=document.querySelector('input[name="mode"]:checked')?.value||"list";

 if(mode==="list"){
  if(selectedDistricts.size===0){
    alert("En az bir ilçe seçin.");
    return;
  }

  [...selectedDistricts].forEach(d=>addHidden("districts",d));

  Object.entries(selectedNeighborhoods).forEach(([district,neighborhoods])=>{
    neighborhoods.forEach(n=>addHidden("neighborhoods",`${district}|||${n}`));
  });
 }

 saveState();

 const button=document.querySelector(".primary");
 const oldText=button.textContent;
 button.disabled=true;
 button.textContent="Hazırlanıyor…";

 try{
   const formData=new FormData(document.getElementById("pasForm"));
   const response=await fetch("/",{
     method:"POST",
     body:formData,
     headers:{"X-Requested-With":"fetch"}
   });

   const payload=await response.json();
   if(!response.ok||!payload.ok){
     throw new Error(payload.error||"Arama hazırlanamadı.");
   }

   const resultsBox=document.getElementById("results");
   const resultsBody=document.getElementById("resultsBody");

   resultsBody.innerHTML=payload.results.map(r=>`
     <div class="result">
       <strong>${esc(r.district)}</strong>
       <div class="compact-links">
         ${r.links.map((link,i)=>`
           <a href="${esc(link.url)}" target="_blank" rel="noopener">${esc(link.name)}</a>${i<r.links.length-1?'<span> · </span>':''}
         `).join("")}
       </div>
     </div>
   `).join("") + (payload.local_filters ? `
     <div class="warn" style="margin-top:10px">
       <strong>PAS ek filtreleri:</strong><br>${esc(payload.local_filters)}
     </div>
   ` : "");

   resultsBox.classList.remove("hidden");
 }catch(err){
   alert(err.message||"Arama hazırlanırken bir hata oluştu.");
 }finally{
   button.disabled=false;
   button.textContent=oldText;
 }
});

initMap();
restoreState();
</script>
</body>
</html>
"""

@app.route("/", methods=["GET", "POST"])
def home():
    results = []
    local_filters = ""

    if request.method == "POST":
        mode = request.form.get("mode", "list")
        street = request.form.get("street", "").strip()
        min_m2 = request.form.get("min_m2", "").strip()
        max_m2 = request.form.get("max_m2", "").strip()
        min_price = request.form.get("min_price", "").strip()
        max_price = request.form.get("max_price", "").strip()
        net_m2_min = request.form.get("net_m2_min", "").strip()
        net_m2_max = request.form.get("net_m2_max", "").strip()
        gross_m2_min = request.form.get("gross_m2_min", "").strip()
        gross_m2_max = request.form.get("gross_m2_max", "").strip()
        rooms = request.form.get("rooms", "").strip()

        local_parts = []
        if min_m2 or max_m2:
            local_parts.append(f"Alan: {min_m2 or '-'} – {max_m2 or '-'} m²")
        if net_m2_min or net_m2_max:
            local_parts.append(f"Net: {net_m2_min or '-'} – {net_m2_max or '-'} TL/m²")
        if gross_m2_min or gross_m2_max:
            local_parts.append(f"Brüt: {gross_m2_min or '-'} – {gross_m2_max or '-'} TL/m²")
        if rooms:
            local_parts.append(f"Oda: {rooms}")
        local_filters = " | ".join(local_parts)

        if mode == "list":
            districts = request.form.getlist("districts")
            raw = request.form.getlist("neighborhoods")
            by_district = {d: [] for d in districts}

            for item in raw:
                if "|||" not in item:
                    continue
                district, neighborhood = item.split("|||", 1)
                if district in by_district:
                    by_district[district].append(neighborhood)

            for district in districts:
                neighborhoods = by_district.get(district, [])
                links = []

                if neighborhoods:
                    for neighborhood in neighborhoods:
                        links.append({
                            "name": neighborhood,
                            "url": sahibinden_url(
                                district,
                                neighborhood,
                                street,
                                min_price,
                                max_price,
                            ),
                        })
                else:
                    links.append({
                        "name": "İlçe genelinde aç",
                        "url": sahibinden_url(
                            district,
                            "",
                            street,
                            min_price,
                            max_price,
                        ),
                    })

                results.append({
                    "district": district,
                    "neighborhoods": neighborhoods,
                    "links": links,
                })

        else:
            lat = request.form.get("lat", "").strip()
            lng = request.form.get("lng", "").strip()
            radius = request.form.get("radius", "3").strip()

            results.append({
                "district": "Harita seçimi",
                "neighborhoods": [f"{lat or '-'}, {lng or '-'} · {radius} km"],
                "links": [{
                    "name": "Sahibinden'de aç",
                    "url": "https://www.sahibinden.com/satilik-daire/istanbul",
                }],
            })

    if request.headers.get("X-Requested-With") == "fetch":
        return jsonify({
            "ok": True,
            "results": results,
            "local_filters": local_filters,
        })

    return render_template_string(
        PAGE,
        results=results,
        local_filters=local_filters,
        districts_json=json.dumps(DISTRICTS, ensure_ascii=False),
        neighborhoods_json=json.dumps(NEIGHBORHOODS, ensure_ascii=False),
    )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
