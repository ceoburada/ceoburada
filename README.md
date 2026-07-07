# CEO Burada

Borsaya kote şirket yöneticilerinin canlı TV yayınlarındaki demeçlerini yapay zekâ
ile derleyip zaman damgalı olarak yayımlayan site. Canlı yayın: **ceoburada.com**

- `index.html` — statik site (Supabase'den okur; Netlify'da yayında)
- `scripts/kanal_canli_guncelle.py` — kanalların o anki canlı yayın ID'sini çözer
- `.github/workflows/kanal-canli.yml` — yukarıdaki script'i 10 dk'da bir çalıştırır (GitHub Actions)
