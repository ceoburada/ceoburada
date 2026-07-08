"""
kanal_canli_guncelle.py — GitHub Actions'ta zamanlanmis calisir (7/24).
YouTube Data API v3 + kanal RSS beslemesi ile kanallarin o anki CANLI yayin
video ID'sini bulur, Supabase kanal_canli tablosunu gunceller.

Neden API? YouTube, datacenter IP'lerine (GitHub Actions) bot/consent duvari
gosterip HTML kazimayi engelliyor. Resmi API + RSS bu engele takilmaz.

Strateji (GitHub cron DUZENSIZ calisabilir — hepsi buna dayanikli):
  1. RSS beslemesi (KOTA YOK): kanalin son videolari -> canli adaylari.
  2. TEK videos.list (1 kota): mevcut ID'ler + RSS adaylari hala/yeni canli mi.
     -> yeni baslayan yayin, pahali arama olmadan ilk kosuda yakalanir.
  3. search.list (100 kota + gunluk 100 arama tavani) SADECE yedek:
     canli aday yoksa ve son karardan >= ARAMA_ARALIK_DK gectiyse.
     Zaman esigi tabloda kayitli 'guncelleme' alanina gore (duvar saati degil).

Defansif: hicbir gecici hata (Supabase okuma / videos.list / search.list)
mevcut sagliki linki null'a dusuremez. null SADECE "gercekten yayin yok"
kesinlesince yazilir.

Sadece Python stdlib. Ortam: SUPABASE_URL, SUPABASE_SECRET, YT_API_KEY.
"""
import os, re, json, urllib.request
from datetime import datetime, timezone

SUPABASE_URL    = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_SECRET = os.environ["SUPABASE_SECRET"]
YT_KEY          = os.environ["YT_API_KEY"]

API = "https://www.googleapis.com/youtube/v3"
ARAMA_ARALIK_DK = 65   # olu kanal icin yedek search.list en erken bu arayla
                       # (gunluk "Search Queries per day"=100 tavanina uyum)

# Kalici kanal ID'leri
KANAL_ID = {
    "Bloomberg": "UCApLxl6oYQafxvykuoC2uxQ",
    "Apara":     "UCzrGg6iyRDuUSnO0cQ5oLcA",
    "Cnbce":     "UCaO-M1dXacMwtyg0Pvovk4w",
    "EkoTurk":   "UCAGVKxpAKwXMWdmcHbrvcwQ",
}

def _get(url, timeout=20):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()

def rss_video_ids(cid):
    """Kanal RSS beslemesi (kota YOK, datacenter'da da erisilir) -> son video ID'leri."""
    try:
        xml = _get(f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}").decode("utf-8", "ignore")
        return re.findall(r"<yt:videoId>([A-Za-z0-9_-]{11})</yt:videoId>", xml)[:10]
    except Exception as e:
        print(f"rss hata ({cid}):", e)
        return []

def canli_kumesi(video_ids):
    """TEK videos.list (1 kota, <=50 id) -> {channelId: {canli vid,...}}.
    None donerse cagri BASARISIZ (kota/ag) -> kosu atlanmali, tablo korunmali."""
    ids = [v for v in dict.fromkeys(video_ids) if v][:50]
    if not ids:
        return {}
    url = f"{API}/videos?part=snippet&id={','.join(ids)}&key={YT_KEY}"
    try:
        data = json.loads(_get(url))
    except Exception as e:
        print("videos.list hata:", e)
        return None
    canli = {}
    for it in data.get("items", []):
        sn = it.get("snippet", {})
        if sn.get("liveBroadcastContent") == "live":
            canli.setdefault(sn.get("channelId"), set()).add(it["id"])
    return canli

def kanal_canli_ara(cid):
    """YEDEK search.list (100 kota). Doner: (durum, vid).
    durum='ok'  -> arama basarili; vid= canli video ID ya da None (gercekten yok)
    durum='hata'-> arama basarisiz (kota/ag); cagiran mevcut degeri KORUMALI."""
    url = (f"{API}/search?part=id&channelId={cid}"
           f"&eventType=live&type=video&maxResults=1&key={YT_KEY}")
    try:
        data = json.loads(_get(url))
    except Exception as e:
        print("search.list hata:", e)
        return ("hata", None)
    items = data.get("items", [])
    return ("ok", items[0]["id"]["videoId"] if items else None)

def sb_oku():
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/kanal_canli?select=kanal,video_id,guncelleme",
        headers={"apikey": SUPABASE_SECRET, "Authorization": f"Bearer {SUPABASE_SECRET}"})
    try:
        data = json.loads(urllib.request.urlopen(req, timeout=20).read())
        return {r["kanal"]: r for r in data}
    except Exception as e:
        print("sb_oku hata:", e)
        return None   # okunamadi -> kosu atlanmali (mevcut tabloyu bozma)

def sb_upsert(rows):
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/kanal_canli?on_conflict=kanal",
        data=json.dumps(rows).encode("utf-8"), method="POST",
        headers={"apikey": SUPABASE_SECRET, "Authorization": f"Bearer {SUPABASE_SECRET}",
                 "Content-Type": "application/json", "Prefer": "resolution=merge-duplicates"})
    urllib.request.urlopen(req, timeout=30).read()

def arama_gerek(gunc_str, now):
    """Yedek aramaya izin var mi? Tabloda kayitli son karar zamanina bakar
    (duvar saati DEGIL -> GitHub cron'u duzensiz calissa da dogru davranir)."""
    if not gunc_str:
        return True
    try:
        t = datetime.fromisoformat(gunc_str)
    except Exception:
        return True
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    fark = (now - t).total_seconds()
    if fark < 0:
        # gelecekte gorunen damga: watcher'in eski surumu yerel saati UTC diye
        # yazmis olabilir -> taze kabul et, arama hakki harcama
        return False
    return fark >= ARAMA_ARALIK_DK * 60

def main():
    mevcut = sb_oku()
    if mevcut is None:
        print("Supabase okunamadi -> kosu atlaniyor (tablo korundu).")
        return
    now = datetime.now(timezone.utc)

    # Adaylar: mevcut ID + RSS'ten son videolar (kanal sirasi korunur:
    # mevcut one yazilir ki hala canliysa ozel-yayina kaymadan korunsun)
    aday = {}
    for ch, cid in KANAL_ID.items():
        cur = (mevcut.get(ch) or {}).get("video_id")
        aday[ch] = ([cur] if cur else []) + rss_video_ids(cid)

    canli = canli_kumesi([v for lst in aday.values() for v in lst])
    if canli is None:
        print("videos.list basarisiz -> kosu atlaniyor (tablo korundu).")
        return

    rows = []
    for ch, cid in KANAL_ID.items():
        cur   = (mevcut.get(ch) or {}).get("video_id")
        gunc  = (mevcut.get(ch) or {}).get("guncelleme")
        c_set = canli.get(cid, set())
        secim = next((v for v in aday[ch] if v in c_set), None)

        if secim:
            vid = secim                       # canli (mevcut oncelikli, yoksa RSS)
            if secim != cur:
                print(f"{ch}: yeni canli yayin (RSS) -> {secim}")
        elif cur:
            # az once oldu (videos.list dogruladi) -> hemen yedek arama dene
            durum, yeni = kanal_canli_ara(cid)
            vid = yeni if durum == "ok" else None   # cur'un olu oldugu KESIN
        elif arama_gerek(gunc, now):
            durum, yeni = kanal_canli_ara(cid)
            if durum == "hata":
                print(f"{ch:10} -> arama hatasi, satir atlandi (throttle korundu)")
                continue                       # guncelleme yazma -> sonra tekrar dener
            vid = yeni
        else:
            continue                           # olu + arama zamani degil -> dokunma

        rows.append({"kanal": ch, "video_id": vid,
                     "guncelleme": now.isoformat()})
        print(f"{ch:10} -> {vid if vid else 'YAYIN YOK (null)'}")

    if rows:
        sb_upsert(rows)
    print(f"kanal_canli guncellendi ({len(rows)} satir).")

if __name__ == "__main__":
    main()
