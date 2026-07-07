"""
kanal_canli_guncelle.py — GitHub Actions'ta zamanlanmış çalışır (7/24).
Kanal ID'lerinden o anki CANLI yayın video ID'sini çözer, Supabase kanal_canli
tablosunu günceller. Yayın yoksa null yazar (site "yayın yok" gösterir).
Akıllı: mevcut yayın hâlâ canlıysa korur (kanalın açtığı özel yayına kaymaz).

Sadece Python stdlib kullanır (pip install gerekmez).
Ortam değişkenleri: SUPABASE_URL, SUPABASE_SECRET (GitHub repo secrets).
"""
import os, re, json, urllib.request
from datetime import datetime, timezone

SUPABASE_URL    = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_SECRET = os.environ["SUPABASE_SECRET"]

# Kalıcı kanal ID'leri
KANAL_ID = {
    "Bloomberg": "UCApLxl6oYQafxvykuoC2uxQ",
    "Apara":     "UCzrGg6iyRDuUSnO0cQ5oLcA",
    "Cnbce":     "UCaO-M1dXacMwtyg0Pvovk4w",
    "EkoTurk":   "UCAGVKxpAKwXMWdmcHbrvcwQ",
}

def _get(url, timeout=20):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0", "Accept-Language": "tr,en;q=0.8",
        "Cookie": "CONSENT=YES+1"})
    return urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "ignore")

def canli_video_id(channel):
    cid = KANAL_ID.get(channel)
    if not cid:
        return None
    try:
        html = _get(f"https://www.youtube.com/channel/{cid}/live")
    except Exception:
        return None
    m = re.search(r'<link rel="canonical" href="https://www\.youtube\.com/watch\?v=([A-Za-z0-9_-]{11})"', html)
    if not m:
        m = re.search(r'"videoId":"([A-Za-z0-9_-]{11})"', html)
    return m.group(1) if m else None

def canli_mi(vid):
    if not vid:
        return False
    try:
        html = _get(f"https://www.youtube.com/watch?v={vid}", 15)
    except Exception:
        return False
    return '"isLiveNow":true' in html

def guncel(channel, mevcut_vid):
    # Mevcut/tablodaki yayın hâlâ canlıysa koru (özel-yayın tuzağına düşme)
    if mevcut_vid and canli_mi(mevcut_vid):
        return mevcut_vid
    yeni = canli_video_id(channel)      # eski öldü → yeniden çöz
    if yeni and canli_mi(yeni):
        return yeni                     # yeni gerçekten canlı
    return None                         # şu an canlı yayın yok

def sb_oku():
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/kanal_canli?select=kanal,video_id",
        headers={"apikey": SUPABASE_SECRET, "Authorization": f"Bearer {SUPABASE_SECRET}"})
    try:
        data = json.loads(urllib.request.urlopen(req, timeout=20).read())
        return {r["kanal"]: r.get("video_id") for r in data}
    except Exception:
        return {}

def sb_upsert(rows):
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/kanal_canli?on_conflict=kanal",
        data=json.dumps(rows).encode("utf-8"), method="POST",
        headers={"apikey": SUPABASE_SECRET, "Authorization": f"Bearer {SUPABASE_SECRET}",
                 "Content-Type": "application/json", "Prefer": "resolution=merge-duplicates"})
    urllib.request.urlopen(req, timeout=30).read()

def main():
    mevcut = sb_oku()
    rows = []
    for ch in KANAL_ID:
        vid = guncel(ch, mevcut.get(ch))
        rows.append({"kanal": ch, "video_id": vid,
                     "guncelleme": datetime.now(timezone.utc).isoformat()})
        print(f"{ch:10} -> {vid if vid else 'YAYIN YOK (null)'}")
    sb_upsert(rows)
    print("kanal_canli guncellendi.")

if __name__ == "__main__":
    main()
