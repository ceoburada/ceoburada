"""
kanal_canli_guncelle.py — GitHub Actions'ta zamanlanmis calisir (7/24).
YouTube Data API v3 ile kanallarin o anki CANLI yayin video ID'sini bulur,
Supabase kanal_canli tablosunu gunceller. Yayin yoksa null yazar.

Neden API? YouTube, datacenter IP'lerine (GitHub Actions) bot/consent duvari
gosterip HTML kazimayi engelliyor. Resmi API bu engele takilmaz.

Akilli/ucuz kota kullanimi:
  - Her kosuda TEK videos.list cagrisi (1 kota) ile mevcut ID'lerin hala canli
    olup olmadigina bakilir.
  - Sadece olmus/bos olan kanal icin search.list (100 kota) yapilir.
  - Yayinlar sabitken gunluk ~150 kota (gunluk ucretsiz limit 10.000).

Sadece Python stdlib kullanir. Ortam degiskenleri:
  SUPABASE_URL, SUPABASE_SECRET, YT_API_KEY  (GitHub repo secrets).
"""
import os, json, urllib.request
from datetime import datetime, timezone

SUPABASE_URL    = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_SECRET = os.environ["SUPABASE_SECRET"]
YT_KEY          = os.environ["YT_API_KEY"]

API = "https://www.googleapis.com/youtube/v3"

# Kalici kanal ID'leri
KANAL_ID = {
    "Bloomberg": "UCApLxl6oYQafxvykuoC2uxQ",
    "Apara":     "UCzrGg6iyRDuUSnO0cQ5oLcA",
    "Cnbce":     "UCaO-M1dXacMwtyg0Pvovk4w",
    "EkoTurk":   "UCAGVKxpAKwXMWdmcHbrvcwQ",
}

def _get_json(url, timeout=20):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())

def hala_canli(video_ids):
    """videos.list (1 kota) — verilen ID'lerden HALA canli olanlarin kumesi."""
    ids = [v for v in video_ids if v]
    if not ids:
        return set()
    url = f"{API}/videos?part=snippet&id={','.join(ids)}&key={YT_KEY}"
    try:
        data = _get_json(url)
    except Exception as e:
        print("videos.list hata:", e)
        return set(ids)   # emin degiliz -> mevcutu koru, null'a dusurme
    canli = set()
    for it in data.get("items", []):
        if it.get("snippet", {}).get("liveBroadcastContent") == "live":
            canli.add(it["id"])
    return canli

def kanal_canli_ara(cid):
    """search.list (100 kota). Doner: (durum, vid).
    durum='ok'  -> arama basarili; vid= canli video ID ya da None (gercekten yok)
    durum='hata'-> arama basarisiz (kota/ag); cagiran mevcut degeri KORUMALI."""
    url = (f"{API}/search?part=id&channelId={cid}"
           f"&eventType=live&type=video&maxResults=1&key={YT_KEY}")
    try:
        data = _get_json(url)
    except Exception as e:
        print("search.list hata:", e)
        return ("hata", None)
    items = data.get("items", [])
    return ("ok", items[0]["id"]["videoId"] if items else None)

def sb_oku():
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/kanal_canli?select=kanal,video_id",
        headers={"apikey": SUPABASE_SECRET, "Authorization": f"Bearer {SUPABASE_SECRET}"})
    try:
        data = json.loads(urllib.request.urlopen(req, timeout=20).read())
        return {r["kanal"]: r.get("video_id") for r in data}
    except Exception as e:
        print("sb_oku hata:", e)
        return None   # okunamadi -> cagiran kosuyu atlamali (mevcut tabloyu bozma)

def sb_upsert(rows):
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/kanal_canli?on_conflict=kanal",
        data=json.dumps(rows).encode("utf-8"), method="POST",
        headers={"apikey": SUPABASE_SECRET, "Authorization": f"Bearer {SUPABASE_SECRET}",
                 "Content-Type": "application/json", "Prefer": "resolution=merge-duplicates"})
    urllib.request.urlopen(req, timeout=30).read()

def main():
    mevcut = sb_oku()
    if mevcut is None:
        print("Supabase okunamadi -> kosu atlaniyor (tablo korundu).")
        return
    canli_set = hala_canli([mevcut.get(ch) for ch in KANAL_ID])
    # KOTA KORUMASI: iki tavan var -> "Queries per day"=10.000 birim VE
    # "Search Queries per day"=100 (search.list cagri sayisi). search.list pahali
    # (100 birim + 1 arama-hakki). Bu yuzden aramayi sadece SAATTE BIR yapariz
    # (cron :00'da; minute<10 sadece :00 kosusunda true). 4 kanal da gun boyu
    # kapali olsa bile en fazla 24x4=96 arama/gun -> her iki tavanin da altinda.
    # Canli kanallar yine her 10 dk'da ucuz videos.list ile dogrulanir (1 birim).
    # Kapali kanalin canliya donmesi en fazla ~1 saat gecikmeyle yakalanir.
    arama_zamani = datetime.now(timezone.utc).minute < 10
    rows = []
    for ch, cid in KANAL_ID.items():
        cur = mevcut.get(ch)
        if cur and cur in canli_set:
            vid = cur                        # hala canli -> koru (ucuz)
        elif arama_zamani:
            durum, yeni = kanal_canli_ara(cid)   # olmus/bos + arama zamani -> coz
            vid = cur if durum == "hata" else yeni  # arama hatasi -> mevcudu KORU
        else:
            vid = None                       # videos.list ONU olu dogruladi -> yayin yok
        rows.append({"kanal": ch, "video_id": vid,
                     "guncelleme": datetime.now(timezone.utc).isoformat()})
        print(f"{ch:10} -> {vid if vid else 'YAYIN YOK (null)'}")
    sb_upsert(rows)
    print("kanal_canli guncellendi.")

if __name__ == "__main__":
    main()
